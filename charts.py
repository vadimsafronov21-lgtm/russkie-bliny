"""Interactive native Qt charts. Geometry follows values without inventing data."""
import math
from datetime import date
from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QColor,QFont,QPainter,QPainterPath,QPen,QLinearGradient
from PySide6.QtWidgets import QWidget,QToolTip
from ui_theme import BURGUNDY,INK

COLORS=['#A4002A','#D47992','#E8B8C6','#111E30','#A8AFBD']

def num(value,decimals=0):
    return f'{value:,.{decimals}f}'.replace(',',' ').replace('.',',')

def font(px,weight=QFont.Weight.Normal):
    f=QFont('Inter'); f.setPixelSize(px); f.setWeight(weight); return f

def smooth_path(points):
    """Cubic controls stay within each interval's values: no decorative peaks."""
    path=QPainterPath()
    if not points: return path
    path.moveTo(*points[0])
    slopes=[]
    for i,(x,y) in enumerate(points):
        a=points[max(0,i-1)]; b=points[min(len(points)-1,i+1)]
        m=(b[1]-a[1])/(b[0]-a[0]) if b[0]!=a[0] else 0
        if 0<i<len(points)-1 and (y-a[1])*(b[1]-y)<=0: m=0
        slopes.append(m)
    for i in range(len(points)-1):
        x,y=points[i]; nx,ny=points[i+1]; step=(nx-x)/3; low,high=sorted([y,ny])
        path.cubicTo(x+step,min(high,max(low,y+slopes[i]*step)),nx-step,min(high,max(low,ny-slopes[i+1]*step)),nx,ny)
    return path


class StockProjectionChart(QWidget):
    """Daily stock with explicit receipt steps; shortages never become fake stock."""
    def __init__(self,parent=None):
        super().__init__(parent); self.base=None; self.picked=None; self.unit=''; self.arrival=''; self.setMinimumHeight(300); self.setMouseTracking(True)
    def set_data(self,base,picked,unit,arrival):
        self.base=base; self.picked=picked; self.unit=unit; self.arrival=arrival; self.update()
    def plot_rect(self): return QRectF(55,35,max(1,self.width()-80),max(1,self.height()-110))
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); rect=self.plot_rect()
        if not self.base:
            p.setFont(font(12)); p.setPen(QColor('#767383')); p.drawText(rect,Qt.AlignmentFlag.AlignCenter,'Для графика нужен актуальный расчёт'); return
        all_points=self.base['points']+self.picked['points']; count=len(self.base['points'])
        ymax=max([1]+[max(r['opening'],r['opening']-r['excluded']+r['incoming']+r['ordered']) for r in all_points])*1.15
        xpos=lambda n:rect.left()+rect.width()*n/max(1,count)
        ypos=lambda value:rect.bottom()-rect.height()*value/ymax
        p.setFont(font(10)); p.setPen(QColor('#777381')); p.drawText(QPointF(rect.left(),18),f'Расчётный запас, {self.unit}')
        for i in range(5):
            value=ymax*i/4; y=ypos(value); p.setPen(QPen(QColor('#ECE9EE'),1)); p.drawLine(QPointF(rect.left(),y),QPointF(rect.right(),y))
            p.setPen(QColor('#777381')); p.drawText(QRectF(0,y-8,rect.left()-10,18),Qt.AlignmentFlag.AlignRight,num(value,1))
        for series,color,dashed in [(self.base,'#697080',True),(self.picked,BURGUNDY,False)]:
            path=QPainterPath()
            for i,row in enumerate(series['points']):
                if i==0: path.moveTo(xpos(0),ypos(row['opening']))
                path.lineTo(xpos(i+.08),ypos(row['opening']-row['excluded']))
                path.lineTo(xpos(i+.08),ypos(row['opening']-row['excluded']+row['incoming']+row['ordered']))
                path.lineTo(xpos(i+1),ypos(row['closing']))
            pen=QPen(QColor(color),2.6); pen.setStyle(Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine); p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)
        for i,row in enumerate(self.picked['points']):
            if row['incoming']+row['ordered']:
                x=xpos(i+.08); p.setPen(QPen(QColor('#D2A2B2'),1,Qt.PenStyle.DotLine)); p.drawLine(QPointF(x,rect.top()),QPointF(x,rect.bottom()))
                title=date.fromisoformat(row['date']).strftime('%d.%m')+' · поступление'
                p.setPen(QColor(BURGUNDY)); p.drawText(QRectF(x-65,rect.top()-18,155,16),Qt.AlignmentFlag.AlignCenter,title)
            if row['shortage']>1e-9:
                p.setPen(QPen(QColor('white'),2)); p.setBrush(QColor(BURGUNDY)); p.drawEllipse(QPointF(xpos(i+1),ypos(row['closing'])),4,4)
        p.setFont(font(10)); p.setPen(QColor('#777381'))
        for i in sorted(set([0]+[round(j*count/5) for j in range(1,6)])):
            value='Начало' if i==0 else date.fromisoformat(self.picked['points'][i-1]['date']).strftime('%d.%m')
            p.drawText(QRectF(xpos(i)-25,rect.bottom()+9,50,18),Qt.AlignmentFlag.AlignCenter,value)
        compact=self.width()<520
        for index,(title,color,dashed) in enumerate([('Без нового заказа','#697080',True),('С выбранным заказом',BURGUNDY,False)]):
            x=rect.left()+(220 if index and not compact else 0)
            y=self.height()-23-(20 if compact and not index else 0)
            pen=QPen(QColor(color),2); pen.setStyle(Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine); p.setPen(pen); p.drawLine(QPointF(x,y),QPointF(x+22,y)); p.setPen(QColor('#555968')); p.drawText(QPointF(x+30,y+4),title)
    def mouseMoveEvent(self,event):
        rect=self.plot_rect()
        if not self.picked or not rect.contains(event.position()): QToolTip.hideText(); return
        index=min(len(self.picked['points'])-1,max(0,int((event.position().x()-rect.left())/rect.width()*len(self.picked['points']))))
        row=self.picked['points'][index]
        QToolTip.showText(event.globalPosition().toPoint(),f'{row["date"]} · на конец дня\nЗапас: {num(row["closing"],2)} {self.unit}\nРасход: {num(row["demand"],2)} {self.unit}\nВ пути: {num(row["incoming"],2)} {self.unit}\nВыбранный заказ: {num(row["ordered"],2)} {self.unit}\nНе хватит: {num(row["shortage"],2)} {self.unit}',self)
    def leaveEvent(self,event): QToolTip.hideText()

