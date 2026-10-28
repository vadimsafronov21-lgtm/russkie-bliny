import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from datetime import date,timedelta
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton
from app import MainWindow
from core import DataError,Store
from tests.ui_helpers import business_dump
from ui_theme import configure_application


@pytest.fixture(scope='module')
def application():
    app=QApplication.instance() or QApplication([]);configure_application(app)
    return app


@pytest.fixture
def ui(tmp_path,application):
    store=Store(tmp_path/'data.sqlite3');store.seed();window=MainWindow(store)
    yield application,store,window
    window.close();store.db.close()


def save_button(window):
    return next(button for button in window.findChildren(QPushButton) if button.text()=='Сохранить настройки')


@pytest.mark.parametrize('offset',[-2,100])
def test_invalid_delivery_is_rejected_before_any_settings_write(ui,offset):
    app,store,window=ui;window.delivery_input.setDate(date.today()+timedelta(days=offset))
    window.author_input.setText('Новое имя');before=business_dump(store)
    with pytest.raises(DataError):window._save_settings()
    assert business_dump(store)==before


def test_save_button_reveals_invalid_date_without_success_message(ui):
    app,store,window=ui;window.resize(1180,800);window.select_route('stock','settings');window.show()
    window.delivery_input.setDate(date.today()-timedelta(days=2));app.processEvents();before=business_dump(store)
    QTest.mouseClick(save_button(window),Qt.MouseButton.LeftButton);app.processEvents()
    assert business_dump(store)==before
    assert window.active_view=='settings'
    assert window.settings_error.isVisible() and 'Ближайшая поставка' in window.settings_error.text()
    viewport=window.settings_scroll.viewport()
    assert viewport.rect().contains(window.delivery_input.mapTo(viewport,window.delivery_input.rect().center()))


def test_correct_save_button_refreshes_data_and_draft_preserving_manual_quantity(ui):
    app,store,window=ui;window._make_order();row=window.current['rows'][0]
    window.edit_current_quantity(row,3,'Ручная правка сохраняется')
    old_id=window.current['draft_id'];tables=store.get('tables');tables['schedules'][0]['next_delivery']=(date.today()-timedelta(days=2)).isoformat()
    with store.db:store.put('tables',tables)
    window.point_changed();window.select_route('stock','settings');window.show()
    assert window.snapshot is None
    window.delivery_input.setDate(date.today()+timedelta(days=1));app.processEvents()
    QTest.mouseClick(save_button(window),Qt.MouseButton.LeftButton);app.processEvents()
    assert window.snapshot and not window.calculation_error and not window.problem_box.isVisible()
    assert window.active_view=='inventory' and window.stock_table.rowCount()==7
    assert window.current['revision']==store.get('revision') and window.current['draft_id']==old_id
    assert window.current['edits'][row['id']]['packs']==3
    assert not window.current['stock_confirmed'] and not window.confirm_btn.isEnabled()
    assert window.analytics.payload['forecast']
    assert 'обновлены' in window.notifications.caption.text()


def test_settings_save_does_not_replace_a_confirmed_order(ui):
    app,store,window=ui;window._make_order();window.stock_check.setChecked(True)
    order_id=store.confirm(window.pid(),window.current,'Оператор');saved=store.get_order(order_id)
    window.reload();window.delivery_input.setDate(date.today()+timedelta(days=2));window._save_settings()
    assert store.get_order(order_id)==saved
    assert window.current['confirmed_order_id']==order_id
    assert store.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==1


def test_manual_calculation_day_accepts_corresponding_historical_delivery(ui):
    app,store,window=ui;window.today_check.setChecked(False)
    window.date_input.setDate(date.today()-timedelta(days=10));window.delivery_input.setDate(date.today()-timedelta(days=9))
    window._save_settings()
    assert window.snapshot and window.snapshot['date']==(date.today()-timedelta(days=10)).isoformat()


def test_saving_without_schedule_does_not_claim_forecast_ready(ui):
    app,store,window=ui;window.select_route('stock','settings');window.schedule_check.setChecked(False)
    window._save_settings()
    assert window.snapshot is None and window.active_view=='settings'
    assert 'График' in window.notifications.caption.text()
