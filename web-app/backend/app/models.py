from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Novosibirsk")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(default=True)


class Scope(Base):
    __tablename__ = "user_scopes"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), primary_key=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Ingredient(Base):
    __tablename__ = "ingredients"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(12))
    pack: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    safety: Mapped[Decimal] = mapped_column(Numeric(18, 3))


class Stock(Base):
    __tablename__ = "stocks"
    __table_args__ = (CheckConstraint("reserved >= 0", name="nonnegative_reserved"),)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), primary_key=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=0)
    reserved: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=0)


class Effect(Base):
    __tablename__ = "inventory_effects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String(220), unique=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    reason: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MenuItem(Base):
    __tablename__ = "menu_items"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class Recipe(Base):
    __tablename__ = "recipe_versions"
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("menu_items.id"), index=True)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Already gross quantities in the ingredient base unit, per one portion.
    components: Mapped[dict] = mapped_column(JSON)


class Sale(Base):
    __tablename__ = "sales"
    __table_args__ = (UniqueConstraint("point_id", "event_id", name="sale_event_once"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    event_id: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    point_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("menu_items.id"))
    recipe_id: Mapped[str] = mapped_column(ForeignKey("recipe_versions.id"))
    day: Mapped[date] = mapped_column(Date, index=True)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=now, nullable=True)
    quantity: Mapped[int]
    refunded_quantity: Mapped[int] = mapped_column(default=0, server_default="0")
    revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    kind: Mapped[str] = mapped_column(String(30), default="sale")
    original_id: Mapped[str | None] = mapped_column(ForeignKey("sales.id"), nullable=True)
    consumption: Mapped[dict] = mapped_column(JSON, default=dict)


class Replenishment(Base):
    __tablename__ = "requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    point_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    warehouse_id: Mapped[str] = mapped_column(ForeignKey("locations.id"))
    status: Mapped[str] = mapped_column(String(20), default="new")
    version: Mapped[int] = mapped_column(default=1)
    active_fingerprint: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    discrepancy: Mapped[str] = mapped_column(String(500), default="")
    invoice_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RequestLine(Base):
    __tablename__ = "request_lines"
    __table_args__ = (
        UniqueConstraint("request_id", "ingredient_id", name="one_ingredient_line"),
        CheckConstraint(
            "quantity > 0 AND received >= 0 AND received <= quantity", name="valid_line_quantities"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), index=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    received: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=0)


class Receipt(Base):
    __tablename__ = "receipts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    lines: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Command(Base):
    __tablename__ = "commands"
    __table_args__ = (UniqueConstraint("actor_id", "key", name="command_once"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    key: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(String(600))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    key: Mapped[str] = mapped_column(String(180), unique=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(String(600))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    delivery_status: Mapped[str] = mapped_column(String(30), default="pending")
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(240), nullable=True)


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    notification_id: Mapped[str] = mapped_column(ForeignKey("notifications.id"))
    status: Mapped[str] = mapped_column(String(30))
    error: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
