"""Daily work, explicit availability records, scenarios and prospective pilot data."""
from __future__ import annotations

import copy
import json
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from core import DataError, calculate, flag, now, number


def ensure_operations(store):
    schema = '''
        CREATE TABLE IF NOT EXISTS availability_events(
            id INTEGER PRIMARY KEY, point TEXT, dish TEXT, at TEXT, available INTEGER,
            author TEXT, reason TEXT, demo INTEGER);
        CREATE TABLE IF NOT EXISTS pilot_forecasts(
            point TEXT, dish TEXT, target TEXT, expected REAL, issued TEXT, method TEXT,
            demo INTEGER, PRIMARY KEY(point,dish,target,demo));
        CREATE TABLE IF NOT EXISTS work_sessions(
            id INTEGER PRIMARY KEY, point TEXT, started TEXT, ended TEXT, author TEXT, demo INTEGER);
    '''
    for statement in schema.split(';'):
        if statement.strip(): store.db.execute(statement)


def timestamp(value=None):
    result = datetime.fromisoformat(value) if value is not None else datetime.now().astimezone()
    if result.tzinfo is None:
        raise DataError('Время должно содержать часовой пояс.')
    return result


def availability_events(store, point, dish=None):
    ensure_operations(store)
    rows = store.db.execute('SELECT id,dish,at,available,author,reason FROM availability_events '
                            'WHERE point=? AND demo=? ORDER BY at,id',
                            (str(point), int(bool(store.get('demo'))))).fetchall()
    result = [dict(zip(('id','dish','at','available','author','reason'), row)) for row in rows
              if dish is None or row[1] == str(dish)]
    return sorted(result,key=lambda row:(timestamp(row['at']),row['id']))


def mark_availability(store, point, dish, available, author, reason='', at=None):
    tables = store.get('tables', {})
    if str(point) not in {str(row['id']) for row in tables.get('points', [])}:
        raise DataError('Точка не сопоставлена.')
    if str(dish) not in {str(row['id']) for row in tables.get('items', []) if row['kind']=='dish'}:
        raise DataError('Блюдо не сопоставлено.')
    value = int(flag(available, 'Наличие'))
    moment = timestamp(at)
    if moment > datetime.now().astimezone():
        raise DataError('Отметка наличия не может быть из будущего.')
    prior = availability_events(store, point, dish)
    if prior and moment < timestamp(prior[-1]['at']):
        raise DataError('Отметка раньше последней записи. История не изменена.')
    if prior and prior[-1]['available'] == value:
        return False
    with store.db:
        store.db.execute('INSERT INTO availability_events(point,dish,at,available,author,reason,demo) VALUES(?,?,?,?,?,?,?)',
                         (str(point),str(dish),moment.isoformat(),value,author,reason.strip(),int(bool(store.get('demo')))))
        store.log('Наличие блюда',prior[-1] if prior else None,
                  {'point':str(point),'dish':str(dish),'available':value,'at':moment.isoformat()},
                  reason.strip() or ('Снова доступно' if value else 'Блюдо закончилось'),author)
    return True


def missing_intervals(events, start, end):
    """Only explicitly observed absence, clipped to [start, end). Unknown is unknown."""
    result = []
    since = None
    for event in events:
        moment = timestamp(event['at'])
        if moment >= end:
            break
        if not event['available']:
            if since is None:
                since = moment
        elif since is not None:
            left, right = max(start, since), min(end, moment)
            if right > left:
                result.append((left, right))
            since = None
    if since is not None and end > max(start, since):
        result.append((max(start, since), end))
    return result


