import copy
from datetime import date,timedelta
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import MainWindow,configure_application
from core import Store


def make_window(tmp_path):
    app=QApplication.instance() or QApplication([]); configure_application(app)
    store=Store(tmp_path/'navigation.sqlite3'); store.seed()
    window=MainWindow(store); window.show(); app.processEvents()
    return app,store,window


def test_domain_subpages_preserve_draft_chart_selection_and_filters(tmp_path):
    app,store,window=make_window(tmp_path)
    try:
        assert window.active_view=='inventory' and window.stock_views.currentIndex()==1
        assert set(window.side_buttons)=={'today','inventory','order','history','imports'}
        window.search.setText('Тесто'); window._make_order()
        window.current['edits']={'dough':{'packs':0,'reason':'Есть резерв','author':'Тест','at':'2026-10-24T00:00:00'}}
        window.save_current(); window.refresh_order(); before=copy.deepcopy(window.current)
        QTest.mouseClick(window.domain_buttons['demand'],Qt.MouseButton.LeftButton)
        assert set(window.side_buttons)=={'dynamics','months','availability','pilot','imports'}
        panel=window.analytics; panel.set_period(14); panel.dish_combo.setCurrentIndex(1)
        dish=panel.dish_combo.currentData()
        QTest.mouseClick(window.side_buttons['months'],Qt.MouseButton.LeftButton)
        assert panel.sales_chart.monthly and window.stack.currentIndex()==0
        QTest.mouseClick(window.domain_buttons['stock'],Qt.MouseButton.LeftButton)
        assert window.active_view=='order' and window.stack.currentIndex()==1
        assert window.current==before and window.search.text()=='Тесто'
        QTest.mouseClick(window.domain_buttons['demand'],Qt.MouseButton.LeftButton)
        assert window.active_view=='months' and panel.sales_chart.monthly
        assert panel.days==14 and panel.dish_combo.currentData()==dish
        panel.mode_combo.setCurrentIndex(0)
        assert window.active_view=='dynamics' and window.side_buttons['dynamics'].isChecked()
    finally:
        window.close(); store.db.close()


def test_data_context_and_search_shortcut(tmp_path):
    app,store,window=make_window(tmp_path)
    try:
        window.select_route('stock','imports'); stock_rows=window.quality.rowCount()
        window.select_route('demand','imports')
        assert window.quality.rowCount()==3 and window.quality.rowCount()<stock_rows
        assert window.page_titles[2].text()=='Данные продаж'
        window.select_route('demand','months')
        # Exercise the registered shortcut rather than bypassing its routing.
        search=next(s for s in window.shortcuts if s.key()==QKeySequence('Ctrl+K'))
        search.activated.emit(); app.processEvents()
        assert window.active_domain=='stock' and window.active_view=='inventory'
        assert window.stock_table.isVisible() and window.search.hasFocus()
    finally:
        window.close(); store.db.close()


def test_terminal_point_restores_without_inheriting_another_points_schedule(tmp_path):
    app,store,window=make_window(tmp_path)
    try:
        tables=store.get('tables'); tables['points'].append({'id':'no-schedule','name':'Точка без графика'})
        with store.db: store.put('tables',tables)
        window.point.addItem('Точка без графика','no-schedule'); window.point.setCurrentIndex(window.point.findData('no-schedule'))
        assert not window.schedule_check.isChecked() and not window.delivery_input.isEnabled()
        window._save_settings()
        assert not any(r['point']=='no-schedule' for r in store.get('tables')['schedules'])
        assert store.get('settings')['terminal_point']=='no-schedule'
        window.close(); window=MainWindow(store)
        assert window.pid()=='no-schedule' and 'без графика' in window.point_name.text()
        assert not window.schedule_check.isChecked()
        window.schedule_check.setChecked(True); window.delivery_input.setDate(date.today()+timedelta(days=4)); window.interval_input.setValue(7); window._save_settings()
        saved=next(r for r in store.get('tables')['schedules'] if r['point']=='no-schedule')
        assert saved['interval_days']==7 and saved['next_delivery']==(date.today()+timedelta(days=4)).isoformat()
    finally:
        window.close(); store.db.close()
