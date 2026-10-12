"""Критические расчёты проверяются на вручную понятных примерах, без GUI."""
import numpy as np
import pandas as pd
import pytest
from blini.config import Config
from blini.data import validate_data, load_csv_directory
from blini.demo import generate_demo, AS_OF, SCENARIOS
from blini.forecast import seasonal_naive, weekday_mean, backtest, metrics, forecast_sales, METHODS
from blini.inventory import ingredient_demand, simulate, recommend_orders, round_order
from blini.repository import save_dataset, load_dataset
from blini.service import run_pipeline


@pytest.fixture(scope="module")
def datasets(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo") / "demo"
    generate_demo(root)
    return {name: load_csv_directory(root / name) for name in SCENARIOS}


def test_portions_to_ingredients_and_unknown():
    forecast = pd.DataFrame({"date": [pd.Timestamp("2026-10-01")]*2, "store_id": ["S"]*2,
                             "dish_id": ["A", "B"], "quantity": [10., 20.]})
    recipes = pd.DataFrame({"dish_id": ["A", "B"], "ingredient_id": ["F", "F"], "quantity": [.05, .1]})
    assert ingredient_demand(forecast, recipes).quantity.iloc[0] == pytest.approx(2.5)
    forecast.loc[0, "quantity"] = np.nan
    assert np.isnan(ingredient_demand(forecast, recipes).quantity.iloc[0])


def stock(rows):
    return pd.DataFrame(rows, columns=["lot_id", "quantity", "expires_on"]).assign(expires_on=lambda df: pd.to_datetime(df.expires_on))


def deliveries(rows=()):
    return pd.DataFrame(rows, columns=["delivery_id", "quantity", "arrival_date", "expires_on"]).assign(
        arrival_date=lambda df: pd.to_datetime(df.arrival_date), expires_on=lambda df: pd.to_datetime(df.expires_on))


def test_fefo_expired_and_expiry_inclusive():
    demand = pd.Series([3., 3.], index=pd.date_range("2026-10-01", periods=2))
    original = stock([("late", 5., "2026-10-10"), ("early", 2., "2026-10-01"), ("bad", 100., "2026-09-30")])
    log, lots = simulate(demand, original, deliveries())
    assert log.expired.tolist() == [100., 0.]
    assert log.shortage.sum() == 0
    assert {r["id"]: r["quantity"] for r in lots} == {"late": 1., "early": 0., "bad": 0.}
    assert original.quantity.sum() == 107.  # Чистая функция не меняет вход.


def test_delivery_not_available_before_arrival_and_zero_lead():
    demand = pd.Series([4., 4.], index=pd.date_range("2026-10-01", periods=2))
    log, _ = simulate(demand, stock([]), deliveries([("d", 8., "2026-10-02", "2026-10-05")]))
    assert log.shortage.tolist() == [4., 0.]
    assert log.remaining.tolist() == [0., 4.]
    immediate, _ = simulate(demand, stock([]), deliveries(), {"quantity": 8., "arrival_date": demand.index[0], "expires_on": demand.index[-1]})
    assert immediate.shortage.sum() == 0


@pytest.mark.parametrize("need,pack,minimum,expected", [(0, 5, 20, 0), (-2, 5, 20, 0), (6, 5, 0, 10), (2, 5, 12, 15), (.3, .1, 0, .3)])
def test_package_rounding(need, pack, minimum, expected):
    assert round_order(need, pack, minimum) == pytest.approx(expected)


def test_metrics_zero_and_missing():
    assert metrics([0, 0], [1, 0]) == {"mae": .5, "wape": None, "n": 2}
    assert metrics([2, np.nan], [1, 5]) == {"mae": 1., "wape": .5, "n": 1}


def test_exact_previous_week_and_mean():
    dates = pd.date_range("2026-07-01", periods=42)
    history = pd.Series(np.arange(42, dtype=float), index=dates)
    future = pd.date_range(dates[-1]+pd.Timedelta(days=1), periods=7)
    config = Config(weekday_mean_weeks=2)
    assert seasonal_naive(history, future, config).tolist() == list(np.arange(35, 42))
    assert weekday_mean(history, future, config).tolist() == list(np.arange(31.5, 38.5))


def test_missing_weekday_is_not_zero():
    dates = pd.date_range("2026-07-01", periods=14)
    history = pd.Series(10., index=dates)
    history.iloc[-7] = np.nan
    next_day = pd.DatetimeIndex([dates[-1]+pd.Timedelta(days=1)])
    assert np.isnan(seasonal_naive(history, next_day, Config()).iloc[0])


def test_backtest_passes_only_past_and_fold_boundaries(monkeypatch):
    seen = []
    original = METHODS["weekday_mean"]
    def spy(history, dates, config):
        assert history.index.max() < dates.min()
        seen.append(history.index.max())
        return original(history, dates, config)
    monkeypatch.setitem(METHODS, "weekday_mean", spy)
    history = pd.Series(10., index=pd.date_range("2026-07-01", periods=70))
    scores, errors = backtest(history, Config())
    assert len(set(seen)) == 3
    assert (errors.origin < errors.date).all()
    assert scores.n.tolist() == [21, 21]


def test_future_sales_do_not_change_forecast(datasets):
    raw = {k: v.copy() for k, v in datasets["normal"].items()}
    original = run_pipeline(raw, AS_OF)
    future = raw["sales"].tail(10).copy()
    future["date"], future["quantity"] = "2026-10-01", "9999999"
    raw["sales"] = pd.concat([raw["sales"], future], ignore_index=True)
    altered = run_pipeline(raw, AS_OF)
    pd.testing.assert_frame_equal(original.forecast, altered.forecast)
    pd.testing.assert_frame_equal(original.metrics, altered.metrics)


def test_explicit_units_and_mismatch(datasets):
    raw = {k: v.copy() for k, v in datasets["normal"].items()}
    idx = raw["recipes"].index[0]
    raw["recipes"].loc[idx, ["quantity", "unit"]] = ["45", "g"]
    result = validate_data(raw, AS_OF)
    assert not result.errors
    assert result.tables["recipes"].loc[idx, "quantity"] == pytest.approx(.045)
    raw["recipes"].loc[idx, "unit"] = "ml"
    assert any("несовместима" in e for e in validate_data(raw, AS_OF).errors)


@pytest.mark.parametrize("case", ["negative", "duplicate", "reference", "missing", "bad_date", "infinite", "calendar_gap", "fractional_lead", "closed_sale", "late_expiry", "past_delivery"])
def test_validation_errors(datasets, case):
    raw = {k: v.copy() for k, v in datasets["normal"].items()}
    if case == "negative": raw["sales"].loc[0, "quantity"] = "-1"
    elif case == "duplicate": raw["sales"] = pd.concat([raw["sales"], raw["sales"].head(1)], ignore_index=True)
    elif case == "reference": raw["sales"].loc[0, "dish_id"] = "unknown"
    elif case == "missing": raw["stock"].loc[0, "quantity"] = ""
    elif case == "bad_date": raw["sales"].loc[0, "date"] = "wrong"
    elif case == "infinite": raw["sales"].loc[0, "quantity"] = "inf"
    elif case == "calendar_gap": raw["calendar"] = raw["calendar"].drop(index=4)
    elif case == "fractional_lead": raw["purchase_params"].loc[0, "lead_days"] = "1.5"
    elif case == "closed_sale": raw["calendar"].loc[0, "is_open"] = "0"
    elif case == "late_expiry": raw["deliveries"].loc[0, "expires_on"] = "2026-10-01"
    elif case == "past_delivery": raw["deliveries"].loc[0, "arrival_date"] = AS_OF
    assert validate_data(raw, AS_OF).errors


def test_missing_sale_warns_without_imputing_zero(datasets):
    raw = {k: v.copy() for k, v in datasets["normal"].items()}
    raw["sales"] = raw["sales"].drop(index=0)
    result = validate_data(raw, AS_OF)
    assert not result.errors
    assert any("без данных" in w for w in result.warnings)
    assert len(result.tables["sales"]) == len(datasets["normal"]["sales"])-1


def test_short_history_and_new_dish(datasets):
    raw = {k: v.copy() for k, v in datasets["short_history"].items()}
    report = run_pipeline(raw, AS_OF)
    assert set(report.forecast.loc[report.forecast.dish_id == "D10", "method"]) == {"fallback_mean"}
    raw["sales"] = raw["sales"][raw["sales"].dish_id != "D10"]
    new = run_pipeline(raw, AS_OF)
    assert new.forecast.loc[new.forecast.dish_id == "D10", "quantity"].isna().all()
    assert new.recommendations.loc[new.recommendations.ingredient_id == "I13", "status"].iloc[0] == "needs_data"
    assert np.isnan(new.recommendations.loc[new.recommendations.ingredient_id == "I13", "order_quantity"].iloc[0])


def test_closed_days_force_zero(datasets):
    raw = {k: v.copy() for k, v in datasets["normal"].items()}
    raw["calendar"].loc[raw["calendar"].date == "2026-10-01", "is_open"] = "0"
    report = run_pipeline(raw, AS_OF)
    assert report.forecast.loc[report.forecast.date == "2026-10-01", "quantity"].sum() == 0


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_end_to_end_scenarios(datasets, scenario):
    report = run_pipeline(datasets[scenario], AS_OF)
    assert len(report.forecast) == 70
    assert len(report.recommendations) == 13
    assert report.recommendations.order_quantity.ge(0).all()
    assert report.inventory_log.remaining.ge(-1e-9).all()
    assert np.allclose(report.recommendations.order_quantity / report.recommendations.pack_size,
                       (report.recommendations.order_quantity / report.recommendations.pack_size).round())
    if scenario == "shortage": assert report.recommendations.early_shortage.max() > 0
    if scenario == "expiry": assert report.inventory_log.expired.sum() > 20
    if scenario == "delayed_delivery":
        row = report.recommendations.set_index("ingredient_id").loc["I06"]
        assert row.scheduled_deliveries == 0
    if scenario == "weekend_growth":
        daily = report.forecast.groupby("date").quantity.sum()
        assert daily[daily.index.dayofweek >= 5].mean() > daily[daily.index.dayofweek < 5].mean()*1.4


def test_sqlite_roundtrip_and_invalid_import_preserves_snapshot(datasets, tmp_path):
    path = tmp_path / "snapshot.sqlite"
    raw = datasets["normal"]
    save_dataset(path, raw, AS_OF)
    loaded, as_of = load_dataset(path)
    a, b = run_pipeline(raw, AS_OF), run_pipeline(loaded, as_of)
    pd.testing.assert_frame_equal(a.forecast, b.forecast)
    pd.testing.assert_frame_equal(a.recommendations, b.recommendations)
    invalid = {k: v.copy() for k, v in raw.items()}
    invalid["sales"].loc[0, "quantity"] = "-5"
    with pytest.raises(ValueError): save_dataset(path, invalid, AS_OF)
    after, _ = load_dataset(path)
    pd.testing.assert_frame_equal(after["sales"], loaded["sales"])


def test_short_shelf_life_warns_about_uncovered_demand_and_waste(datasets):
    raw = {k: v.copy() for k, v in datasets["shortage"].items()}
    raw["purchase_params"].loc[raw["purchase_params"].ingredient_id == "I01", "shelf_life_days"] = "1"
    report = run_pipeline(raw, AS_OF)
    row = report.recommendations.set_index("ingredient_id").loc["I01"]
    assert row.order_waste_risk > 0
    assert row.uncovered_after_arrival > 0
    assert "Одна партия" in row.warning


def test_extended_plan_and_missing_future_calendar(datasets):
    raw = {k: v.copy() for k, v in datasets["normal"].items()}
    raw["purchase_params"].loc[0, "review_days"] = "10"
    report = run_pipeline(raw, AS_OF)
    assert report.planning_forecast.date.nunique() == 12
    assert report.forecast.date.nunique() == 7
    raw["calendar"] = raw["calendar"][raw["calendar"].date <= "2026-10-07"]
    with pytest.raises(ValueError, match="calendar"):
        run_pipeline(raw, AS_OF)


def test_manual_order_formula_excludes_early_lost_demand():
    dates = pd.date_range("2026-10-01", periods=5)
    demand = pd.DataFrame({"date": dates, "store_id": "S", "ingredient_id": "F", "quantity": 1.})
    tables = {
        "ingredients": pd.DataFrame([{"ingredient_id": "F", "name": "Мука", "base_unit": "kg"}]),
        "purchase_params": pd.DataFrame([{"store_id": "S", "ingredient_id": "F", "lead_days": 2,
            "review_days": 3, "pack_size": 3., "min_order": 0., "unit": "kg", "shelf_life_days": 10}]),
        "stock": stock([]).assign(store_id=pd.Series(dtype=str), ingredient_id=pd.Series(dtype=str)),
        "deliveries": deliveries().assign(store_id=pd.Series(dtype=str), ingredient_id=pd.Series(dtype=str)),
    }
    recommendations, logs = recommend_orders(demand, tables, "2026-09-30", Config(safety_pct=.2))
    row = recommendations.iloc[0]
    assert row.forecast_demand == 5
    assert row.early_shortage == 2
    assert row.late_shortage == 3
    assert row.safety_stock == 1
    assert row.raw_order == 4  # Поздний дефицит 3 + буфер 1, ранние 2 не докупаются.
    assert row.order_quantity == 6  # Упаковка 3.
    assert row.arrival_date == pd.Timestamp("2026-10-03")
    assert row.order_by_date == pd.Timestamp("2026-09-29")
    assert row.uncovered_after_arrival == 0
    assert logs.query("scenario == 'with_order'").shortage.sum() == 2