def daily_actions(store, point, day, snapshot=None, error=None):
    tables = store.get('tables', {})
    tasks = []
    def add(priority, title, detail, route, ingredient=None):
        tasks.append(dict(priority=priority,title=title,detail=detail,route=route,ingredient=ingredient))
    if error:
        add(0,'Восстановить расчёт',error,'settings' if 'постав' in error.lower() else 'imports')
    for message in (snapshot or {}).get('errors', []):
        add(0,'Проверить исходные данные',message,'imports')
    last = (snapshot or {}).get('last_closed')
    if not last or last < (day-timedelta(days=1)).isoformat():
        add(1,'Получить закрытые продажи','Нет подтверждённых продаж за предыдущий день.','imports')
    for row in (snapshot or {}).get('rows', []):
        if row['checked_at'][:10] != day.isoformat():
            add(1,'Сверить: '+row['name'],'Остаток не сверен на дату расчёта.','inventory',row['id'])
        if row['shortage_before'] > 1e-8:
            add(0,'Проверить нехватку: '+row['name'],
                f'До поставки не покрыто {row["shortage_before"]:.2f} {row["unit"]}.','inventory',row['id'])
    latest = {}
    for event in availability_events(store, point):
        latest[event['dish']] = event
    absent = sum(not row['available'] for row in latest.values())
    if absent:
        add(1,'Проверить отсутствие блюд',f'Отмечено отсутствие: {absent}.','availability')
    draft = store.get('draft:'+str(point))
    if not draft or not draft.get('confirmed_order_id'):
        stale = draft and (draft.get('revision') != store.get('revision') or draft.get('date') != day.isoformat())
        add(1 if stale else 2,'Пересчитать заявку' if stale else 'Подготовить заявку',
            'Ручные количества сохраняются при пересчёте.' if draft else 'Проверьте рекомендации и подтвердите сверку.','order')
    return sorted(tasks, key=lambda row: row['priority'])


def simulate(tables, point, day, settings, delay=0, demand_change=0, dish=None, extra=0):
    delay_value = number(delay, 'Задержка')
    if delay_value != int(delay_value) or delay_value > 30:
        raise DataError('Задержка: целое от 0 до 30 дней.')
    change = number(demand_change, 'Изменение спроса', nonnegative=False)
    if not -100 <= change <= 300:
        raise DataError('Изменение спроса: от −100 до +300%.')
    extra = number(extra, 'Разовый заказ')
    variant = copy.deepcopy(tables)
    for row in variant.get('schedules', []):
        if str(row['point']) == str(point):
            row['next_delivery'] = (date.fromisoformat(row['next_delivery'])+timedelta(days=int(delay_value))).isoformat()
    baseline = calculate(tables, str(point), day, settings)
    scenario = calculate(variant, str(point), day, settings, demand_multiplier=1+change/100,
                         extra_orders={str(dish):extra} if extra else {})
    scenario['scenario'] = True
    return baseline, scenario


def record_forecasts(store, point, payload, issued=None):
    ensure_operations(store)
    moment = timestamp(issued)
    if payload.get('scenario'):
        raise DataError('Сценарий нельзя сохранять как рабочий прогноз пилота.')
    if str(payload.get('point')) != str(point) or payload.get('date') != moment.date().isoformat():
        raise DataError('Сохраняется только сегодняшний прогноз выбранной точки.')
    if moment > datetime.now().astimezone():
        raise DataError('Дата сохранения прогноза не может быть из будущего.')
    inserted = 0
    with store.db:
        for forecast in payload['forecasts']:
            for index, value in enumerate(forecast['daily']):
                target = date.fromisoformat(payload['date'])+timedelta(days=index)
                # Same-day forecasts cannot be independently assessed from daily sales.
                if target <= moment.date():
                    continue
                cursor = store.db.execute('INSERT OR IGNORE INTO pilot_forecasts VALUES(?,?,?,?,?,?,?)',
                    (str(point),str(forecast['id']),target.isoformat(),number(value,'Прогноз'),moment.isoformat(),
                     forecast['method'],int(bool(store.get('demo')))))
                inserted += cursor.rowcount
        if inserted:
            store.log('Фиксация прогноза пилота',None,{'point':str(point),'rows':inserted},
                      'Первый прогноз на будущую дату; повтор не перезаписывает значения','Приложение')
    return inserted


