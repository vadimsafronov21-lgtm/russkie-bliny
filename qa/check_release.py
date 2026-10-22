"""Render changed workflows at laptop size; use a disposable demo database."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QScrollArea
from app import MainWindow,configure_application
from core import Store
from workflows import QuantityDialog,OrderDetailsDialog

application=QApplication([]); configure_application(application)
folder=ROOT/'qa'/'release-layout'; folder.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    store=Store(Path(temp)/'data.sqlite3'); store.seed(); window=MainWindow(store)
    window.resize(1280,800); window.show(); application.processEvents()
    window.grab().save(str(folder/'overview.png'))
    window.analytics.findChild(QScrollArea).ensureWidgetVisible(window.analytics.stock_timeline)
    application.processEvents(); window.grab().save(str(folder/'timeline.png'))
    window._make_order(); payload=window.current
    preview=QuantityDialog(payload,payload['rows'][0],None,lambda *args:None,window)
    preview.resize(830,660); preview.show(); application.processEvents()
    preview.qty.setValue(0); preview.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click(); application.processEvents()
    assert preview.height()==660
    preview.grab().save(str(folder/'preview-validation.png')); preview.close()
    window.stock_check.setChecked(True); order_id=store.confirm(window.pid(),window.current,'Проверка')
    details=OrderDetailsDialog(store.get_order(order_id),'Центральная',lambda *args:None,window)
    details.resize(1060,660); details.show(); application.processEvents()
    assert details.height()==660
    details.grab().save(str(folder/'order-details.png')); details.close()
    tables=store.get('tables'); tables['schedules']=[]
    with store.db: store.put('tables',tables)
    window.reload(); window.navigate(2); application.processEvents(); window.grab().save(str(folder/'missing-schedule.png'))
    window.navigate(4); application.processEvents(); window.grab().save(str(folder/'settings.png'))
    (folder/'result.json').write_text(json.dumps({'result':'PASS','main_window':[window.width(),window.height()],
        'preview':[830,660],'details':[1060,660],'missing_schedule':window.calculation_error},ensure_ascii=False,indent=2),encoding='utf-8')
    window.close(); store.db.close()
