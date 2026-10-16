"""Transactional outbox; local .eml sink or explicitly configured SMTP."""

import os
import smtplib
import time
from datetime import timedelta
from email.message import EmailMessage

from sqlalchemy import or_, select, update

from .config import DATA
from .db import SessionLocal
from .models import DeliveryAttempt, Notification, now


def process_one(factory=SessionLocal):
    stamp = now()
    with factory() as db:
        row = db.scalar(
            select(Notification)
            .where(
                Notification.delivery_status.in_(["pending", "retry"]),
                Notification.next_attempt <= stamp,
                or_(Notification.lease_until.is_(None), Notification.lease_until < stamp),
            )
            .order_by(Notification.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not row:
            return False
        claimed = db.execute(
            update(Notification)
            .where(
                Notification.id == row.id,
                or_(Notification.lease_until.is_(None), Notification.lease_until < stamp),
            )
            .values(lease_until=stamp + timedelta(seconds=60), attempts=Notification.attempts + 1)
        )
        if claimed.rowcount != 1:
            db.rollback()
            return True
        db.refresh(row)
        nid, title, body, attempt = row.id, row.title, row.body, row.attempts
        db.commit()
    error = None
    try:
        message = EmailMessage()
        message["Subject"] = "[ДЕМО] " + title
        message["From"] = os.getenv("SMTP_FROM", "demo@bliny.invalid")
        # Deliberately cannot address real users in the demo release.
        message["To"] = "notifications@bliny.invalid"
        message["Message-ID"] = f"<{nid}@bliny.invalid>"
        message.set_content("Синтетические данные.\n\n" + body)
        host = os.getenv("SMTP_HOST")
        if host:
            with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "1025")), timeout=10) as smtp:
                smtp.send_message(message)
            status = "sent_demo"
        else:
            sink = DATA / "mail"
            sink.mkdir(parents=True, exist_ok=True)
            (sink / f"{nid}.eml").write_bytes(message.as_bytes())
            status = "local_sink"
    except (OSError, smtplib.SMTPException):
        status, error = (
            ("failed" if attempt >= 3 else "retry"),
            "Не удалось доставить демонстрационное письмо.",
        )
    with factory() as db:
        row = db.get(Notification, nid)
        row.delivery_status = status
        row.last_error = error
        row.lease_until = None
        row.next_attempt = now() + timedelta(seconds=min(300, 5 * 2**attempt))
        db.add(DeliveryAttempt(notification_id=nid, status=status, error=error))
        db.commit()
    return True


if __name__ == "__main__":
    while True:
        try:
            if not process_one():
                time.sleep(2)
        except Exception:
            # No payloads, secrets or DSNs in logs. A crashed worker can reclaim expired leases.
            print("Worker: временная ошибка обработки; повтор через 5 секунд.", flush=True)
            time.sleep(5)
