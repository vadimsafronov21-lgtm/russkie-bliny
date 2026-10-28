import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import copy
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QMessageBox

from app import MainWindow,configure_application
from core import Store
from interaction_ui import CommandPalette,CompareOrdersDialog


@pytest.fixture
def ui(tmp_path):
    application=QApplication.instance() or QApplication([]); configure_application(application)
    store=Store(tmp_path/'ux.sqlite3'); store.seed()
    window=MainWindow(store); window.show(); application.processEvents()
    yield application,store,window
    window.close(); store.db.close(); application.processEvents()


def test_restart_restores_views_filters_dish_period_and_large_mode(ui):
    app,store,window=ui
    window.search.setText('Сыр'); window.filter.setCurrentIndex(1)
    window.select_route('demand','months'); window.analytics.set_period(14); window.chart_dish.setCurrentIndex(2)
    dish=window.chart_dish.currentData(); window.resize(1366,900); window.set_large_mode(True)
    revision=store.get('revision'); tables=copy.deepcopy(store.get('tables'))
    window.close(); restored=MainWindow(store); restored.show(); app.processEvents()
    try:
        assert restored.active_domain=='demand' and restored.active_view=='months'
        assert restored.search.text()=='Сыр' and restored.filter.currentIndex()==1
        assert restored.chart_dish.currentData()==dish and restored.analytics.days==14
        assert restored.large_mode and restored.large_button.isChecked()
        assert store.get('revision')==revision and store.get('tables')==tables
        restored.set_large_mode(False)
        assert not restored.styleSheet()
    finally: restored.close()


def test_side_card_follows_selection_and_does_not_change_data(ui):
    app,store,window=ui; before=store.get('tables'); window.select_route('stock','inventory')
    window.stock_table.selectRow(0); window.open_selected_card(); app.processEvents()
    assert window.inventory_rail.currentWidget() is window.ingredient_card
    assert window.ingredient_card.ingredient=='dough' and window.ingredient_card.chart.isVisible()
    window.stock_table.selectRow(1); app.processEvents()
    assert window.ingredient_card.ingredient==window.visible_stock[1]['id']
    window.search.setText('несуществующее'); assert window.inventory_rail.currentIndex()==0
    assert store.get('tables')==before


def test_palette_search_keyboard_and_guarded_disabled_command(ui):
    app,store,window=ui; seen=[]
    palette=CommandPalette([dict(title='Сверить: Тесто блинное',callback=lambda:seen.append('test')),
                            dict(title='Сверить: Сыр',callback=lambda:seen.append('cheese')),
                            dict(title='Недоступное действие',callback=lambda:seen.append('bad'),enabled=False)],window)
    palette.show(); palette.search.setText('сверить тесто'); app.processEvents()
    assert palette.results.count()==1
    palette.run_current(); app.processEvents(); assert seen==['test']
    palette=CommandPalette(window.command_entries(),window)
    palette.search.setText('карточка тесто'); assert palette.results.count()==1
    palette.run_current(); app.processEvents(); assert window.ingredient_card.ingredient=='dough'
    assert any(shortcut.key()==QKeySequence('Ctrl+Shift+P') for shortcut in window.shortcuts)
    assert any(shortcut.key()==QKeySequence('Ctrl+K') for shortcut in window.shortcuts)


def test_undo_notification_and_confirmed_lock(ui):
    app,store,window=ui; window._make_order(); row=window.current['rows'][0]
    window.edit_current_quantity(row,2,'Проверка количества'); window.refresh_order()
    assert window.undo_button.isEnabled() and not window.notifications.isHidden()
    window.notifications.actions[0].click(); assert not window.current['edits']
    window.edit_current_quantity(window.current['rows'][0],3,'Большой заказ'); window.refresh_order()
    window.stock_check.setChecked(True); store.confirm(window.pid(),window.current,'Оператор'); window.reload()
    assert not window.undo_button.isEnabled()
    before=store.get('draft:central'); window.undo_last_edit()
    assert store.get('draft:central')==before


def test_success_notifications_are_nonmodal_and_file_actions_are_deferred(ui,tmp_path,monkeypatch):
    app,store,window=ui; opened=[]
    monkeypatch.setattr('interaction_ui.QDesktopServices.openUrl',lambda url:opened.append(url.toLocalFile()))
    monkeypatch.setattr(QMessageBox,'information',lambda *args:pytest.fail('Успех не должен открывать модальное окно'))
    window.message('Настройки сохранены'); assert not window.notifications.isHidden()
    path=tmp_path/'export.xlsx'; window.notify_export('Файл сохранён',path)
    assert not opened and len(window.notifications.actions)==2
    window.notifications.actions[0].click(); window.notifications.actions[1].click()
    assert [Path(value) for value in opened]==[path,path.parent]
    window.notifications.close_button.click(); assert window.notifications.isHidden()


def test_comparison_shows_saved_reasons_without_changing_orders(ui):
    app,store,window=ui
    for packs in (2,3):
        window._make_order(); window.edit_current_quantity(window.current['rows'][0],packs,f'Количество {packs}')
        window.stock_check.setChecked(True); store.confirm(window.pid(),window.current,'Оператор'); window.reload()
    before=store.db.execute('SELECT payload FROM orders ORDER BY id').fetchall()
    dialog=CompareOrdersDialog(store,'central',window)
    assert dialog.comparison and dialog.quantities.rowCount()==7
    assert any('Количество 3' in dialog.reasons.item(row,2).text() for row in range(dialog.reasons.rowCount()))
    dialog.after.setCurrentIndex(dialog.before.currentIndex()); assert dialog.comparison is None
    assert store.db.execute('SELECT payload FROM orders ORDER BY id').fetchall()==before


def test_invalid_old_view_preferences_do_not_block_startup(ui):
    app,store,window=ui
    with store.db: store.put('ui_workspace:central',dict(version=1,filter=None,last_views=[],domain=[],view={},scrolls=None,analytics_scroll=None,geometry=1))
    restored=MainWindow(store); restored.show(); app.processEvents()
    try: assert restored.active_view=='inventory' and restored.filter.currentIndex()==0
    finally: restored.close()
