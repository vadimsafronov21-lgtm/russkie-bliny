import copy
import json
from datetime import date
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from core import DataError, Store, calculate
from dalion_exchange import (DalionDemoAdapter, DemoServer, DemoWorkspace, MAX_BYTES,
                             demo_payload, parse_snapshot)


def encode(payload):
    return json.dumps(payload, ensure_ascii=False).encode('utf-8')


def test_http_snapshot_maps_into_forecast_and_order():
    with DemoServer() as server:
        snapshot = DalionDemoAdapter().fetch(server.endpoint)
        assert DalionDemoAdapter().fetch(server.endpoint).digest == snapshot.digest
    assert all(row['date'] < date.today().isoformat() for row in snapshot.tables['sales'])
    assert any(row['qty'] == 0 for row in snapshot.tables['sales'])
    result = calculate(snapshot.tables, 'central', date.today(), {})
    assert len(result['forecasts']) == 5 and len(result['rows']) == 7
    assert not result['errors']
    assert all(row['use_before'] == '' for row in snapshot.tables['batches'])


@pytest.mark.parametrize('change,match', [
    (lambda p: p.update(dataset='REAL'), 'синтетические'),
    (lambda p: p.update(source='DALION'), 'синтетические'),
    (lambda p: p.update(protocol='other'), 'протокол'),
    (lambda p: p.update(generated_at='yesterday'), 'время'),
    (lambda p: p['data'].pop('Партии'), 'восьми'),
    (lambda p: p['data'].update(Продажи={}), 'список'),
    (lambda p: p['data']['Продажи'][0].pop('Количество'), 'состав полей'),
    (lambda p: p['data']['Продажи'][0].update(Количество=None), 'не заполнено'),
    (lambda p: p['data']['Продажи'][0].update(Количество=-1), 'число'),
    (lambda p: p['data']['Продажи'][0].update(Количество={}), 'простые'),
    (lambda p: p['data']['Продажи'][0].update(СменаЗакрыта=0), 'незакрытая'),
    (lambda p: p['data']['Продажи'][0].update(Дата=date.today().isoformat()), 'сегодняшнего'),
    (lambda p: p['data']['Продажи'][0].update(Блюдо='unknown'), 'не сопоставлен'),
    (lambda p: p['data']['Партии'][0].update(Единица='кг'), 'единица не совпадает'),
])
def test_invalid_snapshot_rejected_before_database_creation(tmp_path, change, match):
    payload = demo_payload(); change(payload)
    with pytest.raises(DataError, match=match):
        parse_snapshot(encode(payload))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('raw', [b'not json', b'\xff', b'[]', b'x' * (MAX_BYTES + 1)],
                         ids=['not-json', 'bad-encoding', 'array', 'too-large'])
def test_bad_json_and_size_limit(raw):
    with pytest.raises(DataError):
        parse_snapshot(raw)


@pytest.mark.parametrize('endpoint', [
    'https://127.0.0.1:8000/demo/v1/snapshot',
    'http://example.com:8000/demo/v1/snapshot',
    'http://localhost:8000/demo/v1/snapshot',
    'http://127.0.0.1:8000/real',
    'http://user:secret@127.0.0.1:8000/demo/v1/snapshot',
])
def test_demo_cannot_connect_to_external_1c(endpoint):
    with pytest.raises(DataError, match='локальный'):
        DalionDemoAdapter().fetch(endpoint)


def test_outage_retry_and_get_only():
    with DemoServer() as server:
        server.offline = True
        with pytest.raises(DataError, match='недоступен'):
            DalionDemoAdapter().fetch(server.endpoint)
        server.offline = False
        assert DalionDemoAdapter().fetch(server.endpoint).tables['sales']
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(server.endpoint, data=b'{}', method='POST'), timeout=2)
        assert exc.value.code == 501
    with pytest.raises(DataError, match='недоступен'):
        DalionDemoAdapter().fetch(server.endpoint)


def test_isolated_import_preserves_edits_history_and_real_database(tmp_path):
    real = Store(tmp_path / 'real.sqlite3'); real.seed()
    with real.db:
        real.put('demo', False)
        real.put('production_marker', 'keep')
    real_before = real.db.iterdump()
    real_before = list(real_before)
    workspace = DemoWorkspace(tmp_path)
    try:
        snapshot = parse_snapshot(encode(demo_payload()))
        workspace.import_snapshot(snapshot)
        store = workspace.store
        assert store.get('demo') is True
        assert store.get('dalion_demo_source')['digest'] == snapshot.digest
        assert workspace.directory != tmp_path
        store.correct_batch('b0', 10, True, 'Проверка сохранения сверки', 'Тест')
        result = calculate(store.get('tables'), 'central', date.today(), {})
        result.update(revision=store.get('revision'), stock_confirmed=True,
                      stock_confirmed_revision=store.get('revision'), stock_confirmed_on=date.today().isoformat())
        result['edits'] = {'dough': {'packs': 2, 'reason': 'Демо ручной правки'}}
        store.save_draft('central', result)
        order_id = store.confirm('central', result, 'Тест')
        before = list(store.db.iterdump())
        assert 'уже загружен' in workspace.import_snapshot(snapshot)
        assert list(store.db.iterdump()) == before
        assert store.confirm('central', result, 'Тест') == order_id
        assert list(real.db.iterdump()) == real_before
    finally:
        workspace.close(); real.db.close()


def test_mutated_preview_cannot_be_imported(tmp_path):
    snapshot = parse_snapshot(encode(demo_payload()))
    snapshot.tables['batches'][0]['qty'] = 999
    workspace = DemoWorkspace(tmp_path)
    with pytest.raises(DataError, match='изменён'):
        workspace.import_snapshot(snapshot)
    assert workspace.store is None
    assert not (workspace.directory / 'data.sqlite3').exists()


def test_invalid_replacement_preserves_existing_demo(tmp_path):
    workspace = DemoWorkspace(tmp_path)
    try:
        snapshot = parse_snapshot(encode(demo_payload()))
        workspace.import_snapshot(snapshot)
        before = list(workspace.store.db.iterdump())
        invalid = copy.deepcopy(snapshot)
        payload = json.loads(invalid.raw); payload['dataset'] = 'REAL'
        invalid.raw = encode(payload)
        with pytest.raises(DataError):
            workspace.import_snapshot(invalid)
        assert list(workspace.store.db.iterdump()) == before
    finally:
        workspace.close()
