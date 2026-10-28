"""Exercise bundled operator modules from --smoke on an isolated demo database."""
from datetime import date
import json
from pathlib import Path
import sys

from PySide6.QtWidgets import QDialog

from core import DataError,FileAdapter,Store,now,write_templates
from dalion_demo import DalionDemoDialog
from exchange_review import prepare_import
from interaction_ui import CommandPalette,CompareOrdersDialog
from operations import export_pilot,record_forecasts
from operations_ui import ReviewImportDialog,WhatIfDialog


def run_feature_checks(window,folder,application):
    if not window.store.get('demo'):
        raise DataError('Проверка сборки требует отдельной базы с синтетическими данными.')
    folder=Path(folder); store=window.store; steps=[]
    startup_store=Store(folder/'startup-check'/'data.sqlite3'); startup_store.seed()
    tables=startup_store.get('tables'); tables['schedules'][0]['next_delivery']='2020-01-01'
    with startup_store.db:
        startup_store.put('tables',tables)
        startup_store.put('ui_workspace:central',dict(version=1,domain='stock',view='order',filter=1))
    startup_window=window.__class__(startup_store)
    try:
        startup_window.show(); application.processEvents()
        assert startup_window.snapshot is None and startup_window.stock_table.rowCount()==7
        assert startup_window.active_view=='inventory'
        startup_window.stock_table.selectRow(0); startup_window.open_selected_card()
        assert '14.00' in startup_window.ingredient_card.summary.text()
        assert startup_store.get('tables')==tables
        startup_window.grab().save(str(folder/'startup-existing-data.png'))
    finally:
        startup_window.close(); startup_window.deleteLater(); application.processEvents(); startup_store.db.close()
    steps.append('startup actual stock with expired schedule and saved workspace')
    blank=folder/'blank-template'; write_templates(blank)
    try:
        FileAdapter().read(blank/'import_template.xlsx')
    except DataError: pass
    else: raise AssertionError('An empty template must be rejected')
    original=(blank/'points.csv').read_bytes()
    try: write_templates(blank,store.get('tables'))
    except DataError: pass
    else: raise AssertionError('Existing templates must not be overwritten')
    assert (blank/'points.csv').read_bytes()==original
    from PySide6.QtWidgets import QFileDialog
    source=folder/'button-import'; incoming=store.get('tables'); incoming['batches'][0]['qty']+=1
    write_templates(source,incoming)
    original_picker=QFileDialog.getOpenFileName; original_review=ReviewImportDialog.exec
    def accept_review(dialog):
        for choice in dialog.choices: choice.setCurrentIndex(2)
        dialog.reason.setText('Проверка импорта в сборке')
        dialog.apply(); assert dialog.result is not None
        return QDialog.DialogCode.Accepted
    try:
        QFileDialog.getOpenFileName=lambda *args:(str(source/'demo.xlsx'),'')
        ReviewImportDialog.exec=accept_review
        window.import_data()
        assert store.get('tables')['batches'][0]['qty']==incoming['batches'][0]['qty']
    finally:
        QFileDialog.getOpenFileName=original_picker; ReviewImportDialog.exec=original_review
    steps.append('file import button and empty-template protection')
    window.select_route('stock','today'); application.processEvents()
    assert window.daily_table.rowCount()>0
    window.grab().save(str(folder/'features-today.png')); steps.append('daily actions')
    scenario=WhatIfDialog(store,window.pid(),date.today(),window)
    scenario.delay.setValue(2); scenario.demand.setValue(20); scenario.extra.setValue(30); scenario.compare()
    assert scenario.result and scenario.result['scenario']
    scenario.show(); application.processEvents(); scenario.grab().save(str(folder/'features-what-if.png')); scenario.close()
    steps.append('isolated what-if calculation')

    window._make_order(); row=window.current['rows'][0]
    window.edit_current_quantity(row,2,'Проверка сборки: ручное количество'); window.refresh_order()
    window.undo_last_edit(); assert row['id'] not in window.current['edits']
    window.edit_current_quantity(window.current['rows'][0],3,'Проверка сборки: новая правка'); window.refresh_order()
    window.stock_check.setChecked(True); order_id=store.confirm(window.pid(),window.current,'Проверка сборки')
    window.reload(); assert not window.undo_button.isEnabled(); steps.append('auditable draft undo and confirmed lock')
    comparison=CompareOrdersDialog(store,window.pid(),window); assert comparison.comparison
    comparison.show(); application.processEvents(); comparison.grab().save(str(folder/'features-comparison.png')); comparison.close()
    steps.append('frozen order comparison')
    window.select_route('stock','inventory'); window.stock_table.selectRow(0); window.open_selected_card()
    assert window.ingredient_card.ingredient==str(row['id'])
    application.processEvents(); window.grab().save(str(folder/'features-ingredient.png')); steps.append('ingredient side card')
    palette=CommandPalette(window.command_entries(),window); palette.search.setText('сверить тесто')
    assert palette.results.count()==1
    palette.show(); application.processEvents(); palette.grab().save(str(folder/'features-commands.png')); palette.close()
    steps.append('command palette')
    window.set_large_mode(True); application.processEvents(); window.grab().save(str(folder/'features-large.png'))
    assert window.large_button.isChecked(); window.set_large_mode(False); steps.append('persistent large mode')
    window.search.setText('Сыр'); window.select_route('demand','months'); window.analytics.set_period(14); window.save_workspace()
    saved=store.get('ui_workspace:'+window.pid()); assert saved['view']=='months' and saved['period']==14 and saved['search']=='Сыр'
    steps.append('workspace persistence')
    window.notify_export('Проверка экспорта собранной программы.',folder/'packaged_order.xlsx',order_id)
    assert len(window.notifications.actions)==3
    application.processEvents(); window.grab().save(str(folder/'features-notification.png')); steps.append('nonmodal export actions')

    window.select_route('demand','availability'); window.availability_table.selectRow(0)
    window.set_availability(False); window.set_availability(True)
    assert window.availability_log.rowCount()>=2; steps.append('availability journal')
    window.select_route('demand','pilot'); window.capture_pilot()
    assert store.db.execute('SELECT COUNT(*) FROM pilot_forecasts').fetchone()[0]>0
    export_pilot(folder/'packaged_pilot.xlsx',window.pilot_result); steps.append('prospective pilot and Excel')

    with store.db:
        store.put('seeded_demo',False); store.put('exchange_base',store.get('tables'))
    incoming=store.get('tables'); incoming['batches'][0]['qty']=25
    batch=incoming['batches'][0]
    store.correct_batch(batch['id'],8,True,'Проверка конфликта сборки','Проверка сборки')
    plan=prepare_import(store,incoming,True,'Проверка сборки','release-check-update')
    review=ReviewImportDialog(store,plan,'Проверка сборки',window)
    assert len(review.choices)==1
    review.choices[0].setCurrentIndex(1); review.reason.setText('Сохраняем сверенный остаток'); review.apply()
    assert review.result and next(row for row in store.get('tables')['batches'] if row['id']==batch['id'])['qty']==8
    steps.append('atomic exchange conflict resolution')

    demo=DalionDemoDialog(window,root=folder/'demo-data'); demo.show(); directories=[]
    try:
        for index in range(demo.scenario_choice.count()):
            demo.scenario_choice.setCurrentIndex(index); demo.fetch()
            assert demo.worker.wait(10000), 'Demo HTTP worker timeout'
            application.processEvents(); assert demo.snapshot is not None
            demo.open_analysis(); application.processEvents()
            assert demo.analysis_window is not None and demo.workspace.store.get('demo')
            directories.append(str(demo.workspace.directory))
        assert len(set(directories))==4
        demo.grab().save(str(folder/'features-dalion.png'))
    finally: demo.close()
    steps.extend(['local DALION HTTP adapter','four independent demonstration scenarios'])
    window.search.clear(); window.reload()
    report=dict(status='PASS',frozen=bool(getattr(sys,'frozen',False)),time=now(),steps=steps)
    (folder/'features-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
