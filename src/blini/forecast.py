"""Прогноз по одной паре точка/блюдо и последовательная проверка без будущих данных.

Аналитик добавляет функцию в METHODS. Функция принимает историю (Series с DatetimeIndex),
даты прогноза, Config; возвращает Series на этих датах. NaN означает «нет оценки»,
а не нулевой спрос. Все алгоритмы используют только историю <= origin.
"""
from collections.abc import Callable
import numpy as np
import pandas as pd
from .config import Config


def seasonal_naive(history: pd.Series, dates: pd.DatetimeIndex, config: Config) -> pd.Series:
    """Для первой недели — ровно D-7; для дальнейшего плана повторяет последнюю неделю.

    Если нужное наблюдение отсутствует, результат NaN. Закрытые дни представлены NaN.
    """
    if history.empty:
        return pd.Series(np.nan, index=dates, dtype=float)
    origin = history.index.max()
    values = []
    for date in dates:
        reference = date - pd.Timedelta(days=7)
        while reference > origin:
            reference -= pd.Timedelta(days=7)
        values.append(history.get(reference, np.nan))
    return pd.Series(values, index=dates, dtype=float)


def weekday_mean(history: pd.Series, dates: pd.DatetimeIndex, config: Config) -> pd.Series:
    """Среднее известного спроса по дню недели в последних N календарных неделях."""
    if history.empty:
        return pd.Series(np.nan, index=dates, dtype=float)
    recent = history[history.index > history.index.max() - pd.Timedelta(weeks=config.weekday_mean_weeks)]
    means = recent.groupby(recent.index.dayofweek).mean()
    return pd.Series([means.get(d.dayofweek, np.nan) for d in dates], index=dates, dtype=float)


METHODS: dict[str, Callable] = {"seasonal_naive": seasonal_naive, "weekday_mean": weekday_mean}


def metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    """MAE в порциях, WAPE в долях; WAPE=None при нулевой сумме фактов.

    NaN-пары исключаются. n сообщает, сколько наблюдений реально проверено.
    """
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    valid = np.isfinite(actual) & np.isfinite(predicted)
    actual, predicted = actual[valid], predicted[valid]
    if not len(actual):
        return {"mae": None, "wape": None, "n": 0}
    error = np.abs(actual - predicted)
    total = actual.sum()
    return {"mae": float(error.mean()), "wape": float(error.sum() / total) if total > 0 else None, "n": len(actual)}


