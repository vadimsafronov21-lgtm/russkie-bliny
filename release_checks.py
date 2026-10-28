"""Exercise bundled operator modules from --smoke on an isolated demo database."""
from datetime import date,timedelta
import json
from pathlib import Path
import sys

from PySide6.QtWidgets import QDialog,QPushButton

from core import DataError,FileAdapter,Store,now,write_templates
from dalion_demo import DalionDemoDialog
from exchange_review import prepare_import
from interaction_ui import CommandPalette,CompareOrdersDialog
from operations import export_pilot,record_forecasts
from operations_ui import ReviewImportDialog,WhatIfDialog


def check_chart_tab_hover(window,folder,application):
    """Check actual pixels, including Fusion hover painting, in source and frozen Qt."""
    from PySide6.QtCore import QEvent,QPoint,QPointF,Qt
    from PySide6.QtGui import QColor,QMouseEvent
    window.select_route('demand','dynamics'); window.analytics.chart_tabs.setCurrentIndex(0)
    bar=window.analytics.chart_tabs.tabBar()
    for large in (False,True):
        window.set_large_mode(large,persist=False); application.processEvents()
        rects=[bar.tabRect(index) for index in range(4)]
        for hovered in (0,1,2,3,-1):
            pos=rects[hovered].center() if hovered>=0 else QPoint(-20,-20)
            event=QMouseEvent(QEvent.Type.MouseMove,QPointF(pos),QPointF(bar.mapToGlobal(pos)),
                             Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)
            application.sendEvent(bar,event); application.processEvents(); bar.finish_motion()
            pixels=bar.grab().toImage(); scale=pixels.devicePixelRatio()
            for index,rect in enumerate(rects):
                expected=QColor('#F9E8EB' if index==hovered else '#F6F6F8')
                for x in (rect.left()+3,rect.center().x(),rect.right()-3):
                    assert pixels.pixelColor(round(x*scale),round(rect.top()*scale))==expected
            selected=rects[0]
            assert pixels.pixelColor(round(selected.center().x()*scale),round((selected.bottom()-1)*scale))==QColor('#A4002A')
            assert rects==[bar.tabRect(index) for index in range(4)]
            if hovered==1:
                window.grab().save(str(Path(folder)/f'chart-hover-{"large" if large else "normal"}.png'))
    window.set_large_mode(False,persist=False)


def check_audit_fixes(window,folder,application):
    """Verify compact layouts and preserved routes in the actual packaged widgets."""
    from PySide6.QtCore import QPoint,QRect
    from PySide6.QtWidgets import QLabel
    def rect(widget): return QRect(widget.mapTo(window,QPoint()),widget.size())
    window.select_route('stock','inventory')
    footnote=next(item for item in window.findChildren(QLabel) if item.text().startswith('¹ По норме'))
    for width,height,large in [(1180,800,False),(1280,800,False),(1280,800,True),(1560,1020,False)]:
        window.resize(width,height); window.set_large_mode(large,persist=False)
        window.notify('Проверка компактного уведомления.'); application.processEvents(); application.processEvents()
        viewport=rect(window.stock_table.viewport())
        assert not viewport.intersects(rect(window.details_button)) and not viewport.intersects(rect(footnote))
        window.grab().save(str(Path(folder)/f'audit-overview-{width}-large{int(large)}.png'))
    window.select_route('demand','dynamics'); assert not window.notifications.isVisible()
    panel=window.analytics; panel.chart_tabs.setCurrentIndex(2); application.processEvents()
    assert not panel.dish_metrics.isVisible() and all(button.isVisible() for button in panel.period_buttons)
    panel.period_buttons[0].click(); assert panel.days==14 and 'всех блюд' in panel.mix_period.text()
    window.grab().save(str(Path(folder)/'audit-composition.png'))
    window.select_route('demand','months'); application.processEvents()
    assert [panel.chart_tabs.isTabVisible(i) for i in range(4)]==[True,False,False,False]
    window.select_route('stock','today'); window.daily_table.clearSelection(); application.processEvents()
    assert not window.daily_action_button.isEnabled()
    window.run_daily_action(); assert 'Выберите' in window.daily_status.text()
    window.select_route('demand','pilot'); assert window.work_button.isVisible()
    window.select_route('stock','imports'); application.processEvents()
    assert 'покажем изменения' in window.import_hint.text() and not window.import_preparation.body.isVisible()
    window.import_preparation.toggle.click(); application.processEvents(); assert window.import_preparation.body.isVisible()
    window.import_preparation.toggle.click(); window.grab().save(str(Path(folder)/'audit-import.png'))
    window.select_route('stock','settings'); application.processEvents()
    assert [k for k,v in window.settings_sections.items() if v.body.isVisible()]==['delivery']
    window.reveal_settings_field(window.author_input); assert window.settings_sections['terminal'].body.isVisible()
    window.settings_sections['terminal'].setExpanded(False); application.processEvents()
    window.grab().save(str(Path(folder)/'audit-settings.png'))
    window.select_route('stock','order'); application.processEvents()
    assert window.order_table.width()>window.width()-300
    if (window.current or {}).get('confirmed_order_id'):
        assert not window.stock_check.isVisible() and not window.undo_button.isVisible()
    window.grab().save(str(Path(folder)/'audit-order.png'))
    assert window.notifications.history and window.large_button in window.profile_menu.actions()


