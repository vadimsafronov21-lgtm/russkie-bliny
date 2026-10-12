"""Первый запуск из распакованного ZIP: stdlib -> .venv -> зависимости -> GUI.

Не содержит расчётов приложения. Установка затрагивает только папку проекта.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
ENVIRONMENT = ROOT / ".venv"
PYTHON = ENVIRONMENT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MARKER = ENVIRONMENT / "blini-setup.json"


def execute(command, *, env=None):
    child_env = os.environ.copy() if env is None else env.copy()
    child_env.pop("PYTHONPATH", None)
    child_env.pop("PYTHONHOME", None)
    result = subprocess.run([str(arg) for arg in command], cwd=ROOT, env=child_env)
    if result.returncode:
        raise RuntimeError(f"Команда завершилась с кодом {result.returncode}: {command[0]}")


def ready():
    """Проверяет реальные импорты; отметка установки не заменяет эту проверку."""
    if not PYTHON.exists():
        return False
    child_env = os.environ.copy()
    child_env.pop("PYTHONPATH", None)
    child_env.pop("PYTHONHOME", None)
    result = subprocess.run([str(PYTHON), "-c",
        "import pandas,numpy,matplotlib,PySide6,blini; "
        "from pathlib import Path; import sys; "
        "assert Path(blini.__file__).resolve().parents[2] == Path(sys.argv[1]).resolve()",
        str(ROOT)], cwd=ROOT, env=child_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def setup(dev=False, reinstall=False):
    if not (3, 11) <= sys.version_info[:2] <= (3, 13):
        raise RuntimeError("Нужен Python 3.11, 3.12 или 3.13. Установите подходящую версию и повторите запуск.")
    if not (ROOT / "pyproject.toml").exists() or not (ROOT / "src" / "blini").exists():
        raise RuntimeError("Распакуйте весь ZIP. launch.py должен лежать рядом с pyproject.toml и папкой src.")
    fingerprint = hashlib.sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
    previous = {}
    if MARKER.exists():
        try:
            previous = json.loads(MARKER.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    matching = previous.get("fingerprint") == fingerprint and previous.get("root") == str(ROOT)
    if matching and (not dev or previous.get("dev")) and not reinstall and ready():
        print("Окружение готово. Запускаем приложение.", flush=True)
        return
    if not PYTHON.exists():
        print("Первый запуск: создаём окружение .venv в папке проекта…", flush=True)
        execute([sys.executable, "-m", "venv", ENVIRONMENT])
    print("Устанавливаем зависимости. На этом шаге нужен интернет; дождитесь завершения…", flush=True)
    execute([PYTHON, "-m", "pip", "install", "--disable-pip-version-check", "-e", ".[dev]" if dev else "."])
    if not ready():
        raise RuntimeError("Проверка зависимостей не прошла. Сохраните текст ошибки и повторите запуск с --reinstall.")
    MARKER.write_text(json.dumps({"fingerprint": fingerprint, "root": str(ROOT), "dev": dev}, ensure_ascii=False), encoding="utf-8")
    print("Установка завершена.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Установка и запуск проекта «Русские блины» из ZIP")
    parser.add_argument("--setup-only", action="store_true", help="Установить зависимости без открытия окна")
    parser.add_argument("--dev", action="store_true", help="Добавить pytest и Jupyter")
    parser.add_argument("--reinstall", action="store_true", help="Повторить установку зависимостей")
    parser.add_argument("--smoke-test", action="store_true", help="Проверить GUI и закрыть его автоматически")
    args = parser.parse_args(argv)
    try:
        setup(args.dev, args.reinstall)
        if args.setup_only:
            return 0
        env = os.environ.copy()
        if args.smoke_test:
            env.setdefault("QT_QPA_PLATFORM", "offscreen")
        command = [PYTHON, "-m", "blini.gui"]
        if args.smoke_test:
            command.append("--smoke-test")
        execute(command, env=env)
        return 0
    except (RuntimeError, OSError) as exc:
        print(f"\nНе удалось запустить приложение: {exc}", file=sys.stderr, flush=True)
        print("Инструкция: НАЧНИ_ЗДЕСЬ.md. При ошибке скачивания проверьте интернет и повторите start.bat.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
