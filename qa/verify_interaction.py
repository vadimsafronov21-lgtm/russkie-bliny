"""Native verification of seven interaction features on a fresh synthetic database."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication,QFileDialog

from app import MainWindow,configure_application
from core import Store
from interaction_ui import CommandPalette,CompareOrdersDialog


def main():
    root=Path(__file__).resolve().parent
    output=root/'interaction-smoke'; output.mkdir(exist_ok=True)
    data_root=root/'interaction-data'; data_root.mkdir(exist_ok=True)
    data=Path(tempfile.mkdtemp(prefix='run-',dir=data_root))
    application=QApplication([]); application.setQuitOnLastWindowClosed(False); configure_application(application)
    store=Store(data/'data.sqlite3'); store.seed()
    window=MainWindow(store); window.show(); dialogs=[]; restored=None
    try:
        window.resize(1280,800); window.select_route('stock','inventory'); window.stock_table.selectRow(0); window.open_selected_card()
        application.processEvents(); window.grab().save(str(output/'ingredient-1280.png'))
        assert window.ingredient_card.ingredient=='dough'
        window._make_order(); window.edit_current_quantity(window.current['rows'][0],2,'ДЕМО: дополнительный запас')
        window.refresh_order(); window.undo_last_edit()
        assert not window.current['edits']
        application.processEvents(); window.grab().save(str(output/'undo.png'))
        window.edit_current_quantity(window.current['rows'][0],3,'ДЕМО: большой заказ'); window.refresh_order(); window.stock_check.setChecked(True)
        original=QFileDialog.getSaveFileName
        try:
            QFileDialog.getSaveFileName=lambda *args,**kwargs:(str(output/'order.xlsx'),'Excel (*.xlsx)')
            window._confirm_order()
        finally: QFileDialog.getSaveFileName=original
        assert (output/'order.xlsx').exists() and len(window.notifications.actions)==3
        application.processEvents(); window.grab().save(str(output/'notification.png'))
        window._make_order(); window.edit_current_quantity(window.current['rows'][0],4,'ДЕМО: уточнение потребности')
        window.refresh_order(); window.stock_check.setChecked(True); store.confirm(window.pid(),window.current,'ДЕМО'); window.reload()
        comparison=CompareOrdersDialog(store,window.pid(),window); dialogs.append(comparison); comparison.show()
        application.processEvents(); comparison.grab().save(str(output/'comparison.png'))
        assert comparison.comparison is not None; comparison.close()
        palette=CommandPalette(window.command_entries(),window); dialogs.append(palette); palette.search.setText('сверить'); palette.show()
        application.processEvents(); palette.grab().save(str(output/'commands.png'))
        assert palette.results.count()==7; palette.close()
        window.select_route('demand','months'); window.analytics.set_period(14); window.chart_dish.setCurrentIndex(2)
        dish=window.chart_dish.currentData(); window.search.setText('Сыр'); window.close()
        restored=MainWindow(store); restored.show(); application.processEvents()
        assert restored.active_view=='months' and restored.analytics.days==14 and restored.chart_dish.currentData()==dish
        assert restored.search.text()=='Сыр'
        restored.grab().save(str(output/'restored-workspace.png'))
        restored.search.clear(); restored.select_route('stock','inventory'); restored.stock_table.selectRow(0); restored.open_selected_card()
        restored.resize(1366,900); restored.set_large_mode(True); application.processEvents()
        restored.grab().save(str(output/'large-1366.png'))
        assert restored.large_button.isChecked()
        result=dict(status='PASS',synthetic=True,data_dir=str(data),features=[
            'auditable draft undo','restored workspace','ingredient side card','command palette',
            'nonmodal export notification','frozen order comparison','large interface mode'])
        result['source_sha256']={name:hashlib.sha256((root.parent/name).read_bytes()).hexdigest() for name in
             ('app.py','navigation.py','interaction.py','interaction_ui.py','operations_ui.py','workflows.py')}
        (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        for dialog in reversed(dialogs): dialog.close()
        if restored is not None: restored.close()
        window.close(); store.db.close(); application.processEvents()


if __name__=='__main__': main()
