"""Native hover evidence on an isolated synthetic database; never uses operator data."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from app import MainWindow
from core import Store
from release_checks import check_chart_tab_hover
from ui_theme import configure_application

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--data',type=Path,required=True);args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
application=QApplication([]);configure_application(application)
store=Store(args.data/'data.sqlite3');store.seed();window=MainWindow(store);window.resize(1560,1020);window.show()
try:
    for width,height in [(1560,1020),(1280,800)]:
        window.resize(width,height)
        target=args.output/str(width);target.mkdir(exist_ok=True)
        check_chart_tab_hover(window,target,application)
    (args.output/'result.json').write_text(json.dumps(dict(status='PASS',synthetic=True,
        sizes=[[1560,1020],[1280,800]],modes=['normal','large'],hover_positions=5,
        checks=['tab backgrounds','selected underline','stable geometry']),indent=2),encoding='utf-8')
finally:
    window.close();store.db.close();application.processEvents()
