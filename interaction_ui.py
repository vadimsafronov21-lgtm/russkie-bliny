"""Operator conveniences: workspace memory, side card, commands and notifications."""
from __future__ import annotations

import json
import re
from pathlib import Path

from PySide6.QtCore import QByteArray,QEvent,Qt,QTimer,QUrl
from PySide6.QtGui import QAction,QDesktopServices,QKeySequence,QShortcut
from PySide6.QtWidgets import (QApplication,QComboBox,QDialog,QFrame,QHBoxLayout,QLabel,QLineEdit,
    QListWidget,QListWidgetItem,QPushButton,QScrollArea,QSizePolicy,QTabWidget,QTableWidget,QVBoxLayout,QWidget,QToolButton,QMenu)

from charts import StockProjectionChart
from core import DataError,order_impact
from interaction import compare_orders,save_order_edit,undo_order_edit
from ui_theme import STYLE,DataTable,svg_icon,BURGUNDY
from ui_motion import finish_motion,MotionTabBar


def label(value,role=None):
    widget=QLabel(value); widget.setWordWrap(True); widget.setTextFormat(Qt.TextFormat.PlainText)
    if role: widget.setObjectName(role)
    return widget


def button(value,callback):
    widget=QPushButton(value); widget.clicked.connect(callback); return widget


def fill(table,rows):
    from app import fill as populate
    populate(table,rows)


class NotificationBar(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent); self.setObjectName('rail'); self.box=QHBoxLayout(self)
        self.box.setContentsMargins(10,5,10,5); self.history=[]; self.persistent=False
        self.caption=label(''); self.caption.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.box.addWidget(self.caption,1); self.actions=[]
        self.close_button=button('×',self.hide); self.close_button.setAccessibleName('Закрыть уведомление'); self.close_button.setFixedWidth(42)
        self.box.addWidget(self.close_button)
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.hide); self.hide()

    def dismiss_success(self):
        if not self.persistent: self.timer.stop(); self.hide()

    def display(self,message,actions=(),persistent=False):
        self.persistent=persistent; self.history.append((message,tuple(actions))); self.history=self.history[-30:]
        self.caption.setText(message); self.caption.setToolTip(message)
        for widget in self.actions: self.box.removeWidget(widget); widget.hide(); widget.deleteLater()
        self.actions=[]
        for title,callback in actions:
            widget=button(title,callback); widget.setObjectName('quiet'); self.box.insertWidget(self.box.count()-1,widget); self.actions.append(widget)
        self.show(); self.timer.stop()
        if not persistent: self.timer.start(6000)


class CommandPalette(QDialog):
    def __init__(self,commands,parent=None):
        super().__init__(parent); self.setWindowTitle('Поиск действий'); self.resize(720,540)
        self.commands=commands; box=QVBoxLayout(self); box.addWidget(label('Что нужно сделать?','title'))
        self.search=QLineEdit(); self.search.setPlaceholderText('Например: сверить тесто, история, крупный режим'); box.addWidget(self.search)
        self.results=QListWidget(); box.addWidget(self.results,1)
        self.results.setStyleSheet('QListWidget { background: white; border: 1px solid #E9E8ED; border-radius: 7px; } '
                                  'QListWidget::item { padding: 10px 12px; min-height: 20px; border-bottom: 1px solid #F0EFF3; } '
                                  'QListWidget::item:selected { background: #F9E8EB; color: #A4002A; } '
                                  'QListWidget::item:disabled { color: #979BA5; }')
        box.addWidget(label('Введите слова · ↓ / ↑ — выбрать · Enter — выполнить · Esc — закрыть','subtitle'))
        self.search.textChanged.connect(self.filter); self.search.returnPressed.connect(self.run_current)
        self.results.itemActivated.connect(self.run_current); self.search.installEventFilter(self); self.filter()

    def filter(self):
        words=self.search.text().casefold().replace('ё','е').split(); self.results.clear()
        for index,command in enumerate(self.commands):
            if not all(word in command['title'].casefold().replace('ё','е') for word in words): continue
            item=QListWidgetItem(command['title']); item.setData(Qt.ItemDataRole.UserRole,index)
            if not command.get('enabled',True):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip(command.get('hint','Действие пока недоступно'))
            self.results.addItem(item)
        for index in range(self.results.count()):
            if self.results.item(index).flags() & Qt.ItemFlag.ItemIsEnabled:
                self.results.setCurrentRow(index); break

    def eventFilter(self,watched,event):
        if watched is self.search and event.type()==QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Down,Qt.Key.Key_Up):
            step=1 if event.key()==Qt.Key.Key_Down else -1; index=self.results.currentRow()+step
            while 0<=index<self.results.count():
                if self.results.item(index).flags() & Qt.ItemFlag.ItemIsEnabled: self.results.setCurrentRow(index); break
                index+=step
            return True
        return super().eventFilter(watched,event)

    def run_current(self,*args):
        item=self.results.currentItem()
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled): return
        callback=self.commands[item.data(Qt.ItemDataRole.UserRole)]['callback']
        self.accept(); QTimer.singleShot(0,callback)


