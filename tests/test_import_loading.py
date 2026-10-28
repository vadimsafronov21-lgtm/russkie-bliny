import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import pytest
from core import DataError,Store,demo_data,write_templates
from exchange_review import prepare_file_import
from PySide6.QtWidgets import QApplication,QDialog,QFileDialog
from app import MainWindow
from operations_ui import ReviewImportDialog
from ui_theme import configure_application


@pytest.fixture(scope='module')
def application():
    application=QApplication.instance() or QApplication([])
    configure_application(application)
    return application


@pytest.mark.parametrize('preview',[False,True])
def test_empty_workbook_cannot_erase_existing_data(tmp_path,preview):
    store=Store(tmp_path/'data.sqlite3'); store.seed()
    write_templates(tmp_path/'blank')
    before=list(store.db.iterdump())
    try:
        with pytest.raises(DataError,match='пуст|Пуст|заполн'):
            if preview: prepare_file_import(store,tmp_path/'blank/import_template.xlsx')
            else: store.import_file(tmp_path/'blank/import_template.xlsx')
        assert list(store.db.iterdump())==before
    finally: store.db.close()


def test_template_export_does_not_overwrite_demo_files(tmp_path):
    write_templates(tmp_path,demo_data())
    before={p.name:p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(DataError,match='существ|перезапис'):
        write_templates(tmp_path)
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir()}==before


def test_empty_points_csv_cannot_remove_point(tmp_path):
    store=Store(tmp_path/'data.sqlite3'); store.seed()
    write_templates(tmp_path/'blank')
    before=list(store.db.iterdump())
    try:
        with pytest.raises(DataError,match='пуст|Пуст|точк'):
            prepare_file_import(store,tmp_path/'blank/points.csv','points')
        assert list(store.db.iterdump())==before
    finally: store.db.close()


def test_main_import_button_applies_review_and_refreshes_stock(tmp_path,application,monkeypatch):
    source=demo_data(); source['batches'][0]['qty']=25
    write_templates(tmp_path/'source',source)
    store=Store(tmp_path/'data.sqlite3'); store.seed(); window=MainWindow(store)
    errors=[]; window.error=errors.append
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(tmp_path/'source/demo.xlsx'),''))
    def accept_review(dialog):
        dialog.apply()
        assert dialog.result is not None
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(ReviewImportDialog,'exec',accept_review)
    try:
        window.import_data()
        assert not errors
        assert store.get('tables')['batches'][0]['qty']==25
        assert window.snapshot and window.stock_table.rowCount()>0
        assert next(row for row in window.snapshot['rows'] if row['id']=='dough')['stock']==25
    finally: window.close(); store.db.close()


def test_main_import_button_reports_empty_template_without_writes(tmp_path,application,monkeypatch):
    write_templates(tmp_path/'source')
    store=Store(tmp_path/'data.sqlite3'); store.seed(); window=MainWindow(store)
    errors=[]; window.error=errors.append; before=store.get('tables')
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(tmp_path/'source/import_template.xlsx'),''))
    try:
        window.import_data()
        assert len(errors)==1 and 'Пустой шаблон' in str(errors[0])
        assert store.get('tables')==before and window.stock_table.rowCount()>0
    finally: window.close(); store.db.close()


def test_main_template_export_uses_new_subfolder_when_files_exist(tmp_path,application,monkeypatch):
    write_templates(tmp_path/'source',demo_data())
    original=(tmp_path/'source/points.csv').read_bytes()
    store=Store(tmp_path/'data.sqlite3'); store.seed(); window=MainWindow(store)
    exports=[]; window.notify_export=lambda message,path:exports.append(path)
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args:str(tmp_path/'source'))
    try:
        window.templates(False)
        assert (tmp_path/'source/points.csv').read_bytes()==original
        assert len(exports)==1 and exports[0].is_file()
        assert exports[0].parent!=tmp_path/'source'
    finally: window.close(); store.db.close()
