"""Transparent seasonal baseline. No weather/news inputs or customer quality claims."""

from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import ROUND_CEILING, Decimal
from statistics import mean
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .domain import select_recipe
from .models import Ingredient, Location, MenuItem, Replenishment, RequestLine, Sale, Stock, now


def local_today(db, point):
    return now().astimezone(ZoneInfo(db.get(Location, point).timezone)).date()


def series(db, point, before, as_of=True):
    cutoff = datetime.combine(before, time.min, ZoneInfo(db.get(Location, point).timezone)).astimezone(
        timezone.utc
    )
    query = select(Sale).where(Sale.point_id == point, Sale.day < before, Sale.kind == "sale")
    if as_of:
        query = query.where(Sale.recorded_at <= cutoff)
    rows = db.scalars(query)
    data = defaultdict(dict)
    for row in rows:
        data[row.item_id][row.day] = data[row.item_id].get(row.day, 0) + row.quantity
    return data


def predict(history, target, origin):
    # A2: only known same-weekday values strictly before the origin.
    known = sorted(
        (day, value) for day, value in history.items() if day < origin and day.weekday() == target.weekday()
    )
    if not known:
        return None
    return round(mean(value for _, value in known[-4:]), 2)


def interval(history, origin, estimate, calibration=None):
    errors = []
    for day in sorted(history):
        if origin - timedelta(days=28) <= day < origin:
            prior = predict(calibration.get(day, {}) if calibration is not None else history, day, day)
            if prior is not None:
                errors.append(history[day] - prior)
    if len(errors) < 8 or estimate is None:
        return None
    errors.sort()
    low = max(0, round(estimate + errors[int((len(errors) - 1) * 0.1)], 2))
    high = max(low, round(estimate + errors[int((len(errors) - 1) * 0.9)], 2))
    return {
        "lower": low,
        "upper": high,
        "calibration_n": len(errors),
        "nominal": 0.8,
        "method": "Эмпирические ошибки последовательных однодневных прогнозов; не гарантия покрытия.",
    }


def forecast(db, point, horizon=7):
    today = local_today(db, point)
    histories = series(db, point, today)
    # Reconstruct information availability at every calibration origin, too.
    calibration = {
        today - timedelta(days=i): series(db, point, today - timedelta(days=i)) for i in range(1, 29)
    }
    values = []
    for item in db.scalars(select(MenuItem).order_by(MenuItem.name)):
        daily = []
        for offset in range(horizon):
            day = today + timedelta(days=offset)
            value = predict(histories[item.id], day, today)
            daily.append(
                {
                    "day": day.isoformat(),
                    "quantity": value,
                    "interval": interval(
                        histories[item.id],
                        today,
                        value,
                        {d: series_by_item.get(item.id, {}) for d, series_by_item in calibration.items()},
                    )
                    if offset == 0
                    else None,
                }
            )
        values.append(
            {
                "item_id": item.id,
                "name": item.name,
                "daily": daily,
                "total": round(sum(d["quantity"] for d in daily), 2)
                if all(d["quantity"] is not None for d in daily)
                else None,
            }
        )
    return {
        "data_mode": "demo",
        "origin": today.isoformat(),
        "horizon": horizon,
        "items": values,
        "model": "Среднее четырёх аналогичных дней недели",
        "weather": "Не подключена",
        "news": "Не используются",
        "interval_note": "Диапазон оценён только для 1 дня. Для 7/14 дней ещё не калиброван.",
        "limitations": "Синтетические продажи. Наблюдаемые продажи не равны спросу при отсутствии товара.",
    }


def overview(db, point):
    today = local_today(db, point)
    history = series(db, point, today, as_of=False)
    recent = today - timedelta(days=28)
    rows = []
    revenue_by_item = defaultdict(Decimal)
    for sale in db.scalars(select(Sale).where(Sale.point_id == point, Sale.day >= recent, Sale.day < today)):
        revenue_by_item[sale.item_id] += sale.revenue
    for item in db.scalars(select(MenuItem).order_by(MenuItem.name)):
        values = history[item.id]
        current = sum(q for d, q in values.items() if recent <= d < today)
        prev = sum(q for d, q in values.items() if recent - timedelta(days=28) <= d < recent)
        known = [q for d, q in values.items() if recent <= d < today]
        change = round((current - prev) / prev * 100, 1) if prev else None
        low = len(known) >= 14 and current / len(known) < 3
        reason = (
            "Низкие продажи"
            if low
            else "Снижение продаж"
            if change is not None and change < -15
            else "Стабильно"
        )
        rows.append(
            {
                "id": item.id,
                "name": item.name,
                "quantity": current,
                "revenue": str(revenue_by_item[item.id]),
                "change": change,
                "zero_days": sum(x == 0 for x in known),
                "known_days": len(known),
                "attention": reason != "Стабильно",
                "reason": reason,
                "explanation": "Демо-правило: менее 3 порций/день при ≥14 наблюдениях либо снижение >15%. Доступность задана генератором.",
            }
        )
    total = sum(x["quantity"] for x in rows)
    for row in rows:
        row["share"] = round(row["quantity"] / total * 100, 1) if total else 0
    daily = [
        {
            "day": (today - timedelta(days=i)).isoformat(),
            "quantity": sum(s[today - timedelta(days=i)] for s in history.values())
            if history and all(today - timedelta(days=i) in s for s in history.values())
            else None,
        }
        for i in range(14, 0, -1)
    ]
    return {
        "items": rows,
        "daily": daily,
        "quantity": total,
        "revenue": str(sum(revenue_by_item.values(), Decimal(0))),
        "period": "Последние 28 полных дней",
        "data_mode": "demo",
        "availability": "В синтетической истории точки открыты. Пропуски отмечены «нет данных», а не нулём; фактических данных заказчика нет.",
    }


