"""Создание учебного ноутбука из читаемых ячеек; расчёты находятся в blini."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
cells = []


def md(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)})


def code(text):
    cells.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": text.splitlines(keepends=True)})


md("""# Русские блины: рабочее место аналитика

**Учебные синтетические данные, не данные заказчика.** Одна точка, десять блюд,
шесть месяцев. Снимок на конец 30.09.2026; прогноз 01–07.10.2026.
Все прогнозы, проверки и закупки вызывают функции пакета `blini`.
Изменяйте основной модуль, а затем запускайте ноутбук заново.
""")
code("""from pathlib import Path
import sys
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display

ROOT = Path.cwd()
if not (ROOT / 'src' / 'blini').exists():
    ROOT = ROOT.parent
assert (ROOT / 'src' / 'blini').exists(), 'Откройте ноутбук из корня проекта или notebooks/'
sys.path.insert(0, str(ROOT / 'src'))
from blini.config import Config
from blini.data import load_csv_directory, validate_data
from blini.demo import AS_OF, SCENARIOS, generate_demo
from blini.service import run_pipeline
from blini.inventory import ingredient_demand

if not (ROOT / 'data' / 'demo' / 'normal').exists():
    generate_demo(ROOT / 'data' / 'demo')
config = Config.load(ROOT / 'config' / 'default.json')
raw = load_csv_directory(ROOT / 'data' / 'demo' / 'normal')
""")
md("""## 1. Проверка загрузки

Ошибки блокируют расчёт. Предупреждения о пропущенных продажах и отсутствии
сведений о стоп-листах нужно проверить отдельно. Отсутствующий факт не равен нулю.
""")
code("""validation = validate_data(raw, AS_OF)
print('Ошибки:', validation.errors)
print('Предупреждения:')
for warning in validation.warnings:
    print('-', warning)
tables = validation.require_valid()
display(pd.DataFrame({'table': list(tables), 'rows': [len(df) for df in tables.values()]}))
display(tables['recipes'].head())
""")
md("""## 2. Продажи по дням недели

Сравним обычный режим и специально усиленные выходные. Группировка здесь —
исследование фактов; прогноз далее рассчитывается только основным модулем.
""")
code("""fig, ax = plt.subplots(figsize=(10, 4))
for scenario, label in [('normal', 'Обычная работа'), ('weekend_growth', 'Рост в выходные')]:
    source = validate_data(load_csv_directory(ROOT / 'data' / 'demo' / scenario), AS_OF).require_valid()
    daily = source['sales'].groupby('date').quantity.sum()
    by_weekday = daily.groupby(daily.index.dayofweek).mean().reindex(range(7))
    ax.plot(range(7), by_weekday, 'o-', label=label)
