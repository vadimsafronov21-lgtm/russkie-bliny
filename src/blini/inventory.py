"""Потребность, FEFO и объяснимые закупки. Чистые функции, без SQLite/Qt.

Снимок stock относится к концу as_of. Срок годности включительно. Неудовлетворённый
спрос фиксируется как потерянный расход, не как отрицательный склад или долг.
"""
import math
import pandas as pd
from .config import Config


def ingredient_demand(forecast: pd.DataFrame, recipes: pd.DataFrame) -> pd.DataFrame:
    """Порции × расход на порцию; выход: date, store_id, ingredient_id, quantity.

    Единицы recipes уже приведены validate_data к базовым. Если хотя бы одно
    слагаемое неизвестно, суммарная потребность данного ингредиента тоже NaN.
    """
    joined = forecast.merge(recipes[["dish_id", "ingredient_id", "quantity"]], on="dish_id", suffixes=("_portions", "_recipe"))
    joined["quantity"] = joined.quantity_portions * joined.quantity_recipe
    return joined.groupby(["date", "store_id", "ingredient_id"], as_index=False).quantity.agg(lambda x: x.sum() if x.notna().all() else float("nan"))


def round_order(required: float, pack_size: float, min_order: float) -> float:
    """Неотрицательный заказ кратно упаковке; минимум применяется только при нужде."""
    if pack_size <= 0 or min_order < 0 or not all(math.isfinite(x) for x in (required, pack_size, min_order)):
        raise ValueError("Некорректные параметры округления заказа")
    if required <= 1e-9:
        return 0.0
    return round(math.ceil(max(required, min_order) / pack_size - 1e-10) * pack_size, 9)


def safety_stock(total_demand: float, config: Config) -> float:
    """Упрощённое правило: фиксированная доля потребности за период L+R.

    Здесь аналитики могут заменить правило на функцию неопределённости спроса.
    """
    return total_demand * config.safety_pct


