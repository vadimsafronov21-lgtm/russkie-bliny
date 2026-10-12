"""Минимальный PySide6-интерфейс. Все вычисления выполняет service в QThread."""
import argparse
import json
from pathlib import Path
import sys
import os
import pandas as pd
from PySide6.QtCore import Qt, QThread, Signal, QDate, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QDateEdit, QFileDialog, QTabWidget, QTableWidget,
    QTableWidgetItem, QPlainTextEdit, QMessageBox, QSplitter, QHeaderView)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from .config import Config
from .data import SCHEMAS, load_csv_directory, validate_data
from .demo import AS_OF, SCENARIOS, generate_demo
from .repository import save_dataset, load_dataset
from .service import run_pipeline

ROOT = Path(__file__).resolve().parents[2]
HEADERS = {"date": "Дата", "store_id": "Точка", "dish_id": "Блюдо ID", "ingredient_id": "Ингредиент ID",
 "quantity": "Количество", "name": "Название", "base_unit": "Базовая единица", "unit": "Ед.",
 "introduced_on": "Введено", "lot_id": "Партия", "expires_on": "Годен до (вкл.)", "arrival_date": "Поступление",
 "is_open": "Открыто", "lead_days": "Поставка, дней", "review_days": "Пересмотр, дней", "pack_size": "Упаковка",
 "min_order": "Минимум", "shelf_life_days": "Годность, дней", "method": "Метод", "explanation": "Объяснение",
 "ingredient": "Ингредиент", "order_quantity": "Заказать", "forecast_demand": "Потребность L+R", "usable_stock": "Пригодный остаток",
 "scheduled_deliveries": "Поставки L+R", "safety_stock": "Страховой запас", "early_shortage": "Ранний дефицит",
 "warning": "Предупреждение", "status": "Статус", "order_date": "Разместить заказ", "order_by_date": "Крайний срок",
 "protection_end": "Конец L+R", "mae": "MAE, порции", "wape": "WAPE, доля", "n": "Наблюдений", "folds": "Отрезков",
 "demand": "Потребность", "arrivals": "Поступило", "expired": "Истекло без расхода", "consumed": "Расход",
 "shortage": "Дефицит", "remaining": "Остаток", "scenario": "Модель", "available_before": "Доступно до расхода"}
SCENARIO_LABELS = ["Обычная работа", "Рост спроса в выходные", "Нехватка муки", "Истечение срока молока", "Задержка поставки мяса", "Короткая история блюда"]
TABLE_LABELS = ["Продажи", "Блюда", "Ингредиенты", "Рецептуры", "Партии склада", "Ожидаемые поставки", "Параметры закупки", "Календарь"]
VALUES = {"status": {"ok": "В норме", "attention": "Проверьте", "needs_data": "Нужны данные"},
          "scenario": {"baseline": "Без заказа", "with_order": "С заказом"},
          "unit": {"kg": "кг", "l": "л", "pcs": "шт"},
          "base_unit": {"kg": "кг", "l": "л", "pcs": "шт"}}


def fill_table(widget: QTableWidget, df: pd.DataFrame):
    widget.clear()
    widget.setRowCount(len(df))
    widget.setColumnCount(len(df.columns))
    widget.setHorizontalHeaderLabels([HEADERS.get(c, c) for c in df.columns])
    for r, values in enumerate(df.itertuples(index=False, name=None)):
        for c, value in enumerate(values):
            if pd.isna(value):
                text = "не определено"
            elif isinstance(value, pd.Timestamp):
                text = str(value.date())
            elif isinstance(value, float):
                text = f"{value:.3f}"
            else:
                text = str(value)
            text = VALUES.get(df.columns[c], {}).get(text, text)
            widget.setItem(r, c, QTableWidgetItem(text))
    widget.resizeColumnsToContents()
    for c in range(len(df.columns)):
        if widget.columnWidth(c) > 320:
            widget.setColumnWidth(c, 320)


def make_table():
    table = QTableWidget()
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().hide()
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    return table


