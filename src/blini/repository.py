"""SQLite-адаптер; расчётный модуль не импортирует этот файл.

Импорт всех таблиц атомарный: невалидные CSV не меняют прежний снимок.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import pandas as pd
from .data import SCHEMAS, validate_data

DDL = """
CREATE TABLE IF NOT EXISTS stores (store_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS dishes (dish_id TEXT PRIMARY KEY, name TEXT NOT NULL, introduced_on TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ingredients (ingredient_id TEXT PRIMARY KEY, name TEXT NOT NULL, base_unit TEXT NOT NULL CHECK(base_unit IN ('kg','l','pcs')));
CREATE TABLE IF NOT EXISTS sales (date TEXT NOT NULL, store_id TEXT REFERENCES stores(store_id), dish_id TEXT REFERENCES dishes(dish_id), quantity REAL NOT NULL CHECK(quantity>=0), PRIMARY KEY(date,store_id,dish_id));
CREATE TABLE IF NOT EXISTS recipes (dish_id TEXT REFERENCES dishes(dish_id), ingredient_id TEXT REFERENCES ingredients(ingredient_id), quantity REAL NOT NULL CHECK(quantity>=0), unit TEXT NOT NULL, PRIMARY KEY(dish_id,ingredient_id));
CREATE TABLE IF NOT EXISTS stock (lot_id TEXT PRIMARY KEY, store_id TEXT REFERENCES stores(store_id), ingredient_id TEXT REFERENCES ingredients(ingredient_id), quantity REAL NOT NULL CHECK(quantity>=0), unit TEXT NOT NULL, expires_on TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deliveries (delivery_id TEXT PRIMARY KEY, ingredient_id TEXT REFERENCES ingredients(ingredient_id), store_id TEXT REFERENCES stores(store_id), quantity REAL NOT NULL CHECK(quantity>=0), unit TEXT NOT NULL, arrival_date TEXT NOT NULL, expires_on TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS purchase_params (store_id TEXT REFERENCES stores(store_id), ingredient_id TEXT REFERENCES ingredients(ingredient_id), lead_days INTEGER NOT NULL CHECK(lead_days>=0), review_days INTEGER NOT NULL CHECK(review_days>0), pack_size REAL NOT NULL CHECK(pack_size>0), min_order REAL NOT NULL CHECK(min_order>=0), unit TEXT NOT NULL, shelf_life_days INTEGER NOT NULL CHECK(shelf_life_days>0), PRIMARY KEY(store_id,ingredient_id));
CREATE TABLE IF NOT EXISTS calendar (date TEXT NOT NULL, store_id TEXT REFERENCES stores(store_id), is_open INTEGER NOT NULL CHECK(is_open IN (0,1)), PRIMARY KEY(date,store_id));
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
ORDER = ["dishes", "ingredients", "calendar", "sales", "recipes", "stock", "deliveries", "purchase_params"]


def connect(path: str | Path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(DDL)
    return connection


def save_dataset(path: str | Path, raw: dict[str, pd.DataFrame], as_of: str) -> list[str]:
    """Проверка и транзакционная замена снимка CSV; возвращает предупреждения."""
    check = validate_data(raw, as_of)
    tables = check.require_valid()
    with closing(connect(path)) as conn, conn:
        for name in reversed(ORDER):
            conn.execute(f'DELETE FROM "{name}"')
        conn.execute("DELETE FROM stores")
        conn.executemany("INSERT INTO stores VALUES (?)", [(s,) for s in sorted(set(tables["calendar"].store_id))])
        for name in ORDER:
            df = tables[name].copy()
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    df[col] = df[col].dt.strftime("%Y-%m-%d")
            fields = ",".join(f'"{col}"' for col in SCHEMAS[name])
            marks = ",".join("?" for _ in SCHEMAS[name])
            conn.executemany(f'INSERT INTO "{name}" ({fields}) VALUES ({marks})', df.itertuples(index=False, name=None))
        conn.execute("INSERT OR REPLACE INTO metadata VALUES ('as_of', ?)", (str(pd.Timestamp(as_of).date()),))
    return check.warnings


def load_dataset(path: str | Path) -> tuple[dict[str, pd.DataFrame], str]:
    """Снимок восьми таблиц и дата снимка; выход совместим с run_pipeline."""
    if not Path(path).exists():
        raise ValueError("База ещё не создана. Сначала загрузите папку CSV.")
    with closing(connect(path)) as conn:
        date = conn.execute("SELECT value FROM metadata WHERE key='as_of'").fetchone()
        if date is None:
            raise ValueError("В базе нет импортированного снимка")
        return {name: pd.read_sql_query(f'SELECT * FROM "{name}"', conn) for name in SCHEMAS}, date[0]
