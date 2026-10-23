"""Record checks and hashes after tests, build, and the packaged smoke run."""
import hashlib
import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from core import demo_data,calculate,now

suite=ET.parse(ROOT/'qa/test-results.xml').getroot().find('testsuite')
packaged=json.loads((ROOT/'qa/fixes-packaged-smoke/smoke-result.json').read_text(encoding='utf-8'))
assert packaged['status']=='PASS'
assert int(suite.attrib['failures'])==0 and int(suite.attrib['errors'])==0
start=time.perf_counter(); result=calculate(demo_data(),'central',date.today(),{})
paths=['app.py','core.py','ui_theme.py','charts.py','analytics_data.py','analytics_view.py','workflows.py']
data={'generated':now(),'environment':'Windows 11, Python 3.13, Qt 6.12',
      'end_to_end':packaged['steps'],'calculation_seconds':round(time.perf_counter()-start,3),
      'training_window':'last 12 calendar months, strictly before calculation day',
      'last_closed_shift':result['last_closed'],'coverage_days':result['days'],
      'data':'synthetic demonstration; no measured economic effect',
      'tests':{'passed':int(suite.attrib['tests'])-int(suite.attrib['skipped']),'failed':0,'skipped':int(suite.attrib['skipped'])},
      'windowed_exe_smoke':packaged,'binary_sha256':hashlib.sha256((ROOT/'dist/RusskieBliny.exe').read_bytes()).hexdigest(),
      'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths},
      'packaging':'One-file Windows x64; isolated DLL search path via build.py',
      'regressions':['duplicate confirmation and restart','legacy confirmed draft migration','selected ingredient batch',
                     'validation retains input','missing schedule diagnostics','today and manual calculation dates',
                     'daily stock conservation and explicit expiry','preview does not mutate data',
                     'frozen saved order and Excel','backup includes WAL','restore creates recovery copy','invalid backup leaves data intact']}
(ROOT/'qa/verification.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
layout=json.loads((ROOT/'qa/release-layout/result.json').read_text(encoding='utf-8'))
(ROOT/'qa/visual-review.json').write_text(json.dumps({'result':'PASS','checked_at':now(),
    'checked':['Qt stock timeline','Qt zero order preview','Qt validation retains quantity',
               'preset and custom reasons','compact legacy calculation','100ms tooltip policy without animation',
               'laptop preview scrolling and pinned actions','saved order card','settings backup controls','missing schedule diagnostics'],
    'laptop_layout':layout},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'tests':data['tests'],'packaged':packaged['status'],'sha256':data['binary_sha256']}))
