"""Aggregate measured HTTP runs for RT-DETR + SO400M; no private answers."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def percentile(values, q):
    return sorted(values)[max(0, math.ceil(len(values)*q)-1)] if values else None


def table(title, columns, rows):
    return {"title":title,"columns":[{"key":k,"label":v} for k,v in columns],"rows":rows}


def build(root):
    folder=root/'detectors/rtdetr-so400m-gatev2'
    rows=[];provenance={};notes=[]
    for name,filename in [('Все организаторские файлы','full-organizer.jsonl'),('Замороженные service + retrieval','full-eval.jsonl')]:
        p=folder/filename
        if not p.exists():continue
        data=[json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        times=[r['elapsed_ms'] for r in data]
        failed=sum(r.get('http_status') not in (200,201) or bool(r.get('error')) for r in data)
        rows.append({'sample':name,'n':len(data),'errors':failed,
          'p50':round(percentile(times,.5)/1000,2),'p95':round(percentile(times,.95)/1000,2),
          'max':round(max(times)/1000,2),'over':sum(t>10000 for t in times)})
        provenance[filename]=hashlib.sha256(p.read_bytes()).hexdigest()
    gpu=json.loads((folder/'gpu24.json').read_text())
    perf=[{'system':'RTX 4090 · бутылка + этикетка + OCR','n':gpu['warm_successes'],
      'p50':round(gpu['warm_p50_ms']/1000,2),'p95':round(gpu['warm_p95_ms']/1000,2),
      'max':round(gpu['warm_max_ms']/1000,2),'cold':round(gpu['healthz']['cold_load_ms']/1000,2)}]
    provenance['gpu24.json']=hashlib.sha256((folder/'gpu24.json').read_bytes()).hexdigest()
    cpu_path=folder/'cpu-whole24.json'
    if cpu_path.exists():
        cpu=json.loads(cpu_path.read_text())
        perf.append({'system':'EPYC 75F3 · только целевая область, 4 потока','n':cpu['warm_successes'],
          'p50':round(cpu['warm_p50_ms']/1000,2),'p95':round(cpu['warm_p95_ms']/1000,2),
          'max':round(cpu['warm_max_ms']/1000,2),'cold':round(cpu['healthz']['cold_load_ms']/1000,2)})
        provenance['cpu-whole24.json']=hashlib.sha256(cpu_path.read_bytes()).hexdigest()
        notes.append('CPU-строка — другая, упрощённая архитектура: только вектор выбранной цели, без обычной ветви этикетки и OCR; резервный поиск отдельной этикетки сохранён. На полной offline-выборке её ветвь whole даёт 39/54 вместо 42/54 композиции. Это не CPU-скорость полной GPU-композиции.')
    notes.extend(['24 разных фото: первый запрос исключён из 23 warm, загрузка моделей показана отдельно. Для полной GPU-ветви с выполненным OCR: 21 warm, p95 '+str(round(gpu['full_pipeline_warm_p95_ms']/1000,2))+' с.',
      'Во всех 316 входах конечное действие/Top‑1 совпало с offline-контролем. Полный порядок Top‑20 совпал в 280/316, состав — в 310/316. Изображения, выбранные области и OCR ранги совпали; небольшие изменения визуальных оценок меняют младшие ранги. Точный источник численного дрейфа не изолирован.',
      'Последовательный HTTP на одном хосте: включает декодирование, модели, поиск и ответ. Передача по внешней сети, конкурентная нагрузка и очередь не измерялись.',
      'Диагностический клиент допускает 120 секунд для регистрации ошибок. Колонка >10 с проверяет фактическое время; это не демонстрация принудительного прерывания по 10-секундному таймеру.',
      'GPU аренда: $0.74/ч за RTX 4090; диск оплачивается отдельно. Эта сильная композиция на дешёвой RTX 4000 Ada не измерялась. Более ранний опыт на ней относится к другому энкодеру.',
      'Не требуется дообучение: веса готовые, каталожные векторы вычислены заранее. Модельный сервер временный и после эксперимента удаляется; постоянный CV-сайт хранит отчёты и корзины.'])
    return {'schema_version':1,'source_sha256':provenance,'sections':[{'id':'strong-serving','title':'Сильная композиция: реальный HTTP и время','status':'ready' if len(rows)==2 and cpu_path.exists() else 'partial',
      'summary':'RT-DETR R18 → выбор центрального вина через SigLIP Base → OWLv2 для этикетки → два вектора SigLIP2 SO400M + PaddleOCR → объединение списков по рангам.',
      'tables':[table('Все входные файлы, RTX 4090',[('sample','Набор'),('n','Файлов'),('errors','Ошибок HTTP'),('p50','p50, с'),('p95','p95, с'),('max','Максимум, с'),('over','>10 с')],rows),
        table('Одинаковые 24 фото: 1 первый + 23 warm',[('system','Конфигурация'),('n','Warm'),('p50','p50, с'),('p95','p95, с'),('max','Максимум, с'),('cold','Загрузка, с')],perf)],'notes':notes}]}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(build(a.root),ensure_ascii=False,indent=2)+'\n')
