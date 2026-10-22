import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox,QLabel
from app import MainWindow,configure_application
from core import Store
from workflows import StockCorrectionDialog,QuantityDialog,OrderDetailsDialog

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
    QTest.mouseClick(window.stock_view_tabs[1],Qt.MouseButton.LeftButton)
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

def test_chart_periods_months_and_dish_drilldown(tmp_path,application):
    store=Store(tmp_path/'charts.sqlite3'); store.seed()
    window=MainWindow(store); window.show(); application.processEvents()
    panel=window.analytics
    assert window.stock_views.currentIndex()==0
    QTest.mouseClick(panel.period_buttons[0],Qt.MouseButton.LeftButton)
    assert panel.payload['length']==14 and len(panel.payload['actual'])==14
    selected=panel.payload['composition'][0]['id']
    _,left=panel.mix_chart.geometry_parts(); top=(panel.mix_chart.height()-len(panel.mix_chart.rows)*35)/2
    QTest.mouseClick(panel.mix_chart,Qt.MouseButton.LeftButton,pos=QPoint(int(left+20),int(top+12)))
    assert panel.dish_combo.currentData()==selected
    panel.mode_combo.setCurrentIndex(1)
    assert panel.sales_chart.monthly and len(panel.payload['months'])==3
    assert all(not b.isEnabled() for b in panel.period_buttons)
    panel.mode_combo.setCurrentIndex(0)
    assert panel.payload['length']==14 and all(b.isEnabled() for b in panel.period_buttons)
    window.close(); store.db.close()


def test_stock_form_opens_selected_ingredient_even_after_filter(tmp_path,application,monkeypatch):
    store=Store(tmp_path/'selection.sqlite3'); store.seed(); window=MainWindow(store)
    window.search.setText('Икра'); window.stock_table.selectRow(0)
    seen=[]
    class InspectDialog(StockCorrectionDialog):
        def exec(self):
            seen.append(self.batch.currentData())
            assert self.batch.count()==1
            return QDialog.DialogCode.Rejected
    monkeypatch.setattr('app.StockCorrectionDialog',InspectDialog)
    window._edit_stock()
    assert seen==['b6']
    window.close(); store.db.close()


def test_stock_validation_keeps_form_quantity_and_reason(tmp_path,application):
    store=Store(tmp_path/'validation.sqlite3'); store.seed()
    batches=store.get('tables')['batches'][:1]; names={'dough':'Тесто блинное'}
    dialog=StockCorrectionDialog(store,batches,names,'Анна'); dialog.show(); application.processEvents()
    buttons=dialog.findChild(QDialogButtonBox)
    dialog.mode.setCurrentIndex(1); dialog.qty.setValue(20); dialog.reason.setText('Проверка')
    QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
    assert dialog.isVisible() and dialog.qty.value()==20 and dialog.reason.text()=='Проверка'
    assert store.get('tables')['batches'][0]['qty']==14
    assert any('превышает' in l.text() and not l.isHidden() for l in dialog.findChildren(QLabel))
    dialog.qty.setValue(1)
    QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
    assert dialog.result()==QDialog.DialogCode.Accepted
    assert store.get('tables')['batches'][0]['qty']==13
    dialog.close(); store.db.close()


def test_order_preview_validation_and_save(tmp_path,application):
    store=Store(tmp_path/'preview.sqlite3'); store.seed(); window=MainWindow(store); window._make_order()
    row=window.current['rows'][0]; saved=[]
    dialog=QuantityDialog(window.current,row,None,lambda packs,reason:saved.append((packs,reason)))
    dialog.show(); application.processEvents(); dialog.qty.setValue(0)
    assert dialog.chart.picked['cost']==0 and dialog.chart.picked['shortage']>0
    buttons=dialog.findChild(QDialogButtonBox)
    QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
    assert dialog.isVisible() and dialog.qty.value()==0 and not saved
    dialog.reason.setText('Имеется другой запас')
    QTest.mouseClick(buttons.button(QDialogButtonBox.StandardButton.Save),Qt.MouseButton.LeftButton)
    assert saved==[(0,'Имеется другой запас')]
    window.close(); store.db.close()


def test_confirmed_order_is_readonly_and_reexportable_after_reload(tmp_path,application):
    store=Store(tmp_path/'confirmed.sqlite3'); store.seed(); window=MainWindow(store); window._make_order()
    window.stock_check.setChecked(True); order_id=store.confirm(window.pid(),window.current,'Анна')
    window.reload()
    assert not window.edit_order_btn.isEnabled() and not window.stock_check.isEnabled()
    assert window.confirm_btn.isEnabled() and str(order_id) in window.confirm_btn.text()
    assert window.recalc_btn.text()=='Новая заявка'
    original_id=window.current['draft_id']; window._make_order()
    assert window.current['draft_id']!=original_id and not window.current.get('confirmed_order_id')
    window.close(); store.db.close()


def test_missing_schedule_reports_real_problem_without_hiding_actual_sales(tmp_path,application):
    store=Store(tmp_path/'missing.sqlite3'); store.seed(); tables=store.get('tables'); tables['schedules']=[]
    with store.db: store.put('tables',tables)
    window=MainWindow(store)
    assert window.snapshot is None
    assert 'Нет графика поставок' in window.import_report.toPlainText()
    assert 'Структурные ошибки не обнаружены' not in window.import_report.toPlainText()
    assert 'Нет подтверждённых закрытых смен' not in window.analytics.history_hint.text()
    assert window.analytics.payload['total']>0
    assert not window.problem_box.isHidden()
    assert 'Нет графика поставок' in window.analytics.coverage_chart.empty_message
    window.resolve_problem(); assert window.stack.currentIndex()==4
    window.close(); store.db.close()


def test_history_details_and_filters_preserve_frozen_order(tmp_path,application):
    store=Store(tmp_path/'history.sqlite3'); store.seed(); window=MainWindow(store); window._make_order()
    window.stock_check.setChecked(True); first=store.confirm(window.pid(),window.current,'Анна')
    window._make_order(); window.stock_check.setChecked(True); second=store.confirm(window.pid(),window.current,'Анна')
    window.navigate(3); assert len(window.orders)==2
    window.history_search.setText(str(first)); assert len(window.orders)==1 and window.orders[0][0]==first
    exported=[]; dialog=OrderDetailsDialog(store.get_order(second),'Центральная',lambda order:exported.append(order['id']))
    assert f'№{second}' in dialog.windowTitle()
    from PySide6.QtWidgets import QPushButton
    export=next(b for b in dialog.findChildren(QPushButton) if b.text()=='Экспортировать Excel')
    export.click(); assert exported==[second]
    dialog.close(); window.close(); store.db.close()
