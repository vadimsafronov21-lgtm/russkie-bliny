import hashlib
import json
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, update

from .models import (
    Audit,
    Command,
    Effect,
    Ingredient,
    MenuItem,
    Notification,
    Receipt,
    Recipe,
    Replenishment,
    RequestLine,
    Sale,
    Stock,
    now,
)
from .security import check_location, fail, require_role

STATUS = {
    "new": "Новая",
    "accepted": "Принята",
    "packing": "Комплектуется",
    "sent": "Отправлена",
    "received": "Получена",
    "cancelled": "Отменена",
}


def fingerprint(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str, ensure_ascii=False).encode()
    ).hexdigest()


def run_command(db, user, key, action, payload, operation):
    if not key or len(key) > 100:
        fail("idempotency_key", "Требуется Idempotency-Key длиной до 100 символов.", 422)
    hashed = fingerprint({"action": action, "payload": payload})
    old = db.scalar(select(Command).where(Command.actor_id == user.id, Command.key == key))
    if old:
        if old.payload_hash != hashed:
            fail("key_conflict", "Этот ключ уже использован для другой операции.", 409)
        return old.result
    cmd = Command(actor_id=user.id, key=key, payload_hash=hashed, result={})
    db.add(cmd)
    db.flush()  # Unique constraint protects concurrent command execution.
    result = operation()
    cmd.result = result
    db.commit()
    return result


def audit(db, user, location, action, detail):
    db.add(Audit(actor_id=user.id, location_id=location, action=action, detail=detail))


def notify(db, key, location, title, body):
    db.add(Notification(key=key, location_id=location, title=title, body=body))


def move_stock(db, location, ingredient, quantity, key, reason, guard=False):
    query = update(Stock).where(Stock.location_id == location, Stock.ingredient_id == ingredient)
    if guard:
        query = query.where(Stock.quantity + quantity >= Stock.reserved)
    result = db.execute(query.values(quantity=Stock.quantity + quantity))
    if result.rowcount != 1:
        fail("stock_unavailable", "Недостаточно свободного запаса или отсутствует строка остатка.", 409)
    db.add(Effect(key=key, location_id=location, ingredient_id=ingredient, quantity=quantity, reason=reason))


def request_rows(db, rid):
    return list(
        db.scalars(
            select(RequestLine).where(RequestLine.request_id == rid).order_by(RequestLine.ingredient_id)
        )
    )


def get_request(db, user, rid):
    req = db.get(Replenishment, rid)
    if not req:
        fail("not_found", "Объект не найден.", 404)
    check_location(db, user, req.point_id, "point")
    if user.role == "warehouse":
        check_location(db, user, req.warehouse_id, "warehouse")
    return req


def serialize_request(db, req):
    return {
        "id": req.id,
        "number": req.number,
        "point_id": req.point_id,
        "warehouse_id": req.warehouse_id,
        "status": req.status,
        "status_label": STATUS[req.status],
        "version": req.version,
        "note": req.note,
        "discrepancy": req.discrepancy,
        "invoice_number": req.invoice_number,
        "created_at": req.created_at.isoformat(),
        "shipped_at": req.shipped_at.isoformat() if req.shipped_at else None,
        "lines": [
            {"ingredient_id": x.ingredient_id, "quantity": str(x.quantity), "received": str(x.received)}
            for x in request_rows(db, req.id)
        ],
        "receipts": [
            {"id": r.id, "lines": r.lines, "note": r.note, "created_at": r.created_at.isoformat()}
            for r in db.scalars(
                select(Receipt).where(Receipt.request_id == req.id).order_by(Receipt.created_at)
            )
        ],
    }


