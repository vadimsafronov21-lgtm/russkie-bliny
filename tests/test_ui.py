import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import MainWindow,configure_application
from core import Store

@pytest.fixture(scope='session')
def application():
    application=QApplication.instance() or QApplication([])
    configure_application(application)
    return application

def test_recalculation_keeps_manual_edits_and_offline_draft(tmp_path,application):
    store=Store(tmp_path/'ui.sqlite3'); store.seed()
    window=MainWindow(store); window._make_order()
    window.current['edits']={'dough':{'packs':0,'reason':'Проверка','author':'Тест','at':'2026-10-20T10:00:00+07:00'}}
    window.save_current(); window.offline.setChecked(True)
    store.correct_batch('b0',10,True,'Пересчет','Тест'); window.reload(); window._make_order()
    assert window.current['edits']['dough']['packs']==0
    assert window.current['rows'][0]['packs']>0
    assert not window.stock_check.isChecked()
    window.stock_check.setChecked(True)
    assert store.get('draft:central')['stock_confirmed']
    window.close(); store.db.close()

def test_seller_filters_forecast_tabs_and_confirmation(tmp_path,application):
    store=Store(tmp_path/'navigation.sqlite3'); store.seed()
    window=MainWindow(store); window.show(); application.processEvents()
    QTest.mouseClick(window.stock_tabs[1],Qt.MouseButton.LeftButton)
    assert window.stock_table.rowCount()==sum(r['packs']>0 for r in window.snapshot['rows'])
    window.search.setText('Икра')
    assert window.stock_table.rowCount()==0
    QTest.mouseClick(window.stock_tabs[0],Qt.MouseButton.LeftButton)
    assert window.stock_table.rowCount()==1
    window.search.clear(); window._make_order(); application.processEvents()
    assert not window.confirm_btn.isEnabled()
    QTest.mouseClick(window.stock_check,Qt.MouseButton.LeftButton)
    assert window.confirm_btn.isEnabled()
    QTest.mouseClick(window.order_tabs[1],Qt.MouseButton.LeftButton)
    assert window.forecast_table.isVisible() and not window.edit_order_btn.isVisible()
    QTest.mouseClick(window.order_tabs[0],Qt.MouseButton.LeftButton)
    assert window.order_table.isVisible() and window.edit_order_btn.isVisible()
    store.correct_batch('b0',11,True,'Повторная сверка','Тест')
    window.reload()
    assert not window.confirm_btn.isEnabled()
    window.close(); store.db.close()
