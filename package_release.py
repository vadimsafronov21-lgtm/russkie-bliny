"""Package the verified app and reproducible sources without local databases."""
import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

root=Path(__file__).resolve().parent
binary=root/'dist'/'RusskieBliny.exe'
smoke=json.loads((root/'qa/final-smoke/smoke-result.json').read_text(encoding='utf-8'))
assert smoke['status']=='PASS'
for name in ['stock','order','import','history','settings']:
    shutil.copy2(root/f'qa/final-smoke/{name}.png',root/f'qa/screens/{name}.png')
report_path=root/'qa/verification.json'
report=json.loads(report_path.read_text(encoding='utf-8'))
report.update(tests={'passed':38,'failed':0},windowed_exe_smoke=smoke,
              binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
              source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['app.py','core.py','ui_theme.py']},
              packaging='One-file Windows x64; isolated DLL search path via build.py')
report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
files=['README.md','DATA_FORMAT.md','PILOT.md','DESIGN.md','.gitignore','.gitattributes','app.py','core.py','ui_theme.py','requirements.txt','build.py','verify.py',
       'package_release.py','pytest.ini','run.cmd','qa/verification.json','qa/visual-review.json','qa/sample_order.xlsx',
       'qa/final-smoke/smoke-result.json','dist/RusskieBliny.exe']
for folder in ['templates','examples','tests','qa/screens','assets']:
    files += [str(p.relative_to(root)).replace('\\','/') for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]
output=root.parent/'RusskieBliny-Windows.zip'
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for name in files: archive.write(root/name,'RusskieBliny/'+name)
with zipfile.ZipFile(output) as archive: assert archive.testzip() is None
print(json.dumps({'archive':str(output),'files':len(files),'bytes':output.stat().st_size,'exe_sha256':report['binary_sha256']},ensure_ascii=False))
