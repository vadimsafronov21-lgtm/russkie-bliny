"""Short, local Qt paint animations. No idle timers or full-page compositing."""
from PySide6.QtCore import Qt,QRectF,QSize,QAbstractAnimation,QEasingCurve,QVariantAnimation
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QFontMetrics
from PySide6.QtWidgets import QPushButton,QTabBar,QLabel
from ui_theme import BURGUNDY,svg_icon


def motion_enabled(widget):
    while widget is not None:
        value=widget.property('motionEnabled')
        if value is not None: return bool(value)
        widget=widget.parentWidget()
    return True


def blend(a,b,amount):
    a,b=QColor(a),QColor(b);t=max(0,min(1,amount))
    return QColor(*(round(x+(y-x)*t) for x,y in zip(a.getRgb(),b.getRgb())))


def tween(parent,callback,duration=150):
    animation=QVariantAnimation(parent);animation.setDuration(duration)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic);animation.valueChanged.connect(callback)
    return animation


class MotionButton(QPushButton):
    def __init__(self,title,kind='side',parent=None):
        super().__init__(title,parent);self.kind=kind;self._hover=0.;self._selected=0.;self._over=False
        self._hover_animation=tween(self,self._set_hover,120);self._selection_animation=tween(self,self._set_selected,170)
        self.setCheckable(True);self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icons=None;self.toggled.connect(self._toggle);self.setToolTip(title)
    def set_nav_icon(self,name):
        self._icons=(svg_icon(name,'#858A98'),svg_icon(name,BURGUNDY));self.setIcon(self._icons[0])
    def sizeHint(self):
        hint=super().sizeHint();f=QFont(self.font());f.setWeight(QFont.Weight.DemiBold)
        padding=34 if self.kind=='domain' else 24 if self.kind=='period' else 26
        hint.setWidth(QFontMetrics(f).horizontalAdvance(self.text())+padding+(self.iconSize().width()+9 if not self.icon().isNull() else 0))
        return hint
    def minimumSizeHint(self):return QSize(0,self.sizeHint().height())
    def _set_hover(self,value):self._hover=float(value);self.update()
    def _set_selected(self,value):self._selected=float(value);self.update()
    def _run(self,animation,current,target,setter):
        animation.stop()
        if not self.isVisible() or not motion_enabled(self) or abs(current-target)<.001:setter(target);return
        animation.setStartValue(current);animation.setEndValue(target);animation.start()
    def _toggle(self,checked):self._run(self._selection_animation,self._selected,float(checked),self._set_selected)
    def enterEvent(self,event):
        self._over=True;self._run(self._hover_animation,self._hover,1.,self._set_hover);super().enterEvent(event)
    def leaveEvent(self,event):
        self._over=False;self._run(self._hover_animation,self._hover,0.,self._set_hover);super().leaveEvent(event)
    def hideEvent(self,event):self.finish_motion();super().hideEvent(event)
    def finish_motion(self):
        self._hover_animation.stop();self._selection_animation.stop()
        self._set_hover(float(self._over and self.isVisible()));self._set_selected(float(self.isChecked()))
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);rect=QRectF(self.rect()).adjusted(1,1,-1,-1)
        selected=self._selected;hover=self._hover if self.isEnabled() else 0.
        base='#ECE8F0' if self.kind=='domain' else '#F5F2F6' if self.kind=='period' else '#FFFFFF' if self.kind=='side' else '#F6F6F8'
        background=blend(base,'#F9E8EB',hover*.6)
        background=blend(background,'#FFFFFF' if self.kind=='domain' else '#F9E8EB',selected)
        p.setPen(Qt.PenStyle.NoPen)
        if self.kind!='line' or hover: p.setBrush(background);p.drawRoundedRect(rect,7,7)
        if self.kind=='side' and selected:
            height=(rect.height()-20)*selected;p.setBrush(QColor(BURGUNDY))
            p.drawRoundedRect(QRectF(1,rect.center().y()-height/2,3,height),1.5,1.5)
        if self.kind=='line' and selected:
            width=(rect.width()-6)*selected;p.fillRect(QRectF(rect.center().x()-width/2,rect.bottom()-1,width,2),QColor(BURGUNDY))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#C399A7'),1));p.drawRoundedRect(rect.adjusted(1,1,-1,-1),6,6)
        foreground=blend('#777C89',BURGUNDY,max(selected,hover*.7)) if self.isEnabled() else QColor('#ABA7B0')
        p.setFont(self.font());p.setPen(foreground)
        icon_width=self.iconSize().width() if not self.icon().isNull() else 0
        padding=10;gap=(7 if self.kind=='side' else 9) if icon_width else 0
        text_rect=rect.adjusted(padding+icon_width+gap,0,-(8 if self.kind=='side' else padding),0)
        if icon_width:
            icon_rect=QRectF(rect.left()+padding+hover,rect.center().y()-self.iconSize().height()/2,icon_width,self.iconSize().height())
            if self._icons:
                weight=max(selected,hover*.7)
                for icon,opacity in zip(self._icons,(1-weight,weight)):
                    p.setOpacity(opacity);icon.paint(p,icon_rect.toRect())
                p.setOpacity(1)
            else:self.icon().paint(p,icon_rect.toRect())
        title=p.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,max(1,int(text_rect.width())))
        p.drawText(text_rect,Qt.AlignmentFlag.AlignVCenter|(Qt.AlignmentFlag.AlignLeft if self.kind=='side' else Qt.AlignmentFlag.AlignHCenter),title)


