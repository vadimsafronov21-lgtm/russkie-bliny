"""Real Qt frames and responsive charts on fresh synthetic data, plus an idle sample."""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QAbstractAnimation,QRect
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import MainWindow
from core import Store
from ui_motion import finish_motion
from ui_theme import configure_application

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
app=QApplication([]);configure_application(app);store=Store(args.data/'data.sqlite3');store.seed()
settings=store.get('settings');settings.update(author='Проверка',terminal_name='Демо-терминал')
with store.db:store.put('settings',settings)
w=MainWindow(store);w.show();results=[]
try:
    for width,height in [(1280,800),(1560,1020),(1920,1030)]:
        for large in (False,True):
            w.resize(width,height);w.set_large_mode(large,persist=False);w.select_route('demand','dynamics')
            for index,name in [(1,'coverage'),(2,'composition'),(3,'timeline')]:
                w.analytics.chart_tabs.setCurrentIndex(index);app.processEvents();app.processEvents();finish_motion(w)
                assert w.grab().save(str(args.output/f'{name}-{width}-large{int(large)}.png'))
                p=w.analytics;circle=p.mix_chart.geometry_parts()[0];top,step,left,right=p.coverage_chart.chart_geometry()
                assert step*len(p.coverage_chart.rows)>p.coverage_chart.height()*.78
                assert circle.width()>min(p.mix_chart.width(),p.mix_chart.height())*.55
                results.append(dict(width=width,large=large,chart=name,circle_diameter=circle.width(),coverage_row_height=step,
                    timeline_height=p.stock_timeline.chart.height()))
    w.set_large_mode(False,persist=False);w.resize(1920,1030);w.select_route('stock','inventory');finish_motion(w);QTest.qWait(250)
    frames=args.output/'frames';frames.mkdir(exist_ok=True);timings=[]
    def record(count):
        for _ in range(count):
            app.processEvents();path=frames/f'{len(timings):03}.png'
            assert w.grab(QRect(0,0,1050,600)).save(str(path));timings.append(time.perf_counter());QTest.qWait(25)
    record(3)
    for route in ['history','order']:
        w.side_buttons[route].click();record(9)
    w.domain_buttons['demand'].click();record(9)
    for index in [1,2,3]:w.analytics.chart_tabs.setCurrentIndex(index);record(9)
    QTest.qWait(300);record(2)
    durations=[max(20,round((b-a)*1000)) for a,b in zip(timings,timings[1:])]+[650]
    (frames/'timing.json').write_text(json.dumps(durations),encoding='utf-8')
    QTest.qWait(450);assert not any(a.state()==QAbstractAnimation.State.Running for a in w.findChildren(QAbstractAnimation))
    wall=time.perf_counter();cpu=time.process_time();QTest.qWait(800)
    sample=dict(wall_ms=round((time.perf_counter()-wall)*1000,2),cpu_ms=round((time.process_time()-cpu)*1000,2),running_animations=0)
    report=dict(status='PASS',synthetic=True,geometry=results,idle_sample=sample,frame_count=len(timings))
    (args.output/'visual-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
finally:w.close();store.db.close();app.processEvents()
