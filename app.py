from __future__ import annotations
import calendar
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt,QTimer,QPointF,QRectF
from PySide6.QtGui import QColor,QFont,QPainter,QPainterPath,QPen
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QFrame,QStackedWidget,QComboBox,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
    QMessageBox,QFileDialog,QDialog,QFormLayout,QDialogButtonBox,QDoubleSpinBox,QSpinBox,QTextEdit,
    QCheckBox,QDateEdit,QSplitter)
from core import Store,DataError,calculate,now,export_order,write_templates,LABELS,SCHEMAS

STYLE='''
* { font-family: "Segoe UI"; font-size: 13px; color: #243b34; }
QMainWindow, QDialog { background: #f5f6f2; }
QWidget#sidebar { background: #193c32; }
QWidget#sidebar QLabel { color: #cbd9d2; background: transparent; }
QWidget#sidebar QPushButton { color: #cbd9d2; text-align: left; border: none; border-radius: 9px; padding: 14px 18px; background: transparent; font-size: 14px; }
QWidget#sidebar QPushButton:hover { background: #285045; }
QWidget#sidebar QPushButton:checked { background: #375b4b; color: white; font-weight: 600; }
QLabel#brand { font-size: 22px; font-weight: 700; color: white; }
QLabel#title { font-size: 29px; font-weight: 650; }
QLabel#subtitle { color: #718078; }
QLabel#eyebrow { color: #d6ad70; font-size: 11px; letter-spacing: 2px; }
QLabel#notice { background: #fff0d8; color: #806234; padding: 12px 16px; border-radius: 9px; }
QLabel#success { background: #e2eee6; color: #32634e; padding: 11px 15px; border-radius: 8px; }
QFrame#card { background: white; border: 1px solid #e3e8e2; border-radius: 12px; }
QLabel#number { font-size: 28px; font-weight: 650; }
QLabel#section { font-size: 17px; font-weight: 600; }
QPushButton { border: 1px solid #d5dfd7; border-radius: 7px; background: white; padding: 9px 15px; }
QPushButton:hover { background: #edf2ec; }
QPushButton:disabled { color: #9ca59f; background: #e9ece7; }
QPushButton#primary { color: white; background: #cb653b; border: 1px solid #cb653b; font-weight: 600; }
QPushButton#primary:hover { background: #b9552e; }
QLineEdit,QComboBox,QDateEdit,QSpinBox,QDoubleSpinBox { background: white; border: 1px solid #dce3dc; border-radius: 7px; padding: 8px; min-height: 18px; }
QTextEdit { background: white; border: 1px solid #dce3dc; border-radius: 8px; padding: 10px; }
QTableWidget { border: none; background: white; gridline-color: #ecf0eb; selection-background-color: #e4eee6; selection-color: #193c32; border-radius: 8px; }
QTableWidget::item { padding: 9px; border-bottom: 1px solid #ecf0eb; }
QHeaderView::section { background: #f5f7f3; color: #78857c; font-size: 11px; font-weight: 600; border: none; padding: 12px 9px; }
QTableWidget QTableCornerButton::section { border: none; background: #f5f7f3; }
QCheckBox { spacing: 9px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QScrollBar:vertical { background: #f4f6f1; width: 9px; }
QScrollBar::handle:vertical { background: #cbd6cc; min-height: 24px; border-radius: 4px; }
QToolTip { background: #193c32; color: white; padding: 8px; border: none; }
'''

def label(text,name=None):
    w=QLabel(text)
    if name: w.setObjectName(name)
    return w

def button(text,fn,primary=False):
    b=QPushButton(text); b.clicked.connect(fn)
    if primary: b.setObjectName('primary')
    return b

def fmt(v,d=1):
    return f'{v:,.{d}f}'.replace(',',' ').replace('.',',')

def table(headers):
    t=QTableWidget(0,len(headers)); t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().hide(); t.verticalHeader().setDefaultSectionSize(53)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setShowGrid(False); t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
    return t

def fill(t,rows,colors=None):
    t.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            item=QTableWidgetItem(str(value)); item.setToolTip(str(value)); t.setItem(i,j,item)
            if j and colors and colors[i]: item.setForeground(QColor(colors[i]))
    if rows: t.selectRow(0)

class MonthChart(QWidget):
    def __init__(self):
        super().__init__(); self.series=[]; self.setMinimumHeight(135)
    def set_data(self,sales,dish,point,day):
        self.series=[]
        for delta in [3,2,1]:
            n=day.year*12+day.month-1-delta; y,m=divmod(n,12); m+=1
            records={int(str(r['date'])[8:]):float(r['qty']) for r in sales if str(r['dish'])==dish and str(r['point'])==point and str(r['date']).startswith(f'{y}-{m:02}')}
            names=['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']
            self.series.append((f'{names[m-1]} {y}',records))
        self.update()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w,h=self.width(),self.height(); left,top,right,bottom=46,16,w-15,h-52
        maximum=max([v for _,s in self.series for v in s.values()]+[1])*1.1
        colors=['#d5b47b','#d07650','#39755e']
        p.setFont(QFont('Segoe UI',9))
        for i in range(4):
            y=bottom-(bottom-top)*i/3
            p.setPen(QPen(QColor('#e8eee7'),1)); p.drawLine(QPointF(left,y),QPointF(right,y))
            p.setPen(QColor('#8b968d')); p.drawText(QRectF(0,y-9,38,18),Qt.AlignmentFlag.AlignRight,f'{maximum*i/3:.0f}')
        for j,(name,s) in enumerate(self.series):
            p.setPen(QPen(QColor(colors[j]),2)); path=QPainterPath(); last=None
            for d,v in sorted(s.items()):
                x=left+(right-left)*(d-1)/30; y=bottom-(bottom-top)*v/maximum
                if last is None or d!=last+1: path.moveTo(x,y)
                else: path.lineTo(x,y)
                last=d
            p.drawPath(path)
            x=left+j*170; p.drawLine(QPointF(x,h-10),QPointF(x+20,h-10)); p.setPen(QColor('#63766a')); p.drawText(QPointF(x+28,h-5),name)
        for d in [1,5,10,15,20,25,31]:
            p.drawText(QPointF(left+(right-left)*(d-1)/30-4,bottom+21),str(d))
        p.drawText(QPointF(right-85,bottom+37),'День месяца')

