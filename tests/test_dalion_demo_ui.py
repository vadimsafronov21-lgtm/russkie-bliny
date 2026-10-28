import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QElapsedTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import MainWindow
from core import Store
from dalion_demo import DalionDemoDialog
from ui_theme import configure_application
from tests.ui_helpers import business_dump


@pytest.fixture(scope='module')
def application():
    app = QApplication.instance() or QApplication([])
    configure_application(app)
    return app


def wait_fetch(dialog, application):
    timer = QElapsedTimer(); timer.start()
    while dialog.worker.isRunning() and timer.elapsed() < 5000:
        application.processEvents(); QTest.qWait(10)
    application.processEvents()
    assert not dialog.worker.isRunning()


def test_preview_offline_retry_and_analysis_are_isolated(tmp_path, application):
    production = Store(tmp_path / 'production.sqlite3'); production.seed()
    parent = MainWindow(production)
    before = business_dump(production)
    dialog = DalionDemoDialog(parent, root=tmp_path / 'demos'); dialog.show()
    try:
        assert not dialog.open_button.isEnabled()
        dialog.fetch(); wait_fetch(dialog, application)
        assert dialog.summary.rowCount() == 8 and dialog.sales.rowCount() == 25
        assert dialog.open_button.isEnabled() and dialog.workspace is None
        dialog.open_analysis(); application.processEvents()
        assert dialog.analysis_window.isVisible()
        assert dialog.workspace.store.get('demo')
        assert 'ДЕМО ДАЛИОН' in dialog.analysis_window.windowTitle()
        dialog.analysis_window._make_order()
        assert not dialog.analysis_window.current['errors']
        dialog.workspace.store.correct_batch('b0', 8, True, 'Ручная сверка', 'Тест')
        revision = dialog.workspace.store.get('revision')
        dialog.offline.setChecked(True); dialog.fetch(); wait_fetch(dialog, application)
        assert dialog.snapshot is None and not dialog.open_button.isEnabled()
        assert 'недоступен' in dialog.status.text()
        dialog.offline.setChecked(False); dialog.fetch(); wait_fetch(dialog, application)
        dialog.open_analysis()
        assert dialog.workspace.store.get('revision') == revision
        assert business_dump(production) == before
    finally:
        dialog.close(); parent.day_timer.stop(); parent.close(); production.db.close()
        application.processEvents()


def test_escape_closes_server_and_database(tmp_path, application):
    dialog = DalionDemoDialog(root=tmp_path); dialog.show()
    dialog.fetch(); wait_fetch(dialog, application); dialog.open_analysis()
    dialog.reject(); application.processEvents()
    assert dialog.cleaned_up and dialog.workspace.store is None
    assert not dialog.server.thread.is_alive()


def test_main_window_entry_reuses_dialog_and_closes_resources(tmp_path, application, monkeypatch):
    import dalion_demo
    from types import SimpleNamespace
    monkeypatch.setattr(dalion_demo, 'DalionDemoDialog', lambda parent: DalionDemoDialog(parent, root=tmp_path / 'demos'))
    store = Store(tmp_path / 'main.sqlite3'); store.seed()
    parent = MainWindow(store); parent.show()
    try:
        parent.open_dalion_demo(); dialog = parent.dalion_demo_dialog
        parent.open_dalion_demo()
        assert parent.dalion_demo_dialog is dialog
        dialog.worker = SimpleNamespace(isRunning=lambda: True)
        assert not parent.close()
        assert parent.isVisible() and dialog.isVisible()
        dialog.worker = None
        assert parent.close()
        application.processEvents()
        assert dialog.cleaned_up and not dialog.server.thread.is_alive()
    finally:
        dialog.worker = None; dialog.close(); parent.day_timer.stop(); parent.close(); store.db.close()
