import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from datetime import date,timedelta

import pytest
from PySide6.QtWidgets import QApplication,QDialog

from app import MainWindow,configure_application
from core import Store
from dalion_demo import DalionDemoDialog
from exchange_review import prepare_import
from operations_ui import ReviewImportDialog,WhatIfDialog
from tests.test_dalion_demo_ui import wait_fetch
from tests.ui_helpers import business_dump


@pytest.fixture
def ui(tmp_path):
    application=QApplication.instance() or QApplication([]); configure_application(application)
    store=Store(tmp_path/'ui.sqlite3'); store.seed()
    window=MainWindow(store); window.show(); application.processEvents()
    yield application,store,window
    window.day_timer.stop(); window.close(); store.db.close(); application.processEvents()


def test_daily_routes_availability_and_pilot(ui):
    app,store,window=ui
    window.select_route('stock','today')
    assert window.stack.currentIndex()==5 and window.daily_table.rowCount()>0
    window.select_route('demand','availability')
    assert window.availability_table.rowCount()==5
    before=store.get('tables'); window.availability_table.selectRow(0)
    window.availability_reason.setText('Проверка на точке'); window.set_availability(False)
    assert window.availability_table.item(0,1).text()=='Закончилось'
    assert store.get('tables')==before
    window.set_availability(True)
    assert window.availability_log.rowCount()==2
    window.select_route('demand','pilot'); window.capture_pilot()
    assert 'Зафиксировано' in window.pilot_status.text()
    assert store.db.execute('SELECT COUNT(*) FROM pilot_forecasts').fetchone()[0]>0
    window.pilot_start.setDate(date.today()); window.pilot_end.setDate(date.today()-timedelta(days=1)); window.refresh_pilot()
    assert window.pilot_result is None and window.pilot_details.rowCount()==0


def test_what_if_close_and_error_do_not_mutate_working_plan(ui):
    app,store,window=ui
    window._make_order(); before=business_dump(store)
    dialog=WhatIfDialog(store,'central',date.today(),window)
    dialog.demand.setValue(50); dialog.extra.setValue(100); dialog.compare()
    assert dialog.result['scenario'] and dialog.table.rowCount()==7
    assert business_dump(store)==before
    dialog.delay.setValue(30); dialog.compare(); dialog.reject()
    assert business_dump(store)==before


def test_review_cancel_and_conflict_error_leave_data_intact(ui):
    app,store,window=ui
    with store.db:
        store.put('seeded_demo',False); store.put('exchange_base',store.get('tables'))
    incoming=store.get('tables'); incoming['batches'][0]['qty']=30
    store.correct_batch('b0',7,True,'Сверка','Оператор')
    plan=prepare_import(store,incoming,True,'Демо','update-1')
    before=business_dump(store)
    dialog=ReviewImportDialog(store,plan,'Оператор',window); dialog.apply()
    assert 'причину' in dialog.error.text()
    assert business_dump(store)==before
    dialog.reject(); assert business_dump(store)==before
    dialog=ReviewImportDialog(store,plan,'Оператор',window)
    dialog.reason.setText('Проверено'); dialog.choices[0].setCurrentIndex(1); dialog.apply()
    assert next(row for row in store.get('tables')['batches'] if row['id']=='b0')['qty']==7
    assert dialog.result is not None


def test_all_demo_scenarios_create_separate_databases(ui,tmp_path):
    app,store,parent=ui
    before=business_dump(store); dialog=DalionDemoDialog(parent,root=tmp_path/'demos')
    directories=[]
    try:
        for index in range(dialog.scenario_choice.count()):
            dialog.scenario_choice.setCurrentIndex(index)
            dialog.fetch(); wait_fetch(dialog,app); dialog.open_analysis()
            assert dialog.workspace.store.get('demo') is True
            assert dialog.analysis_window is not None
            directories.append(dialog.workspace.directory)
            if dialog.scenario_choice.currentData()=='missing':
                assert next(row for row in dialog.snapshot.tables['batches'] if row['ingredient']=='chicken_i')['qty']==0
        assert len(set(directories))==4
        assert business_dump(store)==before
    finally: dialog.close()
