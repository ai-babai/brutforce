# -*- coding: utf-8 -*-
"""Build public aggregate report; never publish case answers or raw private files."""
import argparse,datetime,json,re
from pathlib import Path

def load(p):return json.loads(p.read_text())
def table(title,columns,rows,note=''):
    return {'title':title,'columns':[{'key':k,'label':v} for k,v in columns],'rows':rows,'note':note}
def readable(value):
    if isinstance(value,str):
        value=re.sub(r'([А-Яа-яЁё])(\d)',r'\1 \2',value)
        return re.sub(r'(\d)([А-Яа-яЁё])',r'\1 \2',value)
    if isinstance(value,list):return [readable(item) for item in value]
    if isinstance(value,dict):return {key:readable(item) for key,item in value.items()}
    return value
def quality(root,name,service,retrieval,organizer):
    s=load(root/service);r=load(root/retrieval);o=load(root/organizer)['unique_image_level']
    return {'name':name,'service':f"{s['top1_or_pass']}/{s['graded']}",'retrieval':f"{r['top1_or_pass']} / {r['top5']} / {r['top20']} из {r['graded']}",'real':f"{o['exact_top1']} / {o['exact_top5']} / {o['exact_top20']} из {o['exact_total']}"}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();root=a.root
    cols=[('name','Решение'),('service','Service: пройдено'),('retrieval','Retrieval: Top1 / 5 / 20'),('real','Реальные: Top1 / 5 / 20')]
    rows=[{'name':'B · предыдущий GPU-контроль','service':'114/141','retrieval':'57 / 59 / 62 из 62','real':'44 / 51 / 53 из 54'}]
    for name,prefix in [('CPU · Base224','base224'),('CPU · SO400M + OWLv2-640','so-owl640')]:
        rows.append(quality(root,name,f'cpu/scores/{prefix}-service.json',f'cpu/scores/{prefix}-retrieval.json',f'cpu/scores/{prefix}-organizer.json'))
    rows.append(quality(root,'B + исправление смешанных алфавитов','text-homoglyph/service-score.json','text-homoglyph/retrieval-score.json','text-homoglyph/organizer-score.json'))
    sections=[{'id':'overview','title':'Качество: общий ориентир','status':'partial','summary':'Все завершённые прогоны используют одни и те же входы. CPU и дополнения к GPU-поиску сравниваются раздельно. Ночная итерация ещё продолжается.','tables':[table('Завершённые контрольные варианты',cols,rows)],'notes':['213 frozen-кейсов: 151 service, из них 141 с подтверждённой оценкой; 62 retrieval. 10 service-кейсов остаются без оценки.','103 организаторских файла — 100 уникальных SHA. Accuracy только по 54 exact; 42 unresolved и 3 ambiguous исключены из accuracy. Один подтверждённый OOD оценивается отдельно.','Все эти фото уже используются при разработке. Это диагностический прогон, а не независимый официальный score.']}]
    sections.append({'id':'cpu','title':'CPU: полный запрос на Sigma','status':'partial','summary':'SO400M с ограничением входа запасного детектора этикеток до 640 пикселей сохранил качество поиска и убрал пять прежних тайм-аутов.','tables':[table('SO400M + OWLv2-640: свежий HTTP, один запрос за раз',[('data','Набор'),('success','HTTP 200'),('p50','p50'),('p95','p95'),('max','Максимум')],[{'data':'Frozen v2','success':'213/213','p50':'2,95 с','p95':'4,93 с','max':'5,80 с'},{'data':'Организаторы','success':'103/103','p50':'4,44 с','p95':'4,98 с','max':'5,34 с'}])],'notes':['Sigma: 8 vCPU KVM, AMD EPYC 9654 на хосте, 15 GiB RAM. Это не восемь выделенных физических ядер.','Loopback HTTP включает подготовку и inference; внешний upload и очередь другого клиента в этот замер не входят. Исходный скрипт ограничивает весь запрос 10 секундами; цель ТЗ — 3 секунды.','У 208 ранее завершившихся frozen-запросов порядок результатов полностью сохранился. Из пяти прежних тайм-аутов четыре теперь правильны, один остаётся ошибочным.','Base224 значительно быстрее, но потерял качество: на реальных фото 29/54 против 39/54 у SO400M. Его не выбираем только ради скорости.']})
    cpu_section=next(s for s in sections if s['id']=='cpu')
    cpu_rows=[quality(root,'SO400M + OWLv2-640','cpu/scores/so-owl640-service.json','cpu/scores/so-owl640-retrieval.json','cpu/scores/so-owl640-organizer.json')]
    cpu_rows.append(quality(root,'C3: OCR только когда бутылка не найдена','cpu/scores/c3-service.json','cpu/scores/c3-retrieval.json','cpu/scores/c3-organizer.json'))
    cpu_rows.append(quality(root,'SO400M + PaddleOCR на каждом запросе','cpu/scores/so-owl640-ocr-served-service.json','cpu/scores/so-owl640-ocr-served-retrieval.json','cpu/scores/so-owl640-ocr-organizer.json'))
    cpu_section['tables'].append(table('Маршрутизация и OCR: отдельные контроли',cols,cpu_rows))
    cpu_section['notes'].extend(['C3 улучшил ровно один service-кейс и не изменил organizer-ответы: прирост на одном SKU / одной группе сцены. Frozen p95 5,10 с; OCR вызван только на пяти запросах без найденной бутылки.','OCR на каждом запросе ухудшил качество и добавил по шесть тайм-аутов в frozen и organizer. Это не рекомендуемый CPU-профиль.','C3 organizer-тайминги пересеклись с архивным копированием на общий сервер. Не приписываем эту разницу только модели.'])
    cpu_section['tables'].append(table('FP32 ONNX: те же ответы на всех316 запросах',[('set','Набор'),('p50','p50'),('p95','p95'),('max','Максимум'),('timeouts','Timeout')],[{'set':'Frozen213','p50':'2,71 с','p95':'4,85 с','max':'5,23 с','timeouts':'0'},{'set':'Organizer103','p50':'4,28 с','p95':'4,96 с','max':'6,43 с','timeouts':'0'}]))
    cpu_section['notes'].extend(['ORT6: все316 полных рангов/action точно совпали с PyTorch SO640. Frozen запросов дольше3с стало94 вместо104; p95 почти не изменился. Это измеренное ускорение без изменения ответов, но цель3с на всех входах ещё не выполнена.','Неизменённый organizer script через SSH-туннель:12/12 результатов совпали, максимум5,53с. Два одновременных клиента: один200 за4,76с, второй503 busy за57мс; затем обычный запрос200 за3,26с. Сервис допускает один активный inference, а не произвольную нагрузку.'])
    if (root/'cpu/scores/ortdual-service.json').exists():
        ds=load(root/'cpu/scores/ortdual-service.json')
        dr=load(root/'cpu/scores/ortdual-retrieval.json')
        cpu_section['tables'].append(table('Два CPU-кропа: полный отрицательный контроль',
            [('name','Вариант'),('service','Service'),('retrieval','Retrieval Top1/5/20'),
             ('deadline','Ответы до 10 с')],[
                {'name':'ORT6 whole + label, без OCR',
                 'service':f"{ds['top1_or_pass']}/{ds['graded']}",
                 'retrieval':f"{dr['top1_or_pass']}/{dr['top5']}/{dr['top20']} из {dr['graded']}",
                 'deadline':'203/213'}]))
        cpu_section['notes'].extend([
            'Второй вид добавил OWLv2 для этикетки и ещё один SO400M inference. Полный frozen: 9 сетевых тайм-аутов и один поздний HTTP200 за 10,006 с; все десять считаются ошибками. У своевременных ответов p50 6,80 с, p95 9,32 с.',
            'Относительно ORT6 whole-only в service нет исправлений и 12 регрессий по 7 винам/группам сцен. Retrieval: 2 исправления и 4 регрессии. Organizer для этого варианта не запускали: одновременно ухудшились frozen-качество и время.',
            'Отдельные whole-only и label-only строки из dual HTTP показывают извлечённые ветви того же полного запроса. Их время включает обе ветви и не является измерением самостоятельного ускоренного сервиса.',
            'Первый INT8-экспорт превысил лимит RAM 6 GiB; повтор на временном сервере с достаточной памятью завершён. Результат отдельного CPU-прогона указан ниже.'])
    if (root/'cpu/scores/int8-service.json').exists():
        si=load(root/'cpu/scores/int8-service.json');ri=load(root/'cpu/scores/int8-retrieval.json')
        cpu_section['tables'].append(table('INT8 запроса + прежний FP32 индекс: отклонено',
            [('service','Service'),('retrieval','Retrieval Top1/5/20'),('timely','Вовремя'),('p50','p50'),('p95','p95')],
            [{'service':f"{si['top1_or_pass']}/{si['graded']}",'retrieval':f"{ri['top1_or_pass']}/{ri['top5']}/{ri['top20']} из {ri['graded']}",'timely':'213/213','p50':'2,03 с','p95':'3,93 с'}]))
        cpu_section['notes'].extend([
            'Динамический INT8 ускорил запрос, но дал 45 новых service-ошибок и 21 новую retrieval Top1-ошибку, без исправлений. Organizer не запускали после полного отрицательного frozen-контроля.',
            'Это смешанная точность: квантованный обработчик запроса и неизменный FP32-каталожный индекс. Результат не обобщаем на все способы INT8 или согласованное переиндексирование каталога.',
            'Начальные INT8-тайминги пересеклись с переносом артефактов на общий сервер. Качество и отсутствие timeout измерены, небольшую разницу скорости не объясняем только квантованием.'])
    visual=[]
    for mode,name in [('whole','Только целая выбранная цель'),('label','Только найденная этикетка'),('whole-label','Оба вида, без текстового поиска')]:
        visual.append(quality(root,name,f'visual-branches/{mode}/service-score.json',f'visual-branches/{mode}/retrieval-score.json',f'visual-branches/{mode}/organizer-score.json'))
    sections.append({'id':'visual','title':'Бутылка и этикетка: польза второго вида','status':'ready','summary':'На одних и тех же выбранных B областях два визуальных списка дали 42/54 на реальных фото вместо 41/54 у каждого отдельно. При этом результат на frozen ухудшился. Добавлять второй вид только ради усложнения не стоит.','tables':[table('SO400M: сохранённые визуальные ветви B',cols,visual)],'notes':['Здесь одинаковые выбор цели, энкодер и каталог. Меняем только набор используемых ветвей. Полный кадр всё равно проходит выбор центрального вина; whole означает выбранную цель, а не всю фотографию.','Это не доказательство, что этикетка менее информативна. Причиной может быть качество автоматической обрезки, мелкий текст или то, что энкодер лучше работает с более широким контекстом.','B включает дополнительный OCR-поиск и получает 44/54. Его текстовая ветвь может добавить кандидатов, отсутствующих в двух визуальных списках.','Submissions измеряют только слияние сохранённых рангов. Они не являются замером CPU или полного endpoint. CPU39/54 и эта GPU-ветвь41/54 отличаются маршрутизацией и обработкой входа.']})
    lg=[]
    for mode,name in [('local','Только геометрия'),('fusion','Геометрия + ранги B'),('cascade','Осторожный каскад')]:
        lg.append(quality(root,name,f'lightglue/private-score-{mode}-service.json',f'lightglue/private-score-{mode}-retrieval.json',f'lightglue/private-score-organizer-{mode}.json'))
    sections.append({'id':'lightglue','title':'LightGlue: отрицательный результат','status':'ready','summary':'DISK + LightGlue на фиксированных 20 кандидатах ухудшил точную идентификацию. Совпадающие детали оформления часто относятся к другому товару.','tables':[table('Полные frozen и organizer прогоны',cols,lg)],'notes':['Все 316 входов сохранены; случаи без кандидатов остаются ответом B. 2060 разрешённых эталонов, 2055 уникальных SHA; одинаковое фото может относиться к разным slug.','L4, только дополнительный этап на готовых входах: p95 2,25 с frozen и 2,94 с organizer. Это не время полного HTTP-запроса.','Каскад разработан после первого отрицательного прогона и проверен на тех же фото. Он всё ещё хуже B; дальнейший подбор порогов остановлен.','Использованы DISK и LightGlue с Apache-2.0, без SuperPoint. Код, веса, параметры и ошибки сохранены.'],'sources':[{'label':'LightGlue, официальный код','url':'https://github.com/cvg/LightGlue'}]})
    q=[]
    for mode,name in [('top20','Qwen: переставить Top20'),('top5','Qwen: переставить первые 5'),('fusion','Qwen + ранги B'),('confident','Qwen: только при большом отрыве')]:
        if (root/f'qwen/exported/{mode}-organizer-score.json').exists():q.append(quality(root,name,f'qwen/exported/{mode}-service-score.json',f'qwen/exported/{mode}-retrieval-score.json',f'qwen/exported/{mode}-organizer-score.json'))
    sections.append({'id':'qwen','title':'Qwen VL Reranker 2B','status':'ready' if len(q)==4 else 'partial','summary':'Готовая модель сравнивает фото запроса с фото и открытыми полями каждого кандидата. Пул Top20 фиксирован.','tables':[table('Четыре отдельных варианта',cols,q)],'notes':['Все варианты используют одну сохранённую матрицу оценок. Переупорядочивание не может вернуть правильный товар, отсутствующий в исходном Top20.','RTX3090, BF16, batch1. Заменена Conv3d-проекция отдельных патчей на F.linear с теми же весами: это изменение вычисления, без обучения. BF16-результаты не побитово равны; качество относится именно к этой реализации.','Порог 0,8 / отрыв 0,2 — инженерная эвристика, не откалиброванная вероятность и не проверка отсутствия товара. Время в submissions — только дополнительный этап, без B.'],'sources':[{'label':'Модель и лицензия','url':'https://huggingface.co/Qwen/Qwen3-VL-Reranker-2B'}]})
    text_rows=[quality(root,'PaddleOCR + смешанные алфавиты','text-homoglyph/service-score.json','text-homoglyph/retrieval-score.json','text-homoglyph/organizer-score.json')]
    for mode,name in [('reader_ocr','Qwen: только прочитанный текст'),('reader_fused','Qwen-текст + визуальные ветви B')]:
        text_rows.append(quality(root,name,f'reader/private-score-{mode}-service.json',f'reader/private-score-{mode}-retrieval.json',f'reader/private-score-organizer-{mode}.json'))
    for mode,name in [('text-filename','PaddleOCR + имена эталонов в поиске'),('text-filename-normal','То же + смешанные алфавиты')]:
        text_rows.append(quality(root,name,f'{mode}/service-score.json',f'{mode}/retrieval-score.json',f'{mode}/organizer-score.json'))
    text_rows.append(quality(root,'B + явное противоречие по сорту винограда','grape-evidence/service-score.json','grape-evidence/retrieval-score.json','grape-evidence/organizer-score.json'))
    text_rows.append(quality(root,'B + буквальная сладость из OCR / website-поля','sweetness-evidence/service-score.json','sweetness-evidence/retrieval-score.json','sweetness-evidence/organizer-score.json'))
    sections.append({'id':'text','title':'Текст: простое исправление выгоднее новой OCR-модели','status':'ready','summary':'Исправление смешанных алфавитов дало 46/54 на реальных фото. Замена чтения на Qwen — 45/54 и почти 10 секунд только на чтение. Добавление имени файла в обычный текстовый поиск ухудшает результат.','tables':[table('Отдельные текстовые проверки',cols,text_rows)],'notes':['Нормализация меняет только похожие латинские буквы внутри смешанного кириллического слова. На реальных фото +2 правильных ответа, без регрессий. Чистую латиницу и числа не меняем.','Qwen получает только выбранную область и просьбу прочитать видимые строки. Каталог и ответы ему не передаются. Поиск прочитанного текста идёт по всему каталогу и может добавить кандидатов.','Qwen + визуальные ветви: на реальных фото 6 исправлений и 5 новых ошибок. Замена чтения пока не окупается качеством.','L4 reader-only: p50 6,73 с, p95 9,88 с, max 11,29 с; 11/288 вызовов дольше 10 секунд. 28 случаев без выбранной цели не вызывали модель. Полный HTTP для этого варианта не измерялся.','Кроме OCR-модели изменился вход: Qwen читает label-context PNG, PaddleB — выбранную цель в JPEG. Это совместная проверка модели и вида кропа.','Имя файла — открытое поле исходного каталога, добавлено одинаковым правилом для всех 2103 карточек. Его польза как структурированного описания Qwen проверяется отдельно; отрицательный lexical-результат не подменяет этот опыт.']})
    next(section for section in sections if section['id']=='text')['notes'].append('Правило по сорту винограда: один явно найденный сорт в OCR и полностью разобранное поле grapes карточки; несовместимых кандидатов опускаем, неизвестных сохраняем. 44/54 вместо44/54 уB, service113/141 вместо114. Правильный сорт ещё не подтверждает конкретного производителя; улучшения нет. Новые правила по этому тесту не подбирали.')
    next(section for section in sections if section['id']=='text')['notes'].append('Буквальная сладость с дополнительной website-карточкой тоже не улучшила B:43/54 вместо44/54. Один новый промах: OCR содержит одновременно кириллическое «полусухое» и латинское CYXOE; правило увидело только первое. Перед жёсткими противоречиями нужны надёжное чтение и привязка строки к выбранной этикетке.')
    roman=[]
    for mode,name in [('base5','Qwen3.5-4B без адаптера, первые 5'),('roman5','Адаптер Ромы, первые 5'),('roman20','Адаптер Ромы, турнир из 20')]:
        roman.append(quality(root,name,f'roman/scores/final/{mode}-service.json',f'roman/scores/final/{mode}-retrieval.json',f'roman/scores/final/{mode}-organizer.json'))
    sections.append({'id':'roman','title':'Адаптеры Романа','status':'ready','summary':'Турнир из 20 кандидатов улучшил реальные фото с 44 до 50 правильных ответов, без новых ошибок относительно B. Это перенос ранее обученного адаптера, без нового обучения.','tables':[table('Базовая модель и два способа применения адаптера',cols,roman)],'notes':['Оригинальные предшествующие score/pool-файлы Романа отсутствуют. Поэтому это не воспроизведение его полной исходной системы и не сравнение его опубликованных метрик с нашими напрямую.','Roman20 применён в 237 из 316 запросов;51 с недоступным точным эталоном и28 без кандидатов сохраняют B. Roman5 применён в288. Все случаи остаются в знаменателях.','Оператор Conv3d заменён F.linear, BF16 округление отличается. Семь изменённых Top1 Roman5 перепроверены исходным оператором и совпали; полный Roman20 остаётся отдельным runtime-вариантом.','Время в этих submissions — только processor+model, без общего декодирования файлов и без B. Свежий полный HTTP приведён в отдельном разделе с реальными timeout.','Точных SHA-пересечений с переданными train/validation не обнаружено; это не исключает другие фотографии того же вина, сжатые копии или соседние кадры.']})
    ensemble=quality(root,'Qwen20 + Roman20, равные веса RRF','ensemble/service-score.json','ensemble/retrieval-score.json','ensemble/organizer-score.json')
    sections.append({'id':'ensemble','title':'Две сильные модели вместе','status':'ready','summary':'Ошибки моделей частично различаются, но простое объединение выдач не улучшило результат.','tables':[table('Исследовательская композиция сохранённых рангов',cols,[ensemble])],'notes':['Qwen20 исправляет9 ошибок B и вносит3 новых; Roman20 исправляет6 без новых. На фото, где ошиблась одна модель, другая иногда права.','Если выбирать между ними с подсказкой правильного ответа, верхняя граница53/54. Это не реализуемая без такой подсказки модель и не результат сервиса.','Равное RRF даёт48/54, ниже50/54 у каждой модели отдельно. Дополнительная цена двух моделей пока не оправдана. В submission измерено только слияние сохранённых списков.']})
    http_rows=[]
    if (root/'qwen-http/private-score-organizer-uncapped.json').exists():
        for mode,name in [('uncapped','Qwen20 RTX3090: полный HTTP без лимита'),('projected-10s','Тот же лог: поздние ответы считать ошибкой')]:
            http_rows.append(quality(root,name,f'qwen-http/private-score-{mode}-service.json',f'qwen-http/private-score-{mode}-retrieval.json',f'qwen-http/private-score-organizer-{mode}.json'))
        qtime=load(root/'qwen-http/summary-uncapped.json')['groups']
        latency=[]
        for key,name in [('eval-service','Service151'),('eval-retrieval','Retrieval62'),('organizer','Организаторы103')]:
            timing=qtime[key]['client_total_ms']
            latency.append({'set':name,'p50':f"{timing['p50']/1000:.2f} с",'p95':f"{timing['p95']/1000:.2f} с",'max':f"{timing['max']/1000:.2f} с",'late':str(timing['over_10000'])})
        sections.insert(2,{'id':'http','title':'Полный GPU-запрос: цена ограничения в 10 секунд','status':'partial','summary':'Качество ранжирования и качество быстрого сервиса различаются. На RTX3090 исходный B создаёт большую часть задержек до дополнительной модели.','tables':[table('Контроль без лимита и ретроспективная оценка поздних ответов',cols,http_rows),table('RTX3090: от исходных байтов фото до полного ответа, один клиент',[('set','Набор'),('p50','p50'),('p95','p95'),('max','Максимум'),('late','Позже 10 с')],latency)],'notes':['Первый HTTP-клиент ожидал до180 секунд. Он измеряет полную задержку, но не подтверждает соблюдение дедлайна. Ретроспективная строка — расчёт по этим временам, а не ещё один реальный endpoint или независимый эксперимент.','Полный повтор с настоящим10-секундным клиентским дедлайном приведён ниже. Последующие изменения потоков и карточек получают отдельные версии.','В 316 свежих запросах совпали Top1/action и состав Top20 B. В одном поменялись местами ранги8/9. Все Qwen-оценки совпали по slug; итоговое качество воспроизведено.','Organizer p95 этапа B 13,71 с, дополнительного Qwen 3,89 с. Простое кеширование эталонов Qwen не устранит медленную обработку B.','Загрузка фото измеряется через loopback внутри pod; интернет и публичная очередь в эти задержки не входят.']})
    if (root/'qwen-http/private-score-organizer-strict-10s.json').exists():
        http_section=next(section for section in sections if section['id']=='http')
        strict_row=quality(root,'Qwen20 RTX3090: curl max-time10','qwen-http/private-score-strict-10s-service.json','qwen-http/private-score-strict-10s-retrieval.json','qwen-http/private-score-organizer-strict-10s.json')
        http_section['tables'].append(table('Настоящий строгий Qwen HTTP: 307/316 своевременных ответов',cols,[strict_row]))
        http_section['notes'].extend(['Строгий Qwen-прогон:5 timeout на frozen service,0 retrieval,4 organizer. Все307 своевременных предсказаний совпали с uncapped. Успешные organizer: p50 6,42с / p95 9,16с / max9,95с.','В предыдущем uncapped organizer22 ответа были дольше10с, а в свежем strict только4. Это разные наблюдения: причина вариативности не установлена. Ускорение не приписываем ещё не применённой настройке потоков или только смене HTTP-клиента.'])
    if (root/'qwen-http/private-score-organizer-omp1-strict-10s.json').exists():
        http_section=next(section for section in sections if section['id']=='http')
        http_section['tables'].append(table('Qwen: отдельная конфигурация потоков, отрицательный итог',cols,[
            quality(root,'Qwen20: OMP1 + offline flags, strict10',
                'qwen-http/private-score-omp1-strict-10s-service.json',
                'qwen-http/private-score-omp1-strict-10s-retrieval.json',
                'qwen-http/private-score-organizer-omp1-strict-10s.json')]))
        http_section['notes'].extend([
            'В конфигурации OMP1 было 27 тайм-аутов: 5 frozen и 22 organizer. В исходном strict — 9. На 289 запросах, завершившихся в обоих прогонах, все ответы и полные ранги совпали.',
            'Вместе с OMP1 были включены HF_HUB_OFFLINE и TRANSFORMERS_OFFLINE. Это сравнение конфигураций, не изолированное доказательство влияния числа потоков. Причина сильной вариативности задержек пока не установлена; для проверки metadata восстановлен исходный запуск B.'])
    if (root/'qwen-http/private-score-organizer-website-strict-10s.json').exists():
        http_section=next(section for section in sections if section['id']=='http')
        http_section['tables'].append(table('Qwen + публичные поля витрины: отрицательный контроль',cols,[
            quality(root,'Qwen20 website, строгий HTTP',
                'qwen-http/private-score-website-strict-10s-service.json',
                'qwen-http/private-score-website-strict-10s-retrieval.json',
                'qwen-http/private-score-organizer-website-strict-10s.json')]))
        http_section['notes'].extend([
            'Website-профиль: 277/316 своевременных ответов, 39 timeout (5 frozen service и 34 organizer). На 39 уникальных exact-фото, вовремя обработанных обоими профилями, исходный Qwen дал 35 верных ответов, website — 33: 0 исправлений и 2 регрессии.',
            'Добавлены только публичные категория/сладость для 2029 карточек с прямым slug и согласованными названием/производителем. 69 отсутствующих и 5 конфликтных карточек оставлены пустыми; filename не добавляли.',
            'Все общие 277 успешных запросов сохранили полный порядок кандидатов B. Сильная вариативность времени между запусками не позволяет приписать все дополнительные timeout самим полям. Качественного выигрыша нет и на общем своевременном exact-срезе.',
            'У трёх повторных SHA в organizer разошлись исходы по timeout. Основная unique-оценка использует первое появление SHA в исходном порядке, не выбирает лучший повтор. Все 103 файловых запроса также сохранены.'])
    if (root/'roman/live-http-v1-final/score-roman20-organizer.json').exists():
        http_section=next(section for section in sections if section['id']=='http')
        rr=[]
        for mode,name in [('roman5','Roman5 из общего Roman20 HTTP'),('roman20','Roman20 RTX4090: настоящий лимит10 с')]:
            rr.append(quality(root,name,f'roman/live-http-v1-final/score-{mode}-service.json',f'roman/live-http-v1-final/score-{mode}-retrieval.json',f'roman/live-http-v1-final/score-{mode}-organizer.json'))
        http_section['tables'].append(table('Свежий строгий HTTP Roman: 291/316 своевременных ответов',cols,rr))
        http_section['notes'].extend(['Roman20: 16 timeout на frozen и9 на organizer. Retrieval62 завершён полностью; service104/141 и organizer45/54 — уже с учётом дедлайна. Ответы, пришедшие позже, не возвращаем в score.','Сервер в итоге обработал316/316; все порядки B и Roman совпали с сохранённым экспериментом. Падение качества обусловлено дедлайном, а не исчезновением прежнего выигрыша ранжирования.','Roman5 здесь извлечён из общего Roman20 endpoint. Его задержку нельзя выдавать за отдельный оптимизированный сервис Roman5.','Неизменённый participant_test.sh через SSH-туннель: у Roman4 ответа и2 timeout из6. Формат single-slug разобран верно; пример успешного запроса3,29 с, включая upload95,7КБ.'])
    if (root/'roman/live-ocr1280-final/score-roman20-organizer.json').exists():
        http_section=next(section for section in sections if section['id']=='http')
        http_section['tables'].append(table('Уменьшение входа OCR до 1280: отрицательная проверка',cols,[
            quality(root,'Roman20 + OCR1280, строгий HTTP',
                'roman/live-ocr1280-final/score-roman20-service.json',
                'roman/live-ocr1280-final/score-roman20-retrieval.json',
                'roman/live-ocr1280-final/score-roman20-organizer.json')]))
        http_section['notes'].extend([
            'OCR1280 дал 35 тайм-аутов вместо 25. Рамки цели и этикетки совпали на всех 316 входах, но распознанный текст изменился на 184, Top20 B — на 134, первый ответ Roman20 — на 10. Это изменение качества входа, не эквивалентная оптимизация.',
            'При уменьшении изображения OCR не обязательно ускоряется: меняются число и формы найденных текстовых областей. В этом прогоне B p50/p95 выросли с 3,90/7,62 до 4,03/7,93 с. Конкретный механизм требует отдельного профилирования; вариант отклонён.',
            'Отдельная проба MKLDNN вернула ошибку Paddle, после которой B продолжил с пустым OCR. Её короткое время не считается ускорением: все пять проверенных списков изменились. Нужен явный индикатор работы без OCR.'])
    next(section for section in sections if section['id']=='http')['notes'].append('RTX3090 и RTX4090 здесь запускают разные дополнительные модели и стоят на разных CPU-хостах. Большая часть хвоста — OCR на CPU; разницу времени нельзя приписывать только классу GPU.')
    sections.append({'id':'limits','title':'Что ещё не решено','status':'ready','summary':'Увеличение Top1 не закрывает сценарий отсутствующего товара и ошибочно выбранной бутылки. Эти ограничения сохраняются у сильных моделей.','tables':[table('Оставшиеся ограничения и следующая проверка',[('problem','Проблема'),('next','Что проверять дальше')],[{'problem':'Точного товара нет в каталоге','next':'Отдельные подтверждённые отрицательные фото и проверка отказа; не подменять их неразмеченными кадрами.'},{'problem':'Выбрано соседнее вино или составная рамка','next':'Целевая область и привязка OCR к этой области. Reranker не вернёт товар, потерянный до Top20.'},{'problem':'Похожие варианты одной линейки','next':'Читаемые надписи, точные поля и качество эталонов. Не угадывать невидимый год или сладость.'},{'problem':'Мало независимых реальных проверок','next':'Отдельные реальные снимки вне текущей разработки, с подтверждёнными ответами и группировкой по сцене.'}])],'notes':['На единственном подтверждённом organizer OOD исходный B, Qwen20, Roman20 и CPU SO640 пока не дают правильного отказа: 0/1. Это конкретный провал, но одного случая мало для оценки частоты ошибок или выбора порога.','42 unresolved означает, что мы не подтвердили правильную карточку. Это не доказательство отсутствия товара. Они не превращаются в отрицательный класс.','Порог нейросетевой похожести и отрыв Top1 от Top2 сами по себе не являются вероятностью правильного SKU. Новую политику отказа нужно оценивать отдельно от ранжирования.']})
    next(section for section in sections if section['id']=='limits')['notes'].append('В прежней разметке5 из54 exact имеют отмеченные конфликты reference-фото/упаковки. Их не исключаем: на остальных49 B40/49, Qwen20 иRoman20 по46/49; на конфликтном срезе все4/5. Основной знаменатель54 сохранён.')
    if (root/'roman/live-deadline6-final/score-roman20-organizer.json').exists():
        http_section=next(section for section in sections if section['id']=='http')
        http_section['tables'].append(table('Ограниченный каскад: 315/316 ответов до 10 секунд',cols,[
            quality(root,'Roman20: пропустить дополнительную модель, если B уже занял 6 с',
                'roman/live-deadline6-final/score-roman20-service.json',
                'roman/live-deadline6-final/score-roman20-retrieval.json',
                'roman/live-deadline6-final/score-roman20-organizer.json')]))
        http_section['notes'].extend([
            'Deadline6 возвращает свежий ответ B, если базовый поиск уже занял 6 секунд. Это произошло в 27 своевременных запросах. Кеша ответов нет; все 103 organizer-запроса уложились в лимит.',
            'На 316 запросах p50 5,94 с, p95 8,46 с. Единственный timeout: сам B занял 13,03 с. Ограничение дополнительного этапа не может исправить перерасход времени базовым поиском.',
            'Порог 6 секунд выбран по текущим development-замерам. Это полезная рабочая политика, но не независимое доказательство SLA и не гарантия под нагрузкой.'])
        overview=next(section for section in sections if section['id']=='overview')
        overview['tables'].insert(0,table('Практический выбор: свежие полные HTTP-запросы',cols,[
            quality(root,'CPU FP32 ONNX, один визуальный вид',
                'cpu/scores/ort6-service.json','cpu/scores/ort6-retrieval.json',
                'cpu/scores/ort6-organizer.json'),
            quality(root,'GPU Roman20 с ограничением времени дополнительного этапа',
                'roman/live-deadline6-final/score-roman20-service.json',
                'roman/live-deadline6-final/score-roman20-retrieval.json',
                'roman/live-deadline6-final/score-roman20-organizer.json')],
            'CPU: 316/316 ответов до 10 секунд; GPU-каскад: 315/316. CPU быстрее и дешевле в эксплуатации, GPU точнее на текущих real-фото. Ни один результат не доказывает цель 3 секунды или устойчивый отказ на неизвестном вине.'))
    if (root/'roman/live-roman5-final/score-roman5-organizer.json').exists():
        http_section=next(section for section in sections if section['id']=='http')
        http_section['tables'].append(table('Самостоятельный Roman5: один выбор, без турнира Top20',cols,[
            quality(root,'Roman5 RTX4090, свежий строгий HTTP',
                'roman/live-roman5-final/score-roman5-service.json',
                'roman/live-roman5-final/score-roman5-retrieval.json',
                'roman/live-roman5-final/score-roman5-organizer.json')]))
        http_section['notes'].append('Roman5 как отдельный endpoint: 314/316 вовремя, 2 frozen timeout и все 103 organizer вовремя; p50 3,93 с, p95 7,04 с. На всех 314 общих успешных запросах полный порядок B и Roman5 совпал с сохранёнными результатами. Это настоящий более короткий путь, в отличие от строк Roman5, извлечённых из общего Roman20 HTTP.')
    sections[0]['status']='ready'
    sections[0]['summary']='CPU FP32 ONNX — практичный вариант без постоянной аренды GPU. Roman20 с ограничением времени дополнительного этапа точнее на текущих реальных фото. Ночное сравнение завершено; ошибки отказа и недостаточности информации остаются открытыми.'
    next(section for section in sections if section['id']=='cpu')['status']='ready'
    next(section for section in sections if section['id']=='http')['status']='ready'
    slices=load(root/'common/quality-slices.json')
    slice_rows=[]
    for name,tracks in slices.items():
        row={'name':name}
        for origin in ('real','augmentation','ai'):
            values=tracks['service'][origin]
            row[origin]=f"{values['correct']}/{values['graded']}"
        slice_rows.append(row)
    sections.append({'id':'origins','title':'Где именно улучшилось качество','status':'ready','summary':'Прирост на frozen-корзинах в основном приходится на аугментации. Настоящие фото организаторов нужны как отдельная проверка, иначе вывод о пользе новой модели был бы слишком оптимистичным.','tables':[table('Service, происхождение изображения',[('name','Решение'),('real','Реальные'),('augmentation','Аугментации'),('ai','AI')],slice_rows)],'notes':['В retrieval v2 нет независимых реальных фото: 50 аугментаций и 12 AI. Поэтому 61/62 не означает такую же точность на фотографиях пользователей.','32 graded real service-кейса включают сценарии отказа и выбора цели, а не только поиск конкретного вина. Их процент нельзя напрямую сравнивать с 54 exact organizer.','213 frozen-запросов содержат 212 SHA, 103 organizer-запроса — 100 SHA. Между наборами есть 12 совпадающих SHA. Всего300 уникальных изображений, а не316 независимых наблюдений. Среди54 exact organizer —37 разных SKU и42 группы сцен.','Повторные кадры одного вина и аугментации одной сцены не становятся независимыми измерениями. Парные улучшения дополнительно считаем по SKU и группам сцены.']})
    sections.append({'id':'method','title':'Как читать результаты и воспроизводить','status':'partial','summary':'Код и протоколы идут в репозиторий. Фото, веса, приватные ответы и подробные raw-результаты хранятся отдельно.','tables':[],'notes':['На inference GPU нет закрытой разметки. Метрики считаются после записи предсказаний на доверенном хосте. Все входы проверены по SHA.','Не складываем старое время B и новый этап, выдавая сумму за замер endpoint. Для выбранного каскада нужен свежий полный HTTP-прогон.','Новые результаты добавляются к истории, frozen v2 не меняется. TEST и PROD сохраняют прежнюю версию.','Временные GPU: RTX4090 $0,74/ч, L4 $0,49/ч, RTX3090 $0,50/ч плюс хранилище. По завершении экспорта поды удаляются; подтверждение будет сохранено отдельно.']})
    method=next(section for section in sections if section['id']=='method')
    method['status']='ready'
    method['notes'][-1]='Все пять временных pod этой итерации удалены после экспорта. Независимый список провайдера: 0 pod и 0 сетевых дисков. Собственные CPU-стенды остановлены; постоянные TEST и PROD не заменены.'
    method['notes'].append('GPU по времени аренды и тарифам: около $5,51 без хранения. На момент закрытия провайдер отразил $4,19, но биллинг запаздывает; это не окончательный счёт. Тарифы: RTX4090 $0,74/ч, RTX3090 $0,50/ч, L4 $0,49/ч.')
    next(section for section in sections if section['id']=='http')['notes'].append('Неизменённый скрипт организаторов на шести кадрах через SSH-туннель, Qwen website: пять slug и один timeout 10,004 с. Поздний HTTP 200 на сервере не отменяет клиентский timeout. Это проверка контракта на sample, а не SLA публичного ingress.')
    action_path=root/'common/service-action-scores.json'
    if action_path.exists():
        action_rows=[]
        for name,values in load(action_path)['profiles'].items():
            row={'name':name}
            for key,value in values.items():
                row[key]=f"{value['correct']}/{value['total']}"
            action_rows.append(row)
        limitations=next(section for section in sections if section['id']=='limits')
        limitations['tables'].append(table('Какое поведение проверяют 141 service-кейс',
            [('name','Решение'),('match','Верный товар'),('no_match','Нет совпадения'),
             ('insufficient_information','Недостаточно информации')],action_rows))
        limitations['notes'].append('Ни один из этих профилей не проходит 10 проверок недостаточности информации. Увеличение точности выбора товара не исправляет этот дефект поведения. 19/22 отказов frozen и 0/1 реального OOD — разные выборки: первая не доказывает устойчивый отказ на неизвестных винах. Следующий этап должен отдельно проверять качество видимой информации и наличие товара, не просто понижать вес визуального сходства.')
    group_path=root/'common/group-scores.json'
    if group_path.exists():
        group_rows=[]
        for name,value in load(group_path)['profiles'].items():
            group_rows.append({'name':name,
                'macro':f"{value['sku']['macro_accuracy']*100:.1f}%",
                'all':f"{value['sku']['all_images_correct']}/{value['sku']['groups']}",
                'fixed':value['sku']['groups_with_fix'],
                'broken':value['sku']['groups_with_regression']})
        origin=next(section for section in sections if section['id']=='origins')
        origin['tables'].append(table('Повторные фотографии не увеличивают вес одного вина',
            [('name','Вариант'),('macro','Средняя точность по SKU'),
             ('all','SKU: верны все кадры'),('fixed','SKU с исправлением'),
             ('broken','SKU с регрессией')],group_rows))
        origin['notes'].append('В среднем по SKU каждое из 37 вин имеет одинаковый вес: сначала доля верных кадров вина, затем среднее по винам. Это дополнительная диагностика, не новая официальная метрика. Исправления и регрессии сравниваются с B; одно вино может попасть в обе группы. Strict включает реальные тайм-ауты, остальные строки — качество сохранённых предсказаний.')
    data={'schema_version':1,'updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sections':sections}
    a.out.write_text(json.dumps(readable(data),ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
