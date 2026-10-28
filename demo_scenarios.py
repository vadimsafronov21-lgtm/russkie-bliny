"""Synthetic, independently launched customer demonstration situations."""
from datetime import date,timedelta

from core import DataError
from dalion_exchange import demo_payload

SCENARIOS={
    'normal':('Обычный день','Продажи, остатки и график; проверьте список дел и заявку.'),
    'delay':('Поставка задерживается','В синтетическом снимке поставка и ожидаемый приход сдвинуты на два дня.'),
    'missing':('Не хватает начинки','Синтетический остаток куриной начинки равен нулю; программа показывает риск.'),
    'repeat':('Повторная загрузка','Получите и откройте снимок, измените остаток, затем получите тот же снимок повторно. Правки сохранятся.'),
}


def scenario_payload(name):
    if name not in SCENARIOS: raise DataError('Неизвестная демонстрационная ситуация.')
    payload=demo_payload(); payload['notice']+=' Ситуация: '+SCENARIOS[name][0]
    if name=='delay':
        payload['data']['Графики'][0]['БлижайшаяПоставка']=(date.today()+timedelta(days=3)).isoformat()
        payload['data']['ОжидаемыеПоставки'][0]['ДатаПоступления']=(date.today()+timedelta(days=3)).isoformat()
    elif name=='missing':
        next(row for row in payload['data']['Партии'] if row['Ингредиент']=='chicken_i')['Количество']=0
    return payload
