"""Chart-first workspace for the cashier's existing local data."""
from datetime import date,timedelta
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import (QWidget,QFrame,QLabel,QPushButton,QComboBox,QVBoxLayout,QHBoxLayout,
    QScrollArea,QDialog,QApplication)
from charts import SalesChart,CoverageChart,MixChart,num
from analytics_data import make_analytics
from ui_theme import svg_icon,BURGUNDY

def text(value,kind='subtitle'):
    widget=QLabel(value); widget.setObjectName(kind); return widget

def card():
    widget=QFrame(); widget.setObjectName('chartCard'); layout=QVBoxLayout(widget); layout.setContentsMargins(23,20,23,18); layout.setSpacing(10)
    return widget,layout

def days_text(value):
    n=int(value)
    word='дней' if n%100 in range(11,15) else 'день' if n%10==1 else 'дня' if n%10 in (2,3,4) else 'дней'
    return f'{n} {word}'

class AnalyticsPanel(QWidget):
    ingredientSelected=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent); self.tables={}; self.snapshot=None; self.point=''; self.day=date.today(); self.days=30; self.payload=None
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame); scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); layout.addWidget(scroll)
        body=QWidget(); body.setMinimumWidth(850); content=QVBoxLayout(body); content.setContentsMargins(1,0,8,7); content.setSpacing(17); scroll.setWidget(body)
        metrics=QHBoxLayout(); metrics.setSpacing(25); self.metric_values=[]; self.metric_labels=[]; self.metric_hints=[]
        for name in ['Продано за период','Среднее за день','Самый активный день','Спрос к пополнению']:
            slot=QVBoxLayout(); slot.setSpacing(3); caption=text(name); value=text('—','chartMetric'); hint=text('','metricHint')
            slot.addWidget(caption); slot.addWidget(value); slot.addWidget(hint); metrics.addLayout(slot,1); self.metric_labels.append(caption); self.metric_values.append(value); self.metric_hints.append(hint)
        content.addLayout(metrics)
        hero,hero_box=card(); heading=QHBoxLayout(); titlebox=QVBoxLayout(); titlebox.setSpacing(4); self.hero_title=text('Продажи и прогноз','chartTitle'); self.date_range=text('Закрытые смены'); titlebox.addWidget(self.hero_title); titlebox.addWidget(self.date_range); heading.addLayout(titlebox,1)
        self.dish_combo=QComboBox(); self.dish_combo.setMinimumWidth(230); self.dish_combo.currentIndexChanged.connect(self.refresh); heading.addWidget(self.dish_combo)
        self.mode_combo=QComboBox(); self.mode_combo.addItems(['Динамика и прогноз','Сравнение месяцев']); self.mode_combo.setMinimumWidth(202); self.mode_combo.currentIndexChanged.connect(self.refresh); heading.addWidget(self.mode_combo)
        expand=QPushButton(); expand.setObjectName('quiet'); expand.setIcon(svg_icon('expand',BURGUNDY)); expand.setFixedWidth(32); expand.setToolTip('Открыть большой график'); expand.setAccessibleName('Развернуть график'); expand.setCursor(Qt.CursorShape.PointingHandCursor); expand.clicked.connect(self.fullscreen); heading.addWidget(expand); hero_box.addLayout(heading)
        tools=QHBoxLayout(); tools.setSpacing(6); self.period_buttons=[]
        for days in (14,30,90):
            button=QPushButton(f'{days} дней'); button.setObjectName('period'); button.setCheckable(True); button.setCursor(Qt.CursorShape.PointingHandCursor); button.clicked.connect(lambda checked=False,n=days:self.set_period(n)); self.period_buttons.append(button); tools.addWidget(button)
        tools.addStretch(); tools.addWidget(text('Наведите на линию — увидите значения','metricHint')); hero_box.addLayout(tools)
        self.sales_chart=SalesChart(); hero_box.addWidget(self.sales_chart,1)
        self.history_hint=text(''); self.history_hint.setWordWrap(True); hero_box.addWidget(self.history_hint)
        content.addWidget(hero,5)
        bottom=QHBoxLayout(); bottom.setSpacing(18)
        coverage,coverage_box=card(); heading=QHBoxLayout(); heading.addWidget(text('Запас и потребность','chartTitle')); heading.addStretch(); self.coverage_period=text(''); heading.addWidget(self.coverage_period); coverage_box.addLayout(heading)
        coverage_box.addWidget(text('Сколько потребности покрывают остаток и поставки в пути'))
        self.coverage_chart=CoverageChart(); self.coverage_chart.setMinimumHeight(235); self.coverage_chart.ingredientSelected.connect(self.ingredientSelected); coverage_box.addWidget(self.coverage_chart,1)
        legend=QHBoxLayout(); legend.addWidget(text('● Сейчас','legendStock')); legend.addWidget(text('● В пути','legendIncoming')); legend.addStretch(); legend.addWidget(text('Шкала до 150%','metricHint')); coverage_box.addLayout(legend)
        self.coverage_hint=text('Нажмите на ингредиент, чтобы открыть расчёт','metricHint'); self.coverage_hint.setWordWrap(True); coverage_box.addWidget(self.coverage_hint); bottom.addWidget(coverage,6)
        mix,mix_box=card(); mix_box.addWidget(text('Что выбирают гости','chartTitle')); self.mix_period=text('Доли блюд в подтверждённых продажах'); mix_box.addWidget(self.mix_period)
        self.mix_chart=MixChart(); self.mix_chart.dishSelected.connect(self.select_dish); mix_box.addWidget(self.mix_chart,1)
        hint=text('Нажмите на блюдо, чтобы посмотреть его динамику','metricHint'); hint.setWordWrap(True); mix_box.addWidget(hint); bottom.addWidget(mix,4)
        content.addLayout(bottom,4)
    def set_period(self,days): self.days=days; self.refresh()
    def select_dish(self,id):
        index=self.dish_combo.findData(id)
        if index>=0: self.dish_combo.setCurrentIndex(index)
    def set_data(self,tables,point,day,snapshot):
        self.tables=tables; self.point=point; self.day=day; self.snapshot=snapshot; self.refresh()
    def refresh(self):
        if not self.tables: return
        monthly=self.mode_combo.currentIndex()==1
        for index,button in enumerate(self.period_buttons): button.setChecked((14,30,90)[index]==self.days); button.setEnabled(not monthly)
        self.payload=make_analytics(self.tables,self.point,str(self.dish_combo.currentData()),self.day,self.days,self.snapshot,monthly)
        p=self.payload; start=date.fromisoformat(p['start']).strftime('%d.%m'); end=date.fromisoformat(p['end']).strftime('%d.%m')
        self.hero_title.setText('Месяцы день за днём' if monthly else 'Продажи и прогноз')
        last_actual=(date.fromisoformat(p['end'])-timedelta(days=1)).strftime('%d.%m')
        forecast_end=' · прогноз до '+date.fromisoformat(p['future'][-1]['date']).strftime('%d.%m') if p['future'] else ''
        self.date_range.setText('Три завершённых месяца · порций в день' if monthly else f'{start} — {last_actual}{forecast_end} · порций в день')
        self.metric_labels[0].setText('Продано за три месяца' if monthly else f'Продано за {self.days} дней')
        self.metric_values[0].setText(num(p['total']) if p['observed'] else '—')
        self.metric_hints[0].setStyleSheet('color: #8D8593; font-size: 11px;')
        if p['delta'] is not None and not monthly:
            delta=p['delta']; self.metric_hints[0].setText(f'{"+" if delta>=0 else ""}{num(delta,1)}% к предыдущему периоду'); self.metric_hints[0].setStyleSheet(f'color: {"#247047" if delta>=0 else BURGUNDY}; font-size: 11px;')
        else: self.metric_hints[0].setText('Порций по закрытым сменам')
        self.metric_values[1].setText(num(p['average'],1) if p['average'] is not None else '—'); self.metric_hints[1].setText(f'Есть записи за {p["observed"]} из {p["length"]} дней')
        self.metric_values[2].setText(num(p['peak']['value']) if p['peak'] else '—'); self.metric_hints[2].setText(date.fromisoformat(p['peak']['date']).strftime('%d.%m.%Y') if p['peak'] else 'Нет закрытых смен')
        forecast=p['forecast']; days=(self.snapshot or {}).get('days')
        self.metric_labels[3].setText('Прогноз на '+days_text(days) if days else 'Прогноз спроса')
        self.metric_values[3].setText('≈ '+num(forecast['expected']) if forecast else '—')
        self.metric_hints[3].setText(f'Ориентир {num(forecast["low"])}–{num(forecast["high"])} порций' if forecast else 'Проверьте данные и график поставок')
        self.sales_chart.set_data(p,monthly); self.mix_chart.set_data(p['composition'],p['composition_total'],p['composition_observed']); self.coverage_chart.set_data(p['coverage'])
        self.coverage_period.setText('На '+days_text(days) if days else '')
        self.mix_period.setText('Доли продаж за три завершённых месяца' if monthly else f'Доли продаж за последние {self.days} дней')
        missing=p['length']-p['observed']; stockout=sum(v['available'] is False for v in p['actual'])
        hints=[]
        last=(self.snapshot or {}).get('last_closed')
        if last:
            stale=(max(self.day,date.today())-date.fromisoformat(last)).days>1
            hints.append(('Данные устарели. ' if stale else '')+'Закрытые смены до '+date.fromisoformat(last).strftime('%d.%m.%Y'))
        else: hints.append('Нет подтверждённых закрытых смен')
        if missing: hints.append(f'{missing} дней без выгрузки: на графике оставлены разрывы')
        if stockout: hints.append(f'Дней без наличия: {stockout}. Продажи не показывают весь спрос')
        if not monthly and forecast: hints.append('Пунктир — расчётный спрос. Текущая смена не является фактическими продажами')
        if forecast and forecast['method']=='Ручной резерв': hints.append('Короткая история: прогноз использует ручной резерв')
        self.history_hint.setText(' · '.join(hints) if hints else 'На графике показаны подтверждённые продажи закрытых смен')
        self.coverage_hint.setText(f'Показано 7 из {p["coverage_count"]} ингредиентов. Нажмите для расчёта' if p['coverage_count']>7 else 'Нажмите на ингредиент для расчёта. Дефицит до доставки проверяйте в заявке')
    def fullscreen(self):
        if not self.payload: return
        dialog=QDialog(self); dialog.setWindowTitle('КРОНА · '+self.dish_combo.currentText()); screen=QApplication.primaryScreen().availableGeometry(); dialog.resize(min(1350,screen.width()-70),min(800,screen.height()-90))
        layout=QVBoxLayout(dialog); layout.setContentsMargins(30,24,30,24); layout.setSpacing(18)
        top=QHBoxLayout(); top.addWidget(text(self.dish_combo.currentText(),'title')); top.addStretch(); close=QPushButton('Готово'); close.clicked.connect(dialog.accept); top.addWidget(close); layout.addLayout(top)
        layout.addWidget(text(self.date_range.text())); chart=SalesChart(); chart.set_data(self.payload,self.mode_combo.currentIndex()==1); layout.addWidget(chart,1); footer=text(self.history_hint.text()); footer.setWordWrap(True); layout.addWidget(footer); dialog.exec()
