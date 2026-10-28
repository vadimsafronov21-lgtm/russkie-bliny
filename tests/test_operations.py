import copy
from datetime import date,datetime,time,timedelta

import pytest
from openpyxl import load_workbook

from core import DataError,Store,calculate,demo_data,validate
from operations import (availability_events,daily_actions,export_pilot,mark_availability,
    missing_intervals,pilot_report,record_forecasts,simulate,work_session)


@pytest.fixture
def store(tmp_path):
    store=Store(tmp_path/'ops.sqlite3'); store.seed(); yield store; store.db.close()


def moment(day,hour=12):
    return datetime.combine(day,time(hour),datetime.now().astimezone().tzinfo).isoformat()


def test_what_if_preserves_data_drafts_and_confirmed_arrivals(store):
    tables=store.get('tables'); before=copy.deepcopy(tables)
    base,result=simulate(tables,'central',date.today(),{},delay=2,demand_change=20,dish='classic',extra=100)
    assert result['days']==base['days']+2 and result['scenario']
    assert sum(result['forecasts'][0]['daily'])==pytest.approx(result['forecasts'][0]['expected'])
    assert result['rows'][0]['demand']>base['rows'][0]['demand']
    assert result['rows'][0]['inventory_inputs']['arrivals']==base['rows'][0]['inventory_inputs']['arrivals']
    assert tables==before and store.get('tables')==before and store.get('draft:central') is None


def test_what_if_extra_order_consumes_shared_ingredients_once():
    tables=demo_data()
    base,result=simulate(tables,'central',date.today(),{},dish='classic',extra=100)
    dough=lambda payload: next(row['demand'] for row in payload['rows'] if row['id']=='dough')
    assert dough(result)-dough(base)==pytest.approx(12)
    base,result=simulate(tables,'central',date.today(),{},demand_change=-100)
    assert all(row['demand']==0 for row in result['rows'])


@pytest.mark.parametrize('kwargs',[{'delay':-1},{'delay':1.5},{'demand_change':-101},{'dish':'unknown','extra':1}])
def test_bad_scenario_rejected(kwargs):
    with pytest.raises(DataError): simulate(demo_data(),'central',date.today(),{},**kwargs)


def test_daily_actions_order_and_stale_draft(store):
    payload=calculate(store.get('tables'),'central',date.today(),{})
    store.save_draft('central',{'revision':-1,'date':date.today().isoformat(),'edits':{'dough':1}})
    tasks=daily_actions(store,'central',date.today(),payload)
    assert tasks[0]['priority']==0
    assert any(row['title']=='Пересчитать заявку' for row in tasks)
    assert any(row.get('ingredient')=='dough' for row in tasks)
    assert daily_actions(store,'central',date.today(),error='Нет графика поставок')[0]['route']=='settings'


def test_availability_is_explicit_idempotent_and_survives_restart(store):
    day=date.today()-timedelta(days=1)
    before=store.get('tables')
    assert not availability_events(store,'central')
    assert mark_availability(store,'central','classic',0,'Оператор','Закончилась сметана',moment(day,10))
    assert not mark_availability(store,'central','classic',0,'Оператор',at=moment(day,11))
    assert mark_availability(store,'central','classic',1,'Оператор',at=moment(day,13))
    assert store.get('tables')==before
    second=Store(store.path)
    try:
        events=availability_events(second,'central','classic')
        assert len(events)==2 and events[0]['reason']=='Закончилась сметана'
        report=pilot_report(second,'central',day,day)
        assert report['absence'][0]['minutes']==180
        assert not availability_events(second,'other')
    finally: second.db.close()


def test_availability_clips_cross_midnight_and_unknown_period(store):
    yesterday=date.today()-timedelta(days=1)
    mark_availability(store,'central','classic',0,'Тест',at=moment(yesterday-timedelta(days=1),22))
    mark_availability(store,'central','classic',1,'Тест',at=moment(yesterday,2))
    report=pilot_report(store,'central',yesterday,yesterday)
    assert report['absence'][0]['minutes']==120
    assert not missing_intervals([],datetime.fromisoformat(moment(yesterday,0)),datetime.fromisoformat(moment(yesterday,5)))


def test_availability_does_not_mix_demo_with_real(store):
    mark_availability(store,'central','classic',0,'Тест')
    with store.db: store.put('demo',False)
    assert availability_events(store,'central')==[]
    with pytest.raises(DataError): mark_availability(store,'central','unknown',0,'Тест')
    with pytest.raises(DataError): mark_availability(store,'central','classic',0,'Тест',at=moment(date.today()+timedelta(days=1)))


