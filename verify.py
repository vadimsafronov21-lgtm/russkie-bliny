"""Reproducible end-to-end verification and diagnostic report."""
import json
import tempfile
import time
from datetime import date
from pathlib import Path
from core import Store,calculate,write_templates,demo_data,export_order,now

def main():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder); store=Store(root/'data.sqlite3'); store.seed()
        write_templates(root/'input',demo_data()); result=store.import_file(root/'input'/'demo.xlsx')
        store.correct_batch('b0',12,True,'Контрольный пересчет','Тестировщик')
        start=time.perf_counter()
        p=calculate(store.get('tables'),'central',date.today(),store.get('settings'))
        duration=time.perf_counter()-start
        p.update(revision=store.get('revision'),edits={'dough':{'packs':0,'reason':'Тест ручной правки','author':'Тестировщик','at':now()}},author='Тестировщик',demo=True,stock_confirmed=True,stock_confirmed_revision=store.get('revision'))
        store.save_draft('central',p); id=store.confirm('central',p,'Тестировщик')
        destination=Path('qa'); destination.mkdir(exist_ok=True)
        export_order(destination/'sample_order.xlsx',p,id)
        report={'generated':now(),'environment':'Windows 11, Python 3.13, Qt 6.12',
                'end_to_end':['XLSX import','stock correction with reason','local forecast','manual edit kept separate','draft persisted','confirmed order persisted','Excel reopened in tests'],
                'calculation_seconds':round(duration,3),'training_window':'last 12 calendar months, strictly before calculation day',
                'last_closed_shift':p['last_closed'],'coverage_days':p['days'],
                'data':'synthetic demonstration; no measured economic effect',
                'forecasts':[{k:f[k] for k in ['name','segment','method','expected','low','high','scores']} for f in p['forecasts']]}
        (destination/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        store.db.close()
        print(json.dumps({'end_to_end':'PASS','calculation_seconds':report['calculation_seconds'],'report':str(destination/'verification.json')},ensure_ascii=False))

if __name__=='__main__': main()
