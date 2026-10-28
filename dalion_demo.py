"""Native demo exchange UI. Run with python dalion_demo.py."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel,
                              QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget)

from core import LABELS, SCHEMAS, DataError, calculate
from dalion_exchange import DalionDemoAdapter, DemoServer, DemoWorkspace
from demo_scenarios import SCENARIOS,scenario_payload
from ui_theme import DataTable, configure_application


class FetchWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, endpoint, parent=None):
        super().__init__(parent)
        self.endpoint = endpoint

    def run(self):
        try:
            self.ready.emit(DalionDemoAdapter().fetch(self.endpoint))
        except Exception as exc:
            self.failed.emit(str(exc))


class DalionDemoDialog(QDialog):
    def __init__(self, parent=None, root=None):
        super().__init__(parent)
        self.setWindowTitle('КРОНА · Демо обмена с ДАЛИОН')
        self.resize(1080, 780)
        self.setMinimumSize(900, 680)
        self.server = DemoServer()
        self.server.__enter__()
        self.root = Path(root) if root is not None else Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'RusskieBliny-DalionDemo'
        self.workspace = None
        self.snapshot = None
        self.worker = None
        self.analysis_window = None
        self.imported_digest = None
        self.cleaned_up = False
        self.finished.connect(self.cleanup)
        box = QVBoxLayout(self)
        box.setContentsMargins(26, 24, 26, 24)
        box.setSpacing(16)
        title = QLabel('Демо обмена с ДАЛИОН'); title.setObjectName('title'); box.addWidget(title)
        notice = QLabel('СИНТЕТИЧЕСКИЕ ДАННЫЕ · Локальный имитатор 1С\n'
                        'Получите снимок, проверьте состав и откройте его в отдельной демо-базе.')
        notice.setObjectName('success'); notice.setWordWrap(True); box.addWidget(notice)
        self.endpoint = QLabel(self.server.endpoint); self.endpoint.setObjectName('subtitle'); box.addWidget(self.endpoint)
        self.scenario_choice=QComboBox()
        for key,(name,description) in SCENARIOS.items(): self.scenario_choice.addItem(name,key)
        box.addWidget(self.scenario_choice)
        self.scenario_description=QLabel(SCENARIOS['normal'][1]); self.scenario_description.setWordWrap(True); box.addWidget(self.scenario_description)
        self.scenario_choice.currentIndexChanged.connect(self.select_scenario)
        actions = QHBoxLayout()
        self.fetch_button = QPushButton('Получить демо-данные'); self.fetch_button.setObjectName('primary')
        self.fetch_button.clicked.connect(self.fetch); actions.addWidget(self.fetch_button)
        self.offline = QCheckBox('Имитировать отсутствие связи'); actions.addWidget(self.offline); actions.addStretch()
        self.update_button=QPushButton('Имитировать обновление'); self.update_button.setEnabled(False)
        self.update_button.clicked.connect(self.simulate_update); actions.addWidget(self.update_button)
        box.addLayout(actions)
        self.tabs = QTabWidget(); box.addWidget(self.tabs, 1)
        self.summary = DataTable(['Набор данных', 'Строк', 'Результат проверки'])
        self.tabs.addTab(self.summary, 'Состав снимка')
        self.sales = DataTable(['Дата', 'Блюдо', 'Порций', 'Наличие', 'Смена'])
        self.tabs.addTab(self.sales, 'Пример продаж')
        mapping = QTextEdit(); mapping.setReadOnly(True)
        from dalion_exchange import MAPPING
        mapping.setPlainText('Это придуманный демо-контракт, а не названия объектов реальной базы ДАЛИОН.\n\n' + '\n\n'.join(
            f'{external} → {kind}\n' + '\n'.join(f'  {source} → {target}' for source, target in zip(columns, SCHEMAS[kind]))
            for kind, (external, columns) in MAPPING.items()))
        self.tabs.addTab(mapping, 'Сопоставление полей')
        self.status = QLabel('Ожидается получение снимка. Восемь наборов будут проверены до записи.')
        self.status.setWordWrap(True); box.addWidget(self.status)
        self.location = QLabel('Демо-база ещё не создана. Рабочая база приложения не используется.')
        self.location.setWordWrap(True); self.location.setObjectName('subtitle'); box.addWidget(self.location)
        footer = QHBoxLayout()
        explanation = QLabel('Рецептуры, цены, пригодность и графики в этом примере вымышлены.\n'
                             'Обмен с настоящей 1С и отправка заявок не выполняются.')
        explanation.setWordWrap(True); explanation.setObjectName('subtitle'); footer.addWidget(explanation, 1)
        self.open_button = QPushButton('Открыть демо для анализа'); self.open_button.setEnabled(False)
        self.open_button.setObjectName('primary'); self.open_button.clicked.connect(self.open_analysis); footer.addWidget(self.open_button)
        box.addLayout(footer)

    def select_scenario(self):
        if self.worker is not None and self.worker.isRunning(): return
        if self.analysis_window is not None:
            self.analysis_window.day_timer.stop(); self.analysis_window.close(); self.analysis_window.deleteLater(); self.analysis_window=None
        if self.workspace is not None: self.workspace.close(); self.workspace=None
        self.imported_digest=None; self.snapshot=None
        self.open_button.setEnabled(False); self.update_button.setEnabled(False)
        key=self.scenario_choice.currentData()
        self.server.raw=json.dumps(scenario_payload(key),ensure_ascii=False).encode('utf-8')
        self.scenario_description.setText(SCENARIOS[key][1]+' Каждый запуск ситуации использует новую демо-базу.')
        self.summary.setRowCount(0); self.sales.setRowCount(0)
        self.location.setText('Предыдущая демо-база сохранена. Для этой ситуации будет создана новая.')
        self.status.setText('Выбрана ситуация. Нажмите «Получить демо-данные».')

    def simulate_update(self):
        payload=json.loads(self.server.raw)
        payload['data']['Партии'][0]['Количество']+=3
        payload['data']['Продажи'][-1]['Количество']+=2
        self.server.raw=json.dumps(payload,ensure_ascii=False).encode('utf-8')
        self.fetch()

    def fetch(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self.snapshot = None
        self.open_button.setEnabled(False)
        self.summary.setRowCount(0); self.sales.setRowCount(0)
        self.status.setText('Получение снимка и проверка связей, единиц и закрытых смен…')
        self.server.offline = self.offline.isChecked()
        self.fetch_button.setEnabled(False)
        self.scenario_choice.setEnabled(False); self.update_button.setEnabled(False)
        self.worker = FetchWorker(self.server.endpoint, self)
        self.worker.ready.connect(self.received)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(lambda: self.fetch_button.setEnabled(True))
        self.worker.finished.connect(lambda: self.scenario_choice.setEnabled(True))
        self.worker.finished.connect(lambda: self.update_button.setEnabled(self.workspace is not None))
        self.worker.start()

    def received(self, snapshot):
        from app import fill
        self.snapshot = snapshot
        fill(self.summary, [[LABELS[kind], len(snapshot.tables[kind]), 'Проверено · ДЕМО'] for kind in SCHEMAS])
        names = {row['id']: row['name'] for row in snapshot.tables['items']}
        rows = sorted(snapshot.tables['sales'], key=lambda row: row['date'], reverse=True)[:25]
        fill(self.sales, [[row['date'], names[row['dish']], row['qty'], 'Есть' if row['available'] else 'Не было', 'Закрыта'] for row in rows])
        self.status.setText(f'Снимок проверен. Продаж: {len(snapshot.tables["sales"])}; '
                            f'точек: {len(snapshot.tables["points"])}. Сформирован: {snapshot.generated_at[:19].replace("T", " ")}.')
        self.open_button.setEnabled(True)

    def failed(self, message):
        self.snapshot = None
        self.open_button.setEnabled(False)
        self.status.setText('Получение не выполнено. ' + message)

    def open_analysis(self):
        if self.snapshot is None:
            return
        try:
            from app import MainWindow
            if self.workspace is None:
                self.workspace = DemoWorkspace(self.root)
            if self.imported_digest != self.snapshot.digest:
                if self.workspace.store is None:
                    self.workspace.import_snapshot(self.snapshot)
                else:
                    from exchange_review import prepare_import
                    from operations_ui import ReviewImportDialog
                    plan=prepare_import(self.workspace.store,self.snapshot.tables,True,'Имитатор ДАЛИОН',self.snapshot.digest)
                    review=ReviewImportDialog(self.workspace.store,plan,'Демо обмена ДАЛИОН',self)
                    if review.exec()!=QDialog.DialogCode.Accepted: return
                    (self.workspace.directory/('source-'+self.snapshot.digest+'.json')).write_bytes(self.snapshot.raw)
                    if self.analysis_window is not None: self.analysis_window.reload()
                self.imported_digest = self.snapshot.digest
            if self.analysis_window is None:
                self.analysis_window = MainWindow(self.workspace.store)
                self.analysis_window.setWindowTitle('КРОНА · ДЕМО ДАЛИОН · Отдельная база')
            self.analysis_window.show(); self.analysis_window.raise_(); self.analysis_window.activateWindow()
            self.location.setText('Отдельная демо-база: ' + str(self.workspace.directory / 'data.sqlite3'))
            self.update_button.setEnabled(True)
            self.status.setText('Демо открыто. Можно проверить прогноз, остатки и заявку. Повторное открытие сохраняет ваши правки.')
        except (DataError, OSError, ValueError,sqlite3.Error) as exc:
            self.status.setText('Не удалось открыть демо: ' + str(exc))

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            self.status.setText('Дождитесь завершения получения снимка, затем закройте окно.')
            event.ignore()
            return
        super().closeEvent(event)

    def cleanup(self):
        if self.cleaned_up:
            return
        self.cleaned_up = True
        if self.analysis_window is not None:
            self.analysis_window.day_timer.stop()
            self.analysis_window.close()
            self.analysis_window.deleteLater()
        if self.workspace is not None:
            self.workspace.close()
        self.server.__exit__()

    def reject(self):
        if self.worker is not None and self.worker.isRunning():
            self.status.setText('Дождитесь завершения получения снимка, затем закройте окно.')
            return
        super().reject()


def main():
    parser = argparse.ArgumentParser(description='Демонстрационный обмен с локальным имитатором ДАЛИОН')
    parser.add_argument('--demo-root', type=Path, help='Родительская папка новых изолированных демо-баз')
    parser.add_argument('--smoke', type=Path, help='Сохранить снимки интерфейса и результат проверки')
    args = parser.parse_args()
    application = QApplication(sys.argv); configure_application(application)
    dialog = DalionDemoDialog(root=args.demo_root); dialog.show()
    if args.smoke:
        args.smoke.mkdir(parents=True, exist_ok=True)

        def capture(snapshot):
            try:
                application.processEvents()
                dialog.grab().save(str(args.smoke / 'exchange.png'))
                dialog.open_analysis()
                if dialog.analysis_window is None:
                    raise RuntimeError(dialog.status.text())
                window = dialog.analysis_window
                window._make_order()
                assert not window.current['errors'], window.current['errors']
                application.processEvents(); window.grab().save(str(args.smoke / 'analysis.png'))
                result = calculate(dialog.workspace.store.get('tables'), 'central', date.today(), {})
                (args.smoke / 'result.json').write_text(json.dumps({
                    'status': 'PASS', 'synthetic': True, 'sales': len(snapshot.tables['sales']),
                    'forecast_dishes': len(result['forecasts']), 'order_rows': len(result['rows']),
                    'data_dir': str(dialog.workspace.directory),
                }, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception:
                import traceback
                (args.smoke / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
                application.exit(1)
                return
            # The worker may still be finishing when its result signal is delivered.
            QTimer.singleShot(100, dialog.close)

        def start():
            dialog.fetch()
            dialog.worker.ready.connect(capture)
        QTimer.singleShot(0, start)
        QTimer.singleShot(15000, lambda: application.exit(1))
    return application.exec()


if __name__ == '__main__':
    sys.exit(main())
