"""Auditable draft undo and read-only comparison of frozen orders."""
import copy
import uuid

from core import DataError,calculation_day,now,number


def checked_draft(store,point,payload):
    saved=store.get('draft:'+str(point))
    if not saved or saved.get('draft_id')!=payload.get('draft_id'):
        raise DataError('Черновик изменился. Откройте актуальную заявку.')
    if str(saved.get('point'))!=str(point): raise DataError('Черновик другой точки.')
    if saved.get('confirmed_order_id') or store.db.execute('SELECT 1 FROM orders WHERE point=? AND draft_id=?',
                                                          (str(point),saved.get('draft_id'))).fetchone():
        raise DataError('Подтверждённая заявка зафиксирована. Создайте новую.')
    if saved.get('revision')!=store.get('revision') or saved.get('date')!=calculation_day(store.get('settings',{})).isoformat():
        raise DataError('Данные или дата изменились. Сначала пересчитайте заявку.')
    if saved.get('edits',{})!=payload.get('edits',{}):
        raise DataError('Ручные количества изменились. Обновите заявку.')
    return saved


def save_order_edit(store,point,payload,ingredient,packs,reason,author):
    packs=number(packs,'Количество упаковок')
    if packs!=int(packs): raise DataError('Количество упаковок должно быть целым.')
    if not reason.strip(): raise DataError('Укажите причину изменения.')
    store.db.execute('BEGIN IMMEDIATE')
    try:
        saved=checked_draft(store,point,payload)
        row=next((row for row in saved['rows'] if str(row['id'])==str(ingredient)),None)
        if row is None: raise DataError('Ингредиент отсутствует в заявке.')
        previous=copy.deepcopy(saved.get('edits',{}).get(row['id']))
        edit=dict(packs=int(packs),reason=reason.strip(),author=author,at=now())
        saved.setdefault('edits',{})[row['id']]=edit
        saved['_undo']=(saved.get('_undo',[])+[dict(id=uuid.uuid4().hex,ingredient=row['id'],name=row['name'],
                        before=previous,after=edit,revision=saved['revision'])])[-30:]
        store.put('draft:'+str(point),saved)
        store.log('Правка заявки',{'id':row['id'],'name':row['name'],'old':previous,'recommended':row['packs']},edit,reason.strip(),author)
        store.put('reason_history:order',list(dict.fromkeys([reason.strip(),*store.get('reason_history:order',[])]))[:8])
        store.db.commit()
    except Exception:
        store.db.rollback(); raise
    payload.clear(); payload.update(saved)
    return edit


def undo_order_edit(store,point,payload,author):
    store.db.execute('BEGIN IMMEDIATE')
    try:
        saved=checked_draft(store,point,payload)
        stack=saved.get('_undo',[])
        if not stack: raise DataError('Нет ручной правки для отмены.')
        change=stack[-1]
        if change['revision']!=saved['revision'] or saved.get('edits',{}).get(change['ingredient'])!=change['after']:
            raise DataError('После правки изменился расчёт. Эту правку отменить нельзя.')
        if change['before'] is None: saved['edits'].pop(change['ingredient'],None)
        else: saved['edits'][change['ingredient']]=copy.deepcopy(change['before'])
        saved['_undo']=stack[:-1]; saved['stock_confirmed']=False
        saved['stock_confirmed_revision']=None
        store.put('draft:'+str(point),saved)
        store.log('Отмена правки заявки',change['after'],change['before'],
                  'Отмена последней правки: '+change['name'],author)
        store.db.commit()
    except Exception:
        store.db.rollback(); raise
    payload.clear(); payload.update(saved)
    return change['name']


def compare_orders(left,right):
    if left['point']!=right['point']: raise DataError('Выберите заявки одной точки.')
    a,b=left['payload'],right['payload']
    if bool(a.get('demo'))!=bool(b.get('demo')): raise DataError('ДЕМО и реальные заявки сравниваются отдельно.')
    if left['id']==right['id']: raise DataError('Выберите две разные заявки.')
    indexed=lambda payload:{str(row['id']):row for row in payload['rows']}
    old,new=indexed(a),indexed(b); rows=[]
    for ingredient in sorted(set(old)|set(new)):
        before,after=old.get(ingredient),new.get(ingredient)
        def values(payload,row):
            if row is None: return dict(packs=0,qty=0,cost=0,unit=None,reason='Позиции нет')
            edit=payload.get('edits',{}).get(row['id'],{})
            packs=edit.get('packs',row['packs'])
            return dict(packs=packs,qty=packs*row['pack'],cost=packs*row['pack']*row['cost'],unit=row['unit'],
                        reason=edit.get('reason','По рекомендации'))
        x,y=values(a,before),values(b,after)
        same_units=before is None or after is None or x['unit']==y['unit']
        rows.append(dict(id=ingredient,name=(after or before)['name'],before=x,after=y,
                         qty_delta=y['qty']-x['qty'] if same_units else None,cost_delta=y['cost']-x['cost']))
    return dict(rows=rows,before_total=sum(row['before']['cost'] for row in rows),after_total=sum(row['after']['cost'] for row in rows))
