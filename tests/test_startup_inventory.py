import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from datetime import date,timedelta
import pytest
from PySide6.QtWidgets import QApplication
from app import MainWindow
from core import DataError,Store
from ui_theme import configure_application


@pytest.fixture(scope='module')
def application():
    app=QApplication.instance() or QApplication([]); configure_application(app)
    return app


@pytest.mark.parametrize('schedule',['past','missing'])
def test_startup_keeps_actual_stock_when_forecast_is_unavailable(tmp_path,application,schedule):
    store=Store(tmp_path/'data.sqlite3'); store.seed(); tables=store.get('tables')
    if schedule=='past': tables['schedules'][0]['next_delivery']=(date.today()-timedelta(days=2)).isoformat()
    else: tables['schedules']=[]
    with store.db:
        store.put('tables',tables)
        store.put('ui_workspace:central',dict(version=1,domain='stock',view='order',filter=1))
    revision=store.get('revision'); window=MainWindow(store)
    try:
        assert window.snapshot is None and window.calculation_error
        assert window.stock_table.rowCount()==7
        assert window.active_view=='inventory'
        assert window.metrics[0].text()=='7'
        assert window.stock_table.item(0,3).text()=='—'
        assert window.stock_table.item(0,4).text()=='Расчёт недоступен'
        assert not window.stock_tabs[1].isEnabled()
        window.stock_table.selectRow(0); window.open_selected_card()
        assert window.ingredient_card.ingredient=='dough'
        assert '14.00' in window.ingredient_card.summary.text()
        assert not window.ingredient_card.chart.isVisible()
        assert window.analytics.payload['observed']>0
        with pytest.raises(DataError): window._make_order()
        assert store.get('tables')==tables and store.get('revision')==revision
    finally: window.close(); store.db.close()


def test_actual_stock_distinguishes_blocked_unknown_and_other_point(tmp_path,application):
    store=Store(tmp_path/'data.sqlite3'); store.seed(); tables=store.get('tables')
    tables['schedules']=[]; tables['batches'][0]['usable']=0
    tables['batches']=[row for row in tables['batches'] if row['ingredient']!='cream']
    tables['batches'].append(dict(tables['batches'][0],id='other',point='other',qty=999))
    with store.db: store.put('tables',tables)
    window=MainWindow(store)
    try:
        assert window.stock_table.item(0,1).text()=='14,00 л'
        window.stock_table.selectRow(0); window.open_selected_card()
        assert '0.00' in window.ingredient_card.summary.text()
        assert '14.00' in window.ingredient_card.summary.text()
        assert window.stock_table.item(1,1).text()=='Нет данных'
    finally: window.close(); store.db.close()


def test_restoring_valid_schedule_returns_forecast_and_filters(tmp_path,application):
    store=Store(tmp_path/'data.sqlite3'); store.seed(); original=store.get('tables'); broken=store.get('tables')
    broken['schedules']=[]
    with store.db: store.put('tables',broken)
    window=MainWindow(store)
    try:
        assert window.stock_table.rowCount()==7
        window.stock_table.selectRow(0); window.open_selected_card()
        with store.db: store.put('tables',original)
        window.reload()
        assert window.snapshot and window.stock_tabs[1].isEnabled()
        assert 'Потребность:' in window.ingredient_card.summary.text()
        window._make_order(); assert window.current['rows']
    finally: window.close(); store.db.close()


def test_startup_does_not_discard_saved_draft_with_manual_quantity(tmp_path,application):
    path=tmp_path/'data.sqlite3'; store=Store(path); store.seed(); window=MainWindow(store)
    window._make_order(); row=window.current['rows'][0]
    window.edit_current_quantity(row,3,'Проверенная ручная правка')
    window.select_route('stock','order'); window.close()
    saved=store.get('draft:central'); tables=store.get('tables'); tables['schedules']=[]
    with store.db: store.put('tables',tables)
    store.db.close(); store=Store(path); window=MainWindow(store)
    try:
        assert window.active_view=='inventory' and window.stock_table.rowCount()==7
        assert store.get('draft:central')==saved
        assert window.current['edits'][row['id']]['packs']==3
    finally: window.close(); store.db.close()
