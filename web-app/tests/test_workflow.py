from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select

from backend.app.analytics import predict
from backend.app.models import Command, Notification, Recipe, Sale, Stock
from backend.app.worker import process_one


def post(client, path, payload, key=None):
    return client.post(path, json=payload, headers={"Idempotency-Key": key or str(uuid4())})


def qty(client, ingredient="curd", point="point-1"):
    rows = client.get("/api/stocks", params={"location_id": point}).json()
    return Decimal(next(x["quantity"] for x in rows if x["ingredient_id"] == ingredient))


def sale_payload(client, **kwargs):
    return {
        "event_id": "test-sale",
        "point_id": "point-1",
        "item_id": "curd-pancake",
        "quantity": 10,
        "day": client.get("/api/catalog").json()["today"],
        **kwargs,
    }


def new_request(client, amount="500"):
    response = post(
        client,
        "/api/requests",
        {"point_id": "point-1", "lines": [{"ingredient_id": "curd", "quantity": amount}]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def ship(client, req):
    for status in ("accepted", "packing", "sent"):
        response = post(
            client, f"/api/requests/{req['id']}/transition", {"version": req["version"], "status": status}
        )
        assert response.status_code == 200, response.text
        req = response.json()
    return req


def test_sale_exact_and_duplicates(clients, setup):
    client = clients()
    before = qty(client)
    payload = sale_payload(client)
    first = post(client, "/api/demo/sales", payload, "sale-key")
    assert first.status_code == 200, first.text
    assert Decimal(first.json()["consumption"]["curd"]) == 300
    assert qty(client) == before - 300
    assert post(client, "/api/demo/sales", payload, "sale-key").json() == first.json()
    assert post(client, "/api/demo/sales", payload, "other-key").json()["duplicate"]
    assert qty(client) == before - 300
    assert post(client, "/api/demo/sales", {**payload, "quantity": 11}).status_code == 409


def test_historical_recipe_does_not_change(clients, setup):
    client = clients()
    from datetime import date

    today = date.fromisoformat(client.get("/api/catalog").json()["today"])
    with setup[1]() as db:
        old = db.get(Recipe, "curd-pancake-v1")
        old.valid_to = today
        db.add(
            Recipe(id="curd-pancake-v2", item_id="curd-pancake", valid_from=today, components={"curd": "40"})
        )
        db.commit()
    old_sale = post(client, "/api/demo/sales", sale_payload(client, day=str(today - timedelta(days=1))))
    new_sale = post(client, "/api/demo/sales", sale_payload(client, event_id="new-recipe"))
    assert Decimal(old_sale.json()["consumption"]["curd"]) == 300
    assert Decimal(new_sale.json()["consumption"]["curd"]) == 400


def test_cancel_and_refund_do_not_restore_ingredients(clients):
    client = clients()
    before = qty(client)
    assert post(client, "/api/demo/sales", sale_payload(client, kind="cancel_before")).status_code == 200
    assert qty(client) == before
    sale = post(client, "/api/demo/sales", sale_payload(client, event_id="cooked")).json()
    refund = sale_payload(client, event_id="refund", kind="refund_prepared", original_id=sale["id"])
    assert post(client, "/api/demo/sales", refund).status_code == 200
    assert qty(client) == before - 300
    assert post(client, "/api/demo/sales", {**refund, "event_id": "excess-refund"}).status_code == 422


def test_partial_receipt_and_outbox(clients, setup):
    point, warehouse = clients(), clients("warehouse")
    before = qty(point)
    req = new_request(point)
    assert qty(point) == before
    req = ship(warehouse, req)
    assert req["invoice_number"]
    assert qty(point) == before
    payload = {
        "version": req["version"],
        "lines": [{"ingredient_id": "curd", "quantity": "200"}],
        "note": "Остальное ожидаем",
    }
    path = f"/api/requests/{req['id']}/receive"
    response = post(point, path, payload, "receipt-1")
    assert response.status_code == 200, response.text
    partial = response.json()
    assert partial["status"] == "sent" and partial["lines"][0]["received"] == "200.000"
    assert qty(point) == before + 200
    assert post(point, path, payload, "receipt-1").json() == partial
    assert qty(point) == before + 200
    excessive = {"version": partial["version"], "lines": [{"ingredient_id": "curd", "quantity": "301"}]}
    assert post(point, path, excessive).status_code == 422
    final = post(point, path, {**excessive, "lines": [{"ingredient_id": "curd", "quantity": "300"}]}).json()
    assert final["status"] == "received" and qty(point) == before + 500
    with setup[1]() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.title.contains(req["number"]))
            )
            == 6
        )


def test_foreign_point_and_role_are_denied(clients):
    point, analyst = clients(), clients("analyst")
    req = clients("point2").get("/api/requests").json()[0]
    for path, params in [
        ("/api/stocks", {"location_id": "point-2"}),
        ("/api/stocks", {"location_id": "warehouse"}),
        ("/api/analytics", {"point_id": "point-2"}),
        ("/api/forecast", {"point_id": "point-2"}),
        ("/api/requests", {"point_id": "point-2"}),
        (f"/api/requests/{req['id']}", {}),
    ]:
        assert point.get(path, params=params).status_code == 404
    assert (
        post(
            point,
            f"/api/requests/{req['id']}/receive",
            {"version": 4, "lines": [{"ingredient_id": "flour", "quantity": "1"}]},
        ).status_code
        == 404
    )
    assert (
        post(
            analyst,
            "/api/requests",
            {"point_id": "point-1", "lines": [{"ingredient_id": "curd", "quantity": "10"}]},
        ).status_code
        == 403
    )
    assert point.get("/api/admin/users").status_code == 403


