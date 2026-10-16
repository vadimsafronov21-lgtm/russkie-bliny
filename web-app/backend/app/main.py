import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from . import analytics, domain
from .config import COOKIE_SECURE, ROOT
from .db import get_db
from .models import Audit, AuthSession, Ingredient, MenuItem, Notification, Replenishment, Stock, User, now
from .schemas import CreateRequest, DemoSale, Login, Receive, Transition
from .security import check_location, current_user, digest, fail, require_role, scopes, verify_password


def user_info(db, user):
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "role": user.role,
        "locations": [{"id": x.id, "name": x.name, "kind": x.kind} for x in scopes(db, user)],
    }


def create_app():
    app = FastAPI(
        title="Русские блины · демонстрационное API",
        version="0.1.0",
        description="Только синтетические данные. Реальная 1С не подключена.",
    )
    attempts = defaultdict(deque)

    @app.middleware("http")
    async def headers(request, call_next):
        trace = secrets.token_hex(8)
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            if urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse(
                    {"detail": {"code": "origin", "message": "Недопустимый источник запроса."}},
                    status_code=403,
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = trace
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        return JSONResponse(
            {
                "detail": {
                    "code": "validation",
                    "message": "Проверьте введённые значения.",
                    "fields": [".".join(str(x) for x in e["loc"]) for e in exc.errors()],
                }
            },
            status_code=422,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(_, exc):
        return JSONResponse(
            {
                "detail": {
                    "code": "conflict",
                    "message": "Операция уже обрабатывается или нарушает целостность. Обновите данные и повторите с тем же ключом.",
                }
            },
            status_code=409,
        )

    @app.exception_handler(OperationalError)
    async def database_error(_, exc):
        return JSONResponse(
            {
                "detail": {
                    "code": "database_busy",
                    "message": "База временно недоступна. Повторите операцию с тем же ключом.",
                }
            },
            status_code=503,
        )

    @app.get("/api/health")
    def health(db=Depends(get_db)):
        db.execute(select(1))
        return {"status": "ok", "data_mode": "demo"}

    @app.post("/api/auth/login")
    def login(payload: Login, request: Request, response: Response, db=Depends(get_db)):
        key = (request.client.host if request.client else "unknown", payload.username)
        tick = time.monotonic()
        queue = attempts[key]
        while queue and queue[0] < tick - 60:
            queue.popleft()
        if len(queue) >= 8:
            fail("rate_limit", "Слишком много попыток входа. Подождите минуту.", 429)
        queue.append(tick)
        user = db.scalar(select(User).where(User.username == payload.username))
        if not user or not user.active or not verify_password(payload.password, user.password_hash):
            fail("invalid_credentials", "Неверный логин или пароль.", 401)
        old_token = request.cookies.get("bliny_session")
        if old_token:
            old = db.get(AuthSession, digest(old_token))
            if old:
                db.delete(old)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        db.add(
            AuthSession(
                token_hash=digest(token), user_id=user.id, csrf=csrf, expires_at=now() + timedelta(hours=12)
            )
        )
        db.commit()
        response.set_cookie(
            "bliny_session",
            token,
            max_age=43200,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="lax",
            path="/",
        )
        return {"user": user_info(db, user), "csrf": csrf}

    @app.get("/api/auth/me")
    def me(request: Request, user=Depends(current_user), db=Depends(get_db)):
        return {"user": user_info(db, user), "csrf": request.state.auth_session.csrf}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)):
        db.delete(request.state.auth_session)
        db.commit()
        response.delete_cookie("bliny_session", path="/")
        return {"ok": True}

    @app.get("/api/catalog")
    def catalog(user=Depends(current_user), db=Depends(get_db)):
        return {
            "ingredients": [
                {"id": x.id, "name": x.name, "unit": x.unit, "pack": str(x.pack)}
                for x in db.scalars(select(Ingredient).order_by(Ingredient.name))
            ],
            "menu": [
                {"id": x.id, "name": x.name, "price": str(x.price)} for x in db.scalars(select(MenuItem))
            ],
            "today": now().astimezone(__import__("zoneinfo").ZoneInfo("Asia/Novosibirsk")).date().isoformat(),
        }

    @app.get("/api/stocks")
    def stocks(location_id: str, user=Depends(current_user), db=Depends(get_db)):
        check_location(db, user, location_id)
        return [
            {
                "ingredient_id": s.ingredient_id,
                "name": i.name,
                "unit": i.unit,
                "quantity": str(s.quantity),
                "reserved": str(s.reserved),
                "available": str(s.quantity - s.reserved),
                "negative": s.quantity < 0,
            }
            for s, i in db.execute(
                select(Stock, Ingredient)
                .join(Ingredient)
                .where(Stock.location_id == location_id)
                .order_by(Ingredient.name)
            )
        ]

    @app.get("/api/requests")
    def requests(point_id: str | None = None, user=Depends(current_user), db=Depends(get_db)):
        points = [x.id for x in scopes(db, user, "point")]
        if point_id:
            check_location(db, user, point_id, "point")
            points = [point_id]
        query = select(Replenishment).where(Replenishment.point_id.in_(points))
        if user.role == "warehouse":
            query = query.where(Replenishment.warehouse_id.in_([x.id for x in scopes(db, user, "warehouse")]))
        return [
            domain.serialize_request(db, x)
            for x in db.scalars(query.order_by(Replenishment.created_at.desc()).limit(200))
        ]

    @app.get("/api/requests/{rid}")
    def request_detail(rid: str, user=Depends(current_user), db=Depends(get_db)):
        return domain.serialize_request(db, domain.get_request(db, user, rid))

    @app.post("/api/requests")
    def new_request(
        payload: CreateRequest,
        idempotency_key: str = Header(default=""),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        require_role(user, "point", "warehouse")
        check_location(db, user, payload.point_id, "point")
        return domain.run_command(
            db,
            user,
            idempotency_key,
            "request.create",
            payload.model_dump(mode="json"),
            lambda: domain.create_request(db, user, payload),
        )

    @app.post("/api/requests/{rid}/transition")
    def change_request(
        rid: str,
        payload: Transition,
        idempotency_key: str = Header(default=""),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        req = domain.get_request(db, user, rid)
        return domain.run_command(
            db,
            user,
            idempotency_key,
            f"request.transition:{rid}",
            payload.model_dump(mode="json"),
            lambda: domain.transition(db, user, req, payload),
        )

    @app.post("/api/requests/{rid}/receive")
    def receive_request(
        rid: str,
        payload: Receive,
        idempotency_key: str = Header(default=""),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        require_role(user, "point")
        req = domain.get_request(db, user, rid)
        return domain.run_command(
            db,
            user,
            idempotency_key,
            f"request.receive:{rid}",
            payload.model_dump(mode="json"),
            lambda: domain.receive(db, user, req, payload),
        )

    @app.post("/api/demo/sales")
    def demo_sale(
        payload: DemoSale,
        idempotency_key: str = Header(default=""),
        user=Depends(current_user),
        db=Depends(get_db),
    ):
        require_role(user, "point")
        check_location(db, user, payload.point_id, "point")
        return domain.run_command(
            db,
            user,
            idempotency_key,
            "demo.sale",
            payload.model_dump(mode="json"),
            lambda: domain.record_sale(db, user, payload),
        )

    @app.get("/api/analytics")
    def analysis(point_id: str, user=Depends(current_user), db=Depends(get_db)):
        check_location(db, user, point_id, "point")
        return analytics.overview(db, point_id)

    @app.get("/api/forecast")
    def forecast(
        point_id: str, horizon: int = Query(7, ge=1, le=14), user=Depends(current_user), db=Depends(get_db)
    ):
        check_location(db, user, point_id, "point")
        if horizon not in {1, 7, 14}:
            fail("horizon", "Доступные горизонты: 1, 7, 14 дней.", 422)
        return analytics.forecast(db, point_id, horizon)

    @app.get("/api/forecast/evaluation")
    def evaluation(point_id: str, user=Depends(current_user), db=Depends(get_db)):
        check_location(db, user, point_id, "point")
        return analytics.backtest(db, point_id)

    @app.get("/api/recommendations")
    def recommendations(point_id: str, user=Depends(current_user), db=Depends(get_db)):
        check_location(db, user, point_id, "point")
        return analytics.recommendations(db, point_id)

    @app.get("/api/notifications")
    def notifications(user=Depends(current_user), db=Depends(get_db)):
        ids = [x.id for x in scopes(db, user)]
        return [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "created_at": n.created_at.isoformat(),
                "delivery_status": n.delivery_status,
                "attempts": n.attempts,
                "last_error": n.last_error,
            }
            for n in db.scalars(
                select(Notification)
                .where(Notification.location_id.in_(ids))
                .order_by(Notification.created_at.desc())
                .limit(100)
            )
        ]

    @app.get("/api/audit")
    def audit(user=Depends(current_user), db=Depends(get_db)):
        ids = [x.id for x in scopes(db, user)]
        return [
            {"id": x.id, "action": x.action, "detail": x.detail, "created_at": x.created_at.isoformat()}
            for x in db.scalars(
                select(Audit).where(Audit.location_id.in_(ids)).order_by(Audit.created_at.desc()).limit(100)
            )
        ]

    @app.get("/api/system")
    def system(user=Depends(current_user), db=Depends(get_db)):
        return {
            "data_mode": "demo",
            "inventory_mode": "application_ledger",
            "database": db.bind.dialect.name,
            "one_c": "Не подключена",
            "last_successful_sync": None,
            "weather": "Не подключена",
            "llm": "Не подключена; платные запросы отключены",
            "news": "Не подключены",
            "email": "Демонстрационные адреса .invalid; локальный sink / Mailpit",
            "limitations": [
                "Нет партий и проверки сроков годности",
                "Одна отгрузка на заявку, несколько приёмок",
                "Расхождения записываются, закрытие недопоставки — следующий этап",
                "Нет реальной 1С, CatBoost/GRU и администрирования пользователей",
            ],
        }

    @app.get("/api/admin/users")
    def users(user=Depends(current_user), db=Depends(get_db)):
        require_role(user, "admin")
        return [user_info(db, x) for x in db.scalars(select(User).order_by(User.username))]

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
