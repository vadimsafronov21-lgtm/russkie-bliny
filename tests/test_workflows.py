import copy
import json
import sqlite3
from datetime import date,timedelta

import pytest
from core import Store,DataError,calculate,calculation_day,inventory_projection,order_impact


@pytest.fixture
def store(tmp_path):
    store=Store(tmp_path/'working.sqlite3'); store.seed()
    yield store
    store.db.close()


def draft(store):
    payload=calculate(store.get('tables'),'central',date.today(),store.get('settings'))
    payload.update(revision=store.get('revision'),stock_confirmed=True,stock_confirmed_revision=store.get('revision'),stock_confirmed_on=date.today().isoformat(),edits={})
    store.save_draft('central',payload)
    return payload


def test_confirmation_survives_retries_restart_and_another_connection(store):
    payload=draft(store); retry=copy.deepcopy(payload)
    first=store.confirm('central',payload,'Анна')
    other=Store(store.path)
    try:
        assert other.confirm('central',retry,'Анна')==first
        assert other.get('draft:central')['confirmed_order_id']==first
    finally: other.db.close()
    assert store.confirm('central',payload,'Анна')==first
    assert store.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==1
    assert store.db.execute("SELECT COUNT(*) FROM audit WHERE kind='Подтверждение заявки'").fetchone()[0]==1


def test_confirmation_marker_persisted_even_when_export_is_not_attempted(store):
    payload=draft(store); first=store.confirm('central',payload,'Анна')
    saved=store.get_order(first)
    assert saved['payload']==store.get('draft:central')
    assert saved['payload']['confirmed_at']


def test_confirmation_retry_restores_frozen_rows_for_export(store):
    payload=draft(store); retry=copy.deepcopy(payload); first=store.confirm('central',payload,'Анна')
    retry['rows'][0]['packs']=999
    assert store.confirm('central',retry,'Анна')==first
    assert retry['rows']==store.get_order(first)['payload']['rows']


def test_legacy_order_schema_migrates_without_losing_history(tmp_path):
    path=tmp_path/'old.sqlite3'
    db=sqlite3.connect(path); db.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY,created TEXT,point TEXT,status TEXT,payload TEXT)')
    db.execute("INSERT INTO orders VALUES(1,'old','central','Подтверждена','{}')"); db.commit(); db.close()
    store=Store(path)
    assert store.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==1
    assert 'draft_id' in {r[1] for r in store.db.execute('PRAGMA table_info(orders)')}
    store.db.close()


def test_legacy_confirmed_draft_is_recognized_and_not_confirmed_again(store):
    payload=draft(store); payload.pop('draft_id')
    saved=copy.deepcopy(payload); saved.update(author='Анна',confirmed_at='2026-10-22T12:00:00')
    with store.db:
        store.put('draft:central',payload)
        store.db.execute('INSERT INTO orders(created,point,status,payload) VALUES(?,?,?,?)',('2026-10-22T12:00:00','central','Подтверждена',json.dumps(saved)))
    path=store.path; store.db.close(); store.__init__(path)
    migrated=store.get('draft:central')
    assert migrated['confirmed_order_id']==1
    assert store.confirm('central',migrated,'Анна')==1
    assert store.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==1


def test_default_date_follows_today_and_manual_date_is_explicit():
    old=date(2026,10,21); today=old+timedelta(days=1)
    assert calculation_day({'calculation_date':old.isoformat()},today)==today
    assert calculation_day({'date_mode':'today','calculation_date':old.isoformat()},today)==today
    assert calculation_day({'date_mode':'manual','calculation_date':old.isoformat()},today)==old


def test_rollover_invalidates_stock_confirmation_but_keeps_edits(store):
    payload=draft(store); payload['edits']={'dough':{'packs':0,'reason':'Проверка'}}; store.save_draft('central',payload)
    store.sync_day(date.today()+timedelta(days=1))
    with pytest.raises(DataError,match='Данные изменились'): store.confirm('central',payload,'Анна')
    assert store.get('draft:central')['edits']['dough']['packs']==0


def test_old_date_cannot_be_confirmed_as_today(store):
    payload=draft(store); payload['date']=(date.today()-timedelta(days=1)).isoformat()
    with pytest.raises(DataError,match='Дата расчёта'): store.confirm('central',payload,'Анна')
    assert store.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0]==0


def test_daily_projection_conserves_stock_and_tracks_unmet_demand():
    day=date(2026,10,22); days=[day+timedelta(days=i) for i in range(3)]
    inputs={'batches':[{'qty':5.,'expires':'9999-12-31'}],'arrivals':[{'date':days[1].isoformat(),'qty':2.}]}
    baseline=inventory_projection(inputs,days,[6.,4.,3.],days[1])
    picked=inventory_projection(inputs,days,[6.,4.,3.],days[1],8.)
    assert baseline['shortage']==6 and baseline['closing']==0
    assert picked['shortage']==1 and picked['shortage_before']==1 and picked['closing']==3
    for r in picked['points']:
        assert r['closing']==pytest.approx(r['opening']-r['excluded']+r['incoming']+r['ordered']-r['demand']+r['shortage'])
    assert inputs['batches'][0]['qty']==5


def test_projection_expires_only_unused_stock_on_explicit_date():
    day=date(2026,10,22); days=[day,day+timedelta(days=1)]
    inputs={'batches':[{'qty':10.,'expires':day.isoformat()}],'arrivals':[]}
    p=inventory_projection(inputs,days,[3.,4.],days[1])
    assert p['excluded']==7 and p['shortage']==4


def test_preview_uses_snapshot_and_does_not_change_draft(store):
    payload=draft(store); before=copy.deepcopy(payload); row=payload['rows'][0]
    zero=order_impact(payload,row,0); recommended=order_impact(payload,row,row['packs'])
    assert recommended['cost']==row['packs']*row['pack']*row['cost']
    assert recommended['shortage']<=zero['shortage']
    assert recommended['shortage_before']==zero['shortage_before']
    assert payload==before


def test_backup_includes_wal_orders_and_restore_keeps_recovery_copy(store,tmp_path):
    payload=draft(store); order_id=store.confirm('central',payload,'Анна')
    path=store.backup(tmp_path/'backup.sqlite3')
    store.correct_batch('b0',1,True,'После копии','Анна')
    recovery=store.restore(path)
    assert recovery.is_file()
    recovered=sqlite3.connect(recovery)
    try:
        raw=recovered.execute("SELECT value FROM state WHERE key='tables'").fetchone()[0]
        assert json.loads(raw)['batches'][0]['qty']==1
    finally: recovered.close()
    assert store.get('tables')['batches'][0]['qty']==14
    assert store.get_order(order_id)['payload']['author']=='Анна'
    assert store.get('draft:central')['revision']!=store.get('revision')
    assert store.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


@pytest.mark.parametrize('contents',[b'not sqlite',None])
def test_invalid_backup_cannot_change_working_data(store,tmp_path,contents):
    path=tmp_path/'invalid.sqlite3'
    if contents: path.write_bytes(contents)
    else:
        db=sqlite3.connect(path); db.execute('CREATE TABLE unrelated(value TEXT)'); db.close()
    before=store.get('tables')
    with pytest.raises(DataError): store.restore(path)
    assert store.get('tables')==before
    assert not (store.path.parent/'backups').exists()


def test_backup_cannot_overwrite_open_database(store):
    with pytest.raises(DataError): store.backup(store.path)
