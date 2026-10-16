import hashlib
import hmac
import secrets
from datetime import timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .db import get_db
from .models import AuthSession, Location, Scope, User, now


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${value}"


def verify_password(password: str, encoded: str) -> bool:
    _, salt, expected = encoded.split("$")
    value = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(value, expected)


def fail(code: str, message: str, status=400):
    raise HTTPException(status_code=status, detail={"code": code, "message": message})


def current_user(request: Request, db=Depends(get_db)) -> User:
    token = request.cookies.get("bliny_session", "")
    session = db.get(AuthSession, digest(token)) if token else None
    if not session or session.expires_at.replace(tzinfo=timezone.utc) <= now():
        fail("auth_required", "Войдите в приложение.", 401)
    user = db.get(User, session.user_id)
    if not user or not user.active:
        fail("auth_required", "Учётная запись недоступна.", 401)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session.csrf):
            fail("csrf", "Сессия устарела. Обновите страницу.", 403)
    request.state.auth_session = session
    return user


def scopes(db, user, kind=None):
    query = select(Location).join(Scope, Scope.location_id == Location.id).where(Scope.user_id == user.id)
    if kind:
        query = query.where(Location.kind == kind)
    return list(db.scalars(query.order_by(Location.name)))


def check_location(db, user, location_id, kind=None):
    location = db.get(Location, location_id)
    if not location or (kind and location.kind != kind) or not db.get(Scope, (user.id, location_id)):
        fail("not_found", "Объект не найден.", 404)
    return location


def require_role(user, *roles):
    if user.role not in roles:
        fail("forbidden", "Для этого действия недостаточно прав.", 403)
