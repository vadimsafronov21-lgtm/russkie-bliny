from datetime import date,timedelta
import pytest
from core import demo_data,calculate
from analytics_data import make_analytics,completed_months

DAY=date(2026,10,21)

def test_missing_days_are_gaps_not_zero():
    data=demo_data(DAY); missing=(DAY-timedelta(days=2)).isoformat()
    data['sales']=[r for r in data['sales'] if not (r['dish']=='classic' and r['date']==missing)]
    p=make_analytics(data,'central','classic',DAY,14)
    assert p['observed']==13
    assert next(r for r in p['actual'] if r['date']==missing)['value'] is None
    assert p['average']==pytest.approx(p['total']/13)
    assert p['delta'] is None

def test_future_forecast_is_separate_from_measured_sales():
    data=demo_data(DAY); snapshot=calculate(data,'central',DAY,{})
    original=make_analytics(data,'central','classic',DAY,30,snapshot)
    data['sales'].append(dict(data['sales'][0],date=DAY.isoformat(),qty=99999))
    actual=make_analytics(data,'central','classic',DAY,30,snapshot)
    assert actual['total']==original['total']
    assert all(date.fromisoformat(p['date'])<DAY for p in actual['actual'])
    assert all(date.fromisoformat(p['date'])>=DAY and p['kind']=='forecast' for p in actual['future'])
    assert sum(p['value'] for p in actual['future'])==pytest.approx(actual['forecast']['expected'])

def test_closed_shift_point_and_dish_filters():
    data=demo_data(DAY); original=make_analytics(data,'central','classic',DAY,14)
    row=dict(data['sales'][-5]); row['qty']=99999
    data['sales'] += [dict(row,closed=0),dict(row,point='other'),dict(row,dish='other')]
    result=make_analytics(data,'central','classic',DAY,14)
    assert result['total']==original['total']
    assert result['composition_total']==original['composition_total']+99999

def test_zero_previous_period_does_not_produce_infinite_growth():
    data=demo_data(DAY)
    for row in data['sales']:
        if DAY-timedelta(days=28)<=date.fromisoformat(row['date'])<DAY-timedelta(days=14): row['qty']=0
    assert make_analytics(data,'central','classic',DAY,14)['delta'] is None

def test_stockouts_keep_actual_sales_and_unknown_demand():
    data=demo_data(DAY); row=next(r for r in data['sales'] if r['dish']=='classic' and r['date']==(DAY-timedelta(days=1)).isoformat()); row.update(qty=0,available=0)
    last=make_analytics(data,'central','classic',DAY,14)['actual'][-1]
    assert last['value']==0 and last['available'] is False

def test_stock_coverage_uses_ratios_not_mixed_unit_totals():
    data=demo_data(DAY); snapshot=calculate(data,'central',DAY,{})
    rows=make_analytics(data,'central','classic',DAY,30,snapshot)['coverage']
    for r in rows: assert r['percent']==pytest.approx((r['effective']+r['incoming'])/r['demand']*100)
    assert {r['unit'] for r in rows}=={'л','кг'}
    snapshot['rows'][0]['demand']=0
    updated=make_analytics(data,'central','classic',DAY,30,snapshot)['coverage']
    assert next(r for r in updated if r['id']==snapshot['rows'][0]['id'])['percent'] is None

def test_month_comparison_uses_complete_calendar_months():
    cutoff=date(2024,4,15); data=demo_data(cutoff)
    p=make_analytics(data,'central','classic',cutoff,30,monthly=True)
    assert completed_months(cutoff)==[(2024,1),(2024,2),(2024,3)]
    assert [len(s['points']) for s in p['months']]==[31,29,31]
    assert p['start']=='2024-01-01' and p['end']=='2024-04-01' and p['length']==91
    assert sum(r['value'] for r in p['composition'])==p['composition_total']

def test_no_observations_and_measured_zero_sales_are_distinct():
    data=demo_data(DAY)
    for r in data['sales']: r['qty']=0
    measured=make_analytics(data,'central','classic',DAY,14)
    assert measured['total']==0 and measured['composition_total']==0 and measured['composition_observed']>0
    data['sales']=[]
    missing=make_analytics(data,'central','classic',DAY,14)
    assert missing['average'] is None and missing['composition_observed']==0
