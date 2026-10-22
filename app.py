from __future__ import annotations
import calendar
import json
import os
import sys
import uuid
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt,QTimer,QPointF,QRectF,QSize
from PySide6.QtGui import QColor,QFont,QPainter,QPainterPath,QPen,QPixmap,QLinearGradient,QKeySequence,QShortcut
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,
    QFrame,QStackedWidget,QComboBox,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
    QMessageBox,QFileDialog,QDialog,QFormLayout,QDialogButtonBox,QDoubleSpinBox,QSpinBox,QTextEdit,
    QCheckBox,QDateEdit,QSplitter,QScrollArea,QSizePolicy,QGridLayout,QToolTip)
from analytics_view import AnalyticsPanel
from core import Store,DataError,calculate,calculation_day,order_impact,now,export_order,write_templates,LABELS,SCHEMAS
from charts import StockProjectionChart
from workflows import StockCorrectionDialog,QuantityDialog,OrderDetailsDialog,dialog_buttons,order_total,readable_change

from ui_theme import STYLE,ASSETS,BURGUNDY,INK,DataTable,svg_icon,configure_application

def label(text,name=None):
    w=QLabel(text)
    if name: w.setObjectName(name)
    return w

def button(text,fn,primary=False):
    b=QPushButton(text); b.clicked.connect(fn); b.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary: b.setObjectName('primary')
    return b


def fmt(v,d=1):
    return f'{v:,.{d}f}'.replace(',',' ').replace('.',',')

def table(headers):
    return DataTable(headers)


def fill(t,rows,colors=None):
    selected=t.currentRow(); t.setUpdatesEnabled(False); t.setRowCount(len(rows))
    for i,row in enumerate(rows):
        for j,value in enumerate(row):
            item=QTableWidgetItem(str(value)); item.setToolTip(str(value)); t.setItem(i,j,item)
            if j and (str(value).replace(' ','').replace(',','').replace('.','').isdigit() or str(value).endswith((' кг',' л',' ₽'))):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
            if j==0:
                f=item.font(); f.setWeight(QFont.Weight.Medium); item.setFont(f)
    if rows: t.selectRow(min(max(0,selected),len(rows)-1))
    t.update_empty(); t.setUpdatesEnabled(True)