class IngredientCard(QScrollArea):
    def __init__(self,parent=None):
        super().__init__(parent); self.setWidgetResizable(True); self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body=QFrame(); body.setObjectName('surface'); box=QVBoxLayout(body); box.setContentsMargins(16,18,16,18); box.setSpacing(12); self.setWidget(body)
        self.title=label('Ингредиент','section'); heading=QHBoxLayout(); heading.addWidget(self.title,1)
        self.close_button=QPushButton('×'); self.close_button.setFixedWidth(36); self.close_button.setAccessibleName('Закрыть карточку ингредиента')
        heading.addWidget(self.close_button); box.addLayout(heading)
        self.summary=label(''); box.addWidget(self.summary)
        self.chart=StockProjectionChart(); self.chart.setMinimumHeight(190); box.addWidget(self.chart)
        self.contributions=DataTable(['Расход по блюдам','Количество']); self.contributions.verticalHeader().setDefaultSectionSize(34)
        self.contributions.setMinimumHeight(160); box.addWidget(self.contributions)
        self.note=label('','subtitle'); box.addWidget(self.note)
        box.addStretch()
        self.ingredient=None

    def set_row(self,payload,row,draft=None,error=None):
        self.ingredient=str(row['id']); unit=row['unit']; self.title.setText(row['name'])
        if payload is None:
            amount=lambda value:f'{value:.2f} {unit}' if value is not None else 'Нет данных'
            self.summary.setText(f'Фактический остаток: {amount(row["stock"])}\n'
                                 f'Пригодность подтверждена: {amount(row["usable_stock"])}\n'
                                 f'Исключено по пригодности: {amount(row["blocked"])}\nПартий: {row["batch_count"]}')
            self.chart.hide(); self.contributions.hide()
            self.note.setText('Сверка: '+row['checked_at'][:19].replace('T',' ')+ '\n\n'+(error or 'Расчёт пополнения недоступен. Проверьте данные.'))
            return
        self.contributions.show()
        picked=(draft or {}).get('edits',{}).get(row['id'],{}).get('packs',row['packs'])
        self.summary.setText(f'Пригодный остаток: {row["stock"]:.2f} {unit}\nПотребность: {row["demand"]:.2f} {unit}\n'
                             f'Учтено поступлений: {row["incoming"]:.2f} {unit}\n'
                             f'Целевой остаток: {row["target"]:.2f} {unit}\n'
                             f'Рекомендация: {row["packs"]} уп.\nВыбрано: {picked} уп. × {row["pack"]:g} {unit}')
        fill(self.contributions,[[name,f'{value:.2f} {unit}'] for name,value in row['contributions'].items()])
        try:
            self.chart.set_data(order_impact(payload,row,0),order_impact(payload,row,picked),unit,payload['arrival']); self.chart.show()
        except DataError: self.chart.hide()
        self.note.setText(f'До поставки может не хватить {row["shortage_before"]:.2f} {unit}.\n'
                          f'Сверка: {row["checked_at"][:19].replace("T"," ")}.\n'+
                          ('Количество из актуальной заявки.' if draft else 'Количество по рекомендации.'))