def work_session(store, point, author, finish=False, at=None):
    ensure_operations(store)
    if str(point) not in {str(row['id']) for row in store.get('tables',{}).get('points',[])}:
        raise DataError('Сначала настройте точку.')
    moment = timestamp(at)
    if moment > datetime.now().astimezone(): raise DataError('Замер не может быть из будущего.')
    demo = int(bool(store.get('demo')))
    row = store.db.execute('SELECT id,started FROM work_sessions WHERE point=? AND demo=? AND ended IS NULL',
                           (str(point),demo)).fetchone()
    if finish:
        if not row:
            raise DataError('Нет начатого замера времени заявки.')
        if moment < timestamp(row[1]):
            raise DataError('Время окончания раньше начала.')
        with store.db:
            store.db.execute('UPDATE work_sessions SET ended=? WHERE id=?',(moment.isoformat(),row[0]))
        return row[0]
    if row:
        return row[0]
    with store.db:
        return store.db.execute('INSERT INTO work_sessions(point,started,author,demo) VALUES(?,?,?,?)',
                                (str(point),moment.isoformat(),author,demo)).lastrowid


def pilot_report(store, point, start, end, as_of=None):
    """Inclusive dates, explicit missing metrics, no inferred savings or lost sales."""
    ensure_operations(store)
    moment = timestamp(as_of)
    if start > end or end > moment.date():
        raise DataError('Период должен быть по возрастанию и не позже текущей даты.')
    zone = moment.tzinfo
    left = datetime.combine(start, time.min, zone)
    right = min(moment, datetime.combine(end+timedelta(days=1),time.min,zone))
    tables = store.get('tables', {})
    demo = int(bool(store.get('demo')))
    items = {str(row['id']):row for row in tables.get('items', [])}
    events = availability_events(store, point)
    by_dish = defaultdict(list)
    for event in events:
        by_dish[event['dish']].append(event)
    absence = []
    for dish, rows in by_dish.items():
        intervals = missing_intervals(rows,left,right)
        if intervals:
            absence.append(dict(dish=dish,name=items.get(dish,{}).get('name',dish),
                                minutes=sum((b-a).total_seconds()/60 for a,b in intervals),intervals=len(intervals)))
    actual = {(str(row['dish']),str(row['date'])):row for row in tables.get('sales', [])
              if str(row['point'])==str(point) and flag(row['closed'],'closed') and str(row['date'])<moment.date().isoformat()}
    errors = []; details = []; skipped = Counter()
    forecasts = store.db.execute('SELECT dish,target,expected,issued,method FROM pilot_forecasts WHERE point=? AND demo=? '
                                 'AND target>=? AND target<=? ORDER BY target,dish',
                                 (str(point),demo,start.isoformat(),end.isoformat())).fetchall()
    for dish, target, expected, issued, method in forecasts:
        row = actual.get((dish,target))
        day_left = datetime.combine(date.fromisoformat(target),time.min,zone)
        if row is None:
            skipped['Нет закрытого факта'] += 1; continue
        if not flag(row['available'],'available') or missing_intervals(by_dish[dish],day_left,day_left+timedelta(days=1)):
            skipped['Было отсутствие блюда'] += 1; continue
        error = abs(expected-float(row['qty'])); errors.append((error,float(row['qty'])))
        details.append(dict(date=target,dish=items.get(dish,{}).get('name',dish),expected=expected,
                            actual=float(row['qty']),error=error,issued=issued,method=method))
    writeoffs = defaultdict(float)
    cost = 0.; cost_complete = True
    for row in tables.get('movements', []):
        if str(row['point'])==str(point) and row['kind']=='writeoff' and start.isoformat()<=str(row['date'])<=end.isoformat():
            writeoffs[(str(row['ingredient']),row['unit'])] += float(row['qty'])
            item = items.get(str(row['ingredient']))
            if item:
                cost += float(row['qty'])*float(item['cost'])
            else:
                cost_complete = False
    order_rows = 0; edited = 0; reasons = Counter()
    for created, raw in store.db.execute('SELECT created,payload FROM orders WHERE point=?',(str(point),)):
        payload = json.loads(raw)
        if bool(payload.get('demo'))!=bool(demo) or not start.isoformat()<=created[:10]<=end.isoformat():
            continue
        ids = {str(row['id']) for row in payload['rows']}; order_rows += len(ids)
        for ingredient, edit in payload.get('edits',{}).items():
            if str(ingredient) in ids:
                edited += 1; reasons[edit.get('reason') or 'Причина не сохранена'] += 1
    sessions = []
    for started, ended in store.db.execute('SELECT started,ended FROM work_sessions WHERE point=? AND demo=? AND ended IS NOT NULL',
                                         (str(point),demo)):
        if start.isoformat()<=started[:10]<=end.isoformat():
            sessions.append((timestamp(ended)-timestamp(started)).total_seconds())
    total_actual = sum(value for _,value in errors)
    return dict(point=str(point),start=start.isoformat(),end=end.isoformat(),demo=bool(demo),
        forecast_count=len(errors),mae=statistics.mean(error for error,_ in errors) if errors else None,
        wape=sum(error for error,_ in errors)/total_actual*100 if total_actual else None,
        forecasts=details,skipped=dict(skipped),absence=absence,availability_recorded=bool(events),
        writeoffs=[dict(name=items.get(ingredient,{}).get('name',ingredient),unit=unit,qty=qty) for (ingredient,unit),qty in writeoffs.items()],
        writeoff_cost=cost if cost_complete and writeoffs else None,order_rows=order_rows,edited_rows=edited,
        edit_share=edited/order_rows*100 if order_rows else None,reasons=dict(reasons),
        session_count=len(sessions),median_minutes=statistics.median(sessions)/60 if sessions else None,
        note='Отсутствие: только зарегистрированные интервалы; рабочие часы и потерянные продажи не оцениваются. '
             'Списания оценены по текущей себестоимости. Отсутствие записей не означает ноль. Экономия не доказана.')


