"""Seller dialogs: validate in place, preview decisions, inspect saved orders."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut,QKeySequence
import sqlite3
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QFrame,
    QDoubleSpinBox,QSpinBox,QCheckBox,QLineEdit,QDialogButtonBox,QPushButton,QTableWidgetItem,QTabWidget,QWidget,QScrollArea)
from core import DataError,order_impact
from charts import StockProjectionChart,num
from ui_theme import DataTable

ORDER_REASONS=['Ожидается большой заказ','Ожидается повышенный спрос','Ожидается снижение спроса',
    'Есть дополнительный запас','Планируется перемещение с другой точки','Изменился график поставок',
    'Ограничено место хранения','Возврат к рекомендации']
STOCK_REASONS=['Плановая сверка остатков','Расхождение при пересчёте','Списание по решению продавца',
    'Повреждение упаковки','Партия исключена по пригодности','Исправление ошибки ввода']
ITEM_SETTING_REASONS=['Изменилась упаковка поставщика','Уточнён целевой запас',
    'Настройка резерва для нового блюда','Корректировка по фактическому спросу',
    'Обновлена технологическая карта','Исправление ошибки ввода']

class ReasonPicker(QComboBox):
    def __init__(self,presets=ORDER_REASONS,recent=(),parent=None):
        super().__init__(parent); self.setEditable(True); self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.addItems(list(dict.fromkeys([*recent,*presets]))); self.setCurrentIndex(-1)
        self.lineEdit().setPlaceholderText('Выберите причину или напишите свою'); self.lineEdit().setClearButtonEnabled(True)
        self.setMaxVisibleItems(10); self.setMinimumWidth(250)
        self.setToolTip('Готовая причина выбирается из списка. Можно ввести собственную.')
    def text(self): return self.currentText().strip()
    def setText(self,value): self.setEditText(value)
    def setPlaceholderText(self,value): self.lineEdit().setPlaceholderText(value)

def remember_reason(store,kind,reason):
    store.put('reason_history:'+kind,list(dict.fromkeys([reason,*store.get('reason_history:'+kind,[])]))[:8])


def caption(value,kind='subtitle'):
    widget=QLabel(value); widget.setObjectName(kind); widget.setWordWrap(True); return widget


def dialog_buttons(dialog,layout,save):
    error=caption('','notice'); error.setProperty('validationError',True); error.hide(); layout.addWidget(error)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QDialogButtonBox.StandardButton.Save).setText('Сохранить')
    buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Отмена')
    def accept():
        try: save()
        except (DataError,ValueError,OSError,sqlite3.Error) as e:
            error.setText(str(e)); error.show(); return
        dialog.accept()
    buttons.accepted.connect(accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    buttons.validation_error=error
    shortcut=QShortcut(QKeySequence('Ctrl+Return'),dialog); shortcut.activated.connect(accept)
    buttons.button(QDialogButtonBox.StandardButton.Save).setToolTip('Сохранить · Ctrl+Enter')
    return buttons


class StockCorrectionDialog(QDialog):
    def __init__(self,store,batches,names,author,parent=None):
        super().__init__(parent); self.setWindowTitle('Сверка фактического остатка'); self.setMinimumWidth(560)
        box=QVBoxLayout(self); box.setContentsMargins(24,22,24,22); box.setSpacing(14)
        box.addWidget(caption(names[str(batches[0]['ingredient'])],'section'))
        form=QFormLayout(); box.addLayout(form)
        self.batch=QComboBox(); self.batch.setObjectName('batchChoice')
        for b in batches: self.batch.addItem(f'{names[str(b["ingredient"])]} · партия {b["id"]}',str(b['id']))
        self.info=caption(''); self.qty=QDoubleSpinBox(); self.qty.setObjectName('stockQuantity'); self.qty.setRange(0,100000); self.qty.setDecimals(3)
        self.usable=QCheckBox('Пригодность подтверждена по правилам точки')
        self.mode=QComboBox(); self.mode.addItems(['Установить фактический остаток','Зарегистрировать списание'])
        self.reason=ReasonPicker(STOCK_REASONS,store.get('reason_history:stock',[])); self.reason.setObjectName('changeReason')
        form.addRow('Партия',self.batch); form.addRow(self.info); form.addRow('Действие',self.mode)
        form.addRow('Количество',self.qty); form.addRow(self.usable); form.addRow('Причина',self.reason)
        def selected():
            b=batches[self.batch.currentIndex()]
            self.qty.setValue(0 if self.mode.currentIndex()==1 else float(b['qty']))
            self.usable.setChecked(str(b['usable']).lower() in ('1','true'))
            self.info.setText(f'Сейчас: {num(float(b["qty"]),3)} {b["unit"]} · сверка {str(b["checked_at"])[:19].replace("T"," ")}\nДата использования: {b.get("use_before") or "не указана"}')
        self.batch.currentIndexChanged.connect(selected); self.mode.currentIndexChanged.connect(selected); selected()
        def save():
            if not self.reason.text().strip(): self.reason.setFocus(); raise DataError('Укажите причину изменения')
            store.correct_batch(self.batch.currentData(),self.qty.value(),self.usable.isChecked(),self.reason.text(),author,self.mode.currentIndex()==1)
            with store.db: remember_reason(store,'stock',self.reason.text())
        dialog_buttons(self,box,save)


class QuantityDialog(QDialog):
    def __init__(self,payload,row,old,save,parent=None,recent_reasons=()):
        super().__init__(parent); self.setWindowTitle(row['name']); self.resize(830,740)
        self.recalculate_requested=False
        outer=QVBoxLayout(self); outer.setContentsMargins(25,22,25,22); outer.setSpacing(12)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        body=QWidget(); box=QVBoxLayout(body); box.setContentsMargins(0,0,8,0); box.setSpacing(12); box.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(body); outer.addWidget(scroll,1)
        box.addWidget(caption(row['name'],'title'))
        box.addWidget(caption(f'Рекомендация: {row["packs"]} уп. по {num(row["pack"],2)} {row["unit"]}'))
        form=QFormLayout(); self.qty=QSpinBox(); self.qty.setObjectName('orderQuantity'); self.qty.setRange(0,100000)
        self.qty.setValue(old['packs'] if old else row['packs']); self.reason=ReasonPicker(ORDER_REASONS,recent_reasons); self.reason.setObjectName('changeReason')
        self.reason.setText(old.get('reason','') if old else '')
        form.addRow('Итого упаковок',self.qty); form.addRow('Причина',self.reason); box.addLayout(form)
        actions=QHBoxLayout()
        for title,qty in [('Обнулить',0),('Вернуть рекомендацию',row['packs'])]:
            button=QPushButton(title); button.clicked.connect(lambda checked=False,n=qty:self.qty.setValue(n)); actions.addWidget(button)
        box.addLayout(actions)
        self.summary=caption('','section'); box.addWidget(self.summary)
        self.chart=StockProjectionChart(); self.chart.setMinimumHeight(260); box.addWidget(self.chart,1)
        self.risks=caption('','notice'); box.addWidget(self.risks)
        graph_note=caption('Линии показывают расчёт. Новый заказ доступен с начала дня поставки; фактическое поступление нужно подтвердить отдельно.'); box.addWidget(graph_note)
        def preview():
            cost=self.qty.value()*row['pack']*row['cost']; delta=cost-row['packs']*row['pack']*row['cost']
            signed=f'{delta:+,.0f}'.replace(',',' ')
            self.summary.setText(f'{num(self.qty.value()*row["pack"],2)} {row["unit"]} · {num(cost)} ₽ · {signed} ₽ к рекомендации')
            try:
                base=order_impact(payload,row,0); picked=order_impact(payload,row,self.qty.value())
                self.chart.set_data(base,picked,row['unit'],payload['arrival'])
                self.risks.setText(f'Остаток в конце: {num(picked["closing"],2)} {row["unit"]} · цель {num(row["target"],2)} {row["unit"]}\nНепокрытая потребность за период: {num(picked["shortage"],2)} {row["unit"]}, до поставки: {num(picked["shortage_before"],2)} {row["unit"]}')
            except DataError:
                self.chart.hide(); graph_note.hide(); self.risks.setText('В этом сохранённом расчёте нет данных для графика. Пересчитайте заявку — сохранённые ручные количества и причины останутся.'); self.resize(830,520)
        self.qty.valueChanged.connect(preview); preview()
        def persist():
            if not self.reason.text().strip(): self.reason.setFocus(); raise DataError('Укажите причину ручного изменения')
            save(self.qty.value(),self.reason.text().strip())
        buttons=dialog_buttons(self,outer,persist)
        if 'inventory_inputs' not in row or 'daily_demand' not in row:
            recalc=buttons.addButton('Пересчитать заявку',QDialogButtonBox.ButtonRole.ActionRole)
            def recalculate():
                if self.qty.value()!=(old['packs'] if old else row['packs']) or self.reason.text()!=(old.get('reason','') if old else ''):
                    try: persist()
                    except (DataError,ValueError,OSError,sqlite3.Error) as e:
                        buttons.validation_error.setText(str(e)); buttons.validation_error.show(); return
                self.recalculate_requested=True; self.accept()
            recalc.clicked.connect(recalculate)
        self.qty.setFocus(); self.qty.selectAll()


def readable_change(value):
    if value is None: return '—'
    if isinstance(value,dict) and 'payload' in value:
        payload=value['payload']
        lines=[f'Заявка №{value.get("order","—")} · {num(order_total(payload))} ₽',f'Поставка: {payload["arrival"]}']
        for r in payload['rows']:
            packs=payload.get('edits',{}).get(r['id'],{}).get('packs',r['packs'])
            lines.append(f'{r["name"]}: {packs} уп. · {num(packs*r["pack"],2)} {r["unit"]}')
        return '\n'.join(lines)
    if isinstance(value,dict) and 'rows' in value and 'forecasts' in value:
        return readable_change({'payload':value})
    names={'id':'Код','name':'Название','qty':'Количество','unit':'Единица','usable':'Пригодность подтверждена',
           'checked_at':'Сверено','use_before':'Дата использования','packs':'Упаковок','reason':'Причина','author':'Автор',
           'at':'Время','recommended':'Рекомендация, уп.','old':'Предыдущая правка','point':'Точка','ingredient':'Ингредиент',
           'settings':'Настройки','schedules':'Поставки','schedule':'Поставка','next_delivery':'Ближайшая поставка',
           'interval_days':'Интервал, дней','calculation_date':'Ручная дата','date_mode':'Режим даты','regular_share':'Порог регулярного спроса',
           'recent_days':'Свежих наблюдений','pack':'Упаковка','target':'Цель','fallback':'Резерв порций/день',
           'points':'Точки','items':'Ассортимент','sales':'Продажи','batches':'Партии','recipes':'Техкарты','deliveries':'Поставки в пути','movements':'Движения'}
    if isinstance(value,dict):
        return '\n'.join(f'{names.get(k,k)}: {readable_change(v)}' for k,v in value.items() if k not in ('inventory_inputs','projection','daily_demand','draft_id','_undo'))
    if isinstance(value,list): return '\n'.join(readable_change(v) for v in value) or '—'
    if isinstance(value,float): return num(value,3)
    return str(value)


class StockTimelinePanel(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent); self.snapshot=None; self.draft=None; self.error=None
        self.setObjectName('chartCard'); box=QVBoxLayout(self); box.setContentsMargins(23,20,23,18); box.setSpacing(12)
        top=QHBoxLayout(); top.addWidget(caption('Запас по дням','chartTitle')); top.addStretch()
        self.ingredient=QComboBox(); self.ingredient.setMinimumWidth(240); self.ingredient.currentIndexChanged.connect(self.refresh); top.addWidget(self.ingredient); box.addLayout(top)
        self.summary=caption('','section'); box.addWidget(self.summary)
        self.chart=StockProjectionChart(); self.chart.setMinimumHeight(340); box.addWidget(self.chart)
        self.note=caption(''); box.addWidget(self.note)
    def set_snapshot(self,snapshot,draft=None,error=None):
        self.snapshot=snapshot; self.draft=draft; self.error=error
        selected=self.ingredient.currentData(); self.ingredient.blockSignals(True); self.ingredient.clear()
        for r in (snapshot or {}).get('rows',[]): self.ingredient.addItem(r['name'],r['id'])
        index=self.ingredient.findData(selected)
        if index>=0: self.ingredient.setCurrentIndex(index)
        self.ingredient.blockSignals(False); self.refresh()
    def refresh(self):
        if not self.snapshot:
            self.chart.hide(); self.summary.setText(self.error or 'Нужен расчёт потребности и график поставок'); self.note.setText(''); return
        row=next((r for r in self.snapshot['rows'] if r['id']==self.ingredient.currentData()),None)
        if not row: self.chart.hide(); self.summary.setText('Нет ингредиентов для расчёта'); return
        self.chart.show(); edits=(self.draft or {}).get('edits',{})
        picked=edits.get(row['id'],{}).get('packs',row['packs'])
        try:
            base=order_impact(self.snapshot,row,0); scenario=order_impact(self.snapshot,row,picked)
            self.chart.set_data(base,scenario,row['unit'],self.snapshot['arrival'])
            self.summary.setText(f'Заказ: {picked} уп. · {num(picked*row["pack"],2)} {row["unit"]}  |  На конец: {num(scenario["closing"],2)} {row["unit"]}  |  Не хватит за период: {num(scenario["shortage"],2)} {row["unit"]}')
            source='Количество из текущей заявки.' if self.draft else 'Количество по рекомендации.'
            self.note.setText(f'{source} Шаги — подтверждённые поступления и выбранный заказ, доступные с начала дня. Красные точки — непокрытая потребность. Наведите для подробностей.\nРасчёт по заданному снимку остатков; получение нового заказа ещё не подтверждено.'+ (' Даты использования части партий неизвестны.' if row['unknown_dates'] else ''))
        except DataError as e: self.chart.hide(); self.summary.setText(str(e))


def populate(table,rows):
    table.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row): table.setItem(i,j,QTableWidgetItem(str(value)))
    table.update_empty()


def order_total(payload):
    return sum(payload.get('edits',{}).get(r['id'],{}).get('packs',r['packs'])*r['pack']*r['cost'] for r in payload['rows'])


class OrderDetailsDialog(QDialog):
    def __init__(self,order,point_name,export,parent=None):
        super().__init__(parent); self.setWindowTitle(f'Заявка №{order["id"]}'); self.resize(1060,750)
        payload=order['payload']; box=QVBoxLayout(self); box.setContentsMargins(26,23,26,23); box.setSpacing(15)
        top=QHBoxLayout(); top.addWidget(caption(f'Заявка №{order["id"]}','title')); top.addStretch()
        button=QPushButton('Экспортировать Excel'); button.clicked.connect(lambda:export(order)); top.addWidget(button); box.addLayout(top)
        box.addWidget(caption(f'{point_name} · {order["status"]} · сохранена {order["created"][:19].replace("T"," ")}'))
        box.addWidget(caption(f'Поставка {payload["arrival"]} · {num(order_total(payload))} ₽ по себестоимости ингредиентов','section'))
        box.addWidget(caption('Заявка сохранена локально. Отправка поставщику и получение товара не подтверждены.','notice'))
        tabs=QTabWidget(); box.addWidget(tabs,1)
        ingredients=DataTable(['Ингредиент','Совет, уп.','Итог, уп.','Количество','Сумма, ₽','Причина'])
        populate(ingredients,[[r['name'],r['packs'],payload.get('edits',{}).get(r['id'],{}).get('packs',r['packs']),
            f'{num(payload.get("edits",{}).get(r["id"],{}).get("packs",r["packs"])*r["pack"],2)} {r["unit"]}',
            num(payload.get('edits',{}).get(r['id'],{}).get('packs',r['packs'])*r['pack']*r['cost']),
            payload.get('edits',{}).get(r['id'],{}).get('reason','—')] for r in payload['rows']])
        tabs.addTab(ingredients,'Состав заявки')
        forecasts=DataTable(['Блюдо','Ожидается, порций','Ориентир','Метод'])
        populate(forecasts,[[f['name'],num(f['expected']),f'{num(f["low"])}–{num(f["high"])}',f['method']] for f in payload['forecasts']]); tabs.addTab(forecasts,'Сохранённый прогноз')
        box.addWidget(caption(f'Расчёт {payload["date"]} · покрытие до {payload["end"]} (не включая) · автор {payload.get("author","—")}'))
        close=QPushButton('Готово'); close.clicked.connect(self.accept); box.addWidget(close,alignment=Qt.AlignmentFlag.AlignRight)