def simulate(demand: pd.Series, stock: pd.DataFrame, deliveries: pd.DataFrame,
             order: dict | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """Пошаговый FEFO; вход demand — полная дневная Series без NaN, в базовой единице.

    stock: lot_id, quantity, expires_on. deliveries: delivery_id, quantity,
    arrival_date, expires_on. order: quantity, arrival_date, expires_on.
    Выход: дневной журнал и оставшиеся партии; входные таблицы не меняются.
    """
    if demand.isna().any() or demand.lt(0).any():
        raise ValueError("Для моделирования нужна известная неотрицательная потребность на каждый день")
    lots = [{"id": str(r.lot_id), "quantity": float(r.quantity), "expires_on": r.expires_on, "source": "stock"} for r in stock.itertuples()]
    shipments = [{"id": str(r.delivery_id), "quantity": float(r.quantity), "expires_on": r.expires_on, "arrival_date": r.arrival_date, "source": "delivery"} for r in deliveries.itertuples()]
    if order and order["quantity"] > 0:
        shipments.append({"id": "recommended_order", "source": "order", **order})
    rows = []
    for date, needed in demand.sort_index().items():
        expired, expired_order = 0.0, 0.0
        for lot in lots:
            if lot["expires_on"] < date:
                expired += lot["quantity"]
                if lot["source"] == "order":
                    expired_order += lot["quantity"]
                lot["quantity"] = 0.0
        arrivals = [s.copy() for s in shipments if s["arrival_date"] == date]
        lots.extend(arrivals)
        available = sum(lot["quantity"] for lot in lots if lot["expires_on"] >= date)
        remainder, consumed_order = float(needed), 0.0
        for lot in sorted(lots, key=lambda x: (x["expires_on"], x["id"])):
            if lot["expires_on"] < date:
                continue
            take = min(remainder, lot["quantity"])
            lot["quantity"] -= take
            remainder -= take
            if lot["source"] == "order":
                consumed_order += take
        rows.append({"date": date, "demand": float(needed), "arrivals": sum(s["quantity"] for s in arrivals),
                     "expired": expired, "expired_order": expired_order, "available_before": available,
                     "consumed": float(needed)-remainder, "shortage": max(0.0, remainder),
                     "remaining": sum(l["quantity"] for l in lots if l["expires_on"] >= date),
                     "order_consumed": consumed_order})
    return pd.DataFrame(rows), lots


def recommend_orders(demand: pd.DataFrame, tables: dict[str, pd.DataFrame],
                     as_of: str | pd.Timestamp, config: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Возвращает рекомендации и дневной журнал baseline/with_order.

    Заказ размещается утром as_of+1, приходит через lead_days. Защищаем L+R дней
    с этого утра. Дефицит до прихода не переносится на позднюю закупку.
    Невозможность покрытия и запас с неизвестной потребностью явно маркируются.
    """
    cutoff = pd.Timestamp(as_of).normalize()
    start = cutoff + pd.Timedelta(days=1)
    rows, logs = [], []
    names = tables["ingredients"].set_index("ingredient_id")
    for param in tables["purchase_params"].itertuples(index=False):
        lead, review = int(param.lead_days), int(param.review_days)
        arrival = start + pd.Timedelta(days=lead)
        end = start + pd.Timedelta(days=lead + review - 1)
        expiry = arrival + pd.Timedelta(days=int(param.shelf_life_days)-1)
        dates = pd.date_range(start, end)
        selected = demand[(demand.store_id == param.store_id) & (demand.ingredient_id == param.ingredient_id)]
        # Ингредиент без рецептуры имеет нулевую потребность, а не неизвестную.
        series = selected.set_index("date").quantity.reindex(dates) if len(selected) else pd.Series(0.0, index=dates)
        stock = tables["stock"][(tables["stock"].store_id == param.store_id) & (tables["stock"].ingredient_id == param.ingredient_id)]
        incoming = tables["deliveries"][(tables["deliveries"].store_id == param.store_id) & (tables["deliveries"].ingredient_id == param.ingredient_id)]
        common = {"store_id": param.store_id, "ingredient_id": param.ingredient_id,
                  "ingredient": names.loc[param.ingredient_id, "name"], "unit": param.unit,
                  "order_date": start, "arrival_date": arrival, "protection_end": end,
                  "lead_days": lead, "review_days": review, "pack_size": float(param.pack_size), "min_order": float(param.min_order)}
        if series.isna().any():
            rows.append({**common, "order_quantity": float("nan"), "status": "needs_data",
                         "warning": "Неизвестен спрос связанного блюда: автоматический заказ недоступен.",
                         "explanation": "Добавьте историю или согласованный экспертный прогноз; неизвестная потребность не считается нулевой."})
            continue
        baseline, remaining = simulate(series, stock, incoming)
        total = float(series.sum())
        buffer = safety_stock(total, config)
        ending = sum(l["quantity"] for l in remaining if l["expires_on"] > end)
        early = float(baseline.loc[baseline.date < arrival, "shortage"].sum())
        late = float(baseline.loc[baseline.date >= arrival, "shortage"].sum())
        # Все поздние дефициты видны пользователю, даже если срок годности заказа
        # слишком короткий, чтобы их закрыть одной партией.
        required = late + max(0.0, buffer - ending)
        quantity = round_order(required, float(param.pack_size), float(param.min_order))
        with_order, final_lots = simulate(series, stock, incoming,
            {"quantity": quantity, "arrival_date": arrival, "expires_on": expiry})
        after_order_shortage = float(with_order.loc[with_order.date >= arrival, "shortage"].sum())
        actual_buffer = sum(l["quantity"] for l in final_lots if l["expires_on"] > end)
        waste_order = float(with_order.expired_order.sum()) + sum(l["quantity"] for l in final_lots if l["source"] == "order" and l["expires_on"] <= end)
        order_left = sum(l["quantity"] for l in final_lots if l["source"] == "order")
        valid_stock = float(stock.loc[stock.expires_on >= start, "quantity"].sum())
        scheduled = float(incoming.loc[incoming.arrival_date.between(start, end), "quantity"].sum())
        shortages = baseline[baseline.shortage > 1e-9]
        first = shortages.date.min() if not shortages.empty else pd.NaT
        order_by = first - pd.Timedelta(days=lead) if pd.notna(first) else start
        warnings = []
        if early > 1e-9:
            warnings.append(f"До прихода нового заказа дефицит {early:.3f} {param.unit}; нужна ускоренная поставка/изменение меню. Заказать следовало к {order_by.date()}.")
        if after_order_shortage > 1e-9 or actual_buffer + 1e-9 < buffer:
            warnings.append("Одна партия не покрывает период или страховой запас: требуется пересмотр дат/частоты поставок (проверьте срок годности).")
        if waste_order > 1e-9:
            warnings.append(f"Риск списания из нового заказа: {waste_order:.3f} {param.unit} до конца периода.")
        elif quantity > 0 and order_left > buffer + 1e-9:
            warnings.append(f"Упаковка/минимум создаёт излишек: в конце периода останется {order_left:.3f} {param.unit} новой партии, годна до {expiry.date()}; дальнейший спрос не проверен, возможны списания.")
        if float(baseline.expired.sum()) > 1e-9:
            warnings.append(f"Из текущего запаса/поставок истечёт без расхода {baseline.expired.sum():.3f} {param.unit}.")
        explanation = (
            f"Период {start.date()}–{end.date()} (L={lead}, R={review}). Потребность {total:.3f} {param.unit}; "
            f"пригодный на первый день остаток {valid_stock:.3f}, поставки в периоде {scheduled:.3f}. "
            f"FEFO по дням: дефицит до поступления {early:.3f}, после {late:.3f}, "
            f"пригодный на следующий день остаток без заказа {ending:.3f}. "
            f"Упрощённый страховой запас {config.safety_pct:.0%} × {total:.3f} = {buffer:.3f}. "
            f"Нужно {late:.3f} + max(0, {buffer:.3f} − {ending:.3f}) = {required:.3f}. "
            f"С минимумом {param.min_order:g} и упаковкой {param.pack_size:g}: заказать {quantity:.3f} {param.unit}. "
            "Ранний дефицит считается потерянным спросом; поздний заказ его не компенсирует."
        )
        rows.append({**common, "forecast_demand": total, "usable_stock": valid_stock, "scheduled_deliveries": scheduled,
                     "safety_stock": buffer, "baseline_end_stock": ending, "early_shortage": early,
                     "late_shortage": late, "raw_order": required, "order_quantity": quantity,
                     "order_by_date": order_by, "order_expires_on": expiry, "remaining_after_order": actual_buffer,
                     "uncovered_after_arrival": after_order_shortage, "order_waste_risk": waste_order,
                     "status": "attention" if warnings else "ok", "warning": " ".join(warnings), "explanation": explanation})
        for label, log in (("baseline", baseline), ("with_order", with_order)):
            log["scenario"], log["store_id"], log["ingredient_id"] = label, param.store_id, param.ingredient_id
            logs.append(log)
    return pd.DataFrame(rows), pd.concat(logs, ignore_index=True) if logs else pd.DataFrame()