class SalesChart(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.payload=None; self.monthly=False; self.hover=None; self.setMouseTracking(True); self.setMinimumHeight(320)
    def set_data(self,payload,monthly=False): self.payload=payload; self.monthly=monthly; self.hover=None; self.update()
    def plot_rect(self): return QRectF(50,48,max(1,self.width()-75),max(1,self.height()-96))
    def series(self):
        if not self.payload: return []
        if self.monthly: return self.payload['months']
        return [{'name':'Закрытые смены','points':self.payload['actual']+self.payload['future']}]
    def mouseMoveEvent(self,event):
        rect=self.plot_rect(); count=31 if self.monthly else len(self.payload['actual']+self.payload['future']) if self.payload else 0
        self.hover=round((event.position().x()-rect.left())/rect.width()*max(1,count-1)) if rect.contains(event.position()) and count else None
        self.setCursor(Qt.CursorShape.CrossCursor if self.hover is not None else Qt.CursorShape.ArrowCursor); self.update()
    def leaveEvent(self,event): self.hover=None; self.update()
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setFont(font(11))
        rect=self.plot_rect(); series=self.series()
        values=[v['value'] for s in series for v in s['points'] if v['value'] is not None]
        if not values:
            p.setPen(QColor('#8A8C9B')); p.drawText(rect,Qt.AlignmentFlag.AlignCenter,'Нет подтверждённых продаж за выбранный период'); return
        ceiling=max(1,max(values))*1.12
        step=10**math.floor(math.log10(ceiling/4)); step=next((m*step for m in (1,2,2.5,5,10) if m*step>=ceiling/4),step*10)
        ymax=math.ceil(ceiling/step)*step
        count=31 if self.monthly else len(series[0]['points'])
        xpos=lambda i:rect.left()+rect.width()*i/max(1,count-1)
        ypos=lambda v:rect.bottom()-rect.height()*v/ymax
        if not self.monthly and self.payload['future']:
            boundary=xpos(len(self.payload['actual'])-.5)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#F7F0F3')); p.drawRoundedRect(QRectF(boundary,rect.top()-13,rect.right()-boundary,rect.height()+13),8,8)
            if rect.right()-boundary>72:
                p.setPen(QColor('#A56E82')); p.drawText(QRectF(boundary,rect.top()-34,rect.right()-boundary,20),Qt.AlignmentFlag.AlignCenter,'Прогноз')
        for i in range(int(round(ymax/step))+1):
            v=i*step; y=ypos(v); p.setPen(QPen(QColor('#EFEDF2'),1)); p.drawLine(QPointF(rect.left(),y),QPointF(rect.right(),y))
            p.setPen(QColor('#9C9CAB')); p.drawText(QRectF(0,y-8,rect.left()-13,16),Qt.AlignmentFlag.AlignRight,num(v,1 if step<1 else 0))
        for si,s in enumerate(series):
            color=['#E0ACBC',INK,BURGUNDY][si] if self.monthly else BURGUNDY
            segments=[]; segment=[]; last_kind=None
            for i,point in enumerate(s['points']):
                if point['value'] is None:
                    if segment: segments.append((last_kind,segment)); segment=[]
                    last_kind=None; continue
                kind=point['kind']
                if last_kind and last_kind!=kind:
                    segments.append((last_kind,segment)); segment=[segment[-1]]
                segment.append((xpos(i),ypos(point['value']))); last_kind=kind
            if segment: segments.append((last_kind,segment))
            for kind,coords in segments:
                path=smooth_path(coords)
                if not self.monthly and len(coords)>1:
                    area=QPainterPath(path); area.lineTo(coords[-1][0],rect.bottom()); area.lineTo(coords[0][0],rect.bottom()); area.closeSubpath()
                    gradient=QLinearGradient(0,rect.top(),0,rect.bottom()); gradient.setColorAt(0,QColor(164,0,42,42 if kind=='actual' else 17)); gradient.setColorAt(1,QColor(164,0,42,0))
                    p.fillPath(area,gradient)
                pen=QPen(QColor(color),2.7 if not self.monthly or si==2 else 1.8)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                if kind=='forecast' or self.monthly and si==0: pen.setStyle(Qt.PenStyle.DashLine)
                p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(pen); p.drawPath(path)
                if len(coords)==1:
                    p.setBrush(QColor(color)); p.drawEllipse(QPointF(*coords[0]),3,3)
            if not self.monthly:
                known=[(i,v) for i,v in enumerate(s['points']) if v['kind']=='actual' and v['value'] is not None]
                if known:
                    i,v=known[-1]; p.setBrush(QColor(BURGUNDY)); p.setPen(QPen(QColor('white'),2)); p.drawEllipse(QPointF(xpos(i),ypos(v['value'])),4.5,4.5)
        p.setFont(font(10)); p.setPen(QColor('#9699A7'))
        ticks=sorted(set([round(i*(count-1)/5) for i in range(6)]))
        for i in ticks:
            text=str(i+1) if self.monthly else date.fromisoformat(series[0]['points'][i]['date']).strftime('%d.%m')
            p.drawText(QRectF(xpos(i)-25,rect.bottom()+12,50,18),Qt.AlignmentFlag.AlignCenter,text)
        legend=[(s['name'],['#E0ACBC',INK,BURGUNDY][i],i==0) for i,s in enumerate(series)] if self.monthly else [('Закрытые смены',BURGUNDY,False),('Прогноз спроса',BURGUNDY,True)]
        x=rect.left()
        for name,color,dashed in legend:
            pen=QPen(QColor(color),2); pen.setStyle(Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine); p.setPen(pen); p.drawLine(QPointF(x,self.height()-5),QPointF(x+21,self.height()-5)); p.setPen(QColor('#858695')); p.drawText(QPointF(x+29,self.height()-1),name); x+=max(162,p.fontMetrics().horizontalAdvance(name)+52)
        if self.hover is not None and 0<=self.hover<count:
            i=self.hover; x=xpos(i); p.setPen(QPen(QColor('#C4A4B1'),1,Qt.PenStyle.DotLine)); p.drawLine(QPointF(x,rect.top()),QPointF(x,rect.bottom()))
            if self.monthly:
                selected=[s['points'][i] if i<len(s['points']) else None for s in series]
                lines=[f'{i+1}-е число']+[f'{s["name"]}: {num(v["value"])}' if v and v['value'] is not None else f'{s["name"]}: нет записи' for s,v in zip(series,selected)]
                self.bubble(p,min(max(rect.left(),x-112),rect.right()-225),rect.top()+4,lines)
            else:
                point=series[0]['points'][i]; value=point['value']
                lines=[date.fromisoformat(point['date']).strftime('%d.%m.%Y'),f'{num(value,1 if point["kind"]=="forecast" else 0)} порций' if value is not None else 'Нет выгрузки за день','Расчётный спрос' if point['kind']=='forecast' else 'Закрытая смена' if value is not None else 'Пропуск не считается нулём']
                if point['available'] is False: lines[-1]='Нет наличия, спрос неизвестен'
                if value is not None:
                    p.setPen(QPen(QColor('white'),2)); p.setBrush(QColor(BURGUNDY)); p.drawEllipse(QPointF(x,ypos(value)),5,5)
                self.bubble(p,min(max(rect.left(),x-110),rect.right()-225),rect.top()+3,lines)
        elif not self.monthly and self.payload['peak'] and self.payload['peak']['value']>0:
            peak=self.payload['peak']; i=next(i for i,v in enumerate(series[0]['points']) if v['date']==peak['date']); x=xpos(i)
            p.setBrush(QColor('white')); p.setPen(QPen(QColor(BURGUNDY),2)); p.drawEllipse(QPointF(x,ypos(peak['value'])),4,4)
            p.setFont(font(11,QFont.Weight.Medium)); p.setPen(QColor(BURGUNDY)); text=f'Пик {num(peak["value"])} · {date.fromisoformat(peak["date"]).strftime("%d.%m")}'
            width=p.fontMetrics().horizontalAdvance(text)+20; rx=min(rect.right()-width,max(rect.left(),x-width/2)); r=QRectF(rx,max(6,ypos(peak['value'])-35),width,26)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#F9E8EB')); p.drawRoundedRect(r,8,8); p.setPen(QColor(BURGUNDY)); p.drawText(r,Qt.AlignmentFlag.AlignCenter,text)
    def bubble(self,p,x,y,lines):
        rect=QRectF(x,y,225,22+len(lines)*21); p.setPen(QPen(QColor('#E8DEE5'),1)); p.setBrush(QColor('white')); p.drawRoundedRect(rect,12,12)
        for i,line in enumerate(lines):
            p.setFont(font(15 if i==1 else 10,QFont.Weight.DemiBold if i==1 else QFont.Weight.Normal)); p.setPen(QColor(INK if i==1 else '#7E7887')); p.drawText(QPointF(x+14,y+22+i*21),line)

class CoverageChart(QWidget):
    ingredientSelected=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent); self.rows=[]; self.hover=None; self.setMinimumHeight(235); self.setMouseTracking(True)
    def set_data(self,rows): self.rows=rows; self.hover=None; self.update()
    def chart_geometry(self):
        top=12.; step=max(28.,(self.height()-48)/max(1,len(self.rows)))
        left=min(285.,max(180.,self.width()*.23));right=self.width()-66.
        return top,step,left,right
    def row_at(self,pos):
        top,step,_,_=self.chart_geometry();i=math.floor((pos.y()-top)/step)
        return i if 0<=i<len(self.rows) and 0<=pos.x()<=self.width() else None
    def mouseMoveEvent(self,event):
        previous=self.hover;self.hover=self.row_at(event.position()); self.setCursor(Qt.CursorShape.PointingHandCursor if self.hover is not None else Qt.CursorShape.ArrowCursor)
        if self.hover is not None:
            r=self.rows[self.hover]; QToolTip.showText(event.globalPosition().toPoint(),f'{r["name"]}\nСейчас: {num(r["effective"],2)} {r["unit"]}\nВ пути: {num(r["incoming"],2)} {r["unit"]}\nПотребность: {num(r["demand"],2)} {r["unit"]}\nДефицит до доставки: {num(r["shortage_before"],2)} {r["unit"]}\nНажмите для расчёта заявки',self)
        if previous!=self.hover:self.update()
    def mousePressEvent(self,event):
        i=self.row_at(event.position())
        if event.button()==Qt.MouseButton.LeftButton and i is not None:self.ingredientSelected.emit(str(self.rows[i]['id']))
    def leaveEvent(self,event): self.hover=None; QToolTip.hideText(); self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.rows:
            p.setFont(font(13));p.setPen(QColor('#92909D'));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,getattr(self,'empty_message','Расчёт покрытия недоступен'));return
        top,step,left,right=self.chart_geometry();width=max(1,right-left);thickness=min(22.,max(10.,step*.26))
        text_size=15 if step>=60 and self.width()>850 else 13 if step>=40 else 11
        for i,r in enumerate(self.rows):
            y=top+(i+.5)*step
            if self.hover==i:
                p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#FCF4F6'));p.drawRoundedRect(QRectF(0,top+i*step,self.width(),step),8,8)
            p.setFont(font(text_size,QFont.Weight.Medium));p.setPen(QColor(INK))
            p.drawText(QRectF(6,y-(24 if step>=55 else 11),left-24,24),Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(r['name'],Qt.TextElideMode.ElideRight,int(left-24)))
            if step>=55:
                p.setFont(font(11));p.setPen(QColor('#888491'))
                p.drawText(QRectF(6,y+3,left-24,20),Qt.AlignmentFlag.AlignVCenter,f'{num(r["effective"],1)} / {num(r["demand"],1)} {r["unit"]}')
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#F1EFF4'));p.drawRoundedRect(QRectF(left,y-thickness/2,width,thickness),thickness/2,thickness/2)
            if r['percent'] is not None:
                current=min(150,r['effective']/r['demand']*100);incoming=min(150-current,r['incoming']/r['demand']*100)
                p.setBrush(QColor(BURGUNDY));p.drawRoundedRect(QRectF(left,y-thickness/2,width*current/150,thickness),thickness/2,thickness/2)
                if incoming>0:
                    p.setBrush(QColor('#DF9DB3'));p.drawRoundedRect(QRectF(left+width*current/150,y-thickness/2,width*incoming/150,thickness),thickness/2,thickness/2)
            p.setFont(font(text_size,QFont.Weight.Medium));p.setPen(QColor(INK))
            p.drawText(QRectF(right+10,y-14,56,28),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,num(r['percent'])+'%' if r['percent'] is not None else '—')
        x=left+width*100/150;bottom=top+step*len(self.rows)
        p.setPen(QPen(QColor('#B7AEBC'),1,Qt.PenStyle.DashLine));p.drawLine(QPointF(x,top),QPointF(x,bottom))
        p.setFont(font(11));p.setPen(QColor('#918799'));p.drawText(QRectF(x-45,bottom+3,90,22),Qt.AlignmentFlag.AlignCenter,'100%')

