"""Capture the revised native UI and check geometry on separate synthetic data."""
import argparse
import json
import sys
from pathlib import Path
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPoint,QRect
from PySide6.QtWidgets import QApplication,QLabel
from app import MainWindow
from core import Store
from release_checks import check_audit_fixes
from ui_theme import configure_application

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
app=QApplication([]);configure_application(app);store=Store(args.data/'data.sqlite3');store.seed()
settings=store.get('settings');settings.update(author='Проверка',terminal_name='Демо-терминал')
with store.db:store.put('settings',settings)
window=MainWindow(store);window.show();geometry=[]
def settle():app.processEvents();app.processEvents()
def capture(name):settle();assert window.grab().save(str(args.output/(name+'.png')))
def rect(widget):return QRect(widget.mapTo(window,QPoint()),widget.size())
try:
    check_audit_fixes(window,args.output,app);window.notifications.hide()
    for large in (False,True):
        window.resize(1280,800);window.set_large_mode(large,persist=False);window._make_order();settle()
        viewport=rect(window.order_table.viewport())
        for control in (window.edit_order_btn,window.stock_check,window.confirm_btn):
            assert not viewport.intersects(rect(control))
            assert window.rect().contains(rect(control)),control.text()
        capture('order-draft-1280-large'+str(int(large)))
        window.select_route('stock','settings');capture('settings-1280-large'+str(int(large)))
        window.settings_sections['assortment'].setExpanded(True);window.reveal_settings_field(window.item_settings)
        capture('settings-assortment-1280-large'+str(int(large)));window.settings_sections['assortment'].setExpanded(False)
        window.select_route('stock','imports');capture('import-1280-large'+str(int(large)))
        window.import_preparation.setExpanded(True);capture('import-preparation-1280-large'+str(int(large)));window.import_preparation.setExpanded(False)
        window.select_route('demand','dynamics');panel=window.analytics
        for index,name in enumerate(['sales','coverage','composition','timeline']):
            panel.chart_tabs.setCurrentIndex(index);capture('demand-'+name+'-1280-large'+str(int(large)))
        window.select_route('demand','months');capture('months-1280-large'+str(int(large)))
        window.select_route('stock','today');capture('today-1280-large'+str(int(large)))
        window.select_route('demand','pilot');capture('pilot-1280-large'+str(int(large)))
    window.select_route('stock','inventory');window.search.clear();window.filter.setCurrentIndex(0)
    tables=store.get('tables');tables['schedules'][0]['next_delivery']=(date.today()-timedelta(days=2)).isoformat()
    with store.db:store.put('tables',tables)
    window.reload();footnote=next(w for w in window.findChildren(QLabel) if w.text().startswith('¹ По норме'))
    for width in (1180,1280,1560):
        for large in (False,True):
            window.resize(width,800 if width<1560 else 1020);window.set_large_mode(large,persist=False)
            window.notify('Настройки требуют проверки.');settle()
            viewport=rect(window.stock_table.viewport());footer=rect(footnote);details=rect(window.details_button)
            assert not viewport.intersects(footer) and not viewport.intersects(details)
            geometry.append(dict(width=width,large=large,expired=True,notice=True,overlap=False))
            capture(f'overview-expired-{width}-large{int(large)}')
    (args.output/'visual-result.json').write_text(json.dumps(dict(status='PASS',synthetic=True,
        geometry=geometry,order_controls_do_not_overlap=True),ensure_ascii=False,indent=2),encoding='utf-8')
finally:window.close();store.db.close();app.processEvents()
