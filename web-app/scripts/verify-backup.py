"""Restore a SQLite backup into a new file, without replacing the running database."""

import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

root = Path(__file__).resolve().parents[1]
candidates = sorted((root / "backups").glob("demo-*.db"))
source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else candidates[-1] if candidates else None
if source is None or not source.is_file():
    raise SystemExit("Сначала создайте резервную копию scripts/backup-local.py.")
destination = root / ".cache" / f"restored-{uuid4().hex}.db"
destination.parent.mkdir(exist_ok=True)


def manifest(connection):
    tables = [
        r[0]
        for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    result = {}
    for name in tables:
        quoted = '"' + name.replace('"', '""') + '"'
        rows = connection.execute(f"SELECT * FROM {quoted}").fetchall()
        serialized = sorted(json.dumps(row, ensure_ascii=True, default=str) for row in rows)
        result[name] = {
            "rows": len(rows),
            "sha256": hashlib.sha256("\n".join(serialized).encode()).hexdigest(),
        }
    return result


with (
    sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original,
    sqlite3.connect(destination) as restored,
):
    original.backup(restored)
    assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert restored.execute("PRAGMA foreign_key_check").fetchall() == []
    expected, actual = manifest(original), manifest(restored)
    assert expected == actual, "Содержимое восстановленной базы не совпадает с копией"
report = {
    "source": str(source),
    "restored_to": str(destination),
    "integrity": "ok",
    "foreign_keys": "ok",
    "tables_match": True,
    "tables": actual,
}
report_path = root / "docs" / "backup-verification.json"
report_path.parent.mkdir(exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Restored and verified {len(actual)} tables. Report: {report_path}")
