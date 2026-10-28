"""Demo exchange contract, not an API or metadata description of real DALION."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import threading
from dataclasses import dataclass
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from core import AccountingAdapter, DataError, SCHEMAS, Store, demo_data, now, validate, write_templates

PROTOCOL = 'russkie-bliny.dalion-demo/1'
MAX_BYTES = 4 * 1024 * 1024

# An invented, explicit mapping for this demo. Real 1C metadata must be inspected.
MAPPING = {
    'points': ('Точки', ['Код', 'Наименование']),
    'items': ('Номенклатура', ['Код', 'Наименование', 'Вид', 'Единица', 'Цена', 'Себестоимость', 'Упаковка', 'ЦелевойЗапас', 'Резерв']),
    'sales': ('Продажи', ['Дата', 'Точка', 'Блюдо', 'Количество', 'БылоВНаличии', 'СменаЗакрыта']),
    'batches': ('Партии', ['Код', 'Точка', 'Ингредиент', 'Количество', 'Единица', 'ПригодностьПодтверждена', 'ВремяСверки', 'ИспользоватьДо']),
    'recipes': ('Рецептуры', ['Блюдо', 'Ингредиент', 'Расход', 'Единица', 'Версия', 'ДействуетС']),
    'deliveries': ('ОжидаемыеПоставки', ['Код', 'Точка', 'Ингредиент', 'Количество', 'Единица', 'ДатаПоступления', 'Подтверждена']),
    'movements': ('Движения', ['Код', 'Точка', 'Ингредиент', 'Дата', 'Вид', 'Количество', 'Единица', 'Причина']),
    'schedules': ('Графики', ['Точка', 'БлижайшаяПоставка', 'ИнтервалДней']),
}


def demo_payload(today=None):
    tables = demo_data(today)
    tables['points'][0]['name'] = 'ДЕМО · Центральная · Новосибирск'
    return {
        'protocol': PROTOCOL, 'dataset': 'DEMO', 'source': 'LOCAL_SIMULATOR',
        'generated_at': now(),
        'notice': 'Синтетические данные. Формат придуман для демо и не является API ДАЛИОН.',
        'data': {
            external: [dict(zip(columns, [row[field] for field in SCHEMAS[kind]])) for row in tables[kind]]
            for kind, (external, columns) in MAPPING.items()
        },
    }


@dataclass
class DemoSnapshot:
    tables: dict
    generated_at: str
    digest: str
    raw: bytes


def parse_snapshot(raw):
    if len(raw) > MAX_BYTES:
        raise DataError('Снимок превышает лимит 4 МБ.')
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise DataError('Источник вернул некорректный JSON.') from exc
    if not isinstance(payload, dict) or payload.get('protocol') != PROTOCOL:
        raise DataError('Неизвестный протокол. Это модуль только демонстрационного обмена.')
    if payload.get('dataset') != 'DEMO' or payload.get('source') != 'LOCAL_SIMULATOR':
        raise DataError('Разрешены только явно маркированные синтетические данные DEMO.')
    try:
        datetime.fromisoformat(payload['generated_at'])
    except (KeyError, TypeError, ValueError) as exc:
        raise DataError('Не указано корректное время формирования снимка.') from exc
    data = payload.get('data')
    if not isinstance(data, dict) or set(data) != {value[0] for value in MAPPING.values()}:
        raise DataError('Требуется полный снимок всех восьми наборов данных.')
    tables = {}
    for kind, (external, columns) in MAPPING.items():
        rows = data[external]
        if not isinstance(rows, list):
            raise DataError(f'{external}: ожидается список строк.')
        tables[kind] = []
        for index, row in enumerate(rows, 1):
            if not isinstance(row, dict) or set(row) != set(columns):
                raise DataError(f'{external}, строка {index}: состав полей не соответствует демо-контракту.')
            if any(isinstance(value, (dict, list, bool)) for value in row.values()):
                raise DataError(f'{external}, строка {index}: ожидаются простые значения и флаги 0/1.')
            tables[kind].append(dict(zip(SCHEMAS[kind], [row[field] for field in columns])))
    validate(tables)
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return DemoSnapshot(tables, payload['generated_at'], hashlib.sha256(canonical).hexdigest(), bytes(raw))


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DalionDemoAdapter(AccountingAdapter):
    """Read only the local simulator; no credentials or connection to a real 1C."""
    is_demo = True

    def fetch(self, endpoint):
        try:
            url = urlsplit(endpoint)
            allowed = (url.scheme == 'http' and url.hostname == '127.0.0.1' and url.port
                       and not url.username and not url.password and url.path == '/demo/v1/snapshot'
                       and not url.query and not url.fragment)
        except ValueError:
            allowed = False
        if not allowed:
            raise DataError('Демо разрешает только локальный HTTP-имитатор 127.0.0.1.')
        opener = build_opener(ProxyHandler({}), NoRedirects())
        try:
            with opener.open(endpoint, timeout=3) as response:
                if response.headers.get_content_type() != 'application/json':
                    raise DataError('Ожидается ответ application/json.')
                raw = response.read(MAX_BYTES + 1)
        except (URLError, OSError) as exc:
            raise DataError('Демо-источник недоступен. Данные не изменены; повторите получение.') from exc
        return parse_snapshot(raw)

    def read(self, path):
        return self.fetch(path).tables


class DemoServer:
    """A stable snapshot per session, served on loopback with an ephemeral port."""
    def __init__(self, payload=None):
        self.raw = json.dumps(payload if payload is not None else demo_payload(), ensure_ascii=False).encode('utf-8')
        self.offline = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != '/demo/v1/snapshot':
                    self.send_error(404)
                    return
                if owner.offline:
                    self.send_error(503, 'Demo source offline')
                    return
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(owner.raw)))
                self.end_headers()
                self.wfile.write(owner.raw)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        self.endpoint = f'http://127.0.0.1:{self.server.server_port}/demo/v1/snapshot'

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class DemoWorkspace:
    """Always creates a new directory; never accepts an existing production Store."""
    def __init__(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix='dalion-demo-', dir=root))
        (self.directory / 'DEMO.txt').write_text('Только синтетические данные. Не является подключением к ДАЛИОН.\n', encoding='utf-8')
        self.store = None

    def import_snapshot(self, snapshot):
        # Revalidate the source, rather than trusting a mutable preview table.
        checked = parse_snapshot(snapshot.raw)
        if checked.digest != snapshot.digest or checked.tables != snapshot.tables:
            raise DataError('Снимок изменён после проверки. Получите его заново.')
        folder = self.directory / checked.digest
        source = folder / 'demo.xlsx'
        if not source.exists():
            write_templates(folder, copy.deepcopy(checked.tables))
            (folder / 'source.json').write_bytes(checked.raw)
        if self.store is None:
            self.store = Store(self.directory / 'data.sqlite3')
        result = self.store.import_file(source, author='Демо обмена ДАЛИОН')
        metadata = {'protocol': PROTOCOL, 'digest': checked.digest, 'generated_at': checked.generated_at}
        if self.store.get('dalion_demo_source') != metadata:
            with self.store.db:
                self.store.put('dalion_demo_source', metadata)
        return result

    def close(self):
        if self.store is not None:
            self.store.db.close()
            self.store = None
