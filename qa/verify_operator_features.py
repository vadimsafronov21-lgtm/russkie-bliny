"""Run all six operator features using a fresh, explicitly synthetic database."""
import copy
import hashlib
import json
import sys
import tempfile
from datetime import date,datetime,time,timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QElapsedTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import MainWindow,configure_application
from core import Store,calculate
from dalion_demo import DalionDemoDialog
from exchange_review import prepare_import
from operations import export_pilot,mark_availability,record_forecasts,work_session
from operations_ui import ReviewImportDialog,WhatIfDialog


def main():
    root=Path(__file__).resolve().parent
    output=root/'operator-features-smoke'; output.mkdir(exist_ok=True)
    data_root=root/'operator-features-data'; data_root.mkdir(exist_ok=True)
    data=Path(tempfile.mkdtemp(prefix='run-',dir=data_root))
    application=QApplication([]); application.setQuitOnLastWindowClosed(False); configure_application(application)
    store=Store(data/'data.sqlite3'); store.seed(); window=MainWindow(store); window.show()
    dialogs=[]
    try:
        window.select_route('stock','today'); application.processEvents()
        window.grab().save(str(output/'today.png'))
        window.resize(1280,800); application.processEvents(); window.grab().save(str(output/'today-1280.png')); window.resize(1560,1020)
        scenario=WhatIfDialog(store,'central',date.today(),window); dialogs.append(scenario)
        scenario.delay.setValue(2); scenario.demand.setValue(20); scenario.extra.setValue(30); scenario.compare(); scenario.show()
        application.processEvents(); scenario.grab().save(str(output/'what-if.png')); scenario.close()

        yesterday=date.today()-timedelta(days=1)
        def at(day,hour): return datetime.combine(day,time(hour),datetime.now().astimezone().tzinfo).isoformat()
        mark_availability(store,'central','classic',0,'ДЕМО','Синтетический пример отсутствия',at(yesterday,10))
        mark_availability(store,'central','classic',1,'ДЕМО',at=at(yesterday,12))
        window.select_route('demand','availability'); application.processEvents(); window.grab().save(str(output/'availability.png'))
        issued_day=date.today()-timedelta(days=2); tables=copy.deepcopy(store.get('tables'))
        tables['schedules'][0]['next_delivery']=(issued_day+timedelta(days=1)).isoformat()
        payload=calculate(tables,'central',issued_day,{})
        record_forecasts(store,'central',payload,issued=at(issued_day,10))
        work_session(store,'central','ДЕМО',at=at(yesterday,9))
        work_session(store,'central','ДЕМО',finish=True,at=at(yesterday,10))
        window.select_route('demand','pilot'); application.processEvents(); window.grab().save(str(output/'pilot.png'))
        assert window.pilot_result['forecast_count']>0
        export_pilot(output/'pilot.xlsx',window.pilot_result)

        with store.db: store.put('seeded_demo',False); store.put('exchange_base',store.get('tables'))
        incoming=store.get('tables'); incoming['batches'][0]['qty']=25
        store.correct_batch('b0',8,True,'Синтетическая ручная сверка','ДЕМО')
        plan=prepare_import(store,incoming,True,'Демо обновления ДАЛИОН','operator-smoke-update')
        review=ReviewImportDialog(store,plan,'ДЕМО',window); dialogs.append(review); review.show()
        application.processEvents(); review.grab().save(str(output/'exchange-conflict.png'))
        review.choices[0].setCurrentIndex(1); review.reason.setText('Демо: оставлен фактический пересчёт'); review.apply()
        assert next(row for row in store.get('tables')['batches'] if row['id']=='b0')['qty']==8

        demo=DalionDemoDialog(window,root=data/'situations'); dialogs.append(demo); demo.show(); directories=[]
        for index in range(demo.scenario_choice.count()):
            demo.scenario_choice.setCurrentIndex(index); demo.fetch()
            timer=QElapsedTimer(); timer.start()
            while demo.worker.isRunning() and timer.elapsed()<6000:
                application.processEvents(); QTest.qWait(10)
            application.processEvents(); assert demo.snapshot is not None
            demo.open_analysis(); application.processEvents()
            directories.append(str(demo.workspace.directory))
        demo.grab().save(str(output/'situations.png')); demo.close()
        assert len(set(directories))==4
        result={'status':'PASS','synthetic':True,'database':str(data),'features':[
            'daily actions','what-if isolated calculation','review and conflict resolution',
            'availability intervals','prospective pilot report and Excel','four isolated demo situations'],
            'checked_forecasts':window.pilot_result['forecast_count'],'scenario_databases':directories}
        source_root=root.parent
        result['source_sha256']={name:hashlib.sha256((source_root/name).read_bytes()).hexdigest() for name in
            ('app.py','core.py','navigation.py','operations.py','operations_ui.py','exchange_review.py','dalion_demo.py','demo_scenarios.py','customer_demo.py')}
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        for dialog in reversed(dialogs): dialog.close()
        window.day_timer.stop(); window.close(); store.db.close()
        application.processEvents()


if __name__=='__main__': main()