def test_csrf_and_session(clients):
    client = clients()
    client.headers.pop("X-CSRF-Token")
    assert post(client, "/api/demo/sales", sale_payload(client)).status_code == 403
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "point1", "password": "Bliny-demo-2026!"},
            headers={"Origin": "https://evil.invalid"},
        ).status_code
        == 403
    )


def test_existing_supply_dedup_and_optimistic_version(clients):
    point, wh = clients(), clients("warehouse")
    req = new_request(point)
    assert new_request(point)["id"] == req["id"]
    accepted = post(wh, f"/api/requests/{req['id']}/transition", {"version": 1, "status": "accepted"}).json()
    rec = point.get("/api/recommendations", params={"point_id": "point-1"}).json()
    assert Decimal(next(x["incoming"] for x in rec["lines"] if x["ingredient_id"] == "curd")) == 500
    assert (
        post(wh, f"/api/requests/{req['id']}/transition", {"version": 1, "status": "packing"}).status_code
        == 409
    )
    assert accepted["version"] == 2


def test_warehouse_reservations_cancel_and_rollback(clients, setup):
    point, wh = clients(), clients("warehouse")
    req = new_request(point, "60001")
    assert (
        post(wh, f"/api/requests/{req['id']}/transition", {"version": 1, "status": "accepted"}).status_code
        == 409
    )
    assert wh.get(f"/api/requests/{req['id']}").json()["version"] == 1
    req = new_request(point, "300")
    accepted = post(wh, f"/api/requests/{req['id']}/transition", {"version": 1, "status": "accepted"}).json()
    with setup[1]() as db:
        assert db.get(Stock, ("warehouse", "curd")).reserved == 300
    assert (
        post(
            wh,
            f"/api/requests/{req['id']}/transition",
            {"version": accepted["version"], "status": "cancelled"},
        ).status_code
        == 200
    )
    with setup[1]() as db:
        assert db.get(Stock, ("warehouse", "curd")).reserved == 0


def test_negative_stock_is_visible(clients):
    client = clients()
    assert post(client, "/api/demo/sales", sale_payload(client, quantity=100)).status_code == 200
    row = next(
        x
        for x in client.get("/api/stocks", params={"location_id": "point-1"}).json()
        if x["ingredient_id"] == "curd"
    )
    assert row["negative"] and Decimal(row["quantity"]) == -2300


def test_no_future_features_and_temporal_metrics(clients):
    client = clients()
    from datetime import date

    origin = date(2026, 10, 15)
    h = {origin - timedelta(days=7): 10, origin + timedelta(days=7): 9999}
    assert predict(h, origin + timedelta(days=7), origin) == 10
    report = client.get("/api/forecast/evaluation", params={"point_id": "point-1"}).json()
    assert report["data_mode"] == "demo" and len(report["folds"]) == 6
    assert any(x["n"] > 0 and x["mae"] is not None for x in report["folds"])
    assert client.get("/api/forecast", params={"point_id": "point-1", "horizon": 2}).status_code == 422


def test_worker_failure_does_not_break_inventory(clients, setup, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("SMTP_PORT", "1")
    assert process_one(setup[1])
    with setup[1]() as db:
        assert db.scalar(select(Notification).where(Notification.delivery_status == "retry")).attempts == 1
    assert new_request(clients())["status"] == "new"


def test_parallel_repeated_command_has_single_effect(clients, setup):
    client = clients()
    before = qty(client)
    payload = sale_payload(client)

    def send(_):
        return post(client, "/api/demo/sales", payload, "concurrent-sale").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(send, range(2)))
    assert 200 in statuses and all(s in {200, 409, 503} for s in statuses)
    assert post(client, "/api/demo/sales", payload, "concurrent-sale").status_code == 200
    assert qty(client) == before - 300
    with setup[1]() as db:
        assert (
            db.scalar(select(func.count()).select_from(Command).where(Command.key == "concurrent-sale")) == 1
        )


def test_passwords_not_in_responses(clients):
    users = clients("admin").get("/api/admin/users").text
    assert "password" not in users and "Bliny-demo" not in users


def test_late_information_is_not_available_at_old_origin(clients, setup):
    from datetime import date

    from backend.app.analytics import series
    from backend.app.models import now

    client = clients()
    today = date.fromisoformat(client.get("/api/catalog").json()["today"])
    origin = today - timedelta(days=7)
    with setup[1]() as db:
        before = dict(series(db, "point-1", origin)["curd-pancake"])
        db.add(
            Sale(
                event_id="late-report",
                payload_hash="late",
                point_id="point-1",
                item_id="curd-pancake",
                recipe_id="curd-pancake-v1",
                day=origin - timedelta(days=7),
                recorded_at=now(),
                quantity=900,
                revenue=0,
            )
        )
        db.commit()
        assert dict(series(db, "point-1", origin)["curd-pancake"]) == before
        assert (
            series(db, "point-1", origin, as_of=False)["curd-pancake"][origin - timedelta(days=7)]
            == before[origin - timedelta(days=7)] + 900
        )


def test_missing_day_is_not_zero_sales(clients, setup):
    from datetime import date

    from sqlalchemy import delete

    client = clients()
    yesterday = date.fromisoformat(client.get("/api/catalog").json()["today"]) - timedelta(days=1)
    with setup[1]() as db:
        db.execute(delete(Sale).where(Sale.point_id == "point-1", Sale.day == yesterday))
        db.commit()
    result = client.get("/api/analytics", params={"point_id": "point-1"}).json()
    assert result["daily"][-1]["quantity"] is None
