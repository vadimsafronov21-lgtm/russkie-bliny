import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import inspect

from backend.app.db import make_engine


def test_all_migrations_apply_to_empty_database(tmp_path):
    root = Path(__file__).resolve().parents[1]
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    environment = {**os.environ, "DATABASE_URL": url}
    for command in (["upgrade", "head"], ["check"]):
        run = subprocess.run(
            [sys.executable, "-m", "alembic", *command],
            cwd=root,
            env=environment,
            capture_output=True,
            timeout=30,
        )
        assert run.returncode == 0, run.stderr.decode(errors="replace")
    engine = make_engine(url)
    with engine.connect() as conn:
        columns = {column["name"] for column in inspect(conn).get_columns("sales")}
        assert {"refunded_quantity", "recorded_at"} <= columns
        assert {"users", "requests", "stocks", "inventory_effects", "receipts"} <= set(
            inspect(conn).get_table_names()
        )
    engine.dispose()
