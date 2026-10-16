"""Consistent SQLite demo backup. PostgreSQL: use pg_dump, see README."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "data" / "demo.db"
if not source.exists():
    raise SystemExit("Локальная demo.db не найдена. Для PostgreSQL используйте pg_dump.")
dest = root / "backups" / f"demo-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.db"
dest.parent.mkdir(exist_ok=True)
with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as live, sqlite3.connect(dest) as backup:
    live.backup(backup)
    result = backup.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError("Проверка резервной копии не пройдена")
print(dest)
