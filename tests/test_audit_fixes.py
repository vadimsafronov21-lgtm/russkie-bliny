import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

from datetime import date,timedelta
import pytest
from PySide6.QtCore import QPoint,QRect,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog,QFileDialog,QLabel,QListWidget,QPushButton
from app import MainWindow
from core import Store
from tests.ui_helpers import business_dump
from ui_theme import configure_application


@pytest.fixture
def ui(tmp_path):
    app=QApplication.instance() or QApplication([]);configure_application(app)
    store=Store(tmp_path/'data.sqlite3');store.seed();window=MainWindow(store);window.show();app.processEvents()
    yield app,store,window
    window.close();store.db.close();app.processEvents()


@pytest.mark.parametrize('size',[(1180,800),(1280,800),(1560,1020)])
@pytest.mark.parametrize('large',[False,True])
def test_overview_footer_never_overlaps_rows_even_with_notice_and_expired_schedule(ui,size,large):
    app,store,window=ui;window.resize(*size);window.set_large_mode(large);window.select_route('stock','inventory')
    footer=next(w for w in window.findChildren(QLabel) if w.text().startswith('¹ По норме'))
    def rect(widget):return QRect(widget.mapTo(window,QPoint()),widget.size())
    for expired in (False,True):
        if expired:
            tables=store.get('tables');tables['schedules'][0]['next_delivery']=(date.today()-timedelta(days=2)).isoformat()
            with store.db:store.put('tables',tables)
            window.reload()
        for notice in (False,True):
            if notice:window.notify('Настройки сохранены. Остатки и прогноз обновлены.')
            else:window.notifications.hide()
            app.processEvents();app.processEvents()
            viewport=rect(window.stock_table.viewport())
            assert not viewport.intersects(rect(footer)) and not viewport.intersects(rect(window.details_button))
            window.inventory_scroll.ensureWidgetVisible(window.details_button);app.processEvents()
            assert window.inventory_scroll.viewport().rect().contains(window.details_button.mapTo(window.inventory_scroll.viewport(),window.details_button.rect().center()))
            assert window.stock_table.rowCount()==7


def test_each_chart_has_its_own_visible_context_and_months_show_only_months(ui):
    app,store,window=ui;before=business_dump(store);window.select_route('demand','dynamics');p=window.analytics
    p.chart_tabs.setCurrentIndex(2);app.processEvents()
    assert not p.scope.isVisible() and not p.dish_metrics.isVisible() and not p.dish_combo.isVisible()
    assert all(button.isVisible() for button in p.period_buttons)
    QTest.mouseClick(p.period_buttons[0],Qt.MouseButton.LeftButton);app.processEvents()
    assert p.payload['length']==14 and '14 дней' in p.mix_period.text() and 'всех блюд' in p.mix_period.text()
    p.chart_tabs.setCurrentIndex(1);app.processEvents()
    assert not p.dish_metrics.isVisible() and not p.period_tools.isVisible()
    assert window.snapshot['end'] in p.coverage_period.text()
    p.chart_tabs.setCurrentIndex(3);app.processEvents()
    assert p.stock_timeline.isVisible() and not p.scope.isVisible()
    window.select_route('demand','months');app.processEvents()
    assert p.chart_tabs.currentIndex()==0 and p.sales_chart.monthly
    assert [p.chart_tabs.isTabVisible(i) for i in range(4)]==[True,False,False,False]
    window.select_route('demand','dynamics');app.processEvents()
    assert all(p.chart_tabs.isTabVisible(i) for i in range(4)) and p.days==14
    assert business_dump(store)==before


def test_daily_action_requires_selection_and_measurement_is_in_pilot(ui):
    app,store,window=ui;window.select_route('stock','today');window.daily_table.clearSelection()
    assert not window.daily_action_button.isEnabled()
    window.run_daily_action();assert 'Выберите' in window.daily_status.text() and window.active_view=='today'
    window.daily_table.selectRow(0);assert window.daily_action_button.isEnabled()
    titles=[b.text() for b in window.stack.currentWidget().findChildren(QPushButton)]
    assert 'Демонстрации' not in titles and 'Начать замер заявки' not in titles
    window.select_route('demand','pilot');window.work_button.click();app.processEvents()
    assert window.active_view=='order' and window.work_button.text()=='Завершить замер'
    window.select_route('demand','pilot');window.work_button.click();app.processEvents()
    assert window.work_button.text()=='Начать замер заявки'
    assert store.db.execute('SELECT COUNT(*) FROM work_sessions WHERE ended IS NOT NULL').fetchone()[0]==1


