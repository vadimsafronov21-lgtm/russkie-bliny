import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import runpy
import sys
from pathlib import Path
import pytest
from PySide6.QtCore import QPoint,Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
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


def test_overview_selection_keeps_table_full_width_and_opens_details_explicitly(ui):
    app,store,window=ui;before=business_dump(store);width=window.stock_table.width()
    assert not window.ingredient_dialog.isVisible()
    rect=window.stock_table.visualItemRect(window.stock_table.item(0,0))
    QTest.mouseClick(window.stock_table.viewport(),Qt.MouseButton.LeftButton,pos=rect.center());app.processEvents()
    assert not window.ingredient_dialog.isVisible()
    window.details_button.click();app.processEvents()
    assert window.ingredient_dialog.isVisible() and not window.ingredient_dialog.isModal()
    assert window.stock_table.width()==width and window.ingredient_dialog.isWindow()
    window.ingredient_card.close_button.click();app.processEvents()
    assert not window.ingredient_dialog.isVisible() and business_dump(store)==before


def test_analytics_shows_one_chart_at_a_time(ui):
    app,store,window=ui;window.select_route('demand','dynamics');app.processEvents();panel=window.analytics
    charts=[panel.sales_chart,panel.coverage_chart,panel.mix_chart,panel.stock_timeline]
    for index in range(4):
        panel.chart_tabs.setCurrentIndex(index);app.processEvents()
        assert [chart.isVisible() for chart in charts]==[i==index for i in range(4)]
    window.select_route('demand','months');app.processEvents()
    assert panel.chart_tabs.currentIndex()==0 and panel.sales_chart.monthly


@pytest.mark.parametrize('large',[False,True])
def test_chart_hover_preserves_flat_background_and_selected_underline(ui,large):
    app,store,window=ui;window.resize(1560,1020);window.set_large_mode(large)
    window.select_route('demand','dynamics');app.processEvents()
    bar=window.analytics.chart_tabs.tabBar();rects=[bar.tabRect(i) for i in range(4)]
    before=business_dump(store)
    for hovered in [0,1,2,3,-1]:
        QTest.mouseMove(bar,rects[hovered].center() if hovered>=0 else QPoint(-20,-20));QTest.qWait(210);app.processEvents()
        pixels=bar.grab().toImage();scale=pixels.devicePixelRatio()
        for index,rect in enumerate(rects):
            expected=QColor('#F9E8EB' if index==hovered else '#F6F6F8')
            for x in [rect.left()+3,rect.center().x(),rect.right()-3]:
                assert pixels.pixelColor(round(x*scale),round(rect.top()*scale))==expected
        selected=rects[0]
        assert pixels.pixelColor(round(selected.center().x()*scale),round((selected.bottom()-1)*scale))==QColor('#A4002A')
        assert [bar.tabRect(i) for i in range(4)]==rects
    assert business_dump(store)==before


def test_chart_modes_switch_by_click_and_keyboard_after_hover(ui):
    app,store,window=ui;window.select_route('demand','dynamics');app.processEvents()
    panel=window.analytics;bar=panel.chart_tabs.tabBar()
    for index,chart in enumerate([panel.sales_chart,panel.coverage_chart,panel.mix_chart,panel.stock_timeline]):
        QTest.mouseMove(bar,bar.tabRect(index).center());QTest.mouseClick(bar,Qt.MouseButton.LeftButton,pos=bar.tabRect(index).center())
        app.processEvents();assert panel.chart_tabs.currentIndex()==index and chart.isVisible()
    bar.setFocus();QTest.keyClick(bar,Qt.Key.Key_Left);app.processEvents()
    assert panel.chart_tabs.currentIndex()==2 and panel.mix_chart.isVisible()


def test_reopening_workspace_remembers_chart_tab_without_opening_a_popup(ui):
    app,store,window=ui;window.select_route('demand','dynamics');window.analytics.chart_tabs.setCurrentIndex(2)
    window.save_workspace();window.close();restored=MainWindow(store);restored.show();app.processEvents()
    try:
        assert restored.analytics.chart_tabs.currentIndex()==2 and restored.active_domain=='demand'
        assert not restored.ingredient_dialog.isVisible()
    finally:restored.close()


@pytest.mark.parametrize('explicit',[False,True])
def test_preview_entry_uses_separate_data_directory(tmp_path,monkeypatch,explicit):
    import app
    captured=[];monkeypatch.setattr(app,'main',lambda:captured.append(list(sys.argv)))
    argv=['preview.exe']+(['--data-dir',str(tmp_path/'explicit')] if explicit else [])
    monkeypatch.setattr(sys,'argv',argv);monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    runpy.run_path(str(Path(__file__).resolve().parents[1]/'design_preview.py'),run_name='__main__')
    expected=tmp_path/('explicit' if explicit else 'RusskieBliny-DesignPreview')
    assert Path(captured[0][captured[0].index('--data-dir')+1])==expected