def create_request(db, user, payload):
    require_role(user, "point", "warehouse")
    check_location(db, user, payload.point_id, "point")
    # Demo has a single explicitly supported route. Point staff cannot see warehouse stock.
    if payload.warehouse_id != "warehouse":
        fail("route_unavailable", "Этот маршрут снабжения не настроен.", 422)
    if user.role == "warehouse":
        check_location(db, user, payload.warehouse_id, "warehouse")
    for line in payload.lines:
        if not db.get(Ingredient, line.ingredient_id):
            fail("ingredient_missing", "Неизвестный ингредиент.", 422)
    key = fingerprint(
        {
            "point": payload.point_id,
            "warehouse": payload.warehouse_id,
            "lines": sorted((x.ingredient_id, format(x.quantity.normalize(), "f")) for x in payload.lines),
        }
    )
    old = db.scalar(select(Replenishment).where(Replenishment.active_fingerprint == key))
    if old:
        return serialize_request(db, old)
    req = Replenishment(
        id=str(uuid4()),
        number="З-" + uuid4().hex[:10].upper(),
        point_id=payload.point_id,
        warehouse_id=payload.warehouse_id,
        note=payload.note,
        active_fingerprint=key,
    )
    db.add(req)
    db.flush()
    for line in payload.lines:
        db.add(RequestLine(request_id=req.id, ingredient_id=line.ingredient_id, quantity=line.quantity))
    notify(
        db,
        f"request:{req.id}:new",
        req.point_id,
        f"Новая заявка {req.number}",
        "Ожидает принятия кладовщиком.",
    )
    audit(db, user, req.point_id, "request.created", req.number)
    db.flush()
    return serialize_request(db, req)


def claim_version(db, req, version):
    if req.version != version:
        fail("version_conflict", "Документ уже изменился. Обновите данные.", 409)
    result = db.execute(
        update(Replenishment)
        .where(Replenishment.id == req.id, Replenishment.version == version)
        .values(version=version + 1)
    )
    if result.rowcount != 1:
        fail("version_conflict", "Документ изменён другим пользователем.", 409)
    db.refresh(req)


def transition(db, user, req, payload):
    allowed = {
        "new": {"accepted", "cancelled"},
        "accepted": {"packing", "cancelled"},
        "packing": {"sent", "cancelled"},
    }
    if payload.status == "cancelled" and req.status == "new":
        require_role(user, "point", "warehouse")
    else:
        require_role(user, "warehouse")
        check_location(db, user, req.warehouse_id, "warehouse")
    if payload.status not in allowed.get(req.status, set()):
        fail("invalid_transition", "Этот переход статуса недоступен.", 409)
    claim_version(db, req, payload.version)
    previous = req.status
    lines = request_rows(db, req.id)
    for line in lines:
        stock = update(Stock).where(
            Stock.location_id == req.warehouse_id, Stock.ingredient_id == line.ingredient_id
        )
        if payload.status == "accepted":
            changed = db.execute(
                stock.where(Stock.quantity - Stock.reserved >= line.quantity).values(
                    reserved=Stock.reserved + line.quantity
                )
            )
            if changed.rowcount != 1:
                fail(
                    "warehouse_shortage", "На складе недостаточно свободного запаса. Заявка не принята.", 409
                )
        elif payload.status in {"sent", "cancelled"} and previous in {"accepted", "packing"}:
            changed = db.execute(
                stock.where(Stock.reserved >= line.quantity).values(reserved=Stock.reserved - line.quantity)
            )
            if changed.rowcount != 1:
                fail("reservation_conflict", "Резерв не совпадает с заявкой. Требуется проверка.", 409)
            if payload.status == "sent":
                move_stock(
                    db,
                    req.warehouse_id,
                    line.ingredient_id,
                    -line.quantity,
                    f"shipment:{req.id}:{line.ingredient_id}",
                    f"Отправка {req.number}",
                    guard=True,
                )
    req.status = payload.status
    if req.status == "packing":
        req.invoice_number = "Н-" + req.number[2:]
    if req.status == "sent":
        req.shipped_at = now()
    if req.status == "cancelled":
        req.active_fingerprint = None
    audit(
        db, user, req.point_id, "request.status", f"{req.number}: {STATUS[previous]} → {STATUS[req.status]}"
    )
    notify(
        db,
        f"request:{req.id}:{req.status}",
        req.point_id,
        f"{req.number} · {STATUS[req.status]}",
        "Откройте заявку, чтобы посмотреть состав и состояние.",
    )
    db.flush()
    return serialize_request(db, req)