def check_motion_and_chart_scale(window,folder,application):
    from PySide6.QtCore import QAbstractAnimation,QEventLoop,QTimer
    from ui_motion import finish_motion
    def wait(ms):
        loop=QEventLoop(); QTimer.singleShot(ms,loop.quit); loop.exec()
    previous=bool(window.property('motionEnabled'));window.set_motion_enabled(True)
    window.select_route('stock','inventory');application.processEvents();finish_motion(window)
    button=window.side_buttons['history'];button.click();wait(50)
    assert button.isChecked() and 0<button._selected<1
    wait(210);assert button._selected==1
    window.select_route('demand','dynamics');window.resize(1920,1030);application.processEvents();finish_motion(window)
    tabs=window.analytics.chart_tabs;bar=tabs.tabBar();tabs.setCurrentIndex(1);wait(50)
    assert bar._line_animation.state()==QAbstractAnimation.State.Running and bar._line!=bar._target()
    tabs.setCurrentIndex(3);tabs.setCurrentIndex(2);wait(220)
    assert bar._line==bar._target() and window.analytics.mix_chart.geometry_parts()[0].width()>350
    window.grab().save(str(Path(folder)/'motion-large-composition.png'))
    tabs.setCurrentIndex(1);wait(210);chart=window.analytics.coverage_chart
    assert chart.chart_geometry()[1]*len(chart.rows)>chart.height()*.78
    window.grab().save(str(Path(folder)/'motion-large-coverage.png'))
    tabs.setCurrentIndex(3);wait(210);panel=window.analytics.stock_timeline
    assert panel.chart.height()>panel.height()*.7
    window.grab().save(str(Path(folder)/'motion-large-timeline.png'))
    assert not any(a.state()==QAbstractAnimation.State.Running for a in window.findChildren(QAbstractAnimation))
    window.set_motion_enabled(False);window.side_buttons['months'].click();application.processEvents()
    assert not any(a.state()==QAbstractAnimation.State.Running for a in window.findChildren(QAbstractAnimation))
    window.set_motion_enabled(previous)


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
        application.processEvents()
        startup_window.grab().save(str(folder/'startup-existing-data.png'))
        startup_window.select_route('stock','settings'); application.processEvents()
        save=next(button for button in startup_window.findChildren(QPushButton) if button.text()=='Сохранить настройки')
        revision=startup_store.get('revision'); save.click(); application.processEvents()
        assert startup_window.settings_error.isVisible() and startup_store.get('revision')==revision
        assert startup_store.get('tables')==tables
        startup_window.grab().save(str(folder/'settings-invalid-date.png'))
        startup_window.delivery_input.setDate(date.today()+timedelta(days=1)); save.click(); application.processEvents()
        assert startup_window.snapshot and not startup_window.calculation_error
        assert startup_window.active_view=='inventory' and len(startup_window.snapshot['rows'])==7 and startup_window.stock_table.rowCount()>0
        assert not startup_window.problem_box.isVisible() and startup_window.analytics.payload['forecast']
        startup_window.grab().save(str(folder/'settings-save-updated-data.png'))
    finally:
        startup_window.close(); startup_window.deleteLater(); application.processEvents(); startup_store.db.close()
    steps.append('startup actual stock with expired schedule and saved workspace')
    steps.append('settings button rejects expired dates and immediately refreshes data')
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
    application.processEvents(); window.grab().save(str(folder/'features-ingredient.png')); steps.append('separate ingredient details window')
    window.ingredient_dialog.grab().save(str(folder/'ingredient-separate-window.png')); window.close_ingredient_card()
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
    check_chart_tab_hover(window,folder,application); steps.append('chart hover pixels and underline in normal and large modes')
    check_audit_fixes(window,folder,application); steps.append('all seven scenario audit UI findings and compact layout geometry')
    check_motion_and_chart_scale(window,folder,application); steps.append('finite native motion, rapid retargeting, reduced motion and responsive chart geometry')
    window.search.clear(); window.reload()
    report=dict(status='PASS',frozen=bool(getattr(sys,'frozen',False)),time=now(),steps=steps)
    (folder/'features-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report
