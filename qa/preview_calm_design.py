"""Capture the actual desktop UI on fresh synthetic data for visual review."""
import argparse
import json
import sys
from datetime import date,timedelta
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
parser.add_argument('--output',type=Path,required=True);parser.add_argument('--data',type=Path,required=True);parser.add_argument('--before',action='store_true')
args=parser.parse_args();sys.path.insert(0,str(args.source.resolve()))
from PySide6.QtWidgets import QApplication
from app import MainWindow
from core import Store
from ui_theme import configure_application

args.output.mkdir(parents=True,exist_ok=True)
app=QApplication([]);configure_application(app);store=Store(args.data/'data.sqlite3');store.seed();window=MainWindow(store);window.show()
def capture(name,widget=None):
    app.processEvents();app.processEvents()
    if not args.before:
        from ui_motion import finish_motion
        finish_motion(window)
    target=widget or window
    assert target.grab().save(str(args.output/name))

try:
    window.resize(1560,1020);window.select_route('stock','inventory')
    if args.before:
        window.stock_table.selectRow(0);window.open_selected_card();capture('before-overview.png')
        window.select_route('demand','dynamics');capture('before-demand.png')
    else:
        for width,height in [(1560,1020),(1280,800),(1180,800)]:
            window.resize(width,height);capture(f'overview-{width}.png')
            assert window.stock_table.width()>width-290
        window.resize(1560,1020);window.stock_table.selectRow(0);window.details_button.click()
        capture('ingredient-window.png',window.ingredient_dialog)
        window.close_ingredient_card();window.select_route('demand','dynamics')
        for index,name in enumerate(['sales','coverage','composition','stock-timeline']):
            window.analytics.chart_tabs.setCurrentIndex(index);capture('demand-'+name+'.png')
        window.select_route('stock','inventory');window.set_large_mode(True);capture('overview-large.png');window.set_large_mode(False)
        tables=store.get('tables');tables['schedules'][0]['next_delivery']=(date.today()-timedelta(days=2)).isoformat()
        with store.db:store.put('tables',tables)
        window.point_changed();capture('overview-expired-schedule.png')
        assert window.snapshot is None and window.stock_table.rowCount()==7
        window.select_route('stock','settings');window.delivery_input.setDate(date.today()+timedelta(days=1));window.save_settings()
        assert window.snapshot and window.active_view=='inventory';capture('overview-after-settings.png')
    report=dict(status='PASS',source=str(args.source.resolve()),synthetic=True,before=args.before)
    (args.output/('before-result.json' if args.before else 'visual-result.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
finally:
    window.close();store.db.close();app.processEvents()
