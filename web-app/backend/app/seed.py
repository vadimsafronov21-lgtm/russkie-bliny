"""Synthetic fixtures only. No customer data or actual 1C connectivity."""

import random
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .config import DEMO_PASSWORD
from .db import SessionLocal
from .domain import create_request, select_recipe, transition
from .models import Effect, Ingredient, Location, MenuItem, Recipe, Sale, Scope, Stock, User, now
from .schemas import CreateRequest, Transition
from .security import hash_password


def seed(db):
    if db.scalar(select(User.id).limit(1)):
        # Backfill simulated availability of the original synthetic fixture only.
        # This is not a reconstruction of any customer's history.
        for row in db.scalars(select(Sale).where(Sale.payload_hash == "synthetic-seed-v1")):
            row.recorded_at = datetime.combine(
                row.day, time(23, 59), ZoneInfo("Asia/Novosibirsk")
            ).astimezone(timezone.utc)
        db.commit()
        return False
    today = now().astimezone(ZoneInfo("Asia/Novosibirsk")).date()
    db.add_all(
        [
            Location(id="point-1", name="Учебная точка · Центр", kind="point"),
            Location(id="point-2", name="Учебная точка · Парк", kind="point"),
            Location(id="warehouse", name="Учебный склад", kind="warehouse"),
        ]
    )
    ingredients = [
        ("flour", "Мука пшеничная", "г", 1000, 500),
        ("milk", "Молоко", "мл", 1000, 1000),
        ("curd", "Творог", "г", 500, 100),
        ("chicken", "Куриное филе", "г", 500, 300),
        ("berries", "Ягодная начинка", "г", 500, 100),
    ]
    for ident, name, unit, pack, safety in ingredients:
        db.add(Ingredient(id=ident, name=name, unit=unit, pack=pack, safety=safety))
    items = [
        ("classic", "Блин классический", 120, {"flour": "80", "milk": "100"}),
        ("curd-pancake", "Блин с творогом", 190, {"flour": "80", "milk": "100", "curd": "30"}),
        ("chicken-pancake", "Блин с курицей", 240, {"flour": "80", "milk": "100", "chicken": "60"}),
        ("berry-pancake", "Блин с ягодами", 210, {"flour": "80", "milk": "100", "berries": "50"}),
    ]
    for ident, name, price, _ in items:
        db.add(MenuItem(id=ident, name=name, price=price))
    db.flush()
    for ident, _, _, components in items:
        db.add(
            Recipe(
                id=ident + "-v1",
                item_id=ident,
                valid_from=today - timedelta(days=365),
                valid_to=None,
                components=components,
            )
        )
    accounts = [
        ("admin", "Администратор", "admin", ["point-1", "point-2", "warehouse"]),
        ("analyst", "Аналитик", "analyst", ["point-1", "point-2"]),
        ("warehouse", "Кладовщик", "warehouse", ["point-1", "point-2", "warehouse"]),
        ("point1", "Сотрудник · Центр", "point", ["point-1"]),
        ("point2", "Сотрудник · Парк", "point", ["point-2"]),
    ]
    users = {}
    for username, name, role, locations in accounts:
        user = User(username=username, name=name, role=role, password_hash=hash_password(DEMO_PASSWORD))
        db.add(user)
        db.flush()
        users[username] = user
        db.add_all([Scope(user_id=user.id, location_id=x) for x in locations])
    for loc in ("point-1", "point-2", "warehouse"):
        for ident, _, _, _, _ in ingredients:
            qty = (
                60000
                if loc == "warehouse"
                else {"flour": 5500, "milk": 6500, "curd": 700, "chicken": 2500, "berries": 4000}[ident]
            )
            if loc == "point-2":
                qty *= 2
            db.add(Stock(location_id=loc, ingredient_id=ident, quantity=qty, reserved=0))
            db.add(
                Effect(
                    key=f"opening:{loc}:{ident}",
                    location_id=loc,
                    ingredient_id=ident,
                    quantity=qty,
                    reason="Демонстрационный начальный остаток; после исторического набора",
                )
            )
    db.flush()
    rng = random.Random(42)
    # History predates the opening stock; it MUST NOT be replayed over that opening stock.
    for day_offset in range(56, 0, -1):
        day = today - timedelta(days=day_offset)
        for point in ("point-1", "point-2"):
            for index, (ident, _, price, _) in enumerate(items):
                quantity = (
                    rng.choice([0, 0, 0, 0, 0, 1, 2])
                    if index == 3
                    else max(0, [18, 13, 10][index] + rng.randint(-4, 4) + (5 if day.weekday() >= 5 else 0))
                )
                if point == "point-2":
                    quantity = int(quantity * 0.8)
                db.add(
                    Sale(
                        event_id=f"history:{day}:{point}:{ident}",
                        payload_hash="synthetic-seed-v1",
                        point_id=point,
                        item_id=ident,
                        recipe_id=select_recipe(db, ident, day).id,
                        day=day,
                        quantity=quantity,
                        revenue=Decimal(price * quantity),
                        kind="sale",
                        recorded_at=datetime.combine(
                            day, time(23, 59), ZoneInfo("Asia/Novosibirsk")
                        ).astimezone(timezone.utc),
                        consumption={},
                    )
                )
    first = create_request(
        db,
        users["point1"],
        CreateRequest(
            point_id="point-1",
            lines=[
                {"ingredient_id": "curd", "quantity": "1500"},
                {"ingredient_id": "milk", "quantity": "3000"},
            ],
            note="Учебная заявка. Проведите её до приёмки на точке.",
        ),
    )
    second = create_request(
        db,
        users["point2"],
        CreateRequest(
            point_id="point-2",
            lines=[{"ingredient_id": "flour", "quantity": "2000"}],
            note="Учебный пример отправленной накладной.",
        ),
    )
    from .models import Replenishment

    req = db.get(Replenishment, second["id"])
    for status in ("accepted", "packing", "sent"):
        transition(db, users["warehouse"], req, Transition(version=req.version, status=status))
    db.commit()
    return bool(first)


if __name__ == "__main__":
    with SessionLocal() as session:
        print(
            "Демонстрационные данные созданы." if seed(session) else "Данные уже существуют; изменений нет."
        )
