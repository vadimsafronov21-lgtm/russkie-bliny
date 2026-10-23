"""Krona visual language, native Qt controls and accessible table presentation."""
from pathlib import Path
import sys
from PySide6.QtCore import QByteArray,Qt,QRectF,QSize
from PySide6.QtGui import QColor,QFont,QFontDatabase,QIcon,QPainter,QPixmap,QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QTableWidget,QStyledItemDelegate,QStyleOptionViewItem,
    QWidget,QVBoxLayout,QLabel,QAbstractItemView,QHeaderView,QStyle,QProxyStyle)

BURGUNDY='#A4002A'
INK='#111E30'
ROSE='#F9E8EB'
MUTED='#777C89'
ASSETS=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))/'assets'

PATHS={
 'stock':'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10M15 10v10"/>',
 'order':'<path d="M8 4H5v17h14V4h-3"/><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M8 11h8M8 15h5"/>',
 'import':'<path d="M12 3v12m-4-4 4 4 4-4M4 15v6h16v-6"/>',
 'history':'<path d="M3 10a9 9 0 1 1 2 8M3 4v6h6M12 7v5l3 2"/>',
 'settings':'<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="8" cy="6" r="2" fill="white"/><circle cx="16" cy="12" r="2" fill="white"/><circle cx="10" cy="18" r="2" fill="white"/>',
 'arrow':'<path d="M4 12h15m-5-5 5 5-5 5"/>',
 'search':'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
 'edit':'<path d="m4 16 12-12 4 4L8 20H4v-4Zm10-10 4 4"/>',
 'truck':'<path d="M3 5h11v12H3zM14 9h4l3 4v4h-7"/><circle cx="7" cy="18" r="2" fill="white"/><circle cx="18" cy="18" r="2" fill="white"/>',
 'info':'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
 'check':'<path d="m5 12 4 4L20 5"/>',
 'file':'<path d="M5 3h9l5 5v13H5zM14 3v6h5M8 13h8M8 17h6"/>',
 'refresh':'<path d="M20 8a9 9 0 0 0-15-3L3 8m0-5v5h5M4 16a9 9 0 0 0 15 3l2-3m0 5v-5h-5"/>',
 'down':'<path d="m7 10 5 5 5-5"/>',
 'user':'<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
 'chart':'<path d="M3 3v18h18M6 15l4-5 4 2 6-7"/>',
 'expand':'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
}

def svg_icon(name,color=INK,size=20):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
    pix=QPixmap(size*2,size*2); pix.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pix); QSvgRenderer(QByteArray(svg.encode())).render(painter); painter.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)

class QuickHelpStyle(QProxyStyle):
    def styleHint(self,hint,option=None,widget=None,returnData=None):
        if hint==QStyle.StyleHint.SH_ToolTip_WakeUpDelay: return 100
        if hint==QStyle.StyleHint.SH_ToolTip_FallAsleepDelay: return 0
        return super().styleHint(hint,option,widget,returnData)

def configure_application(app):
    QFontDatabase.addApplicationFont(str(ASSETS/'fonts/Inter.ttf'))
    app.setFont(QFont('Inter',10))
    app.setStyle(QuickHelpStyle('Fusion'))
    app.setEffectEnabled(Qt.UIEffect.UI_AnimateTooltip,False)
    app.setEffectEnabled(Qt.UIEffect.UI_FadeTooltip,False)
    palette=app.palette()
    palette.setColor(QPalette.ColorRole.Highlight,QColor(ROSE))
    palette.setColor(QPalette.ColorRole.HighlightedText,QColor(INK))
    palette.setColor(QPalette.ColorRole.Window,QColor('#F6F6F8'))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
    app.setWindowIcon(svg_icon('stock',BURGUNDY,32))

