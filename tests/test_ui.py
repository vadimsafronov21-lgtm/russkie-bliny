import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from app import MainWindow,STYLE
from core import Store

def test_recalculation_keeps_manual_edits_and_offline_draft(tmp_path):
    application=QApplication.instance() or QApplication([])
    application.setStyleSheet(STYLE)
    store=Store(tmp_path/'ui.sqlite3'); store.seed()
    window=MainWindow(store); window._make_order()
    window.current['edits']={'dough':{'packs':0,'reason':'Проверка','author':'Тест','at':'2026-10-20T10:00:00+07:00'}}
    window.save_current(); window.offline.setChecked(True)
    store.correct_batch('b0',10,True,'Пересчет','Тест'); window.reload(); window._make_order()
    assert window.current['edits']['dough']['packs']==0
    assert window.current['rows'][0]['packs']>0
    assert not window.stock_check.isChecked()
    window.stock_check.setChecked(True)
    assert store.get('draft:central')['stock_confirmed']
    window.close(); store.db.close()