class MixChart(QWidget):
    dishSelected=Signal(str)
    def __init__(self,parent=None):
        super().__init__(parent);self.rows=[];self.total=0;self.observed=0;self.hover=None;self.setMinimumHeight(250);self.setMouseTracking(True)
    def set_data(self,rows,total,observed=0):self.rows=rows;self.total=total;self.observed=observed;self.hover=None;self.update()
    def geometry_parts(self):
        diameter=max(112.,min(460.,self.height()-34.,self.width()*.40))
        gap=min(90.,max(24.,self.width()*.055));legend_width=min(610.,max(140.,self.width()-diameter-gap-20))
        group_width=diameter+gap+legend_width;start=max(8.,(self.width()-group_width)/2)
        return QRectF(start,(self.height()-diameter)/2,diameter,diameter),start+diameter+gap
    def legend_geometry(self):
        rect,left=self.geometry_parts();width=min(610.,self.width()-left-8.)
        step=max(34.,min(78.,self.height()*.78/max(1,len(self.rows))))
        return (self.height()-step*len(self.rows))/2,step,left+width
    def ring_width(self):return max(17.,min(46.,self.geometry_parts()[0].width()*.105))
    def row_at(self,pos):
        rect,left=self.geometry_parts();top,step,right=self.legend_geometry()
        if left<=pos.x()<=right:
            i=math.floor((pos.y()-top)/step);return i if 0<=i<len(self.rows) else None
        dx=pos.x()-rect.center().x();dy=pos.y()-rect.center().y();radius=math.hypot(dx,dy);stroke=self.ring_width()
        if self.total and rect.width()/2-stroke-7<=radius<=rect.width()/2:
            angle=(math.degrees(math.atan2(dy,dx))+90)%360;acc=0
            for i,r in enumerate(self.rows):
                acc+=r['value']/self.total*360
                if angle<=acc:return i
        return None
    def mouseMoveEvent(self,event):
        previous=self.hover;self.hover=self.row_at(event.position());self.setCursor(Qt.CursorShape.PointingHandCursor if self.hover is not None and self.rows[self.hover]['id'] is not None else Qt.CursorShape.ArrowCursor)
        if self.hover is not None:
            r=self.rows[self.hover];QToolTip.showText(event.globalPosition().toPoint(),f'{r["name"]}\n{num(r["value"])} порций · {num(r["value"]/self.total*100,1)}%\nНажмите, чтобы посмотреть динамику',self)
        if previous!=self.hover:self.update()
    def mousePressEvent(self,event):
        i=self.row_at(event.position())
        if event.button()==Qt.MouseButton.LeftButton and i is not None and self.rows[i]['id'] is not None:self.dishSelected.emit(str(self.rows[i]['id']))
    def leaveEvent(self,event):self.hover=None;QToolTip.hideText();self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);rect,left=self.geometry_parts();stroke=self.ring_width()
        arc=rect.adjusted(stroke/2+4,stroke/2+4,-stroke/2-4,-stroke/2-4)
        if not self.total:
            p.setPen(QPen(QColor('#F1EDF2'),stroke));p.drawEllipse(arc);p.setFont(font(14));p.setPen(QColor('#92909D'));p.drawText(rect,Qt.AlignmentFlag.AlignCenter,'Нет продаж' if self.observed else 'Нет данных');return
        angle=90
        for i,r in enumerate(self.rows):
            span=r['value']/self.total*360;pen=QPen(QColor(COLORS[i%len(COLORS)]),stroke+(4 if self.hover==i else 0));pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen);p.setBrush(Qt.BrushStyle.NoBrush);p.drawArc(arc,int(angle*16),int(-(span-2 if span>3 else span)*16));angle-=span
        total_size=max(24,min(48,int(rect.width()*.115)));p.setFont(font(total_size,QFont.Weight.DemiBold));p.setPen(QColor(INK))
        p.drawText(rect.adjusted(0,-12,0,-12),Qt.AlignmentFlag.AlignCenter,num(self.total));p.setFont(font(12));p.setPen(QColor('#97909D'));p.drawText(rect.adjusted(0,total_size+12,0,0),Qt.AlignmentFlag.AlignCenter,'порций')
        top,step,right=self.legend_geometry();size=15 if self.width()>850 else 12
        for i,r in enumerate(self.rows):
            y=top+i*step;row_rect=QRectF(left-10,y,max(1,right-left+10),step)
            if self.hover==i:p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#FCF4F6'));p.drawRoundedRect(row_rect,8,8)
            center=y+step/2;p.setBrush(QColor(COLORS[i%len(COLORS)]));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(left+4,center-7 if step>=50 else center),4.5,4.5)
            p.setFont(font(size,QFont.Weight.Medium));p.setPen(QColor(INK));name=p.fontMetrics().elidedText(r['name'],Qt.TextElideMode.ElideRight,max(20,int(right-left-100)))
            p.drawText(QRectF(left+21,center-(23 if step>=50 else 12),max(20,right-left-100),24),Qt.AlignmentFlag.AlignVCenter,name)
            if step>=50:
                p.setFont(font(12));p.setPen(QColor('#928B98'));p.drawText(QRectF(left+21,center+4,max(20,right-left-100),22),Qt.AlignmentFlag.AlignVCenter,num(r['value'])+' порций')
            p.setFont(font(size+2,QFont.Weight.DemiBold));p.setPen(QColor(INK));p.drawText(QRectF(right-72,center-15,72,30),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,num(r['value']/self.total*100)+'%')
