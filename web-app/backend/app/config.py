import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(DATA / 'demo.db').as_posix()}")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "Bliny-demo-2026!")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
if os.getenv("APP_MODE", "demo") != "demo":
    raise RuntimeError("Эта версия поддерживает только демонстрационный режим.")
