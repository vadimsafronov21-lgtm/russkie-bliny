"""Native operator pages and dialogs for daily work and pilot measurements."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (QComboBox,QDateEdit,QDialog,QDialogButtonBox,QDoubleSpinBox,
    QFileDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QSpinBox,
    QTabWidget,QTextEdit,QVBoxLayout,QWidget,QHeaderView)

from core import DataError, LABELS, calculate
from exchange_review import apply_import, row_description
from operations import (availability_events,daily_actions,ensure_operations,export_pilot,
    mark_availability,pilot_report,record_forecasts,simulate,work_session)
from ui_theme import DataTable


def text(value, role=None):
    label=QLabel(value); label.setWordWrap(True)
    if role: label.setObjectName(role)
    return label


def action(value, callback, primary=False):
    button=QPushButton(value); button.clicked.connect(callback)
    if primary: button.setObjectName('primary')
    return button


def fill_rows(table, rows):
    from app import fill
    fill(table,rows)


class WhatIfDialog(QDialog):
    def __init__(self,store,point,day,parent=None):
        super().__init__(parent); self.setWindowTitle('Что, если… · Отдельный расчёт'); self.resize(1060,750)
        self.tables=store.get('tables',{}); self.point=point; self.day=day
        self.settings=store.get('settings',{}); self.result=None
        box=QVBoxLayout(self); box.setSpacing(16)
        box.addWidget(text('Что, если…','title'))
        box.addWidget(text('Сравнение с исходной рекомендацией. Ручные количества в заявке сохраняются. Проценты задаёте вы.','subtitle'))
        controls=QHBoxLayout(); form=QFormLayout()
        self.delay=QSpinBox(); self.delay.setRange(0,30); self.delay.setSuffix(' дн.')
        self.demand=QSpinBox(); self.demand.setRange(-100,300); self.demand.setSuffix(' %')
        self.dish=QComboBox()
        for row in self.tables.get('items',[]):
            if row['kind']=='dish': self.dish.addItem(row['name'],str(row['id']))
        self.extra=QSpinBox(); self.extra.setRange(0,10000); self.extra.setSuffix(' порций')
        form.addRow('Задержка поставки по заявке',self.delay); form.addRow('Изменение ожидаемого спроса',self.demand)
        form.addRow('Блюдо разового заказа',self.dish); form.addRow('Дополнительный заказ на первый день',self.extra)
        controls.addLayout(form,1); controls.addWidget(action('Сравнить варианты',self.compare,True)); box.addLayout(controls)
        box.addWidget(text('Сдвигается график новой заявки. Уже подтверждённые поступления сохраняют свои даты. '
                            'При задержке сравниваются разные периоды покрытия.','subtitle'))
        self.summary=text(''); box.addWidget(self.summary)
        self.table=DataTable(['Ингредиент','Было, уп.','Сценарий, уп.','Разница, уп.','Нехватка до поставки'])
        box.addWidget(self.table,1); self.error=text(''); box.addWidget(self.error)
        box.addWidget(action('Закрыть',self.reject)); self.compare()

    def compare(self):
        try:
            base,variant=simulate(self.tables,self.point,self.day,self.settings,self.delay.value(),self.demand.value(),self.dish.currentData(),self.extra.value())
            before={row['id']:row for row in base['rows']}
            fill_rows(self.table,[[row['name'],before[row['id']]['packs'],row['packs'],row['packs']-before[row['id']]['packs'],
                      f'{row["shortage_before"]:.2f} {row["unit"]}'] for row in variant['rows']])
            def cost(payload): return sum(row['ordered']*row['cost'] for row in payload['rows'])
            self.summary.setText(f'Базовый период: {base["days"]} дн. · сценарий: {variant["days"]} дн.\n'
                                 f'По текущей себестоимости: {cost(base):,.0f} ₽ → {cost(variant):,.0f} ₽')
            self.error.setText('\n'.join(variant['errors'])); self.result=variant
        except (DataError,ValueError) as exc:
            self.result=None; self.table.setRowCount(0); self.summary.setText(''); self.error.setText(str(exc))


class ReviewImportDialog(QDialog):
    def __init__(self,store,plan,author,parent=None):
        super().__init__(parent); self.setWindowTitle('Проверка обновления данных'); self.resize(1120,780)
        self.store=store; self.plan=plan; self.author=author; self.result=None; self.choices=[]
        box=QVBoxLayout(self); box.setSpacing(14)
        box.addWidget(text('Проверка обновления','title'))
        box.addWidget(text(('ДЕМО · ' if plan.is_demo else '')+plan.source+' · изменений: '+str(len(plan.changes))+
                           ' · конфликтов: '+str(len(plan.conflicts))))
        if plan.switching:
            box.addWidget(text('Снимок заменит демонстрационные наборы и черновики. История заявок останется.'))
        if plan.duplicate:
            box.addWidget(text('Этот снимок уже загружен. Повтор не изменит данные и ручные правки.'))
        tabs=QTabWidget(); box.addWidget(tabs,1)
        self.changes=DataTable(['Набор','Ключ','Изменение','Локально','Из источника'])
        fill_rows(self.changes,[[LABELS[row['kind']],' / '.join(row['key']),row['action'],row_description(row['local']),row_description(row['remote'])]
                                for row in plan.changes]); tabs.addTab(self.changes,'Изменения')
        self.conflicts=DataTable(['Набор / ключ','Локально','Из источника','Решение'])
        header=self.conflicts.horizontalHeader()
        header.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed); self.conflicts.setColumnWidth(0,170)
        header.setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3,QHeaderView.ResizeMode.Fixed); self.conflicts.setColumnWidth(3,235)
        fill_rows(self.conflicts,[[LABELS[row['kind']]+' / '+' / '.join(row['key']),row_description(row['local']),row_description(row['remote']),'']
                                  for row in plan.conflicts])
        for index,row in enumerate(plan.conflicts):
            choice=QComboBox(); choice.addItem('Выберите решение',None); choice.addItem('Оставить локальное','local'); choice.addItem('Принять источник','remote')
            holder=QWidget(); holder_box=QVBoxLayout(holder); holder_box.setContentsMargins(6,6,6,6)
            choice.setFixedHeight(42); holder_box.addStretch(); holder_box.addWidget(choice); holder_box.addStretch()
            self.conflicts.setCellWidget(index,3,holder); self.choices.append(choice)
        self.conflicts.resizeRowsToContents()
        for index in range(self.conflicts.rowCount()): self.conflicts.setRowHeight(index,max(160,self.conflicts.rowHeight(index)))
        for index in range(self.changes.columnCount()):
            self.changes.horizontalHeader().setSectionResizeMode(index,QHeaderView.ResizeMode.Stretch)
        self.changes.resizeRowsToContents()
        tabs.addTab(self.conflicts,'Конфликты')
        if plan.conflicts and not plan.duplicate: tabs.setCurrentIndex(1)
        self.reason=QLineEdit(); self.reason.setPlaceholderText('Причина решения конфликтов'); box.addWidget(self.reason)
        box.addWidget(text('Локальные изменения сохраняются, если источник их не менял. '
                            'При конфликте выберите целую строку. Ссылки и единицы будут проверены повторно.','subtitle'))
        self.error=text(''); box.addWidget(self.error)
        buttons=QHBoxLayout(); buttons.addWidget(action('Отмена',self.reject)); buttons.addStretch()
        self.apply_button=action('Применить проверенный снимок',self.apply,True); buttons.addWidget(self.apply_button); box.addLayout(buttons)

    def apply(self):
        try:
            self.result=apply_import(self.store,self.plan,{index:choice.currentData() for index,choice in enumerate(self.choices)},self.reason.text(),self.author)
            self.accept()
        except (DataError,sqlite3.Error) as exc:
            self.error.setText(str(exc))


class OperationsMixin:
    def build_operations(self):
        ensure_operations(self.store)
        box=self.page('Что нужно сделать сегодня','Действия по вашей точке · расчётные риски и фактические отметки')
        self.page_actions[5].addWidget(action('Что, если…',self.open_what_if))
        self.page_actions[5].addWidget(action('Демонстрации',self.open_dalion_demo))
        self.daily_note=text(''); box.addWidget(self.daily_note)
        self.daily_table=DataTable(['Приоритет','Действие','Почему']); box.addWidget(self.daily_table,1)
        self.daily_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.daily_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.daily_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.daily_table.doubleClicked.connect(self.run_daily_action)
        buttons=QHBoxLayout(); buttons.addWidget(action('Перейти к действию',self.run_daily_action,True))
        buttons.addWidget(action('Начать замер заявки',self.start_work)); buttons.addWidget(action('Завершить замер',self.finish_work)); buttons.addStretch(); box.addLayout(buttons)
        self.daily_status=text(''); box.addWidget(self.daily_status)

        box=self.page('Наличие блюд','Ручные отметки по точке · отсутствие продаж не означает отсутствие блюда')
        self.page_actions[6].addWidget(action('Обновить',self.refresh_availability))
        self.availability_table=DataTable(['Блюдо','Последняя отметка','Время отметки']); box.addWidget(self.availability_table,1)
        self.availability_reason=QLineEdit(); self.availability_reason.setPlaceholderText('Комментарий к отметке (необязательно)'); box.addWidget(self.availability_reason)
        buttons=QHBoxLayout(); buttons.addWidget(action('Закончилось',lambda:self.set_availability(False),True))
        buttons.addWidget(action('Снова доступно',lambda:self.set_availability(True))); buttons.addStretch(); box.addLayout(buttons)
        self.availability_status=text('Без отметок наличие остаётся неизвестным. История продаж не изменяется.'); box.addWidget(self.availability_status)
        self.availability_log=DataTable(['Время','Блюдо','Отметка','Автор','Комментарий']); self.availability_log.setMaximumHeight(210); box.addWidget(self.availability_log)

        box=self.page('Отчёт пилота','Измеренные показатели выбранной точки · без обещаний экономии')
        self.page_actions[7].addWidget(action('Зафиксировать прогноз',self.capture_pilot))
        self.page_actions[7].addWidget(action('Экспорт Excel',self.export_pilot_report))
        dates=QHBoxLayout(); dates.addWidget(text('С'))
        self.pilot_start=QDateEdit(date.today()-timedelta(days=30)); self.pilot_start.setCalendarPopup(True); dates.addWidget(self.pilot_start)
        dates.addWidget(text('По')); self.pilot_end=QDateEdit(date.today()); self.pilot_end.setCalendarPopup(True); dates.addWidget(self.pilot_end)
        dates.addWidget(action('Показать',self.refresh_pilot,True)); dates.addStretch(); box.addLayout(dates)
        self.pilot_metrics=DataTable(['Показатель','Значение']); self.pilot_metrics.verticalHeader().setDefaultSectionSize(32)
        self.pilot_metrics.setFixedHeight(244); box.addWidget(self.pilot_metrics)
        tabs=QTabWidget(); box.addWidget(tabs,1)
        self.pilot_details=DataTable(['Дата','Блюдо','Прогноз, порций','Факт, порций','Ошибка, порций']); tabs.addTab(self.pilot_details,'Проверенные прогнозы')
        self.pilot_absence=DataTable(['Блюдо','Зарегистрировано отсутствия, мин','Интервалов']); tabs.addTab(self.pilot_absence,'Отсутствие')
        self.pilot_waste=DataTable(['Ингредиент','Количество','Единица']); tabs.addTab(self.pilot_waste,'Списания')
        self.pilot_reasons=DataTable(['Причина ручной правки','Строк']); tabs.addTab(self.pilot_reasons,'Причины правок')
        self.pilot_note=text(''); box.addWidget(self.pilot_note)
        self.pilot_status=text(''); box.addWidget(self.pilot_status)

    def refresh_operations(self):
        if not hasattr(self,'daily_table'): return
        self.daily_items=daily_actions(self.store,self.pid(),self.calc_day(),self.snapshot,self.calculation_error)
        fill_rows(self.daily_table,[[['Срочно','Проверить','По плану'][row['priority']],row['title'],row['detail']] for row in self.daily_items])
        self.daily_note.setText(('ДЕМО · ' if self.store.get('demo') else '')+f'Действий: {len(self.daily_items)} · '+self.point.currentText())
        self.refresh_availability(); self.refresh_pilot()

    def run_daily_action(self,*args):
        index=self.daily_table.currentRow()
        if index<0 or index>=len(self.daily_items): return
        task=self.daily_items[index]; route=task['route']
        self.select_route('demand' if route=='availability' else 'stock',route)
        if task.get('ingredient'):
            self.search.setText(''); self.filter.setCurrentIndex(0)
            for index,row in enumerate(self.visible_stock):
                if row['id']==task['ingredient']: self.stock_table.selectRow(index); break
        if route=='order': self.make_order()

    def open_what_if(self):
        WhatIfDialog(self.store,self.pid(),self.calc_day(),self).exec()

    def refresh_availability(self):
        if not hasattr(self,'availability_table'): return
        selected=self.availability_table.currentRow()
        self.availability_dishes=[row for row in self.store.get('tables',{}).get('items',[]) if row['kind']=='dish']
        events=availability_events(self.store,self.pid()); latest={row['dish']:row for row in events}
        fill_rows(self.availability_table,[[row['name'],('Есть' if latest[str(row['id'])]['available'] else 'Закончилось') if str(row['id']) in latest else 'Не отмечено',
                       latest[str(row['id'])]['at'][:19].replace('T',' ') if str(row['id']) in latest else '—'] for row in self.availability_dishes])
        if selected>=0: self.availability_table.selectRow(selected)
        names={str(row['id']):row['name'] for row in self.availability_dishes}
        fill_rows(self.availability_log,[[row['at'][:19].replace('T',' '),names.get(row['dish'],row['dish']),
                   'Есть' if row['available'] else 'Закончилось',row['author'],row['reason']] for row in reversed(events[-100:])])

    def set_availability(self,available):
        index=self.availability_table.currentRow()
        if index<0: self.availability_status.setText('Выберите блюдо.'); return
        try:
            changed=mark_availability(self.store,self.pid(),self.availability_dishes[index]['id'],available,self.author(),self.availability_reason.text())
            self.availability_status.setText('Отметка сохранена в журнале.' if changed else 'Такая отметка уже действует. Повтор не добавлен.')
            self.availability_reason.clear(); self.refresh_operations()
        except (DataError,sqlite3.Error) as exc: self.availability_status.setText(str(exc))

    def start_work(self):
        try:
            if not self.snapshot: raise DataError('Сначала восстановите расчёт и проверьте график.')
            work_session(self.store,self.pid(),self.author()); self.daily_status.setText('Замер начат. После подготовки нажмите «Завершить замер».')
            self.make_order()
        except (DataError,sqlite3.Error) as exc: self.daily_status.setText(str(exc))

    def finish_work(self):
        try:
            work_session(self.store,self.pid(),self.author(),finish=True)
            self.daily_status.setText('Продолжительность сохранена в отчёте пилота.'); self.refresh_pilot()
        except DataError as exc: self.daily_status.setText(str(exc))

    def capture_pilot(self):
        try:
            payload=calculate(self.store.get('tables',{}),self.pid(),date.today(),self.store.get('settings',{}))
            if payload['errors']: raise DataError('\n'.join(payload['errors']))
            count=record_forecasts(self.store,self.pid(),payload)
            self.pilot_status.setText(f'Зафиксировано будущих значений: {count}. Первый прогноз не перезаписывается.'); self.refresh_pilot()
        except (DataError,sqlite3.Error) as exc: self.pilot_status.setText(str(exc))

    def refresh_pilot(self):
        if not hasattr(self,'pilot_metrics'): return
        self.pilot_result=None
        try:
            report=pilot_report(self.store,self.pid(),self.pilot_start.date().toPython(),self.pilot_end.date().toPython())
            def show(value,suffix=''): return 'Нет измерений' if value is None else f'{value:.2f}'+suffix
            fill_rows(self.pilot_metrics,[['Проверенных будущих прогнозов',report['forecast_count']],['Средняя ошибка, порций',show(report['mae'])],
                ['WAPE',show(report['wape'],' %')],['Ручные правки строк заявок',show(report['edit_share'],' %')],
                ['Медиана подготовки заявки',show(report['median_minutes'],' мин')],['Списания по текущей себестоимости',show(report['writeoff_cost'],' ₽')]])
            fill_rows(self.pilot_details,[[r['date'],r['dish'],f'{r["expected"]:.2f}',r['actual'],f'{r["error"]:.2f}'] for r in report['forecasts']])
            fill_rows(self.pilot_absence,[[r['name'],f'{r["minutes"]:.1f}',r['intervals']] for r in report['absence']])
            fill_rows(self.pilot_waste,[[r['name'],r['qty'],r['unit']] for r in report['writeoffs']])
            fill_rows(self.pilot_reasons,list(report['reasons'].items()))
            skipped='; '.join(f'{key}: {value}' for key,value in report['skipped'].items())
            self.pilot_note.setText(('ДЕМО · ' if report['demo'] else '')+report['note']+ (' Исключено: '+skipped if skipped else ''))
            self.pilot_result=report
        except (DataError,ValueError) as exc:
            for table in (self.pilot_metrics,self.pilot_details,self.pilot_absence,self.pilot_waste,self.pilot_reasons): table.setRowCount(0)
            self.pilot_note.setText(str(exc))

    def export_pilot_report(self):
        self.refresh_pilot()
        if self.pilot_result is None: return
        path,_=QFileDialog.getSaveFileName(self,'Отчёт пилота','Пилот.xlsx','Excel (*.xlsx)')
        if path:
            def save():
                export_pilot(path,self.pilot_result); self.notify_export('Отчёт пилота экспортирован.',path)
            self.safe(save)