def test_import_preparation_collapses_but_actual_errors_stay_visible(ui):
    app,store,window=ui;window.select_route('stock','imports');app.processEvents()
    assert 'покажем изменения' in window.import_hint.text() and 'заменяется целиком' not in window.import_hint.text()
    assert not window.import_preparation.body.isVisible() and not window.import_report.isVisible()
    window.import_preparation.toggle.setFocus();QTest.keyClick(window.import_preparation.toggle,Qt.Key.Key_Space);app.processEvents()
    assert window.import_preparation.body.isVisible()
    window.import_preparation.setExpanded(False)
    tables=store.get('tables');tables['schedules'][0]['next_delivery']=(date.today()-timedelta(days=2)).isoformat()
    with store.db:store.put('tables',tables)
    window.reload();app.processEvents()
    assert window.import_report.isVisible() and window.calculation_error in window.import_report.toPlainText()


def test_settings_reveal_invalid_field_in_collapsed_section_without_writing(ui):
    app,store,window=ui;window.select_route('stock','settings');app.processEvents()
    assert [k for k,v in window.settings_sections.items() if v.body.isVisible()]==['delivery']
    window.author_input.clear();before=business_dump(store);window.save_settings();app.processEvents()
    assert business_dump(store)==before and window.settings_sections['terminal'].body.isVisible()
    assert window.settings_error.isVisible() and window.author_input.hasFocus()
    viewport=window.settings_scroll.viewport()
    assert viewport.rect().contains(window.author_input.mapTo(viewport,window.author_input.rect().center()))
    assert window.notifications.persistent and not window.notifications.timer.isActive()
    window.settings_sections['terminal'].setExpanded(False);app.processEvents();app.processEvents()
    assert window.settings_sections['terminal'].parentWidget().height()<80


def test_notifications_keep_actions_after_navigation_and_accessibility_stays_in_profile(ui,monkeypatch):
    app,store,window=ui;seen=[]
    window.notify('Проверка действий',[('Открыть результат',lambda:seen.append(True))])
    window.select_route('demand','dynamics');app.processEvents();assert not window.notifications.isVisible()
    def inspect(dialog):
        assert dialog.findChild(QListWidget).count()>0
        next(b for b in dialog.findChildren(QPushButton) if b.text()=='Открыть результат').click()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog,'exec',inspect);window.open_notifications();assert seen==[True]
    window.large_button.trigger();assert window.large_mode
    assert window.profile_button.menu() is window.profile_menu and window.large_button in window.profile_menu.actions()
    assert window.commands_button.accessibleName()=='Поиск действий'


def test_compact_order_preserves_warnings_confirmation_and_repeat_export(ui,tmp_path,monkeypatch):
    app,store,window=ui;window.resize(1280,800);window._make_order();app.processEvents()
    assert window.order_table.width()>950 and window.order_warnings_scroll.isVisible()
    assert 'Даты пригодности' in window.order_warn.text() and 'дефицит' in window.order_warn.text().lower()
    window.edit_current_quantity(window.current['rows'][0],3,'Проверка');window.refresh_order()
    assert not window.notifications.actions and window.undo_button.isVisible()
    window.undo_button.click();assert not window.current['edits']
    window.stock_check.setChecked(True);monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args:(str(tmp_path/'order.xlsx'),''))
    window.confirm_btn.click();app.processEvents()
    assert window.current.get('confirmed_order_id') and not window.stock_check.isVisible() and not window.undo_button.isVisible()
    assert not window.order_warnings_scroll.isVisible() and 'Экспортировать' in window.confirm_btn.text()
    window.confirm_btn.click()
    assert store.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==1 and (tmp_path/'order.xlsx').exists()
