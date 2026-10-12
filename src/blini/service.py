"""Оркестрация чистых функций. Единственный путь расчёта для CLI, GUI и ноутбука."""
from dataclasses import dataclass
from pathlib import Path
import pandas as pd
from .config import Config
from .data import validate_data, load_csv_directory
from .forecast import forecast_sales
from .inventory import ingredient_demand, recommend_orders


@dataclass
class Report:
    forecast: pd.DataFrame
    planning_forecast: pd.DataFrame
    metrics: pd.DataFrame
    errors: pd.DataFrame
    demand: pd.DataFrame
    recommendations: pd.DataFrame
    inventory_log: pd.DataFrame
    warnings: list[str]

    def export(self, directory: str | Path):
        """Экспорт всех результатов в CSV и предупреждений в текстовый файл."""
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        for name in ("forecast", "planning_forecast", "metrics", "errors", "demand", "recommendations", "inventory_log"):
            getattr(self, name).to_csv(root / f"{name}.csv", index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
        (root / "warnings.txt").write_text("\n".join(self.warnings), encoding="utf-8")


def run_pipeline(raw: dict[str, pd.DataFrame], as_of: str, config: Config | None = None) -> Report:
    """Сырые восемь таблиц + конец завершённого дня -> проверенный Report.

    Снимок stock должен соответствовать as_of. При ошибках ValueError до расчётов.
    План расширяется до L+R, если закупкам нужно больше семи дней.
    """
    config = config or Config()
    validation = validate_data(raw, as_of)
    tables = validation.require_valid()
    horizon = max(config.horizon_days, int((tables["purchase_params"].lead_days + tables["purchase_params"].review_days).max()))
    if horizon > config.max_plan_days:
        raise ValueError(f"Период L+R={horizon} больше max_plan_days={config.max_plan_days}; согласуйте параметры")
    forecast, scores, errors = forecast_sales(tables, as_of, horizon, config)
    demand = ingredient_demand(forecast, tables["recipes"])
    recommendations, logs = recommend_orders(demand, tables, as_of, config)
    warnings = list(validation.warnings)
    if horizon > config.horizon_days:
        warnings.append(f"Для закупок прогноз расширен до {horizon} дней (L+R); это увеличивает неопределённость.")
    if forecast.method.str.contains("fallback|no_history").any():
        warnings.append("Есть блюда с резервным прогнозом или без истории; проверьте explanation в forecast.")
    cutoff = pd.Timestamp(as_of) + pd.Timedelta(days=config.horizon_days)
    return Report(forecast[forecast.date <= cutoff].copy(), forecast, scores, errors, demand, recommendations, logs, warnings)


def run_directory(directory: str | Path, as_of: str, config: Config | None = None) -> Report:
    """Удобная точка входа для папки CSV; не обращается к базе данных."""
    return run_pipeline(load_csv_directory(directory), as_of, config)