class CompareOrdersDialog(QDialog):
    def __init__(self,store,point,parent=None):
        super().__init__(parent); self.setWindowTitle('Сравнение заявок'); self.resize(1120,760)
        self.store=store; self.point=str(point); self.orders=[]; self.comparison=None
        box=QVBoxLayout(self); box.addWidget(label('Сравнение двух заявок','title'))
        selectors=QHBoxLayout(); self.before=QComboBox(); self.after=QComboBox()
        selectors.addWidget(label('Раньше')); selectors.addWidget(self.before,1); selectors.addWidget(label('Позже')); selectors.addWidget(self.after,1); box.addLayout(selectors)
        for order_id,raw in store.db.execute('SELECT id,payload FROM orders WHERE point=? ORDER BY id DESC',(self.point,)):
            if bool(json.loads(raw).get('demo'))!=bool(store.get('demo')): continue
            order=store.get_order(order_id); self.orders.append(order)
            title=f'№{order_id} · {order["created"][:16].replace("T"," ")} · поставка {order["payload"]["arrival"]}'
            self.before.addItem(title,order_id); self.after.addItem(title,order_id)
        self.summary=label(''); box.addWidget(self.summary)
        tabs=QTabWidget(); tabs.setTabBar(MotionTabBar(background='#FFFFFF')); box.addWidget(tabs,1)
        self.quantities=DataTable(['Ингредиент','Раньше','Позже','Разница количества','Разница суммы, ₽']); tabs.addTab(self.quantities,'Количество и стоимость')
        self.reasons=DataTable(['Ингредиент','Причина раньше','Причина позже']); tabs.addTab(self.reasons,'Причины правок')
        box.addWidget(label('Сравниваются сохранённые заявки одной точки и одного типа данных. '
                            'Суммы рассчитаны по себестоимости внутри каждой заявки; разница не является экономией.','subtitle'))
        box.addWidget(button('Закрыть',self.accept))
        if len(self.orders)>1: self.before.setCurrentIndex(1)
        self.before.currentIndexChanged.connect(self.compare); self.after.currentIndexChanged.connect(self.compare); self.compare()

    def compare(self):
        self.comparison=None
        if len(self.orders)<2: self.summary.setText('Нужны две сохранённые заявки этой точки.'); return
        try:
            result=compare_orders(self.store.get_order(self.before.currentData()),self.store.get_order(self.after.currentData()))
            def qty(value): return f'{value["packs"]:g} уп. / {value["qty"]:g} {value["unit"] or ""}'
            fill(self.quantities,[[row['name'],qty(row['before']),qty(row['after']),
                 f'{row["qty_delta"]:+g} {row["after"]["unit"] or row["before"]["unit"]}' if row['qty_delta'] is not None else 'Разные единицы',
                 f'{row["cost_delta"]:+.2f}'] for row in result['rows']])
            fill(self.reasons,[[row['name'],row['before']['reason'],row['after']['reason']] for row in result['rows']])
            self.summary.setText(f'Сумма: {result["before_total"]:,.2f} ₽ → {result["after_total"]:,.2f} ₽ · '
                                 f'разница {result["after_total"]-result["before_total"]:+,.2f} ₽')
            self.comparison=result
        except DataError as exc:
            fill(self.quantities,[]); fill(self.reasons,[]); self.summary.setText(str(exc))