ax.set_xticks(range(7), ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'])
ax.set_ylabel('Средние порции за открытый день'); ax.legend(); ax.grid(alpha=.2)
plt.show()
""")
md("""## 3. Сравнение алгоритмов и выбранный прогноз

Три последовательных недельных блока; обучение каждого блока только до origin.
MAE — в порциях, WAPE — доля, NaN при нулевом знаменателе. Методы сравниваются
на одинаковом наборе известных дат, покрытие отражено в n и folds.
Выбор по pooled MAE; эти же отрезки не являются независимым финальным тестом.
""")
code("""report = run_pipeline(raw, AS_OF, config)
display(report.metrics.sort_values(['dish_id', 'mae']))
display(report.forecast[['dish_id', 'method', 'explanation']].drop_duplicates())
dish_id = 'D01'
history = tables['sales'].query('dish_id == @dish_id').set_index('date').quantity.tail(28)
prediction = report.forecast.query('dish_id == @dish_id').set_index('date').quantity
fig, ax = plt.subplots(figsize=(11, 4))
ax.plot(history.index, history, label='Факт')
ax.plot(prediction.index, prediction, 'o--', label='Прогноз')
ax.set_ylabel('Порции'); ax.legend(); ax.grid(alpha=.2); fig.autofmt_xdate()
plt.show()
""")
md("""## 4. Дневные ошибки и даты обучения

Выгрузка ошибок позволяет проверить origin, календарный контрольный блок и
отсутствие будущих фактов в обучении. eligible=False исключён из выбора.
""")
code("""errors = report.errors
assert (errors.origin < errors.date).all()
display(errors.sort_values('absolute_error', ascending=False).head(15))
display(errors.groupby(['method', 'origin']).agg(n=('eligible', 'sum'), mae=('absolute_error', 'mean')))
fig, ax = plt.subplots(figsize=(10, 4))
for method, group in errors.query('dish_id == @dish_id and eligible').groupby('method'):
    ax.plot(group.date, group.absolute_error, 'o-', label=method)
ax.set_ylabel('Абсолютная ошибка, порции'); ax.legend(); fig.autofmt_xdate()
plt.show()
""")
md("""## 5. Одно блюдо и его ингредиенты

Проверяем пересчёт порций на ингредиенты **основной функцией**. Закупки общих
ингредиентов ниже рассчитаны на все блюда: вклад одного блюда показан отдельно,
его нельзя ошибочно считать всей потребностью точки.
""")
code("""one_forecast = report.forecast.query('dish_id == @dish_id')
one_recipe = tables['recipes'].query('dish_id == @dish_id')
display(one_recipe.merge(tables['ingredients'], on='ingredient_id'))
one_demand = ingredient_demand(one_forecast, one_recipe)
display(one_demand)
ingredient_ids = one_recipe.ingredient_id.tolist()
display(report.demand.query('ingredient_id in @ingredient_ids'))
display(report.recommendations.query('ingredient_id in @ingredient_ids')[
    ['ingredient', 'unit', 'forecast_demand', 'usable_stock', 'scheduled_deliveries',
     'safety_stock', 'order_quantity', 'order_date', 'arrival_date', 'warning']])
for row in report.recommendations.query('ingredient_id in @ingredient_ids').itertuples():
    print('\\n', row.ingredient, ':', row.explanation)
    if row.warning: print('ВНИМАНИЕ:', row.warning)
display(report.inventory_log.query("ingredient_id == 'I01'"))
""")
md("""## 6. Проверка шести сценариев

Ранний дефицит до прихода партии не покрывается поздним заказом. Истекающие
партии исключаются по дням. Короткая история использует подписанный fallback.
""")
code("""summary = []
for scenario in SCENARIOS:
    current = run_pipeline(load_csv_directory(ROOT / 'data' / 'demo' / scenario), AS_OF, config)
    summary.append({'scenario': scenario,
                    'orders': int(current.recommendations.order_quantity.fillna(0).gt(0).sum()),
                    'early_shortage_ingredients': int(current.recommendations.early_shortage.fillna(0).gt(0).sum()),
                    'attention': int(current.recommendations.status.ne('ok').sum()),
                    'fallback_dishes': current.forecast.loc[current.forecast.method.str.contains('fallback'), 'dish_id'].nunique()})
display(pd.DataFrame(summary))
short = run_pipeline(load_csv_directory(ROOT / 'data' / 'demo' / 'short_history'), AS_OF, config)
display(short.forecast.query("dish_id == 'D10'")[['date', 'quantity', 'method', 'explanation']])
""")
md("""## 7. Дальнейшая работа

- Новые методы: `src/blini/forecast.py`, реестр METHODS.
- Общие параметры: `config/default.json` и dataclass Config.
- Страховой запас: `inventory.safety_stock`; текущая доля — упрощённое правило.
- Политика закупки: `inventory.recommend_orders`, проверка FEFO: `simulate`.
- Контракты функций: docstring модулей и `docs/analytics.md`.

Прежде чем использовать реальные закупки, согласуйте единицы, технологические
потери, календарь поставщиков, стоп-листы и допустимый риск списаний.
""")

for i, cell in enumerate(cells):
    cell["id"] = f"blini-{i:03}"
notebook = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3 (blini .venv)", "language": "python", "name": "python3"},
           "language_info": {"name": "python", "version": "3.13"}}, "nbformat": 4, "nbformat_minor": 5}
(ROOT / "notebooks" / "analysis.ipynb").write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
print("Created notebooks/analysis.ipynb")
