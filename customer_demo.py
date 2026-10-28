"""Launch the six operator features on a fresh synthetic database."""
import argparse
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from app import MainWindow,configure_application
from dalion_exchange import DemoWorkspace,parse_snapshot
from demo_scenarios import scenario_payload
import json


def main():
    parser=argparse.ArgumentParser(description='Демонстрация шести функций КРОНА на отдельной базе')
    parser.add_argument('--demo-root',type=Path,default=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'RusskieBliny-CustomerDemo')
    parser.add_argument('--smoke',type=Path,help='Сохранить стартовый экран и завершить демонстрацию')
    args=parser.parse_args()
    application=QApplication(sys.argv); configure_application(application)
    workspace=DemoWorkspace(args.demo_root)
    try:
        workspace.import_snapshot(parse_snapshot(json.dumps(scenario_payload('normal'),ensure_ascii=False).encode('utf-8')))
        window=MainWindow(workspace.store); window.setWindowTitle('КРОНА · ДЕМО новых функций · Отдельная база')
        window.select_route('stock','today'); window.show()
        if args.smoke:
            def capture():
                args.smoke.parent.mkdir(parents=True,exist_ok=True)
                window.grab().save(str(args.smoke)); window.close(); application.quit()
            QTimer.singleShot(200,capture)
        return application.exec()
    finally: workspace.close()


if __name__=='__main__': sys.exit(main())