class MainWindow(QMainWindow):
    def __init__(self,store):
        super().__init__(); self.store=store; self.current=None; self.busy=False; self.stock_revision=None
        self.setWindowTitle('Русские блины — управление запасами'); self.resize(1440,940); self.setMinimumSize(1120,780)
        root=QWidget(); self.setCentralWidget(root); outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        sidebar=QWidget(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(235); side=QVBoxLayout(sidebar); side.setContentsMargins(22,30,22,24); side.setSpacing(7)
        side.addWidget(label('◉  РУССКИЕ\n    БЛИНЫ','brand')); side.addSpacing(4); side.addWidget(label('ПЛАНИРОВАНИЕ ЗАПАСОВ','eyebrow')); side.addSpacing(32)
        self.nav=[]
        for idx,(icon,name) in enumerate([('▦','Остатки'),('▤','Заявка на поставку'),('↗','Данные и импорт'),('◷','История'),('⚙','Настройки')]):
            b=button(f'{icon}    {name}',lambda checked=False,i=idx:self.navigate(i)); b.setCheckable(True); self.nav.append(b); side.addWidget(b)
        side.addStretch(); side.addWidget(label('Локальная база данных\nРасчёт доступен офлайн'))
        self.offline=QCheckBox('Режим без связи'); self.offline.setStyleSheet('color: #cbd9d2; margin-top: 12px;'); self.offline.toggled.connect(self.network_changed); side.addWidget(self.offline)
        side.addSpacing(16); side.addWidget(label('●  Продавец\n    Рабочее место · v1.0'))
        outer.addWidget(sidebar)
        content=QWidget(); area=QVBoxLayout(content); area.setContentsMargins(30,24,30,20); area.setSpacing(16)
        top=QHBoxLayout(); top.addWidget(label('РАБОЧЕЕ МЕСТО ПРОДАВЦА','subtitle')); top.addStretch()
        self.point=QComboBox(); self.point.setMinimumWidth(260)
        tables=self.store.get('tables',{})
        for point in tables.get('points',[]): self.point.addItem(point['name'],str(point['id']))
        self.point.currentIndexChanged.connect(self.point_changed); top.addWidget(self.point)
        self.day_label=label(date.today().strftime('%d.%m.%Y'),'subtitle'); top.addSpacing(14); top.addWidget(self.day_label); area.addLayout(top)
        self.banner=label('','notice'); self.banner.setWordWrap(True); area.addWidget(self.banner)
        self.stack=QStackedWidget(); area.addWidget(self.stack,1)
        self.status=label('','subtitle'); area.addWidget(self.status)
        outer.addWidget(content,1)
        self.build_stock(); self.build_order(); self.build_import(); self.build_history(); self.build_settings()
        self.reload(); self.navigate(0)

    def pid(self): return str(self.point.currentData() or '')
    def author(self): return self.store.get('settings',{}).get('author','Продавец')
    def calc_day(self): return date.fromisoformat(self.store.get('settings',{}).get('calculation_date',date.today().isoformat()))
    def page(self,title,subtitle):
        p=QWidget(); box=QVBoxLayout(p); box.setContentsMargins(0,0,0,0); box.setSpacing(10)
        box.addWidget(label(title,'title')); sub=label(subtitle,'subtitle'); sub.setWordWrap(True); box.addWidget(sub)
        self.stack.addWidget(p); return box
    def navigate(self,i):
        self.stack.setCurrentIndex(i)
        for j,b in enumerate(self.nav): b.setChecked(i==j)
        if i==3: self.reload_history()
    def message(self,text): QMessageBox.information(self,'Русские блины',text)
    def error(self,e): QMessageBox.warning(self,'Нужно проверить',str(e))
    def safe(self,fn):
        try: return fn()
        except (DataError,OSError,ValueError,KeyError) as e: self.error(e)
    def network_changed(self):
        self.status.setText('Без связи: импортированные данные, прогноз, черновики и Excel доступны локально.' if self.offline.isChecked() else 'Локальный режим · подключение к учетным системам не настроено · отправка поставщику отключена')
    def point_changed(self):
        self.stock_revision=None; self.stock_check.setChecked(False)
        schedules=[r for r in self.store.get('tables',{}).get('schedules',[]) if str(r['point'])==self.pid()]
        if schedules and hasattr(self,'delivery_input'):
            self.delivery_input.setDate(date.fromisoformat(str(schedules[0]['next_delivery'])))
            self.interval_input.setValue(int(float(schedules[0]['interval_days'])))
        self.reload()

    def build_stock(self):
        box=self.page('Остатки под контролем','Сверьте фактическое наличие перед подготовкой заявки на следующую поставку.')
        self.fresh=label('','success'); self.fresh.setWordWrap(True); box.addWidget(self.fresh)
        metrics=QHBoxLayout(); self.metrics=[]
        for name,hint in [('Позиций на контроле','ингредиенты в ассортименте'),('Требуют пополнения','по расчётному спросу'),('Риск избыточного запаса','проверить количество'),('Следующая поставка','по заданному графику')]:
            frame=QFrame(); frame.setObjectName('card'); inner=QVBoxLayout(frame); inner.setContentsMargins(18,10,18,10)
            inner.addWidget(label(name,'subtitle')); val=label('—','number'); inner.addWidget(val); inner.addWidget(label(hint,'subtitle')); self.metrics.append(val); metrics.addWidget(frame)
        box.addLayout(metrics)
        tools=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText('Поиск ингредиента…'); self.search.textChanged.connect(self.refresh_stock)
        self.filter=QComboBox(); self.filter.addItems(['Все позиции','Нужно пополнить','Возможен излишек']); self.filter.currentIndexChanged.connect(self.refresh_stock)
        tools.addWidget(self.search,1); tools.addWidget(self.filter); tools.addWidget(button('Сверить / списать',self.edit_stock)); tools.addWidget(button('Сформировать заявку →',self.make_order,True)); box.addLayout(tools)
        self.stock_table=table(['Ингредиент','Остаток','В порциях¹','Потребность','Состояние']); self.stock_table.setMinimumHeight(230); self.stock_table.doubleClicked.connect(self.explain_stock); box.addWidget(self.stock_table,3)
        foot=label('¹ Эквивалент по техкарте. Порции блюд с общим ингредиентом нельзя складывать. Двойной щелчок — объяснение.','subtitle'); foot.setWordWrap(True); box.addWidget(foot)
        card=QFrame(); card.setObjectName('card'); cardbox=QVBoxLayout(card); cardbox.setContentsMargins(18,13,18,13)
        heading=QHBoxLayout(); heading.addWidget(label('Продажи по месяцам','section')); heading.addStretch(); heading.addWidget(label('порций / день','subtitle'))
        self.chart_dish=QComboBox(); self.chart_dish.currentIndexChanged.connect(self.refresh_chart); heading.addWidget(self.chart_dish); cardbox.addLayout(heading)
        self.chart=MonthChart(); cardbox.addWidget(self.chart); box.addWidget(card,2)

    def reload(self):
        tables=self.store.get('tables',{}); demo=self.store.get('demo',False)
        self.banner.setText('ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ · Синтетические продажи и условные настройки. Экономический эффект не доказан.' if demo else 'ДАННЫЕ ИЗ ФАЙЛОВ · Проверьте полноту выгрузки, технологические карты и пригодность остатков.')
        self.network_changed()
        self.snapshot=None
        try: self.snapshot=calculate(tables,self.pid(),self.calc_day(),self.store.get('settings',{}))
        except (DataError,KeyError,ValueError) as e: self.status.setText('Расчёт недоступен: '+str(e))
        if self.snapshot:
            s=self.snapshot; last=s.get('last_closed') or 'нет данных'; stale=not s.get('last_closed') or (max(self.calc_day(),date.today())-date.fromisoformat(last)).days>1
            self.fresh.setText(f'{"⚠ Данные устарели. " if stale else "● "}Последняя закрытая смена: {last}   ·   Импорт: {str(self.store.get("import_time","—"))[:19]}\nПродажи текущей смены не получены. Остатки — отдельный фактический снимок; потребность — расчётная оценка.')
            rows=s['rows']; vals=[str(len(rows)),str(sum(r['packs']>0 for r in rows)),str(sum(r['surplus']>r['target'] for r in rows)),date.fromisoformat(s['arrival']).strftime('%d.%m')]
            for l,v in zip(self.metrics,vals): l.setText(v)
        else:
            self.fresh.setText('Недостаточно данных для расчёта. Откройте «Данные и импорт».')
            for l in self.metrics: l.setText('—')
        self.refresh_stock()
        saved=self.store.get('draft:'+self.pid())
        self.current=saved
        self.refresh_order()
        selected=self.chart_dish.currentData(); self.chart_dish.blockSignals(True); self.chart_dish.clear()
        for item in tables.get('items',[]):
            if item['kind']=='dish': self.chart_dish.addItem(item['name'],str(item['id']))
        ix=self.chart_dish.findData(selected)
        if ix>=0: self.chart_dish.setCurrentIndex(ix)
        self.chart_dish.blockSignals(False); self.refresh_chart(); self.refresh_quality()
    def refresh_chart(self):
        if hasattr(self,'chart'): self.chart.set_data(self.store.get('tables',{}).get('sales',[]),str(self.chart_dish.currentData()),self.pid(),self.calc_day())
    def refresh_stock(self):
        if not hasattr(self,'stock_table'): return
        rows=(self.snapshot or {}).get('rows',[]); q=self.search.text().lower(); mode=self.filter.currentIndex()
        self.visible_stock=[r for r in rows if q in r['name'].lower() and (mode==0 or mode==1 and r['packs']>0 or mode==2 and r['surplus']>r['target'])]
        rendered=[]; colors=[]
        for r in self.visible_stock:
            state='Дефицит до доставки' if r['shortage_before']>0 else 'Пополнить' if r['packs']>0 else 'Возможен излишек' if r['surplus']>r['target'] else 'Достаточно'
            rendered.append([r['name'],f'{fmt(r["stock"])} {r["unit"]}',fmt(r['stock']/r['portion_rate'],0) if r['portion_rate'] else 'разный расход',f'{fmt(r["demand"])} {r["unit"]}',state])
            colors.append('#b8683c' if state in ('Пополнить','Дефицит до доставки') else '#38715b')
        fill(self.stock_table,rendered,colors)
    def explain_stock(self):
        i=self.stock_table.currentRow()
        if 0<=i<len(self.visible_stock): self.show_explanation(self.visible_stock[i])
    def show_explanation(self,r):
        p=r['portion_rate']; unit=r['unit']; conv=lambda v:f'{fmt(v)} {unit}'+(f' ≈ {fmt(v/p,0)} порций' if p else '')
        text=f'{r["name"]}\n\nПотребность на период — {conv(r["demand"])}\nТекущий пригодный остаток — {conv(r["stock"])}\nПодтвержденные поступления — {conv(r["incoming"])}\nЦелевой остаток — {conv(r["target"])}\nРекомендация — {r["packs"]} уп. по {conv(r["pack"])}\n\nФормула: max(0, потребность + цель − пригодный остаток − поступления), затем округление до упаковки.\nДополнительный запас от округления — {conv(r["rounding"])}\nДефицит до доставки — {conv(r["shortage_before"])}\nРазрыв из-за времени поступлений — {conv(r["timing_gap"])}\nРиск избыточного запаса — {conv(r["surplus"])}\nСписания за 28 дней — {conv(r["waste"])} / {fmt(r["waste"]*r["cost"],2)} ₽ по себестоимости\nИсключено продавцом — {conv(r["blocked"])}\nНе будет использовано до явно указанной даты — {conv(r["expiry_excluded"])}\nПоследняя сверка партии: {r["checked_at"]}\nПартий без известной даты: {r["unknown_dates"]}. Пригодность подтверждает продавец.\nПросроченных ожидаемых поступлений исключено: {r["late"]}\n\nОбщая потребность ингредиента по блюдам:\n'+ '\n'.join(f'• {name}: {conv(v)}' for name,v in r['contributions'].items())
        self.message(text)
    def edit_stock(self):
        self.safe(self._edit_stock)
    def _edit_stock(self):
        tables=self.store.get('tables',{}); batches=[b for b in tables.get('batches',[]) if str(b['point'])==self.pid()]
        if not batches: raise DataError('Нет партий. Загрузите остатки.')
        names={str(i['id']):i['name'] for i in tables['items']}
        dialog=QDialog(self); dialog.setWindowTitle('Сверка фактического остатка'); dialog.setMinimumWidth(540); form=QFormLayout(dialog)
        combo=QComboBox()
        for b in batches: combo.addItem(f'{names[str(b["ingredient"])]} · партия {b["id"]}',str(b['id']))
        qty=QDoubleSpinBox(); qty.setRange(0,100000); qty.setDecimals(3)
        usable=QCheckBox('Пригодность подтверждена по правилам точки')
        mode=QComboBox(); mode.addItems(['Установить фактический остаток','Зарегистрировать списание'])
        reason=QLineEdit(); reason.setPlaceholderText('Обязательная причина')
        info=label('','subtitle'); info.setWordWrap(True)
        def selected():
            b=batches[combo.currentIndex()]; qty.setValue(float(b['qty'])); usable.setChecked(str(b['usable']).lower() in ('1','true'))
            info.setText(f'Единица: {b["unit"]}. Сверка: {b["checked_at"]}\nЯвная дата использования: {b.get("use_before") or "не указана — приложение её не определяет"}')
        combo.currentIndexChanged.connect(selected); selected()
        form.addRow('Партия',combo); form.addRow(info); form.addRow('Действие',mode); form.addRow('Количество',qty); form.addRow(usable); form.addRow('Причина',reason)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.store.correct_batch(combo.currentData(),qty.value(),usable.isChecked(),reason.text(),self.author(),mode.currentIndex()==1)
            self.stock_revision=None; self.stock_check.setChecked(False); self.reload(); self.status.setText('Изменение сохранено в журнале. Пересчитайте заявку; ручные правки сохранятся.')

    def build_order(self):
        box=self.page('Заявка на поставку','Рекомендация остаётся исходной. Ваши изменения сохраняются отдельно с причиной и временем.')
        tools=QHBoxLayout(); self.cover=label('Сначала сформируйте заявку','success'); tools.addWidget(self.cover,1)
        tools.addWidget(button('Пересчитать',self.make_order)); box.addLayout(tools)
        self.order_warn=label('','notice'); self.order_warn.setWordWrap(True); box.addWidget(self.order_warn)
        self.order_table=table(['Ингредиент','Потребность','Рекоменд., уп.','Итого, уп.','Заказ, ед.','Сумма, ₽']); self.order_table.doubleClicked.connect(self.edit_order)
        box.addWidget(self.order_table,3)
        line=QHBoxLayout(); line.addWidget(button('Изменить количество',self.edit_order)); line.addWidget(button('Объяснить расчёт',self.explain_order)); line.addStretch(); self.total=label('','section'); line.addWidget(self.total); box.addLayout(line)
        self.forecast_table=table(['Прогноз блюд · порции','Ожидается','Ориентир','Спрос','Метод']); self.forecast_table.doubleClicked.connect(self.explain_forecast); self.forecast_table.verticalHeader().setDefaultSectionSize(39); box.addWidget(self.forecast_table,2)
        note=label('Диапазон — описательный ориентир по разбросу прошлых продаж, без гарантии вероятности. Двойной щелчок — сравнение методов.','subtitle'); note.setWordWrap(True); box.addWidget(note)
        self.stock_check=QCheckBox('Фактические остатки и пригодность партий сверены мной для этой заявки'); self.stock_check.toggled.connect(self.check_stock); box.addWidget(self.stock_check)
        footer=QHBoxLayout(); footer.addWidget(label('Сохраняется локально · поставщику не отправляется','subtitle')); footer.addStretch(); self.confirm_btn=button('Подтвердить и экспортировать Excel',self.confirm_order,True); footer.addWidget(self.confirm_btn); box.addLayout(footer)
    def check_stock(self,checked):
        if self.busy or not self.current: return
        self.current['stock_confirmed']=checked
        self.current['stock_confirmed_at']=now() if checked else None
        self.current['stock_confirmed_revision']=self.store.get('revision') if checked else None
        self.save_current()
    def save_current(self):
        if self.current: self.store.save_draft(self.pid(),self.current)
    def make_order(self): self.safe(self._make_order)
    def _make_order(self):
        if not self.snapshot: raise DataError('Расчёт недоступен. Проверьте данные и график поставок.')
        old=self.current or {}; edits=old.get('edits',{})
        payload=calculate(self.store.get('tables'),self.pid(),self.calc_day(),self.store.get('settings',{}))
        payload.update(edits=edits,revision=self.store.get('revision'),demo=self.store.get('demo'),author=self.author(),stock_confirmed=False)
        valid={r['id'] for r in payload['rows']}
        orphan=set(edits)-valid
        if orphan: payload['errors'].append('Правки относятся к удаленным позициям: '+', '.join(orphan)+'. Нужна сверка справочника.')
        self.current=payload
        with self.store.db:
            self.store.log('Пересчёт заявки',old,payload,'Расчет по актуальным данным; ручные правки сохранены',self.author())
            self.store.put('draft:'+self.pid(),payload)
        self.refresh_order(); self.navigate(1)
    def refresh_order(self):
        if not hasattr(self,'order_table'): return
        self.busy=True
        p=self.current
        if not p:
            self.cover.setText('Сначала сформируйте заявку'); fill(self.order_table,[]); fill(self.forecast_table,[]); self.order_warn.setText('Черновик ещё не создан.'); self.confirm_btn.setEnabled(False); self.busy=False; return
        self.cover.setText(f'Покрытие: {p["date"]} → {p["end"]} (не включая) · {p["days"]} дн. · Поставка {p["arrival"]}')
        changed=p.get('revision')!=self.store.get('revision')
        errors=p.get('errors',[])
        warns=[]
        if changed: warns.append('Данные изменились. Пересчитайте перед подтверждением.')
        if errors: warns+=errors
        if any(r['shortage_before']>0 for r in p['rows']): warns.append('Есть дефицит до доставки: обычная заявка не закроет этот разрыв. Проверьте ускоренное пополнение.')
        if any(r['timing_gap']>0 for r in p['rows']): warns.append('Часть поступлений придёт позже потребности. Проверьте даты и ускоренное пополнение.')
        if any(r['waste']>0 for r in p['rows']): warns.append('Есть фактические списания за 28 дней — проверьте излишки и редкий спрос. Дополнительный страховой запас не добавлен.')
        if any(r['unknown_dates'] for r in p['rows']): warns.append('Даты пригодности не заданы. Проверьте партии по действующим правилам точки.')
        self.order_warn.setText('\n'.join(warns) or 'Расчёт готов к проверке продавцом.')
        rendered=[]; total=0
        for r in p['rows']:
            e=p.get('edits',{}).get(r['id']); n=e['packs'] if e else r['packs']; total+=n*r['pack']*r['cost']
            rendered.append([r['name'],f'{fmt(r["demand"])} {r["unit"]}',str(r['packs']),str(n)+(' ✎' if e else ''),f'{fmt(n*r["pack"])} {r["unit"]}',fmt(n*r['pack']*r['cost'],0)])
        fill(self.order_table,rendered)
        fill(self.forecast_table,[[f['name'],fmt(f['expected'],0),f'{fmt(f["low"],0)}–{fmt(f["high"],0)}',f['segment'],f['method']] for f in p['forecasts']])
        self.total.setText(f'Итого: {fmt(total,0)} ₽'); self.stock_check.setChecked(bool(p.get('stock_confirmed')) and not changed)
        self.confirm_btn.setEnabled(not errors and not changed); self.busy=False
    def explain_order(self):
        i=self.order_table.currentRow()
        if self.current and i>=0: self.show_explanation(self.current['rows'][i])
    def explain_forecast(self):
        i=self.forecast_table.currentRow()
        if not self.current or i<0: return
        f=self.current['forecasts'][i]
        self.message(f'{f["name"]}\n\nВыбран метод: {f["method"]}\nСегмент: {f["segment"]}. Наблюдений: {f["observations"]}\n\nПоследовательная проверка на последних 28 доступных днях. Средняя абсолютная ошибка (порций за день):\n'+'\n'.join(f'{m}: {fmt(v,2) if v is not None else "мало истории"}' for m,v in f['scores'].items())+'\n\n'+'\n'.join(f['warnings'])+'\n\nПри проверке используются только прошлые наблюдения. Метод выбирается по этому же окну: это предварительная оценка, не независимый итог пилота.')
    def edit_order(self): self.safe(self._edit_order)
    def _edit_order(self):
        i=self.order_table.currentRow()
        if not self.current or i<0: return
        r=self.current['rows'][i]; old=self.current.get('edits',{}).get(r['id'])
        d=QDialog(self); d.setWindowTitle(r['name']); d.setMinimumWidth(470); form=QFormLayout(d)
        form.addRow(label(f'Исходная рекомендация: {r["packs"]} уп. по {fmt(r["pack"])} {r["unit"]}'))
        qty=QSpinBox(); qty.setRange(0,100000); qty.setValue(old['packs'] if old else r['packs'])
        reason=QLineEdit(); reason.setPlaceholderText('Например: ожидается большой заказ'); form.addRow('Итого упаковок',qty); form.addRow('Причина',reason)
        actions=QHBoxLayout(); actions.addWidget(button('Обнулить',lambda:qty.setValue(0))); actions.addWidget(button('Вернуть рекомендацию',lambda:qty.setValue(r['packs']))); form.addRow(actions)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); form.addRow(bb)
        if d.exec()==QDialog.DialogCode.Accepted:
            if not reason.text().strip(): raise DataError('Нужна причина ручного изменения')
            edit={'packs':qty.value(),'reason':reason.text(),'author':self.author(),'at':now()}
            self.current.setdefault('edits',{})[r['id']]=edit
            with self.store.db:
                self.store.log('Правка заявки',{'id':r['id'],'old':old,'recommended':r['packs']},edit,reason.text(),self.author())
                self.store.put('draft:'+self.pid(),self.current)
            self.refresh_order()
    def confirm_order(self): self.safe(self._confirm_order)
    def _confirm_order(self):
        if not self.current: return
        if not self.stock_check.isChecked(): raise DataError('Сначала подтвердите сверку остатков и пригодности партий.')
        path,_=QFileDialog.getSaveFileName(self,'Экспорт подтверждённой заявки',str(Path.home()/'Desktop'/f'Заявка_{self.calc_day()}.xlsx'),'Excel (*.xlsx)')
        if not path: return
        if Path(path).suffix.lower()!='.xlsx': path+='.xlsx'
        p=json.loads(json.dumps(self.current)); p['author']=self.author(); p['confirmed_at']=now()
        id=self.store.confirm(self.pid(),p,self.author())
        try: export_order(path,p,id)
        except Exception:
            self.message(f'Заявка №{id} сохранена. Excel создать не удалось. Повторите экспорт из истории.'); raise
        self.message(f'Заявка №{id} сохранена и экспортирована:\n{path}\n\nОтправка поставщику не выполнялась.')

    def build_import(self):
        box=self.page('Данные и импорт','Загрузите снимки из XLSX или CSV. Строки проверяются до записи в базу.')
        hint=label('Для первого импорта используйте полный XLSX либо начните с points.csv. Таблица заменяется целиком; повторный файл пропускается. Демо и реальные данные не смешиваются.','notice'); hint.setWordWrap(True); box.addWidget(hint)
        row=QHBoxLayout(); row.addWidget(button('Импорт XLSX / CSV',self.import_data,True)); row.addWidget(button('Сохранить пустые шаблоны',lambda:self.templates(False))); row.addWidget(button('Сохранить демо-пример',lambda:self.templates(True))); row.addStretch(); box.addLayout(row)
        self.quality=table(['Набор данных','Строк','Назначение']); box.addWidget(self.quality)
        self.import_report=QTextEdit(); self.import_report.setReadOnly(True); self.import_report.setMinimumHeight(150); box.addWidget(self.import_report)
    def refresh_quality(self):
        if not hasattr(self,'quality'): return
        tables=self.store.get('tables',{}); notes={'points':'Справочник точек','items':'Цена/себестоимость ₽ за учетную единицу; упаковка и целевой запас','sales':'Только закрытые смены; отсутствие не равно нулевому спросу','batches':'Факт по партиям; пригодность и время сверки обязательны','recipes':'Расход на порцию; версия и дата начала действия','deliveries':'Только подтвержденные; дата и количество','movements':'Журнал операций; не применяется повторно к фактическому остатку','schedules':'Ближайшая дата и интервал между поставками'}
        fill(self.quality,[[LABELS[k],len(tables.get(k,[])),notes[k]] for k in SCHEMAS])
        errors=(self.snapshot or {}).get('errors',[])
        self.import_report.setPlainText('Качество расчёта:\n'+ ('\n'.join(errors) if errors else 'Структурные ошибки не обнаружены. Пригодность, полнота продаж и корректность техкарт требуют проверки на точке.')+'\n\nПодключения Frontol / ДАЛИОН: адаптер не реализован, версии и форматы не согласованы.\nДаты партий необязательны и не выводятся из даты прихода. Незакрытые смены отклоняются.\nПустые ячейки не заменяются нулями. Пустой use_before означает неизвестную дату.\nДля нулевых продаж нужна явная строка; пропущенный день остаётся неизвестным.')
    def templates(self,demo):
        folder=QFileDialog.getExistingDirectory(self,'Папка для шаблонов')
        if folder:
            from core import demo_data
            self.safe(lambda:write_templates(folder,demo_data() if demo else None)); self.status.setText('Файлы сохранены: '+folder)
    def import_data(self):
        path,_=QFileDialog.getOpenFileName(self,'Импорт снимка данных','','Таблицы (*.xlsx *.csv)')
        if not path: return
        kind=None
        if Path(path).suffix.lower()=='.csv':
            dialog=QDialog(self); dialog.setWindowTitle('Тип CSV'); layout=QVBoxLayout(dialog); choice=QComboBox()
            for k in SCHEMAS: choice.addItem(k+' — '+LABELS[k],k)
            ix=choice.findData(Path(path).stem)
            if ix>=0: choice.setCurrentIndex(ix)
            layout.addWidget(choice); bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); bb.accepted.connect(dialog.accept); bb.rejected.connect(dialog.reject); layout.addWidget(bb)
            if dialog.exec()!=QDialog.DialogCode.Accepted: return
            kind=choice.currentData()
        try:
            result=self.store.import_file(path,kind,self.author()); self.message(result)
            self.point.blockSignals(True); self.point.clear()
            for p in self.store.get('tables',{}).get('points',[]): self.point.addItem(p['name'],str(p['id']))
            self.point.blockSignals(False); self.fill_item_settings(); self.point_changed()
        except Exception as e:
            self.import_report.setPlainText('Импорт отменён. Данные не изменены.\n\n'+str(e)); self.error(e)

    def build_history(self):
        box=self.page('История и корректировки','Подтверждённые заявки и журнал изменений с автором, временем и причиной.')
        row=QHBoxLayout(); row.addWidget(label('Сохранённые заявки','section')); row.addStretch(); row.addWidget(button('Экспортировать выбранную',self.export_history)); box.addLayout(row)
        self.orders_table=table(['Заявка / точка','Дата и время','Статус','Правок']); box.addWidget(self.orders_table,2)
        box.addWidget(label('Журнал действий','section'))
        self.audit_table=table(['Действие','Время','Автор','Причина']); self.audit_table.doubleClicked.connect(self.audit_details); box.addWidget(self.audit_table,3)
    def reload_history(self):
        self.orders=list(self.store.db.execute('SELECT id,created,point,status,payload FROM orders ORDER BY id DESC'))
        fill(self.orders_table,[[f'№{r[0]} · {r[2]}',r[1][:19],r[3],len(json.loads(r[4]).get('edits',{}))] for r in self.orders])
        self.audits=list(self.store.db.execute('SELECT kind,created,author,reason,before_json,after_json FROM audit ORDER BY id DESC LIMIT 300'))
        fill(self.audit_table,[[r[0],r[1][:19],r[2],r[3]] for r in self.audits])
    def audit_details(self):
        i=self.audit_table.currentRow()
        if i<0: return
        r=self.audits[i]; dialog=QDialog(self); dialog.setWindowTitle('Подробности изменения'); dialog.resize(750,540); layout=QVBoxLayout(dialog); text=QTextEdit(); text.setReadOnly(True)
        text.setPlainText(f'{r[0]} · {r[1]} · {r[2]}\nПричина: {r[3]}\n\nДо:\n{json.dumps(json.loads(r[4]),ensure_ascii=False,indent=2)}\n\nПосле:\n{json.dumps(json.loads(r[5]),ensure_ascii=False,indent=2)}'); layout.addWidget(text); dialog.exec()
    def export_history(self):
        i=self.orders_table.currentRow()
        if i<0: return
        row=self.orders[i]; path,_=QFileDialog.getSaveFileName(self,'Повторный экспорт',f'Заявка_{row[0]}.xlsx','Excel (*.xlsx)')
        if path:
            if Path(path).suffix.lower()!='.xlsx': path+='.xlsx'
            self.safe(lambda:export_order(path,json.loads(row[4]),row[0]))

    def build_settings(self):
        box=self.page('Настройки расчёта','Технические настройки демонстрации. Значения нужно согласовать до пилота.')
        frame=QFrame(); frame.setObjectName('card'); form=QFormLayout(frame); form.setContentsMargins(24,22,24,22); form.setSpacing(16)
        settings=self.store.get('settings',{})
        self.author_input=QLineEdit(settings.get('author','Продавец')); form.addRow('Имя продавца для журнала',self.author_input)
        self.date_input=QDateEdit(); self.date_input.setCalendarPopup(True); self.date_input.setDate(self.calc_day()); self.date_input.setDisplayFormat('dd.MM.yyyy'); form.addRow('Дата расчёта',self.date_input)
        self.share_input=QDoubleSpinBox(); self.share_input.setRange(.1,1); self.share_input.setSingleStep(.05); self.share_input.setValue(settings.get('regular_share',.6)); form.addRow('Доля дней с продажами для регулярного спроса',self.share_input)
        self.recent_input=QSpinBox(); self.recent_input.setRange(7,90); self.recent_input.setValue(settings.get('recent_days',28)); form.addRow('Окно свежего спроса, наблюдений',self.recent_input)
        self.delivery_input=QDateEdit(); self.delivery_input.setCalendarPopup(True); self.delivery_input.setDisplayFormat('dd.MM.yyyy')
        schedules=self.store.get('tables',{}).get('schedules',[])
        self.delivery_input.setDate(date.fromisoformat(str(schedules[0]['next_delivery'])) if schedules else date.today()+timedelta(days=1)); form.addRow('Следующая поставка выбранной точки',self.delivery_input)
        self.interval_input=QSpinBox(); self.interval_input.setRange(1,60); self.interval_input.setValue(int(float(schedules[0]['interval_days'])) if schedules else 3); form.addRow('Интервал поставок, дней',self.interval_input)
        form.addRow(button('Сохранить настройки',self.save_settings,True)); box.addWidget(frame)
        self.item_settings=table(['Ингредиент / блюдо','Ед.','Тара','Целевой запас','Резерв, порций/день']); self.item_settings.doubleClicked.connect(self.edit_item_setting); box.addWidget(self.item_settings,1)
        self.fill_item_settings()
        note=label('Двойной щелчок по позиции — изменить тару, целевой запас или резерв нового блюда.\nЦелевой запас — остаток к концу периода, без второго страхового запаса. Резерв задаёт продавец при короткой истории. Литры и килограммы не пересчитываются.\nБаза: '+str(self.store.path),'subtitle'); note.setWordWrap(True); box.addWidget(note)
    def fill_item_settings(self):
        if not hasattr(self,'item_settings'): return
        self.config_items=self.store.get('tables',{}).get('items',[])
        fill(self.item_settings,[[r['name'],r['unit'],r['pack'],r['target'],r['fallback'] if r['kind']=='dish' else '—'] for r in self.config_items])
    def save_settings(self): self.safe(self._save_settings)
    def _save_settings(self):
        if not self.author_input.text().strip(): raise DataError('Введите имя продавца')
        before=self.store.get('settings',{}); after={'author':self.author_input.text().strip(),'calculation_date':self.date_input.date().toPython().isoformat(),'regular_share':self.share_input.value(),'recent_days':self.recent_input.value()}
        tables=self.store.get('tables',{}); schedule={'point':self.pid(),'next_delivery':self.delivery_input.date().toPython().isoformat(),'interval_days':self.interval_input.value()}
        previous=[r for r in tables.get('schedules',[]) if str(r['point'])==self.pid()]
        tables['schedules']=[r for r in tables.get('schedules',[]) if str(r['point'])!=self.pid()]+[schedule]
        with self.store.db:
            self.store.put('settings',after); self.store.put('tables',tables); self.store.put('revision',self.store.get('revision',0)+1)
            self.store.log('Настройки расчёта',{'settings':before,'schedules':previous},{'settings':after,'schedule':schedule},'Изменено продавцом',after['author'])
        self.reload(); self.status.setText('Настройки сохранены. Черновик нужно пересчитать.')
    def edit_item_setting(self): self.safe(self._edit_item_setting)
    def _edit_item_setting(self):
        i=self.item_settings.currentRow()
        if i<0: return
        item=self.config_items[i]; d=QDialog(self); d.setWindowTitle(item['name']); form=QFormLayout(d); fields={}
        for k,title in [('pack','Упаковка, '+item['unit']),('target','Целевой запас, '+item['unit']),('fallback','Резерв, порций/день')]:
            v=QDoubleSpinBox(); v.setDecimals(3); v.setRange(.001 if k=='pack' else 0,100000); v.setValue(float(item[k])); fields[k]=v; form.addRow(title,v)
        reason=QLineEdit(); form.addRow('Причина',reason)
        bb=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); form.addRow(bb)
        if d.exec()==QDialog.DialogCode.Accepted:
            if not reason.text().strip(): raise DataError('Укажите причину изменения')
            tables=self.store.get('tables'); before=dict(item); updated=next(x for x in tables['items'] if x['id']==item['id'])
            for k,v in fields.items(): updated[k]=v.value()
            with self.store.db:
                self.store.put('tables',tables); self.store.put('revision',self.store.get('revision',0)+1); self.store.log('Параметры ассортимента',before,updated,reason.text(),self.author())
            self.fill_item_settings(); self.reload()