class MotionTabBar(QTabBar):
    def __init__(self,parent=None,background='#F6F6F8'):
        super().__init__(parent);self.background=background;self.setDrawBase(False);self.setMouseTracking(True)
        self._line=QRectF();self._hover=-1;self._levels={};self._hovers={}
        self._line_animation=tween(self,self._set_line,170);self.currentChanged.connect(self._select)
    def _set_line(self,value):self._line=QRectF(value);self.update()
    def _target(self):
        r=self.tabRect(self.currentIndex());return QRectF(r.left(),r.bottom()-1,r.width(),2) if r.isValid() else QRectF()
    def _select(self,*args):
        target=self._target();self._line_animation.stop()
        if not self.isVisible() or not motion_enabled(self) or self._line.isEmpty():self._set_line(target)
        else:
            self._line_animation.setStartValue(self._line);self._line_animation.setEndValue(target);self._line_animation.start()
    def _set_level(self,index,value):self._levels[index]=float(value);self.update(self.tabRect(index))
    def _move_hover(self,index):
        if index==self._hover:return
        previous=self._hover;self._hover=index
        for i in {previous,index}-{-1}:
            if i not in self._hovers:self._hovers[i]=tween(self,lambda value,n=i:self._set_level(n,value),120)
            animation=self._hovers[i];animation.stop();target=float(i==index)
            if not motion_enabled(self):self._set_level(i,target)
            else:animation.setStartValue(self._levels.get(i,0.));animation.setEndValue(target);animation.start()
    def mouseMoveEvent(self,event):self._move_hover(self.tabAt(event.position().toPoint()));super().mouseMoveEvent(event)
    def leaveEvent(self,event):self._move_hover(-1);super().leaveEvent(event)
    def resizeEvent(self,event):super().resizeEvent(event);self.finish_motion()
    def showEvent(self,event):super().showEvent(event);self.finish_motion()
    def hideEvent(self,event):self._hover=-1;self.finish_motion();super().hideEvent(event)
    def finish_motion(self):
        self._line_animation.stop()
        for animation in self._hovers.values():animation.stop()
        self._levels={i:float(i==self._hover) for i in range(self.count())};self._set_line(self._target())
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor(self.background));p.setFont(self.font())
        for i in range(self.count()):
            if not self.isTabVisible(i):continue
            rect=self.tabRect(i);level=self._levels.get(i,0.)
            if level:p.fillRect(rect,blend(self.background,'#F9E8EB',level))
            p.setPen(QColor(BURGUNDY if i==self.currentIndex() else '#747786'))
            p.drawText(rect.adjusted(12,0,-12,-2),Qt.AlignmentFlag.AlignCenter,self.tabText(i))
            if self.hasFocus() and i==self.currentIndex():
                p.setPen(QPen(QColor('#C399A7'),1,Qt.PenStyle.DotLine));p.drawLine(rect.left()+17,rect.bottom()-5,rect.right()-17,rect.bottom()-5)
        p.fillRect(self._line if not self._line.isEmpty() else self._target(),QColor(BURGUNDY))


class MotionLabel(QLabel):
    def __init__(self,title,parent=None):
        super().__init__(title,parent);self._opacity=1.;self._entry_animation=tween(self,self._set_opacity,150)
    def _set_opacity(self,value):self._opacity=float(value);self.update()
    def reveal(self):
        self._entry_animation.stop()
        if not self.isVisible() or not motion_enabled(self):self._set_opacity(1.);return
        self._entry_animation.setStartValue(.65);self._entry_animation.setEndValue(1.);self._entry_animation.start()
    def finish_motion(self):self._entry_animation.stop();self._set_opacity(1.)
    def hideEvent(self,event):self.finish_motion();super().hideEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.setOpacity(self._opacity);p.setFont(self.font());p.setPen(QColor('#111E30'))
        flags=self.alignment()|(Qt.TextFlag.TextWordWrap if self.wordWrap() else Qt.TextFlag.TextSingleLine)
        p.drawText(self.contentsRect(),flags,self.text())


def reveal_heading(label):
    if isinstance(label,MotionLabel):label.reveal()


def finish_motion(widget):
    for child in [widget,*widget.findChildren(MotionButton),*widget.findChildren(MotionTabBar),*widget.findChildren(MotionLabel)]:
        if isinstance(child,(MotionButton,MotionTabBar,MotionLabel)):child.finish_motion()