def receive(db, user, req, payload):
    require_role(user, "point")
    if req.status != "sent":
        fail("not_sent", "Принимать можно только отправленную накладную.", 409)
    claim_version(db, req, payload.version)
    lines = {x.ingredient_id: x for x in request_rows(db, req.id)}
    receipt = Receipt(
        id=str(uuid4()),
        request_id=req.id,
        actor_id=user.id,
        note=payload.note,
        lines={x.ingredient_id: str(x.quantity) for x in payload.lines},
    )
    for item in payload.lines:
        line = lines.get(item.ingredient_id)
        if not line or item.quantity > line.quantity - line.received:
            fail("over_receipt", "Принятое количество превышает остаток по накладной.", 422)
        line.received += item.quantity
        move_stock(
            db,
            req.point_id,
            item.ingredient_id,
            item.quantity,
            f"receipt:{receipt.id}:{item.ingredient_id}",
            f"Приёмка {req.invoice_number}",
        )
    req.discrepancy = payload.note or req.discrepancy
    if all(x.received == x.quantity for x in lines.values()):
        req.status = "received"
        req.active_fingerprint = None
    db.add(receipt)
    audit(db, user, req.point_id, "request.received", f"{req.number}: {receipt.lines}")
    notify(
        db,
        f"receipt:{receipt.id}",
        req.point_id,
        f"{req.number} · {'Получена' if req.status == 'received' else 'Частичная приёмка'}",
        payload.note or "Принятое количество добавлено к остатку приложения.",
    )
    db.flush()
    return serialize_request(db, req)


def select_recipe(db, item_id, day):
    recipes = list(
        db.scalars(
            select(Recipe).where(
                Recipe.item_id == item_id,
                Recipe.valid_from <= day,
                (Recipe.valid_to.is_(None)) | (Recipe.valid_to > day),
            )
        )
    )
    if len(recipes) != 1:
        fail("recipe_unknown", "Не найдена однозначная рецептура на дату продажи.", 422)
    return recipes[0]


def record_sale(db, user, payload):
    require_role(user, "point")
    location = check_location(db, user, payload.point_id, "point")
    if payload.day > now().astimezone(ZoneInfo(location.timezone)).date():
        fail("future_sale", "Нельзя зарегистрировать продажу из будущего.", 422)
    hashed = fingerprint(payload.model_dump(mode="json"))
    old = db.scalar(select(Sale).where(Sale.point_id == payload.point_id, Sale.event_id == payload.event_id))
    if old:
        if old.payload_hash != hashed:
            fail("event_conflict", "Событие с этим ID уже имеет другое содержание.", 409)
        return {"id": old.id, "consumption": old.consumption, "duplicate": True}
    item = db.get(MenuItem, payload.item_id)
    if not item:
        fail("item_missing", "Позиция меню не найдена.", 422)
    recipe = select_recipe(db, item.id, payload.day)
    revenue = item.price * payload.quantity if payload.kind == "sale" else Decimal(0)
    if payload.kind == "refund_prepared":
        original = db.scalar(select(Sale).where(Sale.id == payload.original_id).with_for_update())
        if (
            not original
            or original.point_id != payload.point_id
            or original.kind != "sale"
            or original.item_id != item.id
        ):
            fail("original_missing", "Нужна исходная продажа этой точки и позиции.", 422)
        changed = db.execute(
            update(Sale)
            .where(Sale.id == original.id, Sale.refunded_quantity + payload.quantity <= Sale.quantity)
            .values(refunded_quantity=Sale.refunded_quantity + payload.quantity)
        )
        if changed.rowcount != 1:
            fail("refund_excess", "Возврат превышает количество в исходной продаже.", 422)
        revenue = -(original.revenue / original.quantity) * payload.quantity
        recipe = db.get(Recipe, original.recipe_id)
    elif payload.original_id:
        fail("unexpected_reference", "Ссылка на исходную продажу допустима только для возврата.", 422)
    consumption = (
        {k: str(Decimal(v) * payload.quantity) for k, v in recipe.components.items()}
        if payload.kind == "sale"
        else {}
    )
    sale = Sale(
        id=str(uuid4()),
        event_id=payload.event_id,
        payload_hash=hashed,
        point_id=payload.point_id,
        item_id=item.id,
        recipe_id=recipe.id,
        day=payload.day,
        quantity=payload.quantity,
        revenue=revenue,
        kind=payload.kind,
        original_id=payload.original_id,
        consumption=consumption,
    )
    db.add(sale)
    for ingredient, quantity in consumption.items():
        move_stock(
            db,
            payload.point_id,
            ingredient,
            -Decimal(quantity),
            f"sale:{sale.id}:{ingredient}",
            f"Демо-продажа: {item.name}, {payload.quantity} порц.",
        )
    audit(db, user, payload.point_id, f"sale.{payload.kind}", f"{item.name}: {payload.quantity} порц.")
    db.flush()
    return {"id": sale.id, "consumption": consumption, "duplicate": False}