def recommendations(db, point):
    # Explicit demo policy: next delivery in 1 day, next order after 2 days.
    prediction = forecast(db, point, 3)
    demand = defaultdict(Decimal)
    incomplete = False
    for item in prediction["items"]:
        recipe = select_recipe(db, item["item_id"], local_today(db, point))
        if item["total"] is None:
            incomplete = True
            continue
        for ingredient, qty in recipe.components.items():
            demand[ingredient] += Decimal(qty) * Decimal(str(item["total"]))
    incoming = defaultdict(Decimal)
    for line in db.scalars(
        select(RequestLine)
        .join(Replenishment)
        .where(Replenishment.point_id == point, Replenishment.status.in_(["accepted", "packing", "sent"]))
    ):
        incoming[line.ingredient_id] += line.quantity - line.received
    result = []
    for ingredient in db.scalars(select(Ingredient).order_by(Ingredient.name)):
        stock = db.get(Stock, (point, ingredient.id))
        usable = max(Decimal(0), stock.quantity)
        expected = demand[ingredient.id].quantize(Decimal(".001"))
        raw = max(Decimal(0), expected + ingredient.safety - usable - incoming[ingredient.id])
        packed = (raw / ingredient.pack).to_integral_value(rounding=ROUND_CEILING) * ingredient.pack
        result.append(
            {
                "ingredient_id": ingredient.id,
                "name": ingredient.name,
                "unit": ingredient.unit,
                "stock": str(stock.quantity),
                "expected": str(expected),
                "safety": str(ingredient.safety),
                "incoming": str(incoming[ingredient.id]),
                "raw": str(raw),
                "quantity": str(packed) if not incomplete else None,
                "risk": raw > 0,
                "review_required": True,
                "explanation": f"{expected} + {ingredient.safety} − {usable} − {incoming[ingredient.id]} = {raw}; упаковка {ingredient.pack} {ingredient.unit}.",
            }
        )
    return {
        "lines": result,
        "window_days": 3,
        "incomplete": incomplete,
        "notice": "Черновой расчёт на условные 3 дня. Сроки поставок, годность партий и вместимость не подтверждены; количество требует проверки кладовщиком. Это не безопасный автоматический заказ.",
    }


def backtest(db, point):
    today = local_today(db, point)
    histories = series(db, point, today)
    result = []
    for fold in range(3):
        origin = today - timedelta(days=21 - fold * 7)
        known_histories = series(db, point, origin)
        for group in ("Редкие", "Остальные"):
            errors, actuals = [], []
            for item_id, history in histories.items():
                known = known_histories.get(item_id, {})
                train = list(known.values())
                if not train:
                    continue
                rare = sum(v > 0 for v in train) / len(train) < 0.25
                if (group == "Редкие") != rare:
                    continue
                for offset in range(7):
                    target = origin + timedelta(days=offset)
                    value = predict(known, target, origin)
                    if value is not None and target in history:
                        errors.append(value - history[target])
                        actuals.append(history[target])
            result.append(
                {
                    "fold": fold + 1,
                    "origin": origin.isoformat(),
                    "group": group,
                    "n": len(errors),
                    "mae": round(mean(abs(x) for x in errors), 3) if errors else None,
                    "wape": round(sum(abs(x) for x in errors) / sum(actuals), 4) if sum(actuals) else None,
                    "bias": round(mean(errors), 3) if errors else None,
                }
            )
    return {
        "data_mode": "demo",
        "model": "Среднее четырёх аналогичных дней недели",
        "folds": result,
        "note": "Три последовательных блока по 7 дней; признаки строго до origin. CatBoost/GRU ещё не реализованы. Полезность для заказчика не оценивалась.",
    }
