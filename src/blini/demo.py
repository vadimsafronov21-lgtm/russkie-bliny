"""Воспроизводимые синтетические данные, не данные ООО «Русские блины»."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .data import SCHEMAS

AS_OF = "2026-09-30"
SCENARIOS = ("normal", "weekend_growth", "shortage", "expiry", "delayed_delivery", "short_history")


def generate_demo(root: str | Path, seed: int = 42):
    """Создаёт шесть наборов CSV и шаблоны. История: 2026-04-01…2026-09-30.

    seed фиксирует генератор. as_of совпадает с датой снимка stock. Сценарии
    различаются ровно описанными факторами и пригодны для повторного запуска.
    """
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    dish_names = ["Блин с маслом", "Блин с творогом", "Блин с мясом", "Блин с сыром", "Блин с грибами",
                  "Блин с курицей", "Блин с ветчиной", "Блин со сгущёнкой", "Блин с вареньем", "Блин с яблоком"]
    ingredient_names = [("Мука", "kg"), ("Молоко", "l"), ("Яйцо", "pcs"), ("Масло", "kg"), ("Творог", "kg"),
                        ("Мясо", "kg"), ("Сыр", "kg"), ("Грибы", "kg"), ("Курица", "kg"), ("Ветчина", "kg"),
                        ("Сгущёнка", "kg"), ("Варенье", "kg"), ("Яблоки", "kg")]
    dishes = pd.DataFrame([{"dish_id": f"D{i+1:02}", "name": n, "introduced_on": "2026-04-01"} for i, n in enumerate(dish_names)])
    ingredients = pd.DataFrame([{"ingredient_id": f"I{i+1:02}", "name": n, "base_unit": u} for i, (n, u) in enumerate(ingredient_names)])
    recipes = []
    for i in range(10):
        dish_id = f"D{i+1:02}"
        for ingredient_id, quantity, unit in (("I01", .045, "kg"), ("I02", .08, "l"), ("I03", .2, "pcs"), ("I04", .008, "kg")):
            recipes.append({"dish_id": dish_id, "ingredient_id": ingredient_id, "quantity": quantity, "unit": unit})
        if i:
            recipes.append({"dish_id": dish_id, "ingredient_id": f"I{i+4:02}", "quantity": .06, "unit": "kg"})
    recipes = pd.DataFrame(recipes)
    history_dates = pd.date_range("2026-04-01", AS_OF)
    calendar = pd.DataFrame({"date": pd.date_range("2026-04-01", "2026-12-31"), "store_id": "S01", "is_open": 1})
    # Стабильный профиль; рост выходных изолирован в отдельном сценарии.
    rng = np.random.default_rng(seed)
    base_rows = []
    for date in history_dates:
        for i in range(10):
            quantity = max(0, round(18 + 2*i + rng.normal(0, 3)))
            base_rows.append({"date": date, "store_id": "S01", "dish_id": f"D{i+1:02}", "quantity": quantity})
    base_sales = pd.DataFrame(base_rows)
    daily_use = base_sales.merge(recipes, on="dish_id", suffixes=("_sales", "_recipe"))
    daily_use["use"] = daily_use.quantity_sales * daily_use.quantity_recipe
    daily_avg = daily_use.groupby("ingredient_id").use.sum() / len(history_dates)
    params = []
    for row in ingredients.itertuples():
        shelf = 30 if row.ingredient_id == "I01" else 7 if row.ingredient_id in ("I02", "I05", "I08", "I13") else 14
        pack = 10 if row.base_unit == "pcs" else 1 if row.ingredient_id == "I02" else .5
        params.append({"store_id": "S01", "ingredient_id": row.ingredient_id, "lead_days": 2,
                       "review_days": 5, "pack_size": pack, "min_order": pack, "unit": row.base_unit, "shelf_life_days": shelf})
    params = pd.DataFrame(params)
    for scenario in SCENARIOS:
        tables = {"dishes": dishes.copy(), "ingredients": ingredients.copy(), "recipes": recipes.copy(),
                  "sales": base_sales.copy(), "purchase_params": params.copy(), "calendar": calendar.copy()}
        stock, deliveries = [], []
        for row in ingredients.itertuples():
            daily = float(daily_avg.loc[row.ingredient_id])
            stock.extend([
                {"lot_id": f"{row.ingredient_id}-A", "store_id": "S01", "ingredient_id": row.ingredient_id,
                 "quantity": round(daily, 4), "unit": row.base_unit, "expires_on": "2026-10-02"},
                {"lot_id": f"{row.ingredient_id}-B", "store_id": "S01", "ingredient_id": row.ingredient_id,
                 "quantity": round(3*daily, 4), "unit": row.base_unit, "expires_on": "2026-10-10"}])
            deliveries.append({"delivery_id": f"DEL-{row.ingredient_id}", "ingredient_id": row.ingredient_id,
                               "store_id": "S01", "quantity": round(2*daily, 4), "unit": row.base_unit,
                               "arrival_date": "2026-10-03", "expires_on": "2026-10-12"})
        tables["stock"], tables["deliveries"] = pd.DataFrame(stock), pd.DataFrame(deliveries)
        if scenario == "weekend_growth":
            mask = tables["sales"].date.dt.dayofweek >= 5
            tables["sales"].loc[mask, "quantity"] = (tables["sales"].loc[mask, "quantity"] * 1.65).round().astype(int)
        elif scenario == "shortage":
            tables["stock"].loc[tables["stock"].ingredient_id == "I01", "quantity"] = .1
            tables["deliveries"] = tables["deliveries"][tables["deliveries"].ingredient_id != "I01"]
        elif scenario == "expiry":
            mask = tables["stock"].ingredient_id == "I02"
            tables["stock"].loc[mask, "quantity"] *= 3
            tables["stock"].loc[mask, "expires_on"] = "2026-10-01"
            # Ещё одна уже просроченная партия для проверки исключения.
            tables["stock"] = pd.concat([tables["stock"], pd.DataFrame([{"lot_id": "EXPIRED", "store_id": "S01", "ingredient_id": "I02", "quantity": 20, "unit": "l", "expires_on": "2026-09-29"}])], ignore_index=True)
        elif scenario == "delayed_delivery":
            tables["stock"].loc[tables["stock"].ingredient_id == "I06", "quantity"] *= .55
            mask = tables["deliveries"].ingredient_id == "I06"
            tables["deliveries"].loc[mask, ["arrival_date", "expires_on"]] = ["2026-10-10", "2026-10-20"]
        elif scenario == "short_history":
            tables["dishes"].loc[tables["dishes"].dish_id == "D10", "introduced_on"] = "2026-09-26"
            tables["sales"] = tables["sales"][(tables["sales"].dish_id != "D10") | (tables["sales"].date >= "2026-09-26")]
        directory = root / scenario
        directory.mkdir(parents=True, exist_ok=True)
        for name, df in tables.items():
            df.to_csv(directory / f"{name}.csv", index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
        (directory / "dataset.json").write_text(json.dumps({"as_of": AS_OF, "scenario": scenario, "seed": seed,
            "synthetic": True, "notice": "Учебные синтетические данные; не данные заказчика"}, ensure_ascii=False, indent=2), encoding="utf-8")
    templates = root.parent / "templates"
    templates.mkdir(parents=True, exist_ok=True)
    for name, columns in SCHEMAS.items():
        pd.DataFrame(columns=columns).to_csv(templates / f"{name}.csv", index=False, encoding="utf-8-sig")
