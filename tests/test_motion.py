import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import math
import pytest
from PySide6.QtCore import QAbstractAnimation,QEvent,QPoint,QPointF,Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import MainWindow
from charts import MixChart,CoverageChart
from core import Store
from tests.ui_helpers import business_dump
from ui_motion import MotionButton,MotionTabBar,finish_motion
from ui_theme import configure_application


@pytest.fixture
def ui(tmp_path):
    app=QApplication.instance() or QApplication([]);configure_application(app)
    store=Store(tmp_path/'data.sqlite3');store.seed();window=MainWindow(store);window.show();app.processEvents();finish_motion(window)
    yield app,store,window
    window.close();window.deleteLater();app.processEvents();store.db.close()


def running(widget):return [a for a in widget.findChildren(QAbstractAnimation) if a.state()==QAbstractAnimation.State.Running]


def test_hover_and_selection_have_intermediate_frames_and_stop_at_idle(ui):
    app,store,w=ui;before=business_dump(store);b=w.side_buttons['history'];rect=b.geometry()
    app.sendEvent(b,QEvent(QEvent.Type.Leave));QTest.qWait(160)
    point=QPointF(b.rect().center());app.sendEvent(b,QEnterEvent(point,point,QPointF(b.mapToGlobal(point.toPoint()))));QTest.qWait(40)
    assert 0<b._hover<1 and b.geometry()==rect
    QTest.qWait(190);assert b._hover==1 and not running(b)
    same=dict(w.side_buttons);QTest.mouseClick(b,Qt.MouseButton.LeftButton);QTest.qWait(40)
    assert 0<b._selected<1 and w.side_buttons==same and b.geometry()==rect
    QTest.qWait(210);assert b._selected==1 and not running(b)
    assert business_dump(store)==before


def test_tab_underline_retargets_fast_clicks_and_keeps_real_page_current(ui):
    app,store,w=ui;w.select_route('demand','dynamics');app.processEvents();finish_motion(w)
    panel=w.analytics;bar=panel.chart_tabs.tabBar();assert isinstance(bar,MotionTabBar)
    panel.chart_tabs.setCurrentIndex(1);QTest.qWait(50)
    assert bar._line!=bar._target() and bar._line_animation.state()==QAbstractAnimation.State.Running
    panel.chart_tabs.setCurrentIndex(3);panel.chart_tabs.setCurrentIndex(2);QTest.qWait(230)
    assert panel.chart_tabs.currentIndex()==2 and panel.mix_chart.isVisible()
    assert bar._line==bar._target() and not running(bar)
    bar.setFocus();QTest.keyClick(bar,Qt.Key.Key_Right);QTest.qWait(210)
    assert panel.stock_timeline.isVisible() and not running(bar)


def test_motion_preference_persists_without_changing_large_mode_or_business_data(ui):
    app,store,w=ui;before=business_dump(store);w.set_large_mode(True);w.motion_button.trigger()
    assert not w.property('motionEnabled') and not running(w)
    w.select_route('demand','dynamics');w.analytics.chart_tabs.setCurrentIndex(2)
    assert not running(w) and store.get('ui_preferences')['large_mode']
    w.save_workspace();restored=MainWindow(store);restored.show();app.processEvents()
    try:
        assert not restored.property('motionEnabled') and not restored.motion_button.isChecked() and restored.large_mode
        restored.set_large_mode(False);assert store.get('ui_preferences')['motion_enabled'] is False
        assert business_dump(store)==before
    finally:restored.close();restored.deleteLater();app.processEvents()


@pytest.mark.parametrize('size',[(900,280),(1100,430),(1660,600)])
def test_scaled_mix_legend_and_ring_use_the_same_hit_geometry(ui,size):
    app,store,w=ui;chart=MixChart();chart.resize(*size);chart.set_data(w.analytics.payload['composition'],w.analytics.payload['composition_total']);chart.show();app.processEvents()
    try:
        circle,left=chart.geometry_parts();top,step,right=chart.legend_geometry()
        assert circle.width()>min(size)*.55 and circle.width()<=size[1]
        assert right-left<=610 and right<=size[0] and left>circle.right()
        selected=[];chart.dishSelected.connect(selected.append)
        angle=0
        for index,row in enumerate(chart.rows):
            point=QPoint(round(left+30),round(top+(index+.5)*step))
            assert chart.row_at(point)==index
            QTest.mouseClick(chart,Qt.MouseButton.LeftButton,pos=point);assert selected[-1]==row['id']
            span=row['value']/chart.total*360;middle=math.radians(angle+span/2-90)
            radius=circle.width()/2-chart.ring_width()/2-4
            ring=QPointF(circle.center().x()+math.cos(middle)*radius,circle.center().y()+math.sin(middle)*radius)
            assert chart.row_at(ring)==index;angle+=span
    finally:chart.close();chart.deleteLater();app.processEvents()


def test_coverage_rows_fill_height_and_click_targets_follow_resize(ui):
    app,store,w=ui;chart=CoverageChart();chart.set_data(w.analytics.payload['coverage']);chart.show();selected=[];chart.ingredientSelected.connect(selected.append)
    try:
        for width,height in [(900,260),(1600,620)]:
            chart.resize(width,height);app.processEvents();top,step,left,right=chart.chart_geometry()
            assert step*len(chart.rows)>height*.78
            for index,row in enumerate(chart.rows):
                point=QPoint(round(left+(right-left)*.6),round(top+(index+.5)*step))
                assert chart.row_at(point)==index
                QTest.mouseClick(chart,Qt.MouseButton.LeftButton,pos=point);assert selected[-1]==str(row['id'])
            assert chart.row_at(QPoint(10,height-1)) is None
    finally:chart.close();chart.deleteLater();app.processEvents()


def test_timeline_uses_free_card_height_and_fast_navigation_does_not_write_data(ui):
    app,store,w=ui;before=business_dump(store);w.resize(1920,1030)
    for route in ['order','history','imports','settings','inventory','today','inventory']:w.select_route('stock',route)
    w.select_route('demand','dynamics');w.analytics.chart_tabs.setCurrentIndex(3);app.processEvents()
    panel=w.analytics.stock_timeline;assert panel.chart.height()>panel.height()*.7
    QTest.qWait(240);assert not running(w) and business_dump(store)==before
    assert not w.page_titles[0].graphicsEffect()


def test_closing_during_motion_stops_all_animation_callbacks(ui):
    app,store,w=ui;w.select_route('demand','dynamics');w.analytics.chart_tabs.setCurrentIndex(2)
    assert running(w)
    w.close();app.processEvents();assert not running(w)
