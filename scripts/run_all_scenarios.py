"""Сохраняет полный путь от учебных CSV до отчётов по шести сценариям."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from blini.config import Config
from blini.demo import AS_OF, SCENARIOS
from blini.data import load_csv_directory
from blini.repository import save_dataset, load_dataset
from blini.service import run_pipeline

ROOT = Path(__file__).resolve().parents[1]


def main():
    summaries, reports = [], {}
    config = Config.load(ROOT / "config" / "default.json")
    for scenario in SCENARIOS:
        raw = load_csv_directory(ROOT / "data" / "demo" / scenario)
        report = run_pipeline(raw, AS_OF, config)
        report.export(ROOT / "reports" / scenario)
        reports[scenario] = report
        summaries.append({"scenario": scenario, "forecast_rows": len(report.forecast),
                          "recommendations": len(report.recommendations),
                          "early_shortage_ingredients": int(report.recommendations.early_shortage.fillna(0).gt(0).sum()),
                          "attention_ingredients": int(report.recommendations.status.ne("ok").sum()),
                          "fallback_dishes": report.forecast.loc[report.forecast.method.str.contains("fallback"), "dish_id"].nunique()})
    summary = pd.DataFrame(summaries)
    summary.to_csv(ROOT / "reports" / "summary.csv", index=False, encoding="utf-8-sig")
    # Сквозная проверка: CSV -> SQLite -> тот же конвейер -> равенство результатов.
    raw = load_csv_directory(ROOT / "data" / "demo" / "normal")
    save_dataset(ROOT / "runtime" / "blini.sqlite", raw, AS_OF)
    loaded, as_of = load_dataset(ROOT / "runtime" / "blini.sqlite")
    from_database = run_pipeline(loaded, as_of, config)
    pd.testing.assert_frame_equal(reports["normal"].recommendations, from_database.recommendations)
    from_database.export(ROOT / "reports" / "from-db")
    fig, ax = plt.subplots(figsize=(10, 4), layout="constrained")
    for scenario, label in (("normal", "Обычная работа"), ("weekend_growth", "Рост в выходные")):
        daily = reports[scenario].forecast.groupby("date").quantity.sum()
        ax.plot(daily.index, daily.values, "o-", label=label)
    ax.set_ylabel("Прогноз, порции за день"); ax.grid(alpha=.2); ax.legend(); fig.autofmt_xdate()
    fig.savefig(ROOT / "reports" / "forecast_comparison.png", dpi=140)
    plt.close(fig)
    row = reports["shortage"].recommendations.set_index("ingredient_id").loc["I01"]
    lines = ["# Демонстрация прототипа", "", "Все данные синтетические. Снимок: 30.09.2026; прогноз: 01–07.10.2026.", "",
             "| Сценарий | Строк прогноза | Рекомендаций | Ингредиентов с ранним дефицитом | Резервных блюд |", "|---|---:|---:|---:|---:|"]
    for item in summaries:
        lines.append(f"| {item['scenario']} | {item['forecast_rows']} | {item['recommendations']} | {item['early_shortage_ingredients']} | {item['fallback_dishes']} |")
    lines.extend(["", "## Пример объяснения: нехватка муки", "", row.explanation, "", row.warning, "",
                  "В каталогах сценариев сохранены входы расчёта, метрики, дневные ошибки, потребность, закупки и журнал baseline/with_order.",
                  "CSV → SQLite → расчёт проверен: рекомендации совпадают. График сравнения: forecast_comparison.png."])
    (ROOT / "reports" / "demo_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(summary.to_string(index=False))
    print("SQLite roundtrip OK; all scenario reports saved")


if __name__ == "__main__":
    main()