STYLE='''
* { font-family: "Inter", "Segoe UI"; font-size: 13px; color: #111E30; }
QMainWindow { background: #F6F6F8; }
QDialog { background: #FFFFFF; }
QWidget#sidebar { background: #FFFFFF; border-right: 1px solid #E9E8ED; }
QWidget#sidebar QPushButton { text-align: left; padding: 12px 17px; background: transparent; border: 1px solid transparent; border-radius: 8px; color: #6F7582; font-weight: 500; }
QWidget#sidebar QPushButton:hover { background: #F7F0F1; color: #80041E; }
QWidget#sidebar QPushButton:checked { background: #F9E8EB; color: #A4002A; font-weight: 600; }
QLabel#workspace { font-size: 11px; color: #9295A1; letter-spacing: 1px; }
QLabel#title { font-size: 34px; font-weight: 650; letter-spacing: -1px; }
QLabel#subtitle { color: #777C89; font-size: 12px; }
QLabel#eyebrow { color: #9396A1; font-size: 10px; font-weight: 600; letter-spacing: 1px; }
QLabel#demo { background: #F9E8EB; border-radius: 5px; color: #80041E; padding: 6px 11px; font-size: 11px; font-weight: 500; }
QLabel#notice { color: #80041E; background: #FCF3F4; border: 1px solid #EED9DC; padding: 12px 14px; border-radius: 8px; }
QLabel#success { color: #646D7B; font-size: 12px; padding: 3px 0; }
QLabel#section { font-size: 15px; font-weight: 600; letter-spacing: -0.2px; }
QLabel#number { font-size: 30px; font-weight: 600; letter-spacing: -1px; }
QLabel#metricAlert { font-size: 30px; font-weight: 600; color: #A4002A; letter-spacing: -1px; }
QLabel#metricIndex { font-size: 11px; color: #AE9DA4; }
QLabel#total { font-size: 29px; font-weight: 600; letter-spacing: -0.8px; }
QFrame#surface, QFrame#card { background: #FFFFFF; border: 1px solid #E9E8ED; border-radius: 12px; }
QFrame#chartCard { background: #FFFFFF; border: 1px solid #EFEBF1; border-radius: 21px; }
QFrame#viewSwitch { background: #ECE8F0; border: none; border-radius: 10px; }
QPushButton#viewMode { background: transparent; color: #95899D; border: none; border-radius: 7px; padding: 8px 17px; font-size: 12px; }
QPushButton#viewMode:checked { background: white; color: #A4002A; font-weight: 600; }
QLabel#chartTitle { font-size: 17px; font-weight: 600; letter-spacing: -0.3px; }
QLabel#chartMetric { font-size: 31px; font-weight: 600; letter-spacing: -0.8px; }
QLabel#metricHint { font-size: 10px; color: #98909E; }
QLabel#legendStock { color: #A4002A; font-size: 10px; }
QLabel#legendIncoming { color: #D18AA2; font-size: 10px; }
QPushButton#period { background: #F5F2F6; color: #8F8492; border: none; border-radius: 7px; padding: 7px 12px; min-height: 14px; font-size: 11px; }
QPushButton#period:checked { background: #F9E8EB; color: #A4002A; font-weight: 600; }
QPushButton#period:disabled { color: #C3BBC6; background: #F7F5F8; }
QFrame#flat { background: #FFFFFF; border: none; }
QFrame#delivery { background: #A4002A; border: none; border-radius: 12px; }
QFrame#delivery QLabel { color: #FFFFFF; background: transparent; }
QFrame#delivery QLabel#deliveryMeta { color: #EAC8D1; font-size: 11px; }
QFrame#delivery QLabel#deliveryDate { font-size: 36px; font-weight: 550; letter-spacing: -1px; }
QFrame#delivery QPushButton { background: #FFFFFF; color: #A4002A; border: none; font-weight: 600; }
QFrame#rail { background: #F0EFF3; border: none; border-radius: 10px; }
QFrame#separator { background: #E9E8ED; border: none; min-height: 1px; max-height: 1px; }
QPushButton { background: white; border: 1px solid #DEDFE5; border-radius: 7px; padding: 10px 14px; min-height: 16px; font-weight: 500; }
QPushButton:hover { border-color: #C7A5B0; background: #FBF6F6; }
QPushButton:pressed { background: #F1DEE2; }
QPushButton:focus { border-color: #A4002A; }
QPushButton:disabled { color: #A8AAB3; background: #F3F3F6; border-color: #E9E8ED; }
QPushButton#primary { background: #A4002A; color: white; border: 1px solid #A4002A; font-weight: 600; padding: 12px 18px; }
QPushButton#primary:hover { background: #80041E; border-color: #80041E; }
QPushButton#primary:pressed { background: #65021B; }
QPushButton#primary:disabled { background: #DECCD2; border-color: #DECCD2; color: white; }
QPushButton#quiet { background: transparent; border: none; color: #777C89; padding: 7px 4px; }
QPushButton#quiet:hover { color: #A4002A; background: #F9E8EB; }
QPushButton#tab { background: transparent; border: none; border-bottom: 2px solid transparent; border-radius: 0; color: #777C89; padding: 10px 3px; margin-right: 20px; }
QPushButton#tab:checked { color: #A4002A; border-bottom-color: #A4002A; font-weight: 600; }
QLineEdit,QComboBox,QDateEdit,QSpinBox,QDoubleSpinBox { background: #FFFFFF; border: 1px solid #DFE0E6; border-radius: 6px; padding: 9px 11px; min-height: 19px; selection-background-color: #F9E8EB; selection-color: #111E30; }
QLineEdit:hover,QComboBox:hover { border-color: #C3A5AF; }
QLineEdit:focus,QComboBox:focus,QDateEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus { border-color: #A4002A; }
QLineEdit[invalid="true"] { border-color: #A4002A; background: #FCF3F4; }
QLineEdit#search { background: #F6F6F8; border: 1px solid #F0EFF3; min-width: 175px; }
QComboBox::drop-down,QDateEdit::drop-down { border: none; width: 24px; }
QComboBox::down-arrow,QDateEdit::down-arrow { image: url("__ICONS__/chevron-down.svg"); width: 13px; height: 13px; }
QSpinBox::up-button,QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 24px; border: none; background: transparent; }
QSpinBox::down-button,QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 24px; border: none; background: transparent; }
QSpinBox::up-arrow,QDoubleSpinBox::up-arrow { image: url("__ICONS__/chevron-up.svg"); width: 11px; height: 11px; }
QSpinBox::down-arrow,QDoubleSpinBox::down-arrow { image: url("__ICONS__/chevron-down.svg"); width: 11px; height: 11px; }
QComboBox QAbstractItemView { background: white; border: 1px solid #E9E8ED; padding: 5px; selection-background-color: #F9E8EB; }
QTextEdit { background: white; border: 1px solid #E9E8ED; border-radius: 8px; padding: 12px; selection-background-color: #F9E8EB; }
QTabWidget::pane { border: 1px solid #E9E8ED; background: white; border-radius: 10px; }
QTabBar::tab { background: transparent; color: #747786; padding: 12px 17px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #A4002A; border-bottom: 2px solid #A4002A; }
QTabBar::tab:hover { background: #FCF3F4; }
QTableWidget { border: none; background: white; alternate-background-color: #FCFBFC; selection-background-color: #FCF3F4; selection-color: #111E30; outline: none; }
QTableWidget::item { padding: 0 12px; border-bottom: 1px solid #F0EFF3; }
QTableWidget::item:selected { background: #FCF3F4; color: #111E30; }
QTableWidget::item:hover { background: #FCFAFB; }
QHeaderView::section { background: #FAF9FB; color: #818592; border: none; border-bottom: 1px solid #EDEBF0; font-size: 11px; font-weight: 500; padding: 13px 12px; }
QTableWidget QTableCornerButton::section { border: none; background: #FAF9FB; }
QCheckBox { spacing: 9px; padding: 3px 0; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #C6C5CF; border-radius: 4px; background: white; }
QCheckBox::indicator:checked { background: #A4002A; border-color: #A4002A; image: url("__ICONS__/check.svg"); }
QCheckBox::indicator:hover { border-color: #A4002A; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 3px 0; }
QScrollBar::handle:vertical { background: #D8D4DD; min-height: 26px; border-radius: 3px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 6px; background: transparent; }
QScrollBar::handle:horizontal { background: #D8D4DD; min-width: 26px; border-radius: 3px; }
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width: 0; }
QToolTip { background: #111E30; color: white; border: none; padding: 9px; border-radius: 4px; }
QSplitter::handle { background: #F6F6F8; width: 14px; height: 14px; }
QCalendarWidget QWidget { background: white; color: #111E30; }
QCalendarWidget QToolButton { color: #A4002A; background: white; }
'''
STYLE=STYLE.replace('__ICONS__',(ASSETS/'icons').as_posix())