class Calculation(QThread):
    completed = Signal(object, object, str)
    failed = Signal(str)

    def __init__(self, raw, as_of, db, config):
        super().__init__()
        self.raw, self.as_of, self.db, self.config = raw, as_of, db, config

    def run(self):
        try:
            report = run_pipeline(self.raw, self.as_of, self.config)
            save_dataset(self.db, self.raw, self.as_of)
            tables = validate_data(self.raw, self.as_of).require_valid()
            self.completed.emit(report, tables, self.as_of)
        except Exception as exc:
            self.failed.emit(str(exc))


class Window(QMainWindow):
    def __init__(self, smoke=False):
        super().__init__()
        self.smoke = smoke
        self.db = ROOT / "runtime" / "blini.sqlite"
        self.report, self.tables, self.worker = None, {}, None
        self.setWindowTitle("Русские блины • прогноз спроса и запасы • учебный прототип")
        self.resize(1320, 850)
        body = QWidget()
        layout = QVBoxLayout(body)
        title = QLabel("Русские блины  /  Спрос и закупки")
        title.setStyleSheet("font-size:25px; font-weight:600; color:#234239; padding:8px;")
        layout.addWidget(title)
        notice = QLabel("УЧЕБНЫЙ ПРОТОТИП · синтетические данные · расчёт по снимку на конец выбранного дня")
        notice.setStyleSheet("color:#71643d; padding:4px 8px;")
        layout.addWidget(notice)
        toolbar = QHBoxLayout()
        self.scenario = QComboBox()
        self.scenario.addItems(SCENARIO_LABELS)
        self.date = QDateEdit(QDate.fromString(AS_OF, "yyyy-MM-dd"))
        self.date.setDisplayFormat("yyyy-MM-dd")
        self.date.setCalendarPopup(True)
        self.demo_button = QPushButton("Открыть учебный сценарий")
        self.load_button = QPushButton("Загрузить папку CSV")
        self.db_button = QPushButton("Открыть сохранённый склад")
        self.export_button = QPushButton("Экспорт CSV")
        self.export_button.setEnabled(False)
        for widget in (self.scenario, self.demo_button, QLabel("Снимок:"), self.date, self.load_button, self.db_button, self.export_button):
            toolbar.addWidget(widget)
        layout.addLayout(toolbar)
        self.status = QLabel("Выберите учебный сценарий или папку с восемью CSV.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        data_page, data_layout = self.page("Данные")
        self.table_choice = QComboBox()
        self.table_choice.addItems(TABLE_LABELS)
        self.data_table = make_table()
        data_layout.addWidget(self.table_choice)
        data_layout.addWidget(self.data_table)
        forecast_page, forecast_layout = self.page("Прогноз 7 дней")
        filter_row = QHBoxLayout()
        self.store_choice, self.dish_choice = QComboBox(), QComboBox()
        filter_row.addWidget(QLabel("Точка:")); filter_row.addWidget(self.store_choice)
        filter_row.addWidget(QLabel("Блюдо:")); filter_row.addWidget(self.dish_choice); filter_row.addStretch()
        forecast_layout.addLayout(filter_row)
        self.figure = Figure(figsize=(9, 3), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.forecast_table = make_table()
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.canvas); split.addWidget(self.forecast_table)
        forecast_layout.addWidget(split)
        _, score_layout = self.page("Проверка методов")
        score_layout.addWidget(QLabel("Последовательные недельные отрезки. Выбор по MAE на общих наблюдениях. WAPE — доля; при нулевом факте не определён."))
        self.score_table = make_table(); score_layout.addWidget(self.score_table)
        _, stock_layout = self.page("Склад")
        stock_layout.addWidget(QLabel("Партии снимка. Годность включительно; просроченные партии не участвуют в расходе."))
        self.stock_table = make_table(); stock_layout.addWidget(self.stock_table)
        _, order_layout = self.page("Закупки")
        order_layout.addWidget(QLabel("Выберите строку для объяснения. Страховой запас — упрощённый процент потребности. L+R может превышать 7 дней."))
        self.order_table, self.details = make_table(), QPlainTextEdit()
        self.details.setReadOnly(True)
        split = QSplitter(Qt.Orientation.Vertical); split.addWidget(self.order_table); split.addWidget(self.details)
        order_layout.addWidget(split)
        _, log_layout = self.page("Дневной расход")
        self.log_table = make_table(); log_layout.addWidget(self.log_table)
        self.messages = QPlainTextEdit()
        self.messages.setReadOnly(True); self.messages.setMaximumHeight(105)
        layout.addWidget(self.messages)
        self.setCentralWidget(body)
        self.demo_button.clicked.connect(self.load_demo)
        self.load_button.clicked.connect(self.load_csv)
        self.db_button.clicked.connect(self.load_db)
        self.export_button.clicked.connect(self.export)
        self.table_choice.currentIndexChanged.connect(self.show_data)
        self.store_choice.currentIndexChanged.connect(self.show_forecast)
        self.dish_choice.currentIndexChanged.connect(self.show_forecast)
        self.order_table.itemSelectionChanged.connect(self.show_recommendation)
        self.setStyleSheet("QMainWindow { background:#f5f6f2; } QPushButton { padding:8px; } QTabWidget::pane { border:1px solid #d3dbd5; } QTableWidget { background:white; alternate-background-color:#f0f5f1; } QHeaderView::section { background:#e0ece4; padding:6px; border:0; }")
        if smoke:
            QTimer.singleShot(100, self.load_demo)
            QTimer.singleShot(120000, lambda: QApplication.exit(3))

    def page(self, name):
        widget = QWidget(); layout = QVBoxLayout(widget)
        self.tabs.addTab(widget, name)
        return widget, layout

    def busy(self, value):
        for widget in (self.load_button, self.db_button, self.demo_button, self.scenario, self.date):
            widget.setEnabled(not value)
        self.export_button.setEnabled(not value and self.report is not None)

    def calculate(self, raw, as_of):
        if self.worker and self.worker.isRunning():
            return
        self.busy(True)
        self.status.setText("Проверка CSV, сравнение прогнозов и дневное моделирование FEFO…")
        self.worker = Calculation(raw, as_of, self.db, Config.load(ROOT / "config" / "default.json"))
        self.worker.completed.connect(self.calculated)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(lambda: self.busy(False))
        self.worker.start()

    def load_demo(self):
        try:
            path = ROOT / "data" / "demo" / SCENARIOS[self.scenario.currentIndex()]
            if not path.exists():
                generate_demo(ROOT / "data" / "demo")
            self.date.setDate(QDate.fromString(AS_OF, "yyyy-MM-dd"))
            self.calculate(load_csv_directory(path), AS_OF)
        except Exception as exc:
            self.failed(str(exc))

    def load_csv(self):
        path = QFileDialog.getExistingDirectory(self, "Папка с восемью CSV", str(ROOT / "data"))
        if not path:
            return
        try:
            metadata = Path(path) / "dataset.json"
            if metadata.exists():
                value = json.loads(metadata.read_text(encoding="utf-8"))["as_of"]
                self.date.setDate(QDate.fromString(value, "yyyy-MM-dd"))
            self.calculate(load_csv_directory(path), self.date.date().toString("yyyy-MM-dd"))
        except Exception as exc:
            self.failed(str(exc))

    def load_db(self):
        try:
            raw, as_of = load_dataset(self.db)
            self.date.setDate(QDate.fromString(as_of, "yyyy-MM-dd"))
            self.calculate(raw, as_of)
        except Exception as exc:
            self.failed(str(exc))

    def calculated(self, report, tables, as_of):
        self.report, self.tables = report, tables
        self.dish_choice.blockSignals(True); self.store_choice.blockSignals(True)
        self.dish_choice.clear(); self.store_choice.clear()
        for dish in tables["dishes"].itertuples():
            self.dish_choice.addItem(dish.name, dish.dish_id)
        self.store_choice.addItems(sorted(tables["calendar"].store_id.unique()))
        self.dish_choice.blockSignals(False); self.store_choice.blockSignals(False)
        self.show_data(); self.show_forecast()
        fill_table(self.score_table, report.metrics)
        stocks = tables["stock"].merge(tables["ingredients"][["ingredient_id", "name"]], on="ingredient_id")
        stocks["status"] = stocks.expires_on.apply(lambda date: "просрочено" if date < pd.Timestamp(as_of)+pd.Timedelta(days=1) else "скоро истечёт" if date <= pd.Timestamp(as_of)+pd.Timedelta(days=2) else "годно")
        fill_table(self.stock_table, stocks)
        order_cols = ["store_id", "ingredient", "unit", "order_quantity", "order_date", "order_by_date", "arrival_date", "forecast_demand", "usable_stock", "scheduled_deliveries", "safety_stock", "early_shortage", "status"]
        fill_table(self.order_table, report.recommendations.reindex(columns=order_cols))
        log_cols = ["date", "store_id", "ingredient_id", "scenario", "demand", "arrivals", "expired", "consumed", "shortage", "remaining"]
        fill_table(self.log_table, report.inventory_log.reindex(columns=log_cols))
        self.messages.setPlainText("\n".join(report.warnings))
        count = int(report.recommendations.order_quantity.fillna(0).gt(0).sum())
        attention = int(report.recommendations.status.ne("ok").sum())
        self.status.setText(f"Снимок {as_of} · прогноз {len(report.forecast)} строк · {count} закупок · {attention} рекомендаций требуют внимания · SQLite сохранён")
        self.export_button.setEnabled(True)
        self.tabs.setCurrentIndex(4)
        self.order_table.selectRow(0)
        if self.smoke:
            QTimer.singleShot(200, self.finish_smoke)

    def finish_smoke(self):
        if self.worker and self.worker.isRunning():
            QTimer.singleShot(100, self.finish_smoke)
            return
        directory = ROOT / "reports" / "gui-smoke"
        self.report.export(directory)
        self.grab().save(str(directory / "gui.png"))
        print(f"GUI smoke OK: {len(self.report.forecast)} forecast rows, {len(self.report.recommendations)} recommendations", flush=True)
        QApplication.exit(0)

    def failed(self, message):
        self.status.setText("Ошибка загрузки/расчёта; предыдущий успешный результат сохранён.")
        self.messages.setPlainText(message)
        if self.smoke:
            print(message, file=sys.stderr, flush=True)
            if self.worker and self.worker.isRunning():
                self.worker.wait()
            QApplication.exit(2)
        else:
            QMessageBox.warning(self, "Исправьте данные", message)

    def show_data(self):
        name = list(SCHEMAS)[self.table_choice.currentIndex()]
        if name in self.tables:
            fill_table(self.data_table, self.tables[name].head(500))

    def show_forecast(self):
        if self.report is None:
            return
        dish, store = self.dish_choice.currentData(), self.store_choice.currentText()
        forecast = self.report.forecast[(self.report.forecast.dish_id == dish) & (self.report.forecast.store_id == store)]
        fill_table(self.forecast_table, forecast)
        history = self.tables["sales"][(self.tables["sales"].dish_id == dish) & (self.tables["sales"].store_id == store)]
        history = history[history.date < forecast.date.min()].sort_values("date").tail(28)
        self.figure.clear(); ax = self.figure.add_subplot(111)
        ax.plot(history.date, history.quantity, color="#527766", label="Факт (известные продажи)")
        ax.plot(forecast.date, forecast.quantity, "o--", color="#b07829", label="Прогноз")
        ax.set_ylabel("Порции"); ax.grid(alpha=.2); ax.legend(); self.figure.autofmt_xdate()
        self.canvas.draw()

    def show_recommendation(self):
        if self.report is None or self.order_table.currentRow() < 0:
            return
        row = self.report.recommendations.iloc[self.order_table.currentRow()]
        self.details.setPlainText(str(row.explanation) + "\n\n" + str(row.warning))

    def export(self):
        path = QFileDialog.getExistingDirectory(self, "Папка экспорта", str(ROOT / "reports"))
        if path:
            try:
                self.report.export(path)
                self.status.setText(f"CSV экспортированы в {path}")
            except OSError as exc:
                self.failed(str(exc))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.status.setText("Дождитесь завершения расчёта, затем закройте окно.")
            event.ignore()
        else:
            event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true", help="Автоматический запуск GUI, расчёт и снимок экрана")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    # offscreen-платформа Qt в Windows может не обнаружить системные шрифты.
    # Подключаем файл явно: кириллица и числа должны читаться и в smoke-снимке.
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
    if font_path.exists():
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            app.setFont(QFont(families[0], 10))
    else:
        app.setFont(QFont("DejaVu Sans", 10))
    window = Window(args.smoke_test); window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