class InteractionMixin:
    def init_interaction(self):
        self._interaction_ready=False; self._ui_closing=False
        self.workspace_timer=QTimer(self); self.workspace_timer.setSingleShot(True); self.workspace_timer.timeout.connect(self.save_workspace)
        area=self.status.parentWidget().layout()
        self.notifications=NotificationBar(); area.addWidget(self.notifications)
        self.commands_button=QToolButton(); self.commands_button.setObjectName('headerTool'); self.commands_button.setIcon(svg_icon('search',BURGUNDY))
        self.commands_button.setToolTip('Поиск действий · Ctrl+Shift+P'); self.commands_button.setAccessibleName('Поиск действий'); self.commands_button.clicked.connect(self.open_commands)
        self.header_layout.insertWidget(self.header_layout.count()-1,self.commands_button)
        self.profile_button=QToolButton(); self.profile_button.setObjectName('headerTool'); self.profile_button.setText('⋯'); self.profile_button.setAccessibleName('Профиль и помощь')
        self.profile_button.setToolTip('Профиль, доступность и помощь'); self.profile_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.profile_menu=QMenu(self.profile_button); self.profile_button.setMenu(self.profile_menu); self.header_layout.addWidget(self.profile_button)
        self.large_button=QAction('Крупный режим',self); self.large_button.setCheckable(True); self.large_button.toggled.connect(self.set_large_mode); self.profile_menu.addAction(self.large_button)
        self.motion_button=QAction('Плавные переходы',self); self.motion_button.setCheckable(True); self.motion_button.setChecked(bool(self.property('motionEnabled')))
        self.motion_button.toggled.connect(self.set_motion_enabled); self.profile_menu.addAction(self.motion_button)
        self.profile_menu.addAction('Настройки точки',lambda:self.navigate(4))
        self.profile_menu.addAction('Уведомления',self.open_notifications)
        help_menu=self.profile_menu.addMenu('Помощь'); help_menu.addAction('Демонстрации обмена',self.open_dalion_demo)
        help_menu.addAction('Подготовить демо-файл',lambda:self.templates(True))
        self.ingredient_dialog=QDialog(self); self.ingredient_dialog.setWindowTitle('Подробности и график запаса'); self.ingredient_dialog.resize(920,790)
        self.ingredient_dialog.setMinimumSize(680,580)
        details=QVBoxLayout(self.ingredient_dialog); details.setContentsMargins(12,12,12,12)
        self.ingredient_card=IngredientCard(); details.addWidget(self.ingredient_card)
        self.ingredient_card.close_button.clicked.connect(self.close_ingredient_card)
        self.stock_table.currentCellChanged.connect(lambda *args:self.refresh_ingredient_card())
        self.undo_button=button('Отменить правку',self.undo_last_edit); self.order_edit_actions.insertWidget(1,self.undo_button)
        self.page_actions[3].addWidget(button('Сравнить заявки',self.open_comparison))
        shortcut=QShortcut(QKeySequence('Ctrl+Shift+P'),self); shortcut.activated.connect(self.open_commands); self.shortcuts.append(shortcut)
        for signal in (self.search.textChanged,self.filter.currentIndexChanged,self.chart_dish.currentIndexChanged,self.history_search.textChanged):
            signal.connect(self.schedule_workspace_save)
        for widget in self.findChildren(QTableWidget):
            widget.currentCellChanged.connect(self.schedule_workspace_save)
            widget.verticalScrollBar().valueChanged.connect(self.schedule_workspace_save)
        for widget in self.findChildren(QScrollArea): widget.verticalScrollBar().valueChanged.connect(self.schedule_workspace_save)
        for widget in self.analytics.period_buttons: widget.clicked.connect(self.schedule_workspace_save)
        self.analytics.chart_tabs.currentChanged.connect(self.schedule_workspace_save)
        self.installEventFilter(self)
        self.set_large_mode(self.store.get('ui_preferences',{}).get('large_mode',False),persist=False)
        self.restore_workspace(); self._interaction_ready=True; self.update_undo_button()

    def notify(self,message,actions=(),persistent=False):
        if hasattr(self,'notifications'): self.notifications.display(message,actions,persistent)
        else: self.status.setText(message)

    def open_notifications(self):
        dialog=QDialog(self); dialog.setWindowTitle('Уведомления за этот запуск'); dialog.resize(720,460); box=QVBoxLayout(dialog)
        entries=QListWidget(); box.addWidget(entries,1); actions=QHBoxLayout(); box.addLayout(actions)
        history=list(reversed(self.notifications.history))
        for message,_ in history: entries.addItem(message)
        if not history: box.addWidget(label('Уведомлений пока нет.','subtitle'))
        def select():
            while actions.count():
                item=actions.takeAt(0)
                if item.widget(): item.widget().deleteLater()
            index=entries.currentRow()
            if 0<=index<len(history):
                for title,callback in history[index][1]: actions.addWidget(button(title,lambda checked=False,fn=callback:self.safe(fn)))
        entries.currentRowChanged.connect(select); entries.setCurrentRow(0)
        box.addWidget(button('Закрыть',dialog.accept)); dialog.exec()

    def notify_export(self,message,path,order_id=None):
        path=Path(path).resolve(); actions=[]
        if order_id is not None: actions.append(('Открыть заявку',lambda:self.show_saved_order(order_id)))
        actions.extend([('Открыть файл',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))),
                        ('Папка',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent))))])
        self.notify(message,actions)

    def show_saved_order(self,order_id):
        from workflows import OrderDetailsDialog
        order=self.store.get_order(order_id)
        if str(order['point'])!=self.pid(): raise DataError('Заявка другой точки.')
        OrderDetailsDialog(order,self.point.currentText(),self.export_saved,self).exec()

    def edit_current_quantity(self,row,packs,reason):
        save_order_edit(self.store,self.pid(),self.current,row['id'],packs,reason,self.author()); self.update_undo_button()
        self.notify('Ручное количество сохранено.')

    def undo_last_edit(self):
        try:
            if not self.current: raise DataError('Сначала откройте неподтверждённую заявку.')
            name=undo_order_edit(self.store,self.pid(),self.current,self.author())
            self.refresh_order(); self.update_undo_button(); self.notify('Правка отменена: '+name+'. Отмена записана в журнале.')
        except DataError as exc: self.notify(str(exc),persistent=True)

    def update_undo_button(self):
        if hasattr(self,'undo_button'):
            payload=self.current or {}
            self.undo_button.setEnabled(bool(payload.get('_undo')) and not payload.get('confirmed_order_id') and payload.get('revision')==self.store.get('revision'))

    def open_selected_card(self):
        index=self.stock_table.currentRow()
        if 0<=index<len(self.visible_stock):
            self.ingredient_dialog.show(); self.refresh_ingredient_card(); self.ingredient_dialog.raise_(); self.ingredient_dialog.activateWindow()

    def refresh_ingredient_card(self):
        if getattr(self,'_stock_filling',False): return
        if not hasattr(self,'ingredient_card') or not self.ingredient_dialog.isVisible(): return
        index=self.stock_table.currentRow()
        if not 0<=index<len(self.visible_stock): self.close_ingredient_card(); return
        draft=self.current if self.current and self.current.get('revision')==self.store.get('revision') and self.current.get('date')==self.calc_day().isoformat() else None
        self.ingredient_card.set_row(self.snapshot,self.visible_stock[index],draft,self.calculation_error)
        self.ingredient_dialog.setWindowTitle('КРОНА · '+self.visible_stock[index]['name']+' · Подробности и график')

    def close_ingredient_card(self):
        self.ingredient_dialog.close()

    def select_ingredient(self,ingredient,correct=False):
        self.select_route('stock','inventory'); self.search.clear(); self.filter.setCurrentIndex(0)
        for index,row in enumerate(self.visible_stock):
            if str(row['id'])==str(ingredient): self.stock_table.selectRow(index); self.open_selected_card(); break
        if correct: self.edit_stock()

    def open_comparison(self): CompareOrdersDialog(self.store,self.pid(),self).exec()

    def command_entries(self):
        result=[]
        for domain,routes in self.ROUTES.items():
            for view,title,icon in routes:
                result.append(dict(title=('Остатки' if domain=='stock' else 'Спрос')+' → '+title,
                    callback=lambda d=domain,v=view:self.select_route(d,v)))
        result.extend([dict(title='Заявка: сформировать или пересчитать',callback=self.make_order),
                       dict(title='Заявка: отменить последнюю правку',callback=self.undo_last_edit,enabled=self.undo_button.isEnabled()),
                       dict(title='История: сравнить две заявки',callback=self.open_comparison),
                       dict(title='Что, если: сравнить сценарии',callback=self.open_what_if),
                       dict(title='Настройки точки',callback=lambda:self.navigate(4)),
                       dict(title='Уведомления за этот запуск',callback=self.open_notifications),
                       dict(title='Помощь: демонстрации обмена',callback=self.open_dalion_demo),
                       dict(title='Пилот: начать замер заявки',callback=self.start_work,enabled=bool(self.snapshot)),
                       dict(title='Пилот: завершить замер',callback=self.finish_work,enabled=self.work_button.text()=='Завершить замер'),
                       dict(title='Крупный режим: переключить',callback=lambda:self.set_large_mode(not self.large_mode))])
        for row in self.snapshot['rows'] if self.snapshot else self.inventory_rows:
            result.append(dict(title='Карточка ингредиента: '+row['name'],callback=lambda key=row['id']:self.select_ingredient(key)))
            result.append(dict(title='Сверить: '+row['name'],callback=lambda key=row['id']:self.select_ingredient(key,True)))
        return result

    def open_commands(self): CommandPalette(self.command_entries(),self).exec()

    def set_large_mode(self,enabled,persist=True):
        self.large_mode=bool(enabled); self.large_button.blockSignals(True); self.large_button.setChecked(self.large_mode); self.large_button.blockSignals(False)
        stylesheet=re.sub(r'font-size:\s*(\d+)px',lambda match:f'font-size: {min(36,round(int(match[1])*1.2))}px',STYLE) if enabled else ''
        if enabled: stylesheet+='\nQPushButton { min-height: 22px; } QLineEdit,QComboBox { min-height: 24px; }'
        self.setStyleSheet(stylesheet)
        self.sidebar.setFixedWidth(228 if enabled else 198)
        for table in self.findChildren(QTableWidget):
            if table.property('normalRowHeight') is None: table.setProperty('normalRowHeight',table.verticalHeader().defaultSectionSize())
            base=table.property('normalRowHeight'); table.verticalHeader().setDefaultSectionSize(round(base*1.2) if enabled else base)
        for title in self.page_titles: title.setWordWrap(bool(enabled))
        if persist:
            with self.store.db: self.store.put('ui_preferences',{**self.store.get('ui_preferences',{}),'large_mode':self.large_mode})
        self.update_identity(); self.schedule_workspace_save()

    def set_motion_enabled(self,enabled):
        self.setProperty('motionEnabled',bool(enabled)); finish_motion(self)
        self.motion_button.blockSignals(True);self.motion_button.setChecked(bool(enabled));self.motion_button.blockSignals(False)
        with self.store.db:self.store.put('ui_preferences',{**self.store.get('ui_preferences',{}),'motion_enabled':bool(enabled)})

    def schedule_workspace_save(self,*args):
        if getattr(self,'_interaction_ready',False) and not getattr(self,'_ui_closing',False): self.workspace_timer.start(250)

    def eventFilter(self,watched,event):
        if watched is self:
            if event.type()==QEvent.Type.Show:
                self._ui_closing=False
                if hasattr(self,'day_timer'): self.day_timer.start()
            elif event.type() in (QEvent.Type.Move,QEvent.Type.Resize,QEvent.Type.WindowStateChange): self.schedule_workspace_save()
        return super().eventFilter(watched,event)

    def workspace_state(self):
        index=self.stock_table.currentRow()
        return dict(version=1,domain=self.active_domain,view=self.active_view,last_views=self.last_views,
            geometry=bytes(self.saveGeometry().toBase64()).decode('ascii'),search=self.search.text(),filter=self.filter.currentIndex(),
            dish=self.chart_dish.currentData(),period=self.analytics.days,history_search=self.history_search.text(),
            ingredient=self.visible_stock[index]['id'] if 0<=index<len(self.visible_stock) else None,
            card=False,
            analytics_tab=self.analytics.chart_tabs.currentIndex(),
            scrolls={name:getattr(self,name).verticalScrollBar().value() for name in
                     ('stock_table','order_table','orders_table','audit_table','daily_table','availability_table','pilot_details')},
            analytics_scroll=self.analytics.findChild(QScrollArea).verticalScrollBar().value(),
            order_row=self.order_table.currentRow())

    def save_workspace(self):
        if not self.pid(): return
        with self.store.db: self.store.put('ui_workspace:'+self.pid(),self.workspace_state())

    def restore_workspace(self):
        state=self.store.get('ui_workspace:'+self.pid(),{})
        if not isinstance(state,dict) or state.get('version')!=1: return
        self._interaction_ready=False
        self.search.setText(str(state.get('search','')))
        mode=state.get('filter',0); self.filter.setCurrentIndex(mode if type(mode) is int and 0<=mode<=2 else 0)
        self.history_search.setText(str(state.get('history_search','')))
        index=self.chart_dish.findData(state.get('dish'))
        if index>=0: self.chart_dish.setCurrentIndex(index)
        self.analytics.set_period(state.get('period') if state.get('period') in (14,30,90) else 30)
        last_views=state.get('last_views',{})
        for domain,view in (last_views.items() if isinstance(last_views,dict) else []):
            if isinstance(view,str) and domain in self.ROUTES and view in {row[0] for row in self.ROUTES[domain]}|{'settings'}: self.last_views[domain]=view
        domain=state.get('domain'); view=state.get('view')
        if isinstance(domain,str) and isinstance(view,str) and domain in self.ROUTES and view in {row[0] for row in self.ROUTES[domain]}|{'settings'}: self.select_route(domain,view)
        for index,row in enumerate(self.visible_stock):
            if row['id']==state.get('ingredient'): self.stock_table.selectRow(index); break
        tab=state.get('analytics_tab',0)
        if type(tab) is int and 0<=tab<self.analytics.chart_tabs.count(): self.analytics.chart_tabs.setCurrentIndex(tab)
        if isinstance(state.get('geometry'),str):
            self.restoreGeometry(QByteArray.fromBase64(state['geometry'].encode('ascii')))
            if not any(screen.availableGeometry().intersects(self.frameGeometry()) for screen in QApplication.screens()):
                self.move(QApplication.primaryScreen().availableGeometry().topLeft())
        def scroll():
            scrolls=state.get('scrolls',{})
            for name,value in (scrolls.items() if isinstance(scrolls,dict) else []):
                if hasattr(self,name) and isinstance(value,int): getattr(self,name).verticalScrollBar().setValue(value)
            value=state.get('analytics_scroll',0)
            self.analytics.findChild(QScrollArea).verticalScrollBar().setValue(value if isinstance(value,int) else 0)
            index=state.get('order_row',-1)
            if isinstance(index,int) and 0<=index<self.order_table.rowCount(): self.order_table.selectRow(index)
        QTimer.singleShot(0,scroll)

    def finish_interaction(self):
        finish_motion(self)
        if hasattr(self,'ingredient_dialog'): self.ingredient_dialog.close()
        if hasattr(self,'workspace_timer'):
            self.workspace_timer.stop(); self.save_workspace(); self.notifications.timer.stop(); self._ui_closing=True
        if hasattr(self,'day_timer'): self.day_timer.stop()
