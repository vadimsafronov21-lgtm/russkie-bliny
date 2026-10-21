"""Read-only projections for charts. Missing observations remain unknown."""
from collections import defaultdict
from datetime import date,timedelta
import calendar
from core import flag

MONTHS=['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь']

def completed_months(cutoff):
    result=[]
    for offset in (3,2,1):
        year,month=divmod(cutoff.year*12+cutoff.month-1-offset,12)
        result.append((year,month+1))
    return result

def make_analytics(tables,point,dish,cutoff,days=30,snapshot=None,monthly=False):
    snapshot=snapshot or {}
    months=completed_months(cutoff)
    start=date(months[0][0],months[0][1],1) if monthly else cutoff-timedelta(days=days)
    end=cutoff.replace(day=1) if monthly else cutoff
    length=(end-start).days
    closed=[r for r in tables.get('sales',[]) if str(r['point'])==str(point) and flag(r['closed'],'closed') and date.fromisoformat(str(r['date']))<cutoff]
    selected={str(r['date']):r for r in closed if str(r['dish'])==str(dish)}
    dates=[start+timedelta(days=i) for i in range(length)]
    actual=[]
    for d in dates:
        row=selected.get(d.isoformat())
        actual.append({'date':d.isoformat(),'value':float(row['qty']) if row else None,'available':flag(row['available'],'available') if row else None,'kind':'actual'})
    observed=[p for p in actual if p['value'] is not None]
    total=sum(p['value'] for p in observed)
    previous=[selected.get((start-timedelta(days=i+1)).isoformat()) for i in range(length)]
    delta=None
    if len(observed)==length and all(previous):
        prior=sum(float(r['qty']) for r in previous)
        if prior>0: delta=(total/prior-1)*100
    forecast=next((f for f in snapshot.get('forecasts',[]) if str(f['id'])==str(dish)),None)
    future=[]
    if forecast:
        future=[{'date':(cutoff+timedelta(days=i)).isoformat(),'value':v,'available':None,'kind':'forecast'} for i,v in enumerate(forecast['daily'])]
    month_series=[]
    for year,month in months:
        values=[]
        for day in range(1,calendar.monthrange(year,month)[1]+1):
            d=date(year,month,day); row=selected.get(d.isoformat())
            values.append({'date':d.isoformat(),'x':day,'value':float(row['qty']) if row else None,'available':flag(row['available'],'available') if row else None,'kind':'actual'})
        month_series.append({'name':f'{MONTHS[month-1]} {year}','points':values})
    names={str(i['id']):i['name'] for i in tables.get('items',[]) if i['kind']=='dish'}
    counts=defaultdict(float); composition_observed=0
    for r in closed:
        if start<=date.fromisoformat(str(r['date']))<end: counts[str(r['dish'])]+=float(r['qty']); composition_observed+=1
    ranked=sorted([{'id':k,'name':names.get(k,k),'value':v} for k,v in counts.items() if v>0],key=lambda r:(-r['value'],r['id']))
    if len(ranked)>5:
        ranked=ranked[:4]+[{'id':None,'name':'Остальные блюда','value':sum(r['value'] for r in ranked[4:])}]
    coverage=[]
    for r in snapshot.get('rows',[]):
        coverage.append({**r,'percent':(r['effective']+r['incoming'])/r['demand']*100 if r['demand']>0 else None})
    coverage.sort(key=lambda r:(r['percent'] is None,r['percent'] if r['percent'] is not None else 0))
    return {'start':start.isoformat(),'end':end.isoformat(),'cutoff':cutoff.isoformat(),'actual':actual,'future':future,
            'observed':len(observed),'length':length,'total':total,'average':total/len(observed) if observed else None,
            'peak':max(observed,key=lambda p:p['value']) if observed else None,'delta':delta,'forecast':forecast,
            'months':month_series,'composition':ranked,'composition_total':sum(r['value'] for r in ranked),'composition_observed':composition_observed,
            'coverage':coverage[:7],'coverage_count':len(coverage),'monthly':monthly}
