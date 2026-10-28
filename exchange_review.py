"""Review snapshot changes and reconcile local edits before an atomic import."""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from core import DataError, FileAdapter, LABELS, SCHEMAS, now, validate

KEYS = {'sales':('date','point','dish'),'recipes':('dish','ingredient','version','valid_from'),'schedules':('point',)}


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def signature(store):
    return canonical([store.get('tables',{}),store.get('exchange_base',{}),store.get('demo'),store.get('revision',0)])


def indexed(kind, rows):
    fields = KEYS.get(kind,('id',))
    return {tuple(str(row[field]) for field in fields):row for row in rows}


@dataclass
class ImportPlan:
    incoming: dict
    is_demo: bool
    source: str
    digest: str
    before: str
    switching: bool
    merged: dict
    conflicts: list = field(default_factory=list)
    changes: list = field(default_factory=list)
    duplicate: bool = False
    seal: str = ''


def prepare_import(store, tables, is_demo, source, digest):
    incoming = copy.deepcopy(tables)
    switching = bool(store.get('seeded_demo')) or (bool(store.get('tables')) and bool(store.get('demo'))!=bool(is_demo))
    existing = {} if switching else store.get('tables',{})
    if switching and 'points' not in incoming:
        raise DataError('Первый импорт должен содержать points; рекомендуется полный XLSX.')
    validate(incoming,existing)
    base = {} if switching else store.get('exchange_base',{})
    plan = ImportPlan(incoming,bool(is_demo),source,digest,signature(store),switching,copy.deepcopy(existing))
    plan.duplicate = bool(store.db.execute('SELECT 1 FROM imports WHERE hash=?',(digest,)).fetchone())
    for kind, rows in incoming.items():
        local = indexed(kind,existing.get(kind,[])); remote = indexed(kind,rows)
        original = indexed(kind,base.get(kind,[]))
        combined = {}
        for key in sorted(set(local)|set(remote)|set(original)):
            current, incoming_row, previous = local.get(key),remote.get(key),original.get(key)
            local_changed = current != previous
            # If there is no baseline, differing existing rows require a decision.
            if kind not in base and not switching:
                local_changed = current is not None
            remote_changed = incoming_row != previous
            chosen = incoming_row
            conflict = local_changed and remote_changed and current != incoming_row
            if conflict:
                chosen = current
                plan.conflicts.append(dict(kind=kind,key=key,local=current,remote=incoming_row))
            elif local_changed and not remote_changed:
                chosen = current
            if chosen is not None:
                combined[key] = copy.deepcopy(chosen)
            if current != incoming_row:
                plan.changes.append(dict(kind=kind,key=key,local=current,remote=incoming_row,
                    action='Конфликт' if conflict else 'Добавление' if current is None else 'Удаление' if incoming_row is None else 'Изменение'))
        plan.merged[kind] = list(combined.values())
    plan.seal = canonical([plan.incoming,plan.merged,plan.conflicts,plan.is_demo,plan.digest,plan.switching,plan.before])
    return plan


def prepare_file_import(store, path, kind=None):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    adapter = FileAdapter(); tables = adapter.read(path,kind)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
        raise DataError('Файл изменился во время чтения. Получите предпросмотр заново.')
    return prepare_import(store,tables,adapter.is_demo,path.name,digest)


def apply_import(store, plan, choices=None, reason='', author='Продавец'):
    choices = choices or {}
    if canonical([plan.incoming,plan.merged,plan.conflicts,plan.is_demo,plan.digest,plan.switching,plan.before]) != plan.seal:
        raise DataError('Предпросмотр изменён. Подготовьте его заново.')
    store.db.execute('BEGIN IMMEDIATE')
    try:
        if signature(store)!=plan.before:
            raise DataError('Данные изменились после предпросмотра. Проверьте новый снимок.')
        if plan.duplicate:
            store.db.rollback()
            return 'Этот снимок уже загружен. Правки сохранены.'
        merged = copy.deepcopy(plan.merged)
        if plan.conflicts and not reason.strip():
            raise DataError('Укажите причину решения конфликтов.')
        decisions = []
        for index, conflict in enumerate(plan.conflicts):
            choice = choices.get(index)
            if choice not in ('local','remote'):
                raise DataError('Выберите решение для каждого конфликта.')
            kind,key = conflict['kind'],conflict['key']
            rows = indexed(kind,merged[kind])
            chosen = conflict[choice]
            if chosen is None:
                rows.pop(key,None)
            else:
                rows[key] = copy.deepcopy(chosen)
            merged[kind] = list(rows.values())
            decisions.append({**conflict,'choice':choice})
        validate(merged)
        old_base = {} if plan.switching else store.get('exchange_base',{})
        store.put('tables',merged)
        store.put('exchange_base',{**old_base,**plan.incoming})
        store.put('demo',plan.is_demo); store.put('seeded_demo',False)
        store.put('revision',store.get('revision',0)+1); store.put('import_time',now())
        if plan.switching:
            store.db.execute("DELETE FROM state WHERE key LIKE 'draft:%'")
        store.db.execute('INSERT INTO imports VALUES(?,?,?)',(plan.digest,plan.source,now()))
        store.log('Обмен с предпросмотром',{'source':plan.source},
                  {'counts':{kind:len(rows) for kind,rows in plan.incoming.items()},'decisions':decisions},
                  reason.strip() or 'Снимок проверен до применения',author)
        store.db.commit()
    except Exception:
        store.db.rollback(); raise
    return 'Снимок применён. Конфликтов разобрано: '+str(len(plan.conflicts))


def row_description(row):
    if row is None:
        return 'Нет строки'
    labels={'name':'Название','qty':'Количество','unit':'Ед.','checked_at':'Сверка','usable':'Пригодность',
            'price':'Цена','cost':'Себестоимость','pack':'Упаковка','target':'Цель','fallback':'Резерв',
            'date':'Дата','next_delivery':'Поставка','interval_days':'Интервал','amount':'Расход',
            'available':'Наличие','closed':'Смена закрыта','arrival':'Приход','confirmed':'Подтверждено',
            'reason':'Причина','use_before':'Использовать до','valid_from':'Действует с','version':'Версия'}
    return '\n'.join(f'{labels[key]}: {value if value not in (None, "") else "—"}' for key,value in row.items() if key in labels)