class StatusDelegate(QStyledItemDelegate):
    COLORS={
        'Дефицит до доставки':('#A4002A','#F9E8EB'),
        'Пополнить':('#9F0830','#FCF0F3'),
        'Возможен излишек':('#805F39','#F7F0E6'),
        'Достаточно':('#247047','#EAF4ED'),
        'Подтверждена':('#247047','#EAF4ED'),
        'Регулярный':('#58647A','#F0F2F6'),
        'Редкий':('#8D5E74','#F6EDF2'),
    }
    def paint(self,painter,option,index):
        text=str(index.data() or '')
        if text not in self.COLORS: return super().paint(painter,option,index)
        base=QStyleOptionViewItem(option); self.initStyleOption(base,index); base.text=''
        option.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem,base,painter,option.widget)
        fg,bg=self.COLORS[text]; painter.save(); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font=QFont(option.font); font.setPixelSize(11); font.setWeight(QFont.Weight.Medium); painter.setFont(font)
        width=min(option.rect.width()-16,painter.fontMetrics().horizontalAdvance(text)+18)
        rect=QRectF(option.rect.x()+10,option.rect.center().y()-12,width,25)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(bg)); painter.drawRoundedRect(rect,5,5)
        painter.setPen(QColor(fg)); painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,painter.fontMetrics().elidedText(text,Qt.TextElideMode.ElideRight,int(width-12)))
        painter.restore()

class DataTable(QTableWidget):
    def __init__(self,headers):
        super().__init__(0,len(headers)); self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().hide(); self.verticalHeader().setDefaultSectionSize(47)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False); self.setMouseTracking(True); self.setAlternatingRowColors(False)
        self.setItemDelegate(StatusDelegate(self))
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setMinimumSectionSize(70)
        self.empty=QWidget(self.viewport()); layout=QVBoxLayout(self.empty); layout.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.setSpacing(9)
        self.empty_title=QLabel('Здесь пока нет записей'); self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty_title.setStyleSheet('font-size: 17px; font-weight: 500; color: #77808E;')
        self.empty_hint=QLabel('Данные появятся после первого действия'); self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty_hint.setWordWrap(True); self.empty_hint.setStyleSheet('font-size: 12px; color: #979BA5;')
        layout.addWidget(self.empty_title); layout.addWidget(self.empty_hint); self.empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    def empty_text(self,title,hint): self.empty_title.setText(title); self.empty_hint.setText(hint)
    def resizeEvent(self,event):
        super().resizeEvent(event); self.empty.setGeometry(self.viewport().rect())
    def update_empty(self): self.empty.setVisible(self.rowCount()==0); self.empty.setGeometry(self.viewport().rect())