def backtest(history: pd.Series, config: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Несколько последовательных блоков перед концом истории, без перемешивания.

    Каждый метод получает отдельную копию train <= origin. Сравнение происходит
    на общих известных фактах и прогнозах всех методов. Возвращает метрики и ошибки
    (origin, date, method, actual, predicted, absolute_error, eligible).
    """
    rows = []
    if history.empty:
        return pd.DataFrame(), pd.DataFrame()
    end = history.index.max()
    for fold in range(config.backtest_folds, 0, -1):
        origin = end - pd.Timedelta(days=fold * config.backtest_days)
        train = history.loc[history.index <= origin]
        if train.dropna().empty or (origin - train.dropna().index.min()).days + 1 < config.min_training_days:
            continue
        dates = pd.date_range(origin + pd.Timedelta(days=1), periods=config.backtest_days)
        actual = history.reindex(dates)
        predictions = {name: func(train.copy(), dates, config).reindex(dates) for name, func in METHODS.items()}
        common = actual.notna()
        for prediction in predictions.values():
            common &= prediction.notna()
        for method, prediction in predictions.items():
            for date in dates:
                a, p = actual.loc[date], prediction.loc[date]
                rows.append({"origin": origin, "date": date, "method": method, "actual": a,
                             "predicted": p, "absolute_error": abs(a-p), "eligible": bool(common.loc[date])})
    errors = pd.DataFrame(rows)
    summaries = []
    if not errors.empty:
        for method, group in errors.groupby("method"):
            paired = group[group.eligible]
            summaries.append({"method": method, **metrics(paired.actual.values, paired.predicted.values),
                              "folds": paired.origin.nunique()})
    return pd.DataFrame(summaries), errors


def forecast_sales(tables: dict[str, pd.DataFrame], as_of: str | pd.Timestamp,
                   horizon: int, config: Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Возвращает прогноз по дню/точке/блюду, сводку backtest и ошибки.

    cutoff — последний завершённый день. Наблюдения позже него исключаются.
    Прогноз содержит quantity, method, explanation; закрытые дни имеют 0.
    Новое блюдо без данных получает NaN и явное объяснение.
    """
    cutoff = pd.Timestamp(as_of).normalize()
    dates = pd.date_range(cutoff + pd.Timedelta(days=1), periods=horizon)
    all_forecasts, all_scores, all_errors = [], [], []
    sales = tables["sales"][tables["sales"].date <= cutoff]
    cal = tables["calendar"]
    for store in sorted(cal.store_id.unique()):
        store_cal = cal[cal.store_id == store].set_index("date").is_open
        if not dates.isin(store_cal.index).all():
            raise ValueError(f"calendar: добавьте дни плана до {dates[-1].date()} для точки {store}")
        for dish in tables["dishes"].itertuples(index=False):
            observed = sales[(sales.store_id == store) & (sales.dish_id == dish.dish_id)].set_index("date").quantity.astype(float)
            start = max(dish.introduced_on, store_cal.index.min())
            history_dates = pd.date_range(start, cutoff) if start <= cutoff else pd.DatetimeIndex([])
            history = observed.reindex(history_dates)
            open_history = store_cal.reindex(history_dates).eq(1)
            history.loc[~open_history] = np.nan
            scores, errors = backtest(history, config)
            for frame, destination in ((scores, all_scores), (errors, all_errors)):
                if not frame.empty:
                    frame["store_id"], frame["dish_id"] = store, dish.dish_id
                    destination.append(frame)
            viable = scores[scores.n >= config.min_eval_points].sort_values(["mae", "method"]) if not scores.empty else pd.DataFrame()
            known = history.dropna()
            if known.empty:
                method, reason = "no_history", "Нет истории: прогноз неизвестен; задайте экспертный спрос и проверьте его отдельно."
                prediction = pd.Series(np.nan, index=dates)
            elif viable.empty:
                method = "fallback_mean"
                sample = known.tail(config.fallback_observations)
                prediction = pd.Series(float(sample.mean()), index=dates)
                reason = f"Недостаточно проверки: среднее последних {len(sample)} известных открытых дней. Сезонность не подтверждена."
            else:
                selected = viable.iloc[0]
                method = selected.method
                prediction = METHODS[method](history.copy(), dates, config).reindex(dates)
                reason = f"Минимальный MAE={selected.mae:.3f} на {int(selected.n)} общих наблюдениях, {int(selected.folds)} отрезках."
                missing = prediction.isna()
                if missing.any():
                    prediction.loc[missing] = float(known.tail(config.fallback_observations).mean())
                    reason += " Для отсутствующих дней применено резервное среднее."
                    method += "+fallback"
            for date in dates:
                closed = store_cal.loc[date] == 0 or date < dish.introduced_on
                value = 0.0 if closed else prediction.loc[date]
                if pd.notna(value) and (not np.isfinite(value) or value < 0):
                    raise ValueError(f"Алгоритм {method} вернул отрицательное/бесконечное значение")
                all_forecasts.append({"date": date, "store_id": store, "dish_id": dish.dish_id,
                                      "quantity": value, "method": "closed" if closed else method,
                                      "explanation": "Точка закрыта или блюдо ещё не введено" if closed else reason})
    return (pd.DataFrame(all_forecasts), pd.concat(all_scores, ignore_index=True) if all_scores else pd.DataFrame(),
            pd.concat(all_errors, ignore_index=True) if all_errors else pd.DataFrame())