def export_pilot(path, report):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active; ws.title='Пилот'
    ws.append(['Русские блины · пилот','ДЕМО' if report['demo'] else 'Данные точки'])
    for key,label in [('point','Точка'),('start','С'),('end','По'),('forecast_count','Проверенных прогнозов'),
                      ('mae','Средняя абсолютная ошибка, порций'),('wape','WAPE, %'),
                      ('edit_share','Изменённых строк заявки, %'),('median_minutes','Медиана подготовки заявки, мин'),
                      ('writeoff_cost','Списания по текущей себестоимости, ₽')]:
        ws.append([label,report[key] if report[key] is not None else 'Нет измерений'])
    ws.append([report['note']])
    for name, rows, fields in [('Прогнозы',report['forecasts'],['date','dish','expected','actual','error','issued','method']),
                               ('Отсутствие',report['absence'],['name','minutes','intervals']),
                               ('Списания',report['writeoffs'],['name','unit','qty'])]:
        labels={'date':'Дата','dish':'Блюдо','expected':'Прогноз, порций','actual':'Факт, порций','error':'Ошибка, порций',
                'issued':'Прогноз сохранён','method':'Метод','name':'Позиция','minutes':'Отсутствие, минут',
                'intervals':'Интервалов','unit':'Единица','qty':'Количество'}
        sheet=wb.create_sheet(name); sheet.append([labels[field] for field in fields])
        for row in rows: sheet.append([row.get(field) for field in fields])
        sheet.freeze_panes='A2'
    for sheet in wb:
        for col in sheet.columns: sheet.column_dimensions[col[0].column_letter].width=28
    wb.save(path)
