import copy
import json
from datetime import date

import pytest

from core import DataError,Store,calculate
from interaction import compare_orders,save_order_edit,undo_order_edit


@pytest.fixture
def store(tmp_path):
    result=Store(tmp_path/'interaction.sqlite3'); result.seed(); yield result; result.db.close()


def draft(store):
    payload=calculate(store.get('tables'),'central',date.today(),{})
    payload.update(revision=store.get('revision'),demo=True,stock_confirmed=False)
    store.save_draft('central',payload)
    return payload


def test_undo_restores_previous_manual_value_then_recommendation(store):
    payload=draft(store); before_tables=store.get('tables')
    save_order_edit(store,'central',payload,'dough',2,'Первый пересчёт','Анна')
    save_order_edit(store,'central',payload,'dough',3,'Уточнение','Анна')
    undo_order_edit(store,'central',payload,'Анна')
    assert payload['edits']['dough']['packs']==2 and payload['edits']['dough']['reason']=='Первый пересчёт'
    undo_order_edit(store,'central',payload,'Анна')
    assert not payload['edits'] and not payload['stock_confirmed']
    assert store.get('tables')==before_tables
    assert store.db.execute('SELECT kind FROM audit').fetchall()==[
        ('Правка заявки',),('Правка заявки',),('Отмена правки заявки',),('Отмена правки заявки',)]
    before=list(store.db.iterdump())
    with pytest.raises(DataError,match='Нет ручной'): undo_order_edit(store,'central',payload,'Анна')
    assert list(store.db.iterdump())==before


def test_undo_survives_database_restart(store):
    payload=draft(store); save_order_edit(store,'central',payload,'dough',0,'Есть запас','Анна')
    second=Store(store.path)
    try:
        saved=second.get('draft:central'); undo_order_edit(second,'central',saved,'Анна')
        assert not second.get('draft:central')['edits']
    finally: second.db.close()


def test_confirmed_order_cannot_be_undone_or_edited(store):
    payload=draft(store); save_order_edit(store,'central',payload,'dough',2,'Большой заказ','Анна')
    stale_view=copy.deepcopy(payload)
    payload.update(stock_confirmed=True,stock_confirmed_revision=store.get('revision'),stock_confirmed_on=date.today().isoformat())
    order_id=store.confirm('central',payload,'Анна'); before=list(store.db.iterdump())
    with pytest.raises(DataError,match='зафиксирована'): undo_order_edit(store,'central',stale_view,'Анна')
    with pytest.raises(DataError,match='зафиксирована'): save_order_edit(store,'central',payload,'dough',1,'Ошибка','Анна')
    assert list(store.db.iterdump())==before and store.get_order(order_id)['payload']['edits']['dough']['packs']==2


def test_stale_revision_and_stale_view_rejected_atomically(store):
    payload=draft(store); other=copy.deepcopy(payload)
    save_order_edit(store,'central',payload,'dough',2,'Запас','Анна')
    before=list(store.db.iterdump())
    with pytest.raises(DataError,match='количества изменились'): save_order_edit(store,'central',other,'dough',1,'Устаревшее окно','Анна')
    assert list(store.db.iterdump())==before
    store.correct_batch('b0',8,True,'Новая сверка','Анна'); before=list(store.db.iterdump())
    with pytest.raises(DataError,match='пересчитайте'): undo_order_edit(store,'central',payload,'Анна')
    assert list(store.db.iterdump())==before


@pytest.mark.parametrize('packs,reason',[(-1,'Причина'),(1.5,'Причина'),(2,'')])
def test_invalid_edit_keeps_draft_and_audit(store,packs,reason):
    payload=draft(store); before=list(store.db.iterdump())
    with pytest.raises(DataError): save_order_edit(store,'central',payload,'dough',packs,reason,'Анна')
    assert list(store.db.iterdump())==before


def test_comparison_uses_frozen_pack_sizes_costs_and_reasons(store):
    payload=draft(store)
    left=dict(id=1,point='central',payload=copy.deepcopy(payload))
    right=dict(id=2,point='central',payload=copy.deepcopy(payload))
    left['payload']['edits']={'dough':{'packs':2,'reason':'Раньше'}}
    right['payload']['edits']={'dough':{'packs':3,'reason':'Большой заказ'}}
    row=next(row for row in right['payload']['rows'] if row['id']=='dough'); row.update(pack=10,cost=100)
    before=list(store.db.iterdump()); result=compare_orders(left,right)
    row=next(row for row in result['rows'] if row['id']=='dough')
    assert row['before']['qty']==10 and row['after']['qty']==30 and row['qty_delta']==20
    assert row['cost_delta']==2050 and row['after']['reason']=='Большой заказ'
    assert list(store.db.iterdump())==before
    next(row for row in right['payload']['rows'] if row['id']=='dough')['unit']='кг'
    assert next(row for row in compare_orders(left,right)['rows'] if row['id']=='dough')['qty_delta'] is None


@pytest.mark.parametrize('mutation', ['point','demo','same'])
def test_comparison_rejects_mixed_context(store,mutation):
    payload=draft(store); left=dict(id=1,point='central',payload=payload); right=copy.deepcopy(left); right['id']=2
    if mutation=='point': right['point']='other'
    if mutation=='demo': right['payload']['demo']=False
    if mutation=='same': right['id']=1
    with pytest.raises(DataError): compare_orders(left,right)