def main():
    application=QApplication(sys.argv); application.setApplicationName('RusskieBliny'); application.setStyle('Fusion'); application.setStyleSheet(STYLE)
    data_dir=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'RusskieBliny'
    if '--data-dir' in sys.argv: data_dir=Path(sys.argv[sys.argv.index('--data-dir')+1])
    store=Store(data_dir/'data.sqlite3'); store.seed(); window=MainWindow(store); window.show()
    if '--smoke' in sys.argv:
        folder=Path(sys.argv[sys.argv.index('--smoke')+1]); folder.mkdir(parents=True,exist_ok=True)
        def smoke():
            try:
                for i,name in enumerate(['stock','order','import','history','settings']):
                    if i==1: window._make_order()
                    window.navigate(i); application.processEvents(); window.grab().save(str(folder/(name+'.png')))
                # Exercise bundled XLSX reader/writer and SQLite, not just Qt startup.
                write_templates(folder/'input',store.get('tables'))
                store.import_file(folder/'input'/'demo.xlsx',author='Smoke test')
                batches=store.get('tables')['batches']
                if batches:
                    b=batches[0]; store.correct_batch(b['id'],float(b['qty']),True,'Проверка сборки','Smoke test')
                window.reload(); window._make_order()
                if window.current['rows']:
                    r=window.current['rows'][0]
                    window.current.setdefault('edits',{})[r['id']]={'packs':0,'reason':'Проверка сборки','author':'Smoke test','at':now()}
                window.refresh_order(); window.stock_check.setChecked(True); window.save_current()
                order_id=store.confirm(window.pid(),window.current,'Smoke test')
                export_order(folder/'packaged_order.xlsx',window.current,order_id)
                (folder/'smoke-result.json').write_text(json.dumps({'status':'PASS','steps':['Qt screens','XLSX import','stock correction','forecast','manual edit','SQLite confirmation','Excel export'],'order_id':order_id,'time':now()},ensure_ascii=False,indent=2),encoding='utf-8')
                window.navigate(1); application.processEvents(); window.grab().save(str(folder/'order.png'))
                window.navigate(3); application.processEvents(); window.grab().save(str(folder/'history.png'))
                application.quit()
            except Exception:
                import traceback
                (folder/'smoke-error.txt').write_text(traceback.format_exc(),encoding='utf-8')
                application.exit(1)
        QTimer.singleShot(900,smoke)
    sys.exit(application.exec())

if __name__=='__main__': main()
