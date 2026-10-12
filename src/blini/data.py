"""Контракт CSV и проверка данных. Все даты — локальные календарные даты, без времени."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

SCHEMAS = {
    "sales": ["date", "store_id", "dish_id", "quantity"],
    "dishes": ["dish_id", "name", "introduced_on"],
    "ingredients": ["ingredient_id", "name", "base_unit"],
    "recipes": ["dish_id", "ingredient_id", "quantity", "unit"],
    "stock": ["lot_id", "store_id", "ingredient_id", "quantity", "unit", "expires_on"],
    "deliveries": ["delivery_id", "ingredient_id", "store_id", "quantity", "unit", "arrival_date", "expires_on"],
    "purchase_params": ["store_id", "ingredient_id", "lead_days", "review_days", "pack_size", "min_order", "unit", "shelf_life_days"],
    "calendar": ["date", "store_id", "is_open"],
}
KEYS = {
    "sales": ["date", "store_id", "dish_id"], "dishes": ["dish_id"],
    "ingredients": ["ingredient_id"], "recipes": ["dish_id", "ingredient_id"],
    "stock": ["lot_id"], "deliveries": ["delivery_id"],
    "purchase_params": ["store_id", "ingredient_id"], "calendar": ["date", "store_id"],
}
DATES = {"sales": ["date"], "dishes": ["introduced_on"], "stock": ["expires_on"],
         "deliveries": ["arrival_date", "expires_on"], "calendar": ["date"]}
NUMBERS = {"sales": ["quantity"], "recipes": ["quantity"], "stock": ["quantity"],
           "deliveries": ["quantity"], "purchase_params": ["lead_days", "review_days", "pack_size", "min_order", "shelf_life_days"], "calendar": ["is_open"]}
# Явное преобразование при импорте. Произвольные единицы не допускаются.
UNITS = {"kg": ("kg", 1.0), "g": ("kg", 0.001), "l": ("l", 1.0),
         "ml": ("l", 0.001), "pcs": ("pcs", 1.0)}


@dataclass
class ValidationResult:
    tables: dict[str, pd.DataFrame]
    errors: list[str]
    warnings: list[str]

    def require_valid(self):
        if self.errors:
            raise ValueError("Ошибки данных:\n" + "\n".join(self.errors))
        return self.tables


def load_csv_directory(directory: str | Path) -> dict[str, pd.DataFrame]:
    """Читает восемь CSV в UTF-8 (BOM допустим), разделитель — запятая, десятичная точка.

    Возвращает сырые таблицы. Отсутствующий файл даёт пустую таблицу без колонок,
    чтобы validate_data мог перечислить сразу все ошибки.
    """
    root = Path(directory)
    result = {}
    for name in SCHEMAS:
        path = root / f"{name}.csv"
        try:
            result[name] = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame()
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as exc:
            raise ValueError(f"{path.name}: проверьте UTF-8 и структуру CSV: {exc}") from exc
    return result


def validate_data(raw: dict[str, pd.DataFrame], as_of: str | pd.Timestamp) -> ValidationResult:
    """Проверяет ссылки, даты, числа, дубликаты, календарь и единицы.

    Возвращает копии с датами Timestamp, числовыми значениями и базовыми единицами.
    Пропущенные продажи НЕ превращает в нули. as_of — дата конца истории/снимка склада.
    """
    cutoff = pd.Timestamp(as_of).normalize()
    tables, errors, warnings = {}, [], []
    for name, columns in SCHEMAS.items():
        df = raw.get(name, pd.DataFrame()).copy()
        missing = sorted(set(columns) - set(df.columns))
        if missing:
            errors.append(f"{name}.csv: добавьте колонки {', '.join(missing)}")
            continue
        df = df[columns]
        for col in columns:
            if df[col].isna().any() or df[col].astype(str).str.strip().eq("").any():
                errors.append(f"{name}.{col}: заполните пустые значения")
            if col not in DATES.get(name, []) and col not in NUMBERS.get(name, []):
                df[col] = df[col].astype(str).str.strip()
        for col in DATES.get(name, []):
            parsed = pd.to_datetime(df[col], errors="coerce", format="%Y-%m-%d")
            if parsed.isna().any():
                errors.append(f"{name}.{col}: даты должны быть в формате YYYY-MM-DD")
            df[col] = parsed
        for col in NUMBERS.get(name, []):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
            if (~np.isfinite(df[col].astype(float))).any() or df[col].lt(0).any():
                errors.append(f"{name}.{col}: нужны конечные неотрицательные числа")
        if df.duplicated(KEYS[name]).any():
            example = df.loc[df.duplicated(KEYS[name], keep=False), KEYS[name]].head(3).to_dict("records")
            errors.append(f"{name}: устраните дубликаты ключей {KEYS[name]}: {example}")
        tables[name] = df
    if errors:
        return ValidationResult(tables, errors, warnings)
    for required in ("dishes", "ingredients", "recipes", "purchase_params", "calendar"):
        if tables[required].empty:
            errors.append(f"{required}.csv: таблица не должна быть пустой")
    ingredients = tables["ingredients"].set_index("ingredient_id")["base_unit"].to_dict()
    dish_ids = set(tables["dishes"]["dish_id"])
    store_ids = set(tables["calendar"]["store_id"])
    if not set(ingredients.values()) <= {"kg", "l", "pcs"}:
        errors.append("ingredients.base_unit: используйте только kg, l, pcs")
    for name, df in tables.items():
        for col, allowed in (("dish_id", dish_ids), ("ingredient_id", set(ingredients)), ("store_id", store_ids)):
            if col in df and name not in ("dishes", "ingredients", "calendar"):
                unknown = set(df[col]) - allowed
                if unknown:
                    errors.append(f"{name}.{col}: отсутствуют справочные записи {sorted(unknown)}")
        if "unit" in df:
            for idx, row in df.iterrows():
                spec = UNITS.get(row.unit)
                base = ingredients.get(row.ingredient_id)
                if not spec or spec[0] != base:
                    errors.append(f"{name}, строка {idx + 2}: единица {row.unit} несовместима с {base}; укажите явную единицу kg/g, l/ml или pcs")
                else:
                    for field in (["pack_size", "min_order"] if name == "purchase_params" else ["quantity"]):
                        df.at[idx, field] = float(row[field]) * spec[1]
                    df.at[idx, "unit"] = base
    params = tables["purchase_params"]
    for col in ("lead_days", "review_days", "shelf_life_days"):
        if (params[col] % 1 != 0).any():
            errors.append(f"purchase_params.{col}: нужны целые дни")
    if params["pack_size"].le(0).any() or params["review_days"].le(0).any() or params["shelf_life_days"].le(0).any():
        errors.append("purchase_params: pack_size, review_days и shelf_life_days должны быть больше нуля")
    cal = tables["calendar"]
    if not cal.is_open.isin([0, 1]).all():
        errors.append("calendar.is_open: допустимы только 0 (закрыто) и 1 (открыто)")
    if (tables["deliveries"].expires_on < tables["deliveries"].arrival_date).any():
        errors.append("deliveries: срок годности не может быть раньше поступления")
    if tables["deliveries"].arrival_date.le(cutoff).any():
        errors.append("deliveries: поставки до/на дату снимка должны быть перенесены в stock, либо исправьте дату ожидаемого поступления")
    if tables["stock"].expires_on.le(cutoff).any():
        warnings.append("В stock есть партии, которые уже просрочены или истекут до первого дня плана; они не покроют потребность.")
    if tables["sales"].date.gt(cutoff).any():
        warnings.append("Продажи после даты расчёта исключены из прогноза и проверки методов.")
    sales = tables["sales"].merge(cal, on=["date", "store_id"], how="left")
    if sales.is_open.isna().any():
        errors.append("sales: для каждой даты и точки добавьте запись в calendar")
    if ((sales.is_open == 0) & (sales.quantity > 0)).any():
        errors.append("sales: положительные продажи в закрытые дни — исправьте продажи или calendar")
    intro = tables["dishes"].set_index("dish_id").introduced_on
    if (sales.date < sales.dish_id.map(intro)).any():
        errors.append("sales: продажа раньше introduced_on; исправьте дату появления блюда")
    missing_recipes = dish_ids - set(tables["recipes"].dish_id)
    if missing_recipes:
        errors.append(f"recipes: добавьте рецептуры для {sorted(missing_recipes)}")
    used = set(tables["recipes"].ingredient_id) | set(tables["stock"].ingredient_id) | set(tables["deliveries"].ingredient_id)
    param_keys = set(zip(params.store_id, params.ingredient_id))
    for store in sorted(store_ids):
        for ingredient in sorted(used):
            if (store, ingredient) not in param_keys:
                errors.append(f"purchase_params: добавьте параметры для {store}/{ingredient}")
        history = cal[(cal.store_id == store) & (cal.date <= cutoff)]
        if not history.empty:
            expected_dates = pd.date_range(history.date.min(), cutoff)
            if len(set(expected_dates) - set(history.date)):
                errors.append(f"calendar: заполните все исторические дни для {store}, включая закрытые")
            known = tables["sales"][(tables["sales"].store_id == store) & (tables["sales"].date <= cutoff)]
            for dish, start in intro.items():
                expected = set(history.loc[(history.is_open == 1) & (history.date >= start), "date"])
                absent = expected - set(known.loc[known.dish_id == dish, "date"])
                if absent:
                    warnings.append(f"sales {store}/{dish}: {len(absent)} открытых дней без данных; отсутствие записи не считается нулём.")
    warnings.append("Нет сведений об отсутствии товара: наблюдаемые продажи могут быть ниже реального спроса. Данные о потерянных продажах нужны для коррекции.")
    return ValidationResult(tables, errors, warnings)