def test_future_forecast_locked_once_and_assessed_without_leakage(store):
    issued_day=date.today()-timedelta(days=2); target=issued_day+timedelta(days=1)
    payload=dict(point='central',date=issued_day.isoformat(),forecasts=[{'id':'classic','daily':[999,10,20],'method':'Тест'}])
    assert record_forecasts(store,'central',payload,issued=moment(issued_day))==2
    payload['forecasts'][0]['daily']=[1,1,1]
    assert record_forecasts(store,'central',payload,issued=moment(issued_day))==0
    tables=store.get('tables')
    row=next(row for row in tables['sales'] if row['date']==target.isoformat() and row['dish']=='classic')
    row.update(qty=5,available=1)
    with store.db: store.put('tables',tables)
    report=pilot_report(store,'central',issued_day,date.today())
    assert report['forecast_count']==1 and report['mae']==5 and report['wape']==100
    assert report['skipped']=={'Нет закрытого факта':1}
    assert report['forecasts'][0]['expected']==10
    mark_availability(store,'central','classic',0,'Тест',at=moment(target,10))
    mark_availability(store,'central','classic',1,'Тест',at=moment(target,11))
    assert pilot_report(store,'central',target,target)['forecast_count']==0


def test_no_measurements_are_not_zeros_and_zero_actual_has_no_wape(store):
    issued_day=date.today()-timedelta(days=2); target=issued_day+timedelta(days=1)
    report=pilot_report(store,'central',target,target)
    assert report['mae'] is None and report['edit_share'] is None and report['median_minutes'] is None
    record_forecasts(store,'central',dict(point='central',date=issued_day.isoformat(),forecasts=[{'id':'classic','daily':[5,10],'method':'Тест'}]),issued=moment(issued_day))
    tables=store.get('tables')
    next(row for row in tables['sales'] if row['date']==target.isoformat() and row['dish']=='classic').update(qty=0,available=1)
    with store.db: store.put('tables',tables)
    report=pilot_report(store,'central',target,target)
    assert report['mae']==10 and report['wape'] is None


def test_pilot_rejects_scenario_and_mismatched_point(store):
    with pytest.raises(DataError): record_forecasts(store,'central',{'scenario':True})
    with pytest.raises(DataError): record_forecasts(store,'central',{'point':'other','date':date.today().isoformat()})
    with pytest.raises(DataError): pilot_report(store,'central',date.today(),date.today()-timedelta(days=1))


def test_work_duration_and_export_missing_values(store,tmp_path):
    day=date.today()-timedelta(days=1)
    first=work_session(store,'central','Оператор',at=moment(day,10))
    assert work_session(store,'central','Оператор',at=moment(day,10))==first
    work_session(store,'central','Оператор',finish=True,at=moment(day,11))
    report=pilot_report(store,'central',day,day)
    assert report['median_minutes']==60 and report['session_count']==1
    path=tmp_path/'pilot.xlsx'; export_pilot(path,report)
    wb=load_workbook(path)
    assert wb['Пилот']['B1'].value=='ДЕМО'
    assert any(row[1].value=='Нет измерений' for row in wb['Пилот'] if len(row)>1)
    wb.close()


def test_recipe_version_has_one_effective_date():
    tables=demo_data(); tables['recipes'][1]['valid_from']=(date.today()-timedelta(days=1)).isoformat()
    with pytest.raises(DataError,match='Одна версия'): validate(tables)


def test_pilot_counts_confirmed_manual_edits_and_reasons(store):
    payload=calculate(store.get('tables'),'central',date.today(),{})
    payload.update(revision=store.get('revision'),demo=True,stock_confirmed=True,
                   stock_confirmed_revision=store.get('revision'),stock_confirmed_on=date.today().isoformat())
    payload['edits']={'dough':{'packs':2,'reason':'Большой заказ'}}
    store.save_draft('central',payload); store.confirm('central',payload,'Оператор')
    report=pilot_report(store,'central',date.today(),date.today())
    assert report['order_rows']==7 and report['edited_rows']==1
    assert report['edit_share']==pytest.approx(100/7)
    assert report['reasons']=={'Большой заказ':1}
    with store.db: store.put('demo',False)
    assert pilot_report(store,'central',date.today(),date.today())['order_rows']==0
