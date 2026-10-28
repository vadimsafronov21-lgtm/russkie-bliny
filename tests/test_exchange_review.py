import copy
import hashlib
import json

import pytest

from core import DataError,Store,demo_data,write_templates
from exchange_review import apply_import,prepare_file_import,prepare_import,row_description


@pytest.fixture
def store(tmp_path):
    result=Store(tmp_path/'exchange.sqlite3'); result.seed()
    # Establish a first source baseline, separate from later operator corrections.
    with result.db:
        result.put('seeded_demo',False); result.put('exchange_base',result.get('tables'))
    yield result
    result.db.close()


def plan(store,tables):
    digest=hashlib.sha256(json.dumps(tables,ensure_ascii=False).encode()).hexdigest()
    return prepare_import(store,tables,True,'Тестовый источник',digest)


def test_preview_is_read_only_and_remote_change_applies(store):
    before=list(store.db.iterdump()); tables=store.get('tables'); tables['sales'][-1]['qty']+=1
    preview=plan(store,tables)
    assert len(preview.changes)==1 and not preview.conflicts
    assert list(store.db.iterdump())==before
    apply_import(store,preview)
    expected=tables['sales'][-1]
    actual=next(row for row in store.get('tables')['sales'] if row['date']==expected['date'] and row['dish']==expected['dish'])
    assert actual['qty']==expected['qty']


@pytest.mark.parametrize('choice',['local','remote'])
def test_conflicting_stock_requires_decision_and_reason(store,choice):
    incoming=store.get('tables'); incoming['batches'][0]['qty']=40
    store.correct_batch('b0',8,True,'Пересчёт на точке','Оператор')
    preview=plan(store,incoming)
    assert len(preview.conflicts)==1
    before=list(store.db.iterdump())
    with pytest.raises(DataError,match='причину'): apply_import(store,preview,{0:choice})
    with pytest.raises(DataError,match='каждого'): apply_import(store,preview,reason='Проверено')
    assert list(store.db.iterdump())==before
    apply_import(store,preview,{0:choice},'Повторно сверен остаток','Оператор')
    assert store.get('tables')['batches'][0]['qty']==(8 if choice=='local' else 40)
    assert any(row['id'].startswith('local-') for row in store.get('tables')['movements'])
    assert 'Повторно сверен остаток' in str(store.db.execute('SELECT reason FROM audit').fetchall())


def test_unchanged_source_preserves_local_edit_and_draft(store):
    incoming=store.get('tables'); store.correct_batch('b0',8,True,'Пересчёт','Оператор')
    store.save_draft('central',{'edits':{'dough':{'packs':2,'reason':'Запас'}}})
    preview=plan(store,incoming)
    assert not preview.conflicts
    apply_import(store,preview)
    assert next(row for row in store.get('tables')['batches'] if row['id']=='b0')['qty']==8
    assert store.get('draft:central')['edits']['dough']['packs']==2
    before=list(store.db.iterdump())
    assert 'уже загружен' in apply_import(store,plan(store,incoming))
    assert list(store.db.iterdump())==before


def test_stale_preview_cannot_overwrite_new_correction(store):
    tables=store.get('tables'); tables['sales'][-1]['qty']+=1; preview=plan(store,tables)
    store.correct_batch('b0',9,True,'После предпросмотра','Оператор')
    before=list(store.db.iterdump())
    with pytest.raises(DataError,match='после предпросмотра'): apply_import(store,preview)
    assert list(store.db.iterdump())==before


def test_modified_plan_and_invalid_refs_are_atomic(store):
    incoming=store.get('tables'); incoming['batches'][0]['qty']=40
    preview=plan(store,incoming); preview.merged['batches'][0]['qty']=99
    before=list(store.db.iterdump())
    with pytest.raises(DataError,match='Предпросмотр изменён'): apply_import(store,preview)
    assert list(store.db.iterdump())==before
    incoming['batches'][0]['unit']='кг'
    with pytest.raises(DataError,match='единица'): plan(store,incoming)


def test_file_import_can_preview_without_writing(store,tmp_path):
    write_templates(tmp_path/'source',demo_data())
    before=list(store.db.iterdump()); preview=prepare_file_import(store,tmp_path/'source'/'demo.xlsx')
    assert preview.is_demo and list(store.db.iterdump())==before


def test_demo_switch_clears_only_draft_and_separates_dataset(store):
    store.save_draft('central',{'edits':{}})
    incoming=demo_data()
    preview=prepare_import(store,incoming,False,'Реальная выгрузка','real-hash')
    assert preview.switching and not preview.conflicts
    apply_import(store,preview)
    assert store.get('demo') is False and store.get('draft:central') is None


def test_local_deletion_kept_if_source_unchanged(store):
    incoming=store.get('tables'); tables=copy.deepcopy(incoming); tables['movements']=[]
    with store.db: store.put('tables',tables)
    apply_import(store,plan(store,incoming))
    assert not store.get('tables')['movements']


def test_zero_is_visible_in_preview():
    assert 'Количество: 0' in row_description({'qty':0,'use_before':''})
    assert 'Использовать до: —' in row_description({'use_before':''})


def test_conflict_choice_cannot_break_references(store):
    incoming=store.get('tables'); store.correct_batch('b0',8,True,'Сверка','Оператор')
    incoming['items']=[row for row in incoming['items'] if row['id']!='dough']
    for kind in ('batches','recipes','deliveries','movements'):
        incoming[kind]=[row for row in incoming[kind] if row['ingredient']!='dough']
    preview=plan(store,incoming); before=list(store.db.iterdump())
    choices={index:'local' for index,_ in enumerate(preview.conflicts)}
    with pytest.raises(DataError,match='не сопоставлен'): apply_import(store,preview,choices,'Оставить локальный остаток')
    assert list(store.db.iterdump())==before