class MainWindow(QMainWindow):
    def __init__(self,store):
        super().__init__(); self.store=store; self.store.sync_day(); self.current=None; self.busy=False; self.stock_revision=None; self.page_actions=[]; self.calculation_error=None
        self.setWindowTitle('КРОНА · Русские блины'); self.resize(1560,1020); self.setMinimumSize(1180,800)
        root=QWidget(); self.setCentralWidget(root); outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        sidebar=QWidget(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(208); side=QVBoxLayout(sidebar); side.setContentsMargins(16,25,16,20); side.setSpacing(6)
        brand=QLabel(); brand.setPixmap(QPixmap(str(ASSETS/'krona-wordmark.png')).scaledToWidth(151,Qt.TransformationMode.SmoothTransformation)); brand.setContentsMargins(8,0,0,0); side.addWidget(brand)
        client=label('РУССКИЕ БЛИНЫ','workspace'); client.setContentsMargins(9,10,0,0); side.addWidget(client); side.addSpacing(37)
        self.nav=[]; self.nav_icons=['chart','order','import','history','settings']
        for idx,name in enumerate(['Обзор','Заявка','Данные','История','Настройки']):
            b=button(name,lambda checked=False,i=idx:self.navigate(i)); b.setCheckable(True); b.setIcon(svg_icon(self.nav_icons[idx],'#8B8E9B')); b.setIconSize(QSize(19,19)); b.setToolTip(f'{name} · Ctrl+{idx+1}'); self.nav.append(b); side.addWidget(b)
        side.addStretch()
        local=QFrame(); local.setObjectName('rail'); localbox=QVBoxLayout(local); localbox.setContentsMargins(13,14,13,14); localbox.setSpacing(7)
        localbox.addWidget(label('Локальные данные','section')); hint=label('Данные и черновики\nсохраняются локально','subtitle'); localbox.addWidget(hint)
        self.offline=QCheckBox('Без связи'); self.offline.toggled.connect(self.network_changed); localbox.addWidget(self.offline); side.addWidget(local); side.addSpacing(15)
        profile=QHBoxLayout(); avatar=label('П'); avatar.setAlignment(Qt.AlignmentFlag.AlignCenter); avatar.setFixedSize(32,32); avatar.setStyleSheet('background: #F9E8EB; color: #A4002A; border-radius: 16px; font-weight: 600;'); profile.addWidget(avatar)
        profile_text=QVBoxLayout(); profile_text.setSpacing(2); profile_text.addWidget(label(self.author())); profile_text.addWidget(label('Продавец','subtitle')); profile.addLayout(profile_text); profile.addStretch(); side.addLayout(profile)
        outer.addWidget(sidebar)
        content=QWidget(); area=QVBoxLayout(content); area.setContentsMargins(28,20,28,14); area.setSpacing(19)
        top=QHBoxLayout(); top.setSpacing(15); top.addWidget(label('Торговая точка','subtitle'))
        self.point=QComboBox(); self.point.setMinimumWidth(245)
        for point in self.store.get('tables',{}).get('points',[]): self.point.addItem(point['name'],str(point['id']))
        self.point.currentIndexChanged.connect(self.point_changed); top.addWidget(self.point); top.addStretch()
        self.banner=label('','demo'); top.addWidget(self.banner); top.addSpacing(6)
        self.day_label=label(date.today().strftime('%d.%m.%Y'),'subtitle'); top.addWidget(self.day_label); area.addLayout(top)
        self.problem_box=QFrame(); self.problem_box.setObjectName('rail'); problem_layout=QHBoxLayout(self.problem_box)
        self.problem_text=label('','notice'); self.problem_text.setWordWrap(True); problem_layout.addWidget(self.problem_text,1)
        self.problem_action=button('Проверить данные',self.resolve_problem); problem_layout.addWidget(self.problem_action); area.addWidget(self.problem_box); self.problem_box.hide()
        self.stack=QStackedWidget(); area.addWidget(self.stack,1)
        self.status=label('','subtitle'); self.status.setStyleSheet('font-size: 10px; color: #9598A3;'); area.addWidget(self.status)
        outer.addWidget(content,1)
        self.build_stock(); self.build_order(); self.build_import(); self.build_history(); self.build_settings()
        self.shortcuts=[]
        for i in range(5):
            shortcut=QShortcut(QKeySequence(f'Ctrl+{i+1}'),self); shortcut.activated.connect(lambda ix=i:self.navigate(ix)); self.shortcuts.append(shortcut)
        search_shortcut=QShortcut(QKeySequence('Ctrl+K'),self); search_shortcut.activated.connect(lambda:(self.navigate(0),self.switch_stock_view(1),self.search.setFocus())); self.shortcuts.append(search_shortcut)
        self.reload(); self.navigate(0)
        self.day_timer=QTimer(self); self.day_timer.setInterval(30000); self.day_timer.timeout.connect(self.check_day); self.day_timer.start()


    def pid(self): return str(self.point.currentData() or '')
    def author(self): return self.store.get('settings',{}).get('author','Продавец')
    def calc_day(self): return calculation_day(self.store.get('settings',{}))
    def check_day(self):
        if self.store.sync_day():
            if self.today_check.isChecked(): self.date_input.setDate(date.today())
            self.reload()
    def resolve_problem(self):
        self.navigate(4 if self.calculation_error and 'постав' in self.calculation_error.lower() else 2)
    def page(self,title,subtitle):
        p=QWidget(); box=QVBoxLayout(p); box.setContentsMargins(0,0,0,0); box.setSpacing(18)
        heading=QHBoxLayout(); heading.setSpacing(20); wording=QVBoxLayout(); wording.setSpacing(7); wording.addWidget(label(title,'title')); sub=label(subtitle,'subtitle'); sub.setWordWrap(True); wording.addWidget(sub); heading.addLayout(wording,1)
        self.page_actions.append(heading); box.addLayout(heading); self.stack.addWidget(p); return box

    def navigate(self,i):
        self.stack.setCurrentIndex(i)
        for j,b in enumerate(self.nav):
            b.setChecked(i==j); b.setIcon(svg_icon(self.nav_icons[j],BURGUNDY if i==j else '#8B8E9B'))
        if i==3: self.reload_history()

    def message(self,text): QMessageBox.information(self,'Русские блины',text)
    def error(self,e): QMessageBox.warning(self,'Нужно проверить',str(e))
    def safe(self,fn):
        try: return fn()
        except (DataError,OSError,ValueError,KeyError,sqlite3.Error) as e: self.error(e)
    def network_changed(self):
        self.status.setText('Режим без связи. Прогноз, черновики и экспорт работают на этом компьютере.' if self.offline.isChecked() else 'Сохранение на этом компьютере. Подключение к учётным системам не настроено.')

    def point_changed(self):
        self.stock_revision=None; self.stock_check.setChecked(False)
        schedules=[r for r in self.store.get('tables',{}).get('schedules',[]) if str(r['point'])==self.pid()]
        if schedules and hasattr(self,'delivery_input'):
            self.delivery_input.setDate(date.fromisoformat(str(schedules[0]['next_delivery'])))
            self.interval_input.setValue(int(float(schedules[0]['interval_days'])))
        self.reload()

    def build_stock(self):
        box=self.page('Обзор точки','Продажи, ожидаемый спрос и запас для следующего пополнения')
        primary=button('Сформировать заявку',self.make_order,True); primary.setIcon(svg_icon('arrow','#FFFFFF')); self.page_actions[0].addWidget(primary)
        switcher=QFrame(); switcher.setObjectName('viewSwitch'); switcher.setFixedHeight(42); view_tabs=QHBoxLayout(switcher); view_tabs.setContentsMargins(4,4,4,4); view_tabs.setSpacing(3); self.stock_view_tabs=[]
        for i,name in enumerate(['Графики','Остатки']):
            tab=button(name,lambda checked=False,index=i:self.switch_stock_view(index)); tab.setObjectName('viewMode'); tab.setCheckable(True); self.stock_view_tabs.append(tab); view_tabs.addWidget(tab)
        self.page_actions[0].insertWidget(1,switcher)
        self.stock_views=QStackedWidget(); box.addWidget(self.stock_views,1)
        self.analytics=AnalyticsPanel(); self.analytics.ingredientSelected.connect(self.explain_chart_ingredient); self.stock_views.addWidget(self.analytics)
        self.chart_dish=self.analytics.dish_combo; self.chart=self.analytics.sales_chart
        inventory_page=QWidget(); inventory_box=QVBoxLayout(inventory_page); inventory_box.setContentsMargins(0,0,0,0); inventory_box.setSpacing(18)
        summary=QHBoxLayout(); summary.setSpacing(38); self.metrics=[]
        for j,name in enumerate(['Ингредиентов','К пополнению','Возможный излишек']):
            metric=QVBoxLayout(); metric.setSpacing(3); row=QHBoxLayout(); val=label('—','metricAlert' if j==1 else 'number'); self.metrics.append(val); row.addWidget(val); row.addStretch(); metric.addLayout(row); metric.addWidget(label(name,'subtitle')); summary.addLayout(metric)
        summary.addStretch(); inventory_box.addLayout(summary)
        main=QHBoxLayout(); main.setSpacing(20); left=QVBoxLayout(); left.setSpacing(16)
        inventory=QFrame(); inventory.setObjectName('surface'); inventorybox=QVBoxLayout(inventory); inventorybox.setContentsMargins(0,0,0,6); inventorybox.setSpacing(0)
        toolbar=QHBoxLayout(); toolbar.setContentsMargins(18,12,18,9); toolbar.setSpacing(6)
        self.stock_tabs=[]
        for idx,text in enumerate(['Все','Пополнить','Излишек']):
            tab=button(text,lambda checked=False,i=idx:self.filter.setCurrentIndex(i)); tab.setObjectName('tab'); tab.setCheckable(True); self.stock_tabs.append(tab); toolbar.addWidget(tab)
        toolbar.addStretch(); self.search=QLineEdit(); self.search.setObjectName('search'); self.search.setPlaceholderText('Поиск  ·  Ctrl+K'); self.search.addAction(svg_icon('search','#969AA6'),QLineEdit.ActionPosition.LeadingPosition); self.search.setClearButtonEnabled(True); self.search.textChanged.connect(self.refresh_stock); toolbar.addWidget(self.search)
        self.filter=QComboBox(); self.filter.addItems(['Все позиции','Нужно пополнить','Возможен излишек']); self.filter.hide(); self.filter.currentIndexChanged.connect(self.refresh_stock)
        inventorybox.addLayout(toolbar)
        self.stock_table=table(['Ингредиент','Факт','Порций¹','На период','Состояние']); self.stock_table.setMinimumHeight(280); self.stock_table.doubleClicked.connect(self.explain_stock); inventorybox.addWidget(self.stock_table,1)
        tablefoot=QHBoxLayout(); tablefoot.setContentsMargins(17,7,17,4); tablefoot.addWidget(label('¹ По норме техкарты. Общие ингредиенты не суммируются в порции.','subtitle'),1)
        stock_chart=button('График запаса',self.open_stock_chart); stock_chart.setObjectName('quiet'); tablefoot.addWidget(stock_chart)
        edit=button('Сверить / списать',self.edit_stock); edit.setObjectName('quiet'); edit.setIcon(svg_icon('edit',BURGUNDY,17)); tablefoot.addWidget(edit); inventorybox.addLayout(tablefoot); left.addWidget(inventory,1)
        main.addLayout(left,1)
        rail=QWidget(); rail.setFixedWidth(252); right=QVBoxLayout(rail); right.setContentsMargins(0,0,0,0); right.setSpacing(18)
        delivery=QFrame(); delivery.setObjectName('delivery'); d=QVBoxLayout(delivery); d.setContentsMargins(21,22,21,21); d.setSpacing(13)
        d.addWidget(label('БЛИЖАЙШАЯ ПОСТАВКА','deliveryMeta')); self.delivery_date=label('—','deliveryDate'); self.metrics.append(self.delivery_date); d.addWidget(self.delivery_date)
        self.delivery_period=label('Период покрытия —','deliveryMeta'); self.delivery_period.setWordWrap(True); d.addWidget(self.delivery_period)
        d.addSpacing(4); delivery_settings=button('Проверить график',lambda:self.navigate(4)); d.addWidget(delivery_settings); right.addWidget(delivery)
        info=QFrame(); info.setObjectName('surface'); info_box=QVBoxLayout(info); info_box.setContentsMargins(18,19,18,19); info_box.setSpacing(14); info_box.addWidget(label('Данные к расчёту','section'))
        self.fresh=label('','success'); self.fresh.setWordWrap(True); info_box.addWidget(self.fresh)
        rule=QFrame(); rule.setObjectName('separator'); info_box.addWidget(rule)
        control=label('Пригодность партий\nподтверждает продавец','subtitle'); control.setWordWrap(True); info_box.addWidget(control)
        details=button('Проверить данные',lambda:self.navigate(2)); details.setObjectName('quiet'); details.setIcon(svg_icon('arrow',BURGUNDY,16)); info_box.addWidget(details); right.addWidget(info)
        note=label('Перед заказом\nсверьте фактическое наличие.\nРекомендация останется\nдоступной для изменений.','subtitle'); note.setWordWrap(True); note.setContentsMargins(4,2,4,0); right.addWidget(note); right.addStretch()
        delivery.setMinimumHeight(205); info.setMinimumHeight(300)
        rail_scroll=QScrollArea(); rail_scroll.setWidgetResizable(True); rail_scroll.setFrameShape(QFrame.Shape.NoFrame); rail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); rail_scroll.setFixedWidth(260); rail_scroll.setWidget(rail); main.addWidget(rail_scroll)
        inventory_box.addLayout(main,1)
        self.stock_views.addWidget(inventory_page); self.switch_stock_view(0)



    def reload(self):
        tables=self.store.get('tables',{}); demo=self.store.get('demo',False)
        self.banner.setText('Демонстрационные данные' if demo else 'Данные из файлов')
        self.banner.setToolTip('Синтетические продажи и условные настройки. Экономический эффект не доказан.' if demo else 'Проверьте полноту выгрузки, технологические карты и пригодность остатков.')
        self.network_changed()
        self.snapshot=None; self.calculation_error=None
        manual=self.store.get('settings',{}).get('date_mode')=='manual'
        self.day_label.setText(('Ручная дата: ' if manual else '')+self.calc_day().strftime('%d.%m.%Y'))
        try: self.snapshot=calculate(tables,self.pid(),self.calc_day(),self.store.get('settings',{}))
        except (DataError,KeyError,ValueError) as e:
            self.calculation_error=str(e); self.status.setText('Расчёт недоступен: '+str(e))
        problems=([self.calculation_error] if self.calculation_error else (self.snapshot or {}).get('errors',[]))
        self.problem_box.setVisible(bool(problems)); self.problem_text.setText('Расчёт требует внимания: '+ '; '.join(problems[:3]))
        self.problem_action.setText('Настроить поставки' if self.calculation_error and 'постав' in self.calculation_error.lower() else 'Проверить данные')
        if self.snapshot:
            s=self.snapshot; last=s.get('last_closed') or 'нет данных'; stale=not s.get('last_closed') or (max(self.calc_day(),date.today())-date.fromisoformat(last)).days>1
            readable=date.fromisoformat(last).strftime('%d.%m.%Y') if s.get('last_closed') else last
            self.fresh.setText(f'{"Данные устарели.\n" if stale else ""}Закрытая смена\n{readable}\n\nИмпорт\n{str(self.store.get("import_time","—"))[:19].replace("T","  " )}\n\nПродажи текущей смены\nещё не получены.')
            self.delivery_period.setText(f'Покрытие на {s["days"]} дня\nдо {date.fromisoformat(s["end"]).strftime("%d.%m")} (не включая)')
            delivery=date.fromisoformat(s['arrival']); months=['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
            rows=s['rows']; vals=[str(len(rows)),str(sum(r['packs']>0 for r in rows)),str(sum(r['surplus']>r['target'] for r in rows)),f'{delivery.day} {months[delivery.month-1]}']
            for l,v in zip(self.metrics,vals): l.setText(v)
        else:
            self.fresh.setText('Расчёт недоступен.\n'+(self.calculation_error or 'Проверьте данные.'))
            self.delivery_period.setText('Период не рассчитан')
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
        if hasattr(self,'analytics'):
            draft=self.current if self.current and self.current.get('revision')==self.store.get('revision') and self.current.get('date')==self.calc_day().isoformat() else None
            self.analytics.set_data(self.store.get('tables',{}),self.pid(),self.calc_day(),self.snapshot,self.calculation_error,draft)
    def switch_stock_view(self,index):
        self.stock_views.setCurrentIndex(index)
        for i,tab in enumerate(self.stock_view_tabs): tab.setChecked(i==index)

    def explain_chart_ingredient(self,id):
        row=next((r for r in (self.snapshot or {}).get('rows',[]) if str(r['id'])==id),None)
        if row: self.show_explanation(row)

    def refresh_stock(self):
        if not hasattr(self,'stock_table'): return
        rows=(self.snapshot or {}).get('rows',[]); q=self.search.text().lower(); mode=self.filter.currentIndex()
        for i,tab in enumerate(self.stock_tabs): tab.setChecked(i==mode)
        self.visible_stock=[r for r in rows if q in r['name'].lower() and (mode==0 or mode==1 and r['packs']>0 or mode==2 and r['surplus']>r['target'])]
        rendered=[]; colors=[]
        for r in self.visible_stock:
            state='Дефицит до доставки' if r['shortage_before']>0 else 'Пополнить' if r['packs']>0 else 'Возможен излишек' if r['surplus']>r['target'] else 'Достаточно'
            rendered.append([r['name'],f'{fmt(r["stock"],2)} {r["unit"]}',fmt(r['stock']/r['portion_rate'],0) if r['portion_rate'] else 'разный расход',f'{fmt(r["demand"],2)} {r["unit"]}',state])
            colors.append('#b8683c' if state in ('Пополнить','Дефицит до доставки') else '#38715b')
        fill(self.stock_table,rendered,colors)
    def explain_stock(self):
        i=self.stock_table.currentRow()
        if 0<=i<len(self.visible_stock): self.show_explanation(self.visible_stock[i])
    def open_stock_chart(self):
        i=self.stock_table.currentRow()
        if i<0 or i>=len(self.visible_stock): return
        ingredient=self.visible_stock[i]['id']; panel=self.analytics.stock_timeline
        panel.ingredient.setCurrentIndex(panel.ingredient.findData(ingredient)); self.navigate(0); self.switch_stock_view(0)
        self.analytics.findChild(QScrollArea).ensureWidgetVisible(panel,0,0)
    def show_explanation(self,r):
        dialog=QDialog(self); dialog.setWindowTitle('Расчёт рекомендации'); dialog.resize(800,800); layout=QVBoxLayout(dialog); layout.setContentsMargins(28,25,28,24); layout.setSpacing(14)
        header=QHBoxLayout(); words=QVBoxLayout(); words.addWidget(label(r['name'],'title')); words.addWidget(label('Как получено количество к заказу','subtitle')); header.addLayout(words,1); layout.addLayout(header)
        summary=QFrame(); summary.setObjectName('rail'); summarybox=QHBoxLayout(summary); summarybox.setContentsMargins(20,18,20,18)
        summarybox.addWidget(label(f'{r["packs"]} упаковок','number')); summarybox.addStretch(); summarybox.addWidget(label(f'по {fmt(r["pack"])} {r["unit"]}\n{fmt(r["ordered"])} {r["unit"]} к заказу','section')); layout.addWidget(summary)
        form=QFormLayout(); form.setSpacing(12)
        for name,value in [('Потребность на период',r['demand']),('Фактический пригодный остаток',r['stock']),('Остаток, учтённый в расчёте',r['effective']),('Подтверждено в пути',r['incoming']),('Цель к концу периода',r['target']),('Добавилось при округлении до тары',r['rounding'])]:
            val=label(f'{fmt(value,2)} {r["unit"]}'); val.setAlignment(Qt.AlignmentFlag.AlignRight); form.addRow(label(name,'subtitle'),val)
        layout.addLayout(form)
        formula=label('max(0, потребность + цель − учтённый остаток − поступления), затем округление до упаковки','subtitle'); formula.setWordWrap(True); layout.addWidget(formula)
        risks=label(f'До доставки может не хватить {fmt(r["shortage_before"])} {r["unit"]}. Риск избыточного запаса: {fmt(r["surplus"])} {r["unit"]}.\nИсключено продавцом: {fmt(r["blocked"])} {r["unit"]}. Не использовано до заданной даты: {fmt(r["expiry_excluded"])} {r["unit"]}.\nСписания за 28 дней: {fmt(r["waste"])} {r["unit"]}, {fmt(r["waste"]*r["cost"],2)} ₽. Неизвестных дат партий: {r["unknown_dates"]}.','notice'); risks.setWordWrap(True); layout.addWidget(risks)
        contributions=table(['Вклад блюд в потребность',r['unit']]); contributions.verticalHeader().setDefaultSectionSize(36)
        fill(contributions,[[name,fmt(v,2)] for name,v in r['contributions'].items()]); layout.addWidget(contributions,1)
        close=QHBoxLayout(); checked=label('Сверка: '+r['checked_at'][:19],'subtitle'); close.addWidget(checked); close.addStretch(); close.addWidget(button('Понятно',dialog.accept,True)); layout.addLayout(close); dialog.exec()

    def edit_stock(self):
        self.safe(self._edit_stock)
    def _edit_stock(self):
        tables=self.store.get('tables',{}); batches=[b for b in tables.get('batches',[]) if str(b['point'])==self.pid()]
        selected=self.stock_table.currentRow()
        if 0<=selected<len(self.visible_stock):
            ingredient=self.visible_stock[selected]['id']; batches=[b for b in batches if str(b['ingredient'])==str(ingredient)]
        if not batches: raise DataError('Нет партий. Загрузите остатки.')
        names={str(i['id']):i['name'] for i in tables['items']}
        dialog=StockCorrectionDialog(self.store,batches,names,self.author(),self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.stock_revision=None; self.stock_check.setChecked(False); self.reload(); self.status.setText('Изменение сохранено в журнале. Пересчитайте заявку; ручные правки сохранятся.')

    def build_order(self):
        box=self.page('Заявка на поставку','Проверьте рекомендацию, скорректируйте количество и сохраните в Excel')
        self.recalc_btn=button('Пересчитать',self.make_order); self.recalc_btn.setIcon(svg_icon('refresh',BURGUNDY,18)); self.page_actions[1].addWidget(self.recalc_btn)
        self.cover=label('Сначала сформируйте заявку','success'); box.addWidget(self.cover)
        main=QHBoxLayout(); main.setSpacing(20); left=QVBoxLayout(); left.setSpacing(16)
        surface=QFrame(); surface.setObjectName('surface'); contents=QVBoxLayout(surface); contents.setContentsMargins(0,0,0,8); contents.setSpacing(0)
        tabs=QHBoxLayout(); tabs.setContentsMargins(18,9,18,0); self.order_tabs=[]
        for i,name in enumerate(['Ингредиенты к заказу','Прогноз блюд']):
            tab=button(name,lambda checked=False,ix=i:self.switch_order_tab(ix)); tab.setObjectName('tab'); tab.setCheckable(True); self.order_tabs.append(tab); tabs.addWidget(tab)
        tabs.addStretch(); contents.addLayout(tabs)
        self.order_views=QStackedWidget()
        self.order_table=table(['Ингредиент','Потребность','Совет, уп.','Итог, уп.','К заказу','Сумма, ₽']); self.order_table.doubleClicked.connect(self.edit_order); self.order_table.empty_text('Начните с расчёта заявки','Нажмите «Пересчитать», чтобы получить рекомендации')
        self.forecast_table=table(['Блюдо','Порций','Диапазон','Спрос','Метод']); self.forecast_table.doubleClicked.connect(self.explain_forecast); self.forecast_table.empty_text('Прогноз ещё не рассчитан','Он появится вместе с рекомендациями к заказу')
        self.order_views.addWidget(self.order_table); self.order_views.addWidget(self.forecast_table); contents.addWidget(self.order_views,1)
        line=QHBoxLayout(); line.setContentsMargins(16,8,16,2); self.edit_order_btn=button('Изменить количество',self.edit_order); self.edit_order_btn.setIcon(svg_icon('edit',BURGUNDY,17)); line.addWidget(self.edit_order_btn); self.explain_order_btn=button('Объяснить расчёт',lambda:self.explain_order() if self.order_views.currentIndex()==0 else self.explain_forecast()); self.explain_order_btn.setObjectName('quiet'); line.addWidget(self.explain_order_btn); line.addStretch(); contents.addLayout(line)
        left.addWidget(surface,1)
        note=label('Двойной щелчок по строке меняет количество. В прогнозе — раскрывает сравнение методов. Диапазон спроса не является гарантией вероятности.','subtitle'); note.setWordWrap(True); left.addWidget(note)
        main.addLayout(left,1)
        rail=QWidget(); rail.setFixedWidth(280); right=QVBoxLayout(rail); right.setContentsMargins(0,0,0,0); right.setSpacing(16)
        totalcard=QFrame(); totalcard.setObjectName('surface'); totalcard.setMinimumHeight(320); totalbox=QVBoxLayout(totalcard); totalbox.setContentsMargins(21,22,21,22); totalbox.setSpacing(15)
        totalbox.addWidget(label('ИТОГО ПО ЗАЯВКЕ','eyebrow')); self.total=label('—','total'); totalbox.addWidget(self.total); totalbox.addWidget(label('По себестоимости ингредиентов','subtitle'))
        sep=QFrame(); sep.setObjectName('separator'); totalbox.addWidget(sep)
        self.stock_check=QCheckBox('Остатки и пригодность\nпартий сверены мной'); self.stock_check.toggled.connect(self.check_stock); totalbox.addWidget(self.stock_check)
        self.confirm_btn=button('Подтвердить и сохранить',self.confirm_order,True); self.confirm_btn.setIcon(svg_icon('check','#FFFFFF',18)); totalbox.addWidget(self.confirm_btn)
        detail=label('Заявка сохранится в истории.\nВы выберете файл Excel.','subtitle'); detail.setWordWrap(True); totalbox.addWidget(detail); right.addWidget(totalcard)
        right.addWidget(label('Перед подтверждением','section')); self.order_warn=label('','notice'); self.order_warn.setWordWrap(True); self.order_warn.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Minimum); right.addWidget(self.order_warn)
        manual=label('Ваше количество сохраняется\nотдельно от рекомендации.\nПоставщику заявка не отправляется.','subtitle'); manual.setWordWrap(True); manual.setMinimumHeight(50); right.addWidget(manual); right.addStretch()
        order_scroll=QScrollArea(); order_scroll.setWidgetResizable(True); order_scroll.setFrameShape(QFrame.Shape.NoFrame); order_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); order_scroll.setFixedWidth(288); order_scroll.setWidget(rail); main.addWidget(order_scroll); box.addLayout(main,1)
        self.switch_order_tab(0)

    def switch_order_tab(self,index):
        self.order_views.setCurrentIndex(index)
        for i,tab in enumerate(self.order_tabs): tab.setChecked(i==index)
        self.edit_order_btn.setVisible(index==0)
        self.explain_order_btn.setText('Объяснить расчёт' if index==0 else 'Сравнение методов прогноза')

    def check_stock(self,checked):
        if self.busy or not self.current or self.current.get('confirmed_order_id'): return
        self.current['stock_confirmed']=checked
        self.current['stock_confirmed_at']=now() if checked else None
        self.current['stock_confirmed_revision']=self.store.get('revision') if checked else None
        self.current['stock_confirmed_on']=date.today().isoformat() if checked else None
        self.save_current()
        self.confirm_btn.setEnabled(checked and not self.current.get('errors') and self.current.get('revision')==self.store.get('revision'))
    def save_current(self):
        if self.current: self.store.save_draft(self.pid(),self.current)
    def make_order(self): self.safe(self._make_order)
    def _make_order(self):
        self.check_day()
        if not self.snapshot: raise DataError('Расчёт недоступен. Проверьте данные и график поставок.')
        old=self.current or {}; edits=old.get('edits',{}) if not old.get('confirmed_order_id') else {}
        payload=calculate(self.store.get('tables'),self.pid(),self.calc_day(),self.store.get('settings',{}))
        payload.update(edits=edits,revision=self.store.get('revision'),demo=self.store.get('demo'),author=self.author(),stock_confirmed=False,
                       draft_id=old.get('draft_id') if old.get('draft_id') and not old.get('confirmed_order_id') else uuid.uuid4().hex)
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
        confirmed=bool(p and p.get('confirmed_order_id'))
        self.edit_order_btn.setEnabled(not confirmed); self.stock_check.setEnabled(not confirmed)
        self.recalc_btn.setText('Новая заявка' if confirmed else 'Пересчитать')
        self.confirm_btn.setText(f'Экспортировать №{p["confirmed_order_id"]}' if confirmed else 'Подтвердить и сохранить')
        if not p:
            self.cover.setText('Сначала сформируйте заявку'); fill(self.order_table,[]); fill(self.forecast_table,[]); self.order_warn.setText('Черновик ещё не создан.'); self.confirm_btn.setEnabled(False); self.busy=False; return
        self.cover.setText(f'Поставка {date.fromisoformat(p["arrival"]).strftime("%d.%m")}   ·   Покрытие на {p["days"]} дня: {date.fromisoformat(p["date"]).strftime("%d.%m")} — {date.fromisoformat(p["end"]).strftime("%d.%m")} (не включая)')
        changed=p.get('revision')!=self.store.get('revision') or p.get('date')!=self.calc_day().isoformat() or (p.get('stock_confirmed') and p.get('stock_confirmed_on',p.get('date'))!=date.today().isoformat())
        errors=p.get('errors',[])
        warns=[]
        if changed: warns.append('Данные изменились. Пересчитайте перед подтверждением.')
        if errors: warns+=errors
        if any(r['shortage_before']>0 for r in p['rows']): warns.append('Есть дефицит до доставки: обычная заявка не закроет этот разрыв. Проверьте ускоренное пополнение.')
        if any(r['timing_gap']>0 for r in p['rows']): warns.append('Часть поступлений придёт позже потребности. Проверьте даты и ускоренное пополнение.')
        if any(r['waste']>0 for r in p['rows']): warns.append('Есть фактические списания за 28 дней — проверьте излишки и редкий спрос. Дополнительный страховой запас не добавлен.')
        if any(r['unknown_dates'] for r in p['rows']): warns.append('Даты пригодности не заданы. Проверьте партии по действующим правилам точки.')
        self.order_warn.setText('\n\n'.join(warns) or 'Расчёт готов к проверке продавцом.')
        if confirmed:
            self.cover.setText(f'Заявка №{p["confirmed_order_id"]} сохранена · поставка {p["arrival"]} · отправка поставщику не подтверждена')
            self.order_warn.setText('Состав заявки зафиксирован. Повторный экспорт использует тот же номер.\n\nДля нового расчёта нажмите «Новая заявка».')
        self.order_warn.setMinimumHeight(self.order_warn.heightForWidth(280))
        rendered=[]; total=0
        for r in p['rows']:
            e=p.get('edits',{}).get(r['id']); n=e['packs'] if e else r['packs']; total+=n*r['pack']*r['cost']
            rendered.append([r['name'],f'{fmt(r["demand"])} {r["unit"]}',str(r['packs']),str(n)+(' ✎' if e else ''),f'{fmt(n*r["pack"])} {r["unit"]}',fmt(n*r['pack']*r['cost'],0)])
        fill(self.order_table,rendered)
        fill(self.forecast_table,[[f['name'],fmt(f['expected'],0),f'{fmt(f["low"],0)}–{fmt(f["high"],0)}',f['segment'],f['method']] for f in p['forecasts']])
        self.total.setText(f'{fmt(total,0)} ₽'); self.stock_check.setChecked(bool(p.get('stock_confirmed')) and not changed)
        self.confirm_btn.setEnabled(confirmed or (not errors and not changed and self.stock_check.isChecked())); self.busy=False
        self.refresh_chart()
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
        if not self.current or i<0 or self.current.get('confirmed_order_id'): return
        r=self.current['rows'][i]; old=self.current.get('edits',{}).get(r['id'])
        def save(packs,reason):
            edit={'packs':packs,'reason':reason,'author':self.author(),'at':now()}
            self.current.setdefault('edits',{})[r['id']]=edit
            with self.store.db:
                self.store.log('Правка заявки',{'id':r['id'],'name':r['name'],'old':old,'recommended':r['packs']},edit,reason,self.author())
                self.store.put('draft:'+self.pid(),self.current)
        dialog=QuantityDialog(self.current,r,old,save,self)
        if dialog.exec()==QDialog.DialogCode.Accepted: self.refresh_order()
    def confirm_order(self): self.safe(self._confirm_order)
    def _confirm_order(self):
        self.check_day()
        if not self.current: return
        if self.current.get('confirmed_order_id'):
            self.export_saved(self.store.get_order(self.current['confirmed_order_id'])); return
        if not self.stock_check.isChecked(): raise DataError('Сначала подтвердите сверку остатков и пригодности партий.')
        path,_=QFileDialog.getSaveFileName(self,'Экспорт подтверждённой заявки',str(Path.home()/'Desktop'/f'Заявка_{self.calc_day()}.xlsx'),'Excel (*.xlsx)')
        if not path: return
        if Path(path).suffix.lower()!='.xlsx': path+='.xlsx'
        p=json.loads(json.dumps(self.current)); p['author']=self.author(); p['confirmed_at']=now()
        id=self.store.confirm(self.pid(),p,self.author())
        self.current=self.store.get('draft:'+self.pid()); self.refresh_order()
        try: export_order(path,p,id)
        except Exception:
            self.message(f'Заявка №{id} сохранена. Excel создать не удалось. Повторите экспорт из истории.'); raise
        self.message(f'Заявка №{id} сохранена и экспортирована:\n{path}\n\nОтправка поставщику не выполнялась.')

    def build_import(self):
        box=self.page('Данные и импорт','Продажи закрытых смен, фактические остатки и технологические карты')
        upload=button('Импортировать файл',self.import_data,True); upload.setIcon(svg_icon('import','#FFFFFF')); self.page_actions[2].addWidget(upload)
        hint=label('XLSX или CSV. Загружаемая таблица заменяется целиком. Повторный файл не добавляет дубли.','success'); box.addWidget(hint)
        main=QHBoxLayout(); main.setSpacing(20); left=QVBoxLayout(); left.setSpacing(16)
        surface=QFrame(); surface.setObjectName('surface'); surfacebox=QVBoxLayout(surface); surfacebox.setContentsMargins(0,0,0,0)
        self.quality=table(['Набор данных','Строк','Содержимое']); self.quality.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents); self.quality.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch); self.quality.verticalHeader().setDefaultSectionSize(52); surfacebox.addWidget(self.quality); left.addWidget(surface,1)
        left.addWidget(label('Результат проверки','section')); self.import_report=QTextEdit(); self.import_report.setReadOnly(True); self.import_report.setMaximumHeight(170); left.addWidget(self.import_report); main.addLayout(left,1)
        rail=QFrame(); rail.setObjectName('surface'); rail.setFixedWidth(260); r=QVBoxLayout(rail); r.setContentsMargins(20,22,20,22); r.setSpacing(15); r.addWidget(label('Подготовка файла','section'))
        info=label('Начните с полного XLSX.\nДля отдельных CSV сначала\nзагрузите points и items.','subtitle'); info.setWordWrap(True); r.addWidget(info)
        r.addWidget(button('Шаблоны XLSX / CSV',lambda:self.templates(False))); r.addWidget(button('Демо-пример',lambda:self.templates(True)))
        sep=QFrame(); sep.setObjectName('separator'); r.addWidget(sep)
        rules=label('Обязательны единицы,\nвремя сверки, версия техкарты\nи график поставок.\n\nПустая ячейка не означает ноль.\nПригодность подтверждает\nпродавец на точке.','subtitle'); rules.setWordWrap(True); r.addWidget(rules); r.addStretch(); main.addWidget(rail); box.addLayout(main,1)

    def refresh_quality(self):
        if not hasattr(self,'quality'): return
        tables=self.store.get('tables',{}); notes={'points':'Справочник точек','items':'Цена/себестоимость ₽ за учетную единицу; упаковка и целевой запас','sales':'Только закрытые смены; отсутствие не равно нулевому спросу','batches':'Факт по партиям; пригодность и время сверки обязательны','recipes':'Расход на порцию; версия и дата начала действия','deliveries':'Только подтвержденные; дата и количество','movements':'Журнал операций; не применяется повторно к фактическому остатку','schedules':'Ближайшая дата и интервал между поставками'}
        fill(self.quality,[[LABELS[k],len(tables.get(k,[])),notes[k]] for k in SCHEMAS])
        errors=([self.calculation_error] if self.calculation_error else (self.snapshot or {}).get('errors',[]))
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
        row=QHBoxLayout(); row.addWidget(label('Заявки выбранной точки','section')); row.addStretch()
        self.history_search=QLineEdit(); self.history_search.setPlaceholderText('Номер или дата'); self.history_search.textChanged.connect(self.reload_history); row.addWidget(self.history_search)
        row.addWidget(button('Открыть',self.open_history)); row.addWidget(button('Экспортировать',self.export_history)); box.addLayout(row)
        self.orders_table=table(['Заявка / точка','Сохранена','Поставка','Сумма, ₽','Статус','Правок']); self.orders_table.doubleClicked.connect(self.open_history); self.orders_table.empty_text('Первой заявки пока нет','Подтвердите заявку на поставку — она сохранится здесь'); box.addWidget(self.orders_table,2)
        box.addWidget(label('Журнал действий','section'))
        self.audit_table=table(['Действие','Время','Автор','Причина']); self.audit_table.empty_text('Изменений пока не было','Сверки, пересчёты и ручные правки будут записаны автоматически'); self.audit_table.doubleClicked.connect(self.audit_details); box.addWidget(self.audit_table,3)
    def reload_history(self):
        if not hasattr(self,'orders_table'): return
        names={str(p['id']):p['name'] for p in self.store.get('tables',{}).get('points',[])}
        rows=list(self.store.db.execute('SELECT id,created,point,status,payload FROM orders WHERE point=? ORDER BY id DESC',(self.pid(),)))
        query=self.history_search.text().strip().lower()
        self.orders=[r for r in rows if not query or (str(r[0])==query.lstrip('№#') if query.lstrip('№#').isdigit() else query in f'{r[1]} {json.loads(r[4])["arrival"]}'.lower())]
        fill(self.orders_table,[[f'№{r[0]} · {names.get(r[2],r[2])}',r[1][:19].replace('T',' '),json.loads(r[4])['arrival'],fmt(order_total(json.loads(r[4])),0),r[3],len(json.loads(r[4]).get('edits',{}))] for r in self.orders])
        self.audits=list(self.store.db.execute('SELECT kind,created,author,reason,before_json,after_json FROM audit ORDER BY id DESC LIMIT 300'))
        fill(self.audit_table,[[r[0],r[1][:19],r[2],r[3]] for r in self.audits])
    def audit_details(self):
        i=self.audit_table.currentRow()
        if i<0: return
        r=self.audits[i]; dialog=QDialog(self); dialog.setWindowTitle('Подробности изменения'); dialog.resize(750,540); layout=QVBoxLayout(dialog); text=QTextEdit(); text.setReadOnly(True)
        text.setPlainText(f'{r[0]} · {r[1][:19].replace("T"," ")} · {r[2]}\nПричина: {r[3]}\n\nБыло:\n{readable_change(json.loads(r[4]))}\n\nСтало:\n{readable_change(json.loads(r[5]))}'); layout.addWidget(text); dialog.exec()
    def export_history(self):
        i=self.orders_table.currentRow()
        if i<0: return
        self.export_saved(self.store.get_order(self.orders[i][0]))
    def export_saved(self,order):
        path,_=QFileDialog.getSaveFileName(self,'Повторный экспорт',f'Заявка_{order["id"]}.xlsx','Excel (*.xlsx)')
        if path:
            if Path(path).suffix.lower()!='.xlsx': path+='.xlsx'
            def save():
                export_order(path,order['payload'],order['id']); self.status.setText(f'Заявка №{order["id"]} экспортирована: {path}')
            self.safe(save)
    def open_history(self):
        i=self.orders_table.currentRow()
        if i<0: return
        order=self.store.get_order(self.orders[i][0])
        name=next((p['name'] for p in self.store.get('tables',{}).get('points',[]) if str(p['id'])==order['point']),order['point'])
        OrderDetailsDialog(order,name,self.export_saved,self).exec()

    def build_settings(self):
        box=self.page('Настройки','Параметры точки и правила расчёта под контролем продавца')
        save=button('Сохранить настройки',self.save_settings,True); save.setIcon(svg_icon('check','#FFFFFF')); self.page_actions[4].addWidget(save)
        main=QHBoxLayout(); main.setSpacing(20)
        frame=QFrame(); frame.setObjectName('surface'); frame.setMaximumWidth(475); pane=QVBoxLayout(frame); pane.setContentsMargins(24,23,24,23); pane.setSpacing(18); pane.addWidget(label('Точка и прогноз','section')); form=QFormLayout(); form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows); form.setSpacing(9)
        settings=self.store.get('settings',{}); self.author_input=QLineEdit(settings.get('author','Продавец')); form.addRow('Имя для журнала изменений',self.author_input)
        self.date_input=QDateEdit(); self.date_input.setCalendarPopup(True); self.date_input.setDate(self.calc_day()); self.date_input.setDisplayFormat('dd.MM.yyyy'); form.addRow('Дата расчёта',self.date_input)
        self.today_check=QCheckBox('Всегда использовать сегодняшнюю дату'); self.today_check.setChecked(settings.get('date_mode')!='manual')
        self.date_input.setEnabled(not self.today_check.isChecked()); self.today_check.toggled.connect(lambda checked:self.date_input.setEnabled(not checked)); form.addRow(self.today_check)
        self.share_input=QDoubleSpinBox(); self.share_input.setRange(.1,1); self.share_input.setSingleStep(.05); self.share_input.setValue(settings.get('regular_share',.6)); form.addRow('Доля дней с продажами для регулярного спроса',self.share_input)
        self.recent_input=QSpinBox(); self.recent_input.setRange(7,90); self.recent_input.setValue(settings.get('recent_days',28)); form.addRow('Окно свежего спроса, наблюдений',self.recent_input)
        self.delivery_input=QDateEdit(); self.delivery_input.setCalendarPopup(True); self.delivery_input.setDisplayFormat('dd.MM.yyyy'); schedules=self.store.get('tables',{}).get('schedules',[])
        self.delivery_input.setDate(date.fromisoformat(str(schedules[0]['next_delivery'])) if schedules else date.today()+timedelta(days=1)); form.addRow('Ближайшая поставка',self.delivery_input)
        self.interval_input=QSpinBox(); self.interval_input.setRange(1,60); self.interval_input.setValue(int(float(schedules[0]['interval_days'])) if schedules else 3); form.addRow('Интервал между поставками, дней',self.interval_input)
        pane.addLayout(form); technical=label('Проверьте график при переходе на новый день. Прошедшая поставка не переносится автоматически.','subtitle'); technical.setWordWrap(True); pane.addWidget(technical)
        pane.addWidget(label('Резервные копии','section'))
        pane.addWidget(button('Создать резервную копию',self.backup_data)); pane.addWidget(button('Восстановить из копии',self.restore_data))
        self.backup_hint=label('Копия включает данные, заявки и журнал. Перед восстановлением текущая база сохраняется отдельно.','subtitle'); self.backup_hint.setWordWrap(True); pane.addWidget(self.backup_hint); pane.addStretch()
        settings_scroll=QScrollArea(); settings_scroll.setWidgetResizable(True); settings_scroll.setFrameShape(QFrame.Shape.NoFrame); settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); settings_scroll.setWidget(frame); main.addWidget(settings_scroll,2)
        right=QVBoxLayout(); right.setSpacing(14); right.addWidget(label('Ассортимент и упаковки','section'))
        self.item_settings=table(['Позиция','Ед.','Тара','Цель','Резерв / день']); self.item_settings.doubleClicked.connect(self.edit_item_setting); self.item_settings.empty_text('Ассортимент не загружен','Загрузите справочник items на экране «Данные»')
        surface=QFrame(); surface.setObjectName('surface'); tablebox=QVBoxLayout(surface); tablebox.setContentsMargins(0,0,0,0); tablebox.addWidget(self.item_settings); right.addWidget(surface,1); self.fill_item_settings()
        note=label('Двойной щелчок — изменить тару, целевой запас или резерв нового блюда.\nЦель — остаток к концу периода. Второй страховой запас не добавляется.','subtitle'); note.setWordWrap(True); right.addWidget(note); main.addLayout(right,3); box.addLayout(main,1)

    def fill_item_settings(self):
        if not hasattr(self,'item_settings'): return
        self.config_items=self.store.get('tables',{}).get('items',[])
        fill(self.item_settings,[[r['name'],r['unit'],r['pack'],r['target'],r['fallback'] if r['kind']=='dish' else '—'] for r in self.config_items])
    def save_settings(self): self.safe(self._save_settings)
    def _save_settings(self):
        if not self.author_input.text().strip(): raise DataError('Введите имя продавца')
        before=self.store.get('settings',{}); after={**before,'author':self.author_input.text().strip(),'date_mode':'today' if self.today_check.isChecked() else 'manual','calculation_date':self.date_input.date().toPython().isoformat(),'regular_share':self.share_input.value(),'recent_days':self.recent_input.value()}
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
        item=self.config_items[i]; d=QDialog(self); d.setWindowTitle(item['name']); layout=QVBoxLayout(d); form=QFormLayout(); layout.addLayout(form); fields={}
        for k,title in [('pack','Упаковка, '+item['unit']),('target','Целевой запас, '+item['unit']),('fallback','Резерв, порций/день')]:
            v=QDoubleSpinBox(); v.setDecimals(3); v.setRange(.001 if k=='pack' else 0,100000); v.setValue(float(item[k])); fields[k]=v; form.addRow(title,v)
        reason=QLineEdit(); form.addRow('Причина',reason)
        def save():
            if not reason.text().strip(): raise DataError('Укажите причину изменения')
            tables=self.store.get('tables'); before=dict(item); updated=next(x for x in tables['items'] if x['id']==item['id'])
            for k,v in fields.items(): updated[k]=v.value()
            with self.store.db:
                self.store.put('tables',tables); self.store.put('revision',self.store.get('revision',0)+1); self.store.log('Параметры ассортимента',before,updated,reason.text(),self.author())
            self.fill_item_settings(); self.reload()
        dialog_buttons(d,layout,save); d.exec()

    def backup_data(self):
        path,_=QFileDialog.getSaveFileName(self,'Сохранить резервную копию',f'Русские_блины_{date.today()}.sqlite3','База приложения (*.sqlite3)')
        if path:
            if not path.lower().endswith('.sqlite3'): path+='.sqlite3'
            def save():
                self.store.backup(path); self.backup_hint.setText('Копия проверена и сохранена:\n'+path)
            self.safe(save)
    def restore_data(self):
        path,_=QFileDialog.getOpenFileName(self,'Восстановить резервную копию','','База приложения (*.sqlite3)')
        if not path: return
        answer=QMessageBox.question(self,'Восстановление базы','Текущие данные, черновики и история будут заменены выбранной копией. Перед заменой приложение сохранит текущую базу в папке backups.\n\nВосстановить выбранную копию?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes: return
        def restore():
            recovery=self.store.restore(path); self.store.sync_day()
            self.point.blockSignals(True); self.point.clear()
            for p in self.store.get('tables',{}).get('points',[]): self.point.addItem(p['name'],str(p['id']))
            self.point.blockSignals(False)
            settings=self.store.get('settings',{}); self.author_input.setText(settings.get('author','Продавец'))
            self.today_check.setChecked(settings.get('date_mode')!='manual'); self.date_input.setDate(self.calc_day())
            self.share_input.setValue(settings.get('regular_share',.6)); self.recent_input.setValue(settings.get('recent_days',28))
            self.fill_item_settings(); self.point_changed(); self.reload_history()
            self.backup_hint.setText('База восстановлена. Копия предыдущего состояния:\n'+str(recovery)); self.message('База восстановлена. Сверьте остатки и пересчитайте черновики.')
        self.safe(restore)

def main():
    application=QApplication(sys.argv); application.setApplicationName('RusskieBliny'); configure_application(application)
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
                    if i==0:
                        window.switch_stock_view(1); application.processEvents(); window.grab().save(str(folder/'inventory.png')); window.switch_stock_view(0)
                        window.analytics.mode_combo.setCurrentIndex(1); application.processEvents(); window.grab().save(str(folder/'months.png')); window.analytics.mode_combo.setCurrentIndex(0)
                        application.processEvents(); window.analytics.findChild(QScrollArea).widget().grab().save(str(folder/'overview-body.png'))
                        window.analytics.stock_timeline.grab().save(str(folder/'stock-timeline.png'))
                        def capture_large_chart():
                            dialog=application.activeModalWidget()
                            if dialog: dialog.grab().save(str(folder/'large-chart.png')); dialog.accept()
                        QTimer.singleShot(150,capture_large_chart); window.analytics.fullscreen()
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
                assert store.confirm(window.pid(),window.current,'Smoke test')==order_id
                store.backup(folder/'backup.sqlite3')
                for dialog,name in [(QuantityDialog(window.current,window.current['rows'][0],None,lambda *args:None,window),'quantity-preview'),
                                    (OrderDetailsDialog(store.get_order(order_id),'Центральная',lambda *args:None,window),'order-details')]:
                    dialog.show(); application.processEvents(); dialog.grab().save(str(folder/(name+'.png'))); dialog.close()
                window.refresh_order()
                (folder/'smoke-result.json').write_text(json.dumps({'status':'PASS','steps':['Qt screens','XLSX import','stock correction','forecast','manual edit','idempotent confirmation','Excel export','daily stock projection','quantity preview','saved order details','SQLite backup'],'order_id':order_id,'time':now()},ensure_ascii=False,indent=2),encoding='utf-8')
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
