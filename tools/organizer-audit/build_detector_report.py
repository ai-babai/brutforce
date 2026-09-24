"""Publish only aggregate diagnostics, never private case answers or input paths."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def table(title,columns,rows,note=''):
    return {'title':title,'columns':[{'key':k,'label':v} for k,v in columns],'rows':rows,'note':note}


def read(path):return json.loads(path.read_text()) if path.exists() else None

def fraction(s,k='correct_top1'):
    return f"{s[k]}/{s['graded']}" if s else '—'


def report(root,old,gold=None):
    sections=[]
    corrected={}
    for path in sorted((root/'annotation').glob('frozen-v1-corrected*/*.json')):
        value=read(path)
        provenance=value.get('diagnostic_erratum',{})
        if provenance.get('source_report_sha256'):
            corrected[provenance['source_report_sha256']]=value
    def scored(path):
        value=read(path)
        if value is None:return None
        if corrected:
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            if sha not in corrected:
                raise ValueError('Report needs the same frozen-gold erratum first: '+str(path))
            return corrected[sha]
        return value
    erratum=read(root/'frozen-v1-errata-all-public-summary.json') or read(root/'frozen-v1-errata-public-summary.json')
    if erratum:
        sections.append({'id':'gold-erratum','title':'Исправление эталона: те же фото и предсказания','status':'ready',
          'summary':'В старом ответе перепутаны полусладкое вино и брют: ошибочное каталожное фото послужило неверным эталоном. Проверены исходное фото и производные — исправлены 13 service и 7 retrieval случаев.',
          'tables':[], 'notes':['Все таблицы замороженных корзин в этом отчёте пересчитаны с этим исправлением. Модели, изображения и предсказания остались прежними.',
          'Общая матрица хранит исходные append-only прогоны. Их исторические числа отличаются от исправленной интерпретации здесь; это не улучшение модели.',
          '103 организаторских файла размечены отдельно как 100 уникальных фото. Их локальный набор ответов не заменяет исходный официальный каталог.']})
    specs=[('OWLv2 · v2',old/'eval-v2-label-context/reports',''),
           ('YOLOE-26s',root/'detectors/yoloe26s/reports','report-'),
           ('YOLO26n + OWLv2',root/'detectors/yolo26n/reports','report-'),
           ('YOLO26n + геометрия',root/'detectors/yolo26n-geometric/reports','report-'),
           ('RT-DETR R18 + OWLv2',root/'detectors/rtdetr-r18/reports','report-')]
    loaded={}
    rows=[]
    for name,folder,prefix in specs:
        s=scored(folder/(prefix+'all-service.json'));r=scored(folder/(prefix+'all-retrieval.json'))
        if not s or not r:continue
        loaded[name]=(folder,prefix,s,r)
        rows.append({'model':name,'service':fraction(s['overall']),'top1':fraction(r['overall']),
                     'top5':fraction(r['overall'],'correct_top5'),'top20':fraction(r['overall'],'correct_top20'),
                     'real':fraction(s.get('by_origin',{}).get('real'))})
    if erratum:
        delta_rows=[]
        for name,(folder,prefix,s,r) in loaded.items():
            original_s=read(folder/(prefix+'all-service.json'))
            original_r=read(folder/(prefix+'all-retrieval.json'))
            delta_rows.append({'model':name,'old_s':fraction(original_s['overall']),
                'new_s':fraction(s['overall']),'old_r':fraction(original_r['overall']),
                'new_r':fraction(r['overall'])})
        sections[0]['tables'].append(table('Изменился ответ теста, а не модель',
          [('model','Решение'),('old_s','Service: старый ответ'),('new_s','Исправленный'),
           ('old_r','Retrieval Top‑1: старый'),('new_r','Исправленный')],delta_rows))
    sections.append({'id':'frozen','title':'Одинаковые замороженные корзины','status':'ready' if len(rows)==len(specs) else 'partial',
      'summary':'213 случаев: 151 service (141 с эталоном) и 62 retrieval. Ответы пересчитаны с erratum; исходный каталог одинаков у этих детекторов. Отдельный контроль с карантином приведён ниже.',
      'tables':[table('Все три ветви вместе',[('model','Детектор'),('service','Service: прошли'),('real','Service: реальные'),('top1','Retrieval Top‑1'),('top5','Top‑5'),('top20','Top‑20')],rows)],
      'notes':['Service проверяет конечное действие и точный slug; отрицательные случаи тоже входят в 141. В retrieval все 62 кадра являются AI или аугментациями — это не оценка на новых мобильных фото.',
               '10 сервисных случаев без однозначного эталона видны, но не включаются в знаменатель. Пропуски и ошибки решения из знаменателя не удаляются.',
               'Один и тот же диагностический набор уже просматривался. Это сравнение разработки, а не независимый holdout; веса моделей не обучались.']})
    branch_rows=[]
    branch_names={'whole':'Вся цель','label':'Этикетка','ocr':'OCR','whole_label':'Цель + этикетка','whole_ocr':'Цель + OCR','label_ocr':'Этикетка + OCR','all':'Все три'}
    for variant,label in branch_names.items():
        row={'branch':label}
        for name,(folder,prefix,s,r) in loaded.items():
            svc=scored(folder/(prefix+variant+'-service.json'));ret=scored(folder/(prefix+variant+'-retrieval.json'))
            if name == 'OWLv2 · v2' and variant in ('whole','ocr','whole_ocr'):
                # v2 changed label crops only; unchanged branches retain their v1 artifacts.
                svc=scored(old/'eval-v1/reports'/(variant+'-service.json'))
                ret=scored(old/'eval-v1/reports'/(variant+'-retrieval.json'))
            row[name]=(fraction(svc['overall'])+' · '+fraction(ret['overall'])) if svc and ret else '—'
        branch_rows.append(row)
    sections.append({'id':'branches','title':'Сначала отдельные методы, затем сочетания','status':'ready',
      'summary':'В каждой ячейке: service /141 · retrieval Top‑1 /62. Отдельная ветвь позволяет понять, откуда появился выигрыш или ошибка.',
      'tables':[table('Качество ветвей',[('branch','Метод')]+[(name,name) for name in loaded],branch_rows)],
      'notes':['Ветви используют одинаковый выбранный фрагмент. Для новых детекторов «Все три» — реальный полный HTTP-ответ. Исходный OWLv2 v2 и остальные ветви — пересчёты ранее полученных предсказаний; отдельные HTTP-замеры приведены в разделе скорости.',
               'У исходного OWLv2 ветви без этикетки сохранены из v1: в v2 менялся только фрагмент этикетки.',
               'Задержку полного запроса нельзя выдавать за измеренную скорость каждой отдельной ветви.']})
    chosen={'IMG-02':'Отдельная этикетка','IMG-03':'Неполный кадр','IMG-10':'Размытие','IMG-12':'Вино сбоку, не-вино в центре','IMG-15':'Нет цели','IMG-16':'Бутылка без этикетки'}
    basket_rows=[]
    for bid,title in chosen.items():
        row={'basket':bid+' · '+title}
        for name,(_,_,s,_) in loaded.items():row[name]=fraction(s['by_basket'].get(bid))
        basket_rows.append(row)
    sections.append({'id':'failures','title':'Что скрывается за общей цифрой','status':'ready',
      'summary':'Полезная замена детектора должна проходить сложные случаи, а не только чаще выдавать рамку.',
      'tables':[table('Проверки поведения',[('basket','Корзина')]+[(name,name) for name in loaded],basket_rows)],
      'notes':['Число обнаружений не является точностью детекции. Полной ручной разметки всех рамок плотной полки здесь нет: mAP и полноту всех бутылок не заявляем.']})
    if 'OWLv2 · v2' in loaded:
        baseline={r['case_id']:r for r in loaded['OWLv2 · v2'][2]['cases'] if r['graded']}
        paired=[]
        for name,(_,_,service,_) in loaded.items():
            if name=='OWLv2 · v2':continue
            candidate={r['case_id']:r for r in service['cases'] if r['graded']}
            if set(candidate)!=set(baseline):raise ValueError('paired service cases differ')
            wins=sum(candidate[k]['correct'] and not baseline[k]['correct'] for k in baseline)
            losses=sum(baseline[k]['correct'] and not candidate[k]['correct'] for k in baseline)
            paired.append({'model':name,'improved':wins,'regressed':losses,'net':wins-losses})
        sections[-1]['tables'].append(table('Что изменилось относительно OWLv2 на тех же 141 случаях',
          [('model','Решение'),('improved','Ошибка → верно'),('regressed','Верно → ошибка'),('net','Изменение числа верных')],paired))
        sections[-1]['notes'].append('Это парная диагностика на повторно используемых случаях, а не статистическое доказательство преимущества на новых фотографиях.')
    if gold:
        gold_by_id={r['case_id']:r for r in gold['cases']}
        outcome_rows=[]
        for name,(_,_,s,_) in loaded.items():
            row={'model':name}
            for key,origin,action in [('real_match','real','match'),('real_negative','real','no_match'),
                                      ('aug_match','augmentation','match'),('ai_match','ai','match'),
                                      ('insufficient','ai','insufficient_information')]:
                cases=[r for r in s['cases'] if r['graded'] and r['origin_kind']==origin
                       and gold_by_id[r['case_id']]['service'].get('expected_action','match')==action]
                row[key]=f"{sum(r['correct'] for r in cases)}/{len(cases)}"
            outcome_rows.append(row)
        sections.append({'id':'outcomes','title':'Распознавание вина и корректный отказ','status':'ready',
          'summary':'Из 32 реальных сервисных проверок 22 требуют отказа на не-вине. Общий результат на этих 32 нельзя считать точностью распознавания реального вина.',
          'tables':[table('Правильное действие по типу входа',[('model','Решение'),('real_match','Реальное вино'),('real_negative','Реальное не-вино'),('aug_match','Вино: аугментации'),('ai_match','Вино: AI'),('insufficient','AI без достаточных данных')],outcome_rows)],
          'notes':['Случай с бутылкой без этикетки требует insufficient_information. Отказ no_match тоже не проходит этот контракт: отсутствие данных и отсутствие вина различаются.',
                   'В текущем коде insufficient_information возникает лишь при найденной цели и пустом списке кандидатов. При непустом визуальном индексе ближайший сосед почти всегда есть. Поэтому 0/10 на бутылках без этикетки отражает отсутствующую проверку достаточности информации, а не только качество нейросети.',
                   'Десять положительных реальных случаев повторяют небольшой набор вин; это ограниченный диагностический контроль. Расширенный аудит 100 фото приведён отдельно.']})
    gray_rows=[]
    for mode,label in [('color','Цвет'),('gray','Чёрно-белая этикетка'),('color_gray_equal_rrf60','Цвет + ч/б, равные ранги')]:
        folder=old/'eval-v2-label-context/reports' if mode=='color' else root/'detectors/gray-label/reports'
        prefix='' if mode=='color' else 'report-'+mode+'-'
        for branch in ('label','label_ocr','all'):
            svc=scored(folder/(prefix+branch+'-service.json'));ret=scored(folder/(prefix+branch+'-retrieval.json'))
            if svc and ret:
                gray_rows.append({'mode':label,'branch':branch_names[branch],
                  'service':fraction(svc['overall']),'top1':fraction(ret['overall']),
                  'top5':fraction(ret['overall'],'correct_top5'),'top20':fraction(ret['overall'],'correct_top20')})
    if len(gray_rows)>3:
        sections.append({'id':'gray','title':'Помогает ли убрать цвет','status':'ready',
          'summary':'Одинаковые OWLv2-фрагменты и SigLIP2 Base-224. В ч/б переводится и каталожная этикетка, и запрос; исходная ветвь бутылки и OCR сохраняются.',
          'tables':[table('Отдельная этикетка и сочетания',[('mode','Преобразование'),('branch','Ветви'),('service','Service /141'),('top1','Top‑1 /62'),('top5','Top‑5 /62'),('top20','Top‑20 /62')],gray_rows)],
          'notes':['Одно улучшение отдельной метрики не означает общий выигрыш. Смотрите одновременно service, retrieval и отдельные реальные фото ниже.',
                   'Это пересчёт качества с сохранёнными фрагментами, а не измерение нового полного HTTP-запроса. Время стадий не объявляется сквозной задержкой.',
                   'Результат не обосновывает добавление второй ветви в основной сервис. Веса сочетания не подбирались под ответы корзин. Негатив не запускали: подтверждённой потребности в таком входе не найдено.']})
    gate=read(root/'catalog-audit/index-reference-gated-v1/index-info.json')
    sections.append({'id':'reference-audit','title':'Каталог: восстановили границу доверия','status':'ready' if gate else 'partial',
      'summary':'Проверка прежнего аудита выявила возврат 17 карантинных изображений через архивный fallback. Ещё два несоответствия нашли при просмотре оригинальных этикеток.',
      'tables':[table('Что означает новый индекс',[('kind','Состояние'),('count','Количество')],[{'kind':'Официальные карточки в текстовом поиске','count':2103},{'kind':'Визуальные эталоны исходного опыта','count':2080},{'kind':'Исключены с записью причины и SHA','count':19},{'kind':'Остались в отдельном индексе после фильтра','count':gate['visual_refs'] if gate else 'ожидается'},{'kind':'Недоступны визуальному поиску; текстовый доступ сохранён','count':len(gate['missing']) if gate else 'ожидается'}])],
      'notes':['Исходный каталог, прошлые результаты и frozen v1 не переписаны. Исправление проверяется отдельными прогонами.',
               'Сокращённый манифест также скрывал различие сухого, полусухого и полусладкого вина. Для разметки теперь используются полные метаданные; одинаковые названия не объединяются автоматически.',
               '2061 оставшийся снимок не означает новую визуальную сертификацию всего каталога. Целостность файла, display-фото, ML-reference и правильный ответ теста — разные проверки.']})
    gate_rows=[]
    for key,name in [('owlv2','OWLv2 · v2'),('yoloe26s','YOLOE-26s')]:
        folder=root/'detectors/reference-gated'/key/'reports'
        svc=scored(folder/'report-all-service.json');ret=scored(folder/'report-all-retrieval.json')
        if svc and ret and name in loaded:
            previous=loaded[name]
            gate_rows.append({'model':name,'before_service':fraction(previous[2]['overall']),
              'after_service':fraction(svc['overall']),'before_top1':fraction(previous[3]['overall']),
              'after_top1':fraction(ret['overall']),'after_top20':fraction(ret['overall'],'correct_top20')})
    if gate_rows:
        sections[-1]['tables'].append(table('Отдельные реальные прогоны после исключения 19 изображений',
          [('model','Решение'),('before_service','Service: до'),('after_service','После'),('before_top1','Retrieval Top‑1: до'),('after_top1','После'),('after_top20','Top‑20 после')],gate_rows))
        sections[-1]['notes'].append('Исключение спорных изображений восстанавливает правило допуска эталонов. Оно само по себе не гарантирует роста метрик; отсутствие изменения на небольшом наборе не оправдывает возврат ошибочных фото.')
    gate2=read(root/'catalog-audit/index-reference-gated-v2/index-info.json')
    if gate2:
        sections[-1]['tables'].append(table('Дополнительная версия допуска v2',
          [('kind','Изменение'),('value','Результат')],
          [{'kind':'Ещё одно фото противоречит сладости карточки','value':'20 исключений суммарно'},
           {'kind':'Визуальные эталоны после дополнительного исключения','value':gate2['visual_refs']},
           {'kind':'Карточки без визуального эталона','value':len(gate2['missing'])}]))
        sections[-1]['notes'].append('После первых прогонов найден ещё один конфликт: фото полусладкого вина в карточке брют. Gate v2 исключает его отдельно. Старые прогоны gate v1 сохранены; сравнение Base и SO400M использует одинаковый gate v2. Версия допуска не равна версии фрагментов этикетки.')
    audit=read(root/'annotation/sealed-v1-audit.json');comparison=read(root/'annotation/comparison-v1.json')
    annotation_tables=[]
    if audit:
        annotation_tables.append(table('Покрытие разметки',[('status','Статус'),('count','Фото')],[{'status':{'exact':'Однозначный ответ','ambiguous':'Несколько возможных вариантов','catalog_unresolved':'Связь с каталогом не разрешена'}.get(k,k),'count':v} for k,v in audit['status_counts'].items()]))
    if comparison:
        real_rows=[]
        for item in comparison['models']:
            if item['variant'] not in ('standalone','all'):continue
            s=item['all'];n=s['exact_denominator']
            row={'model':item['name'],'n':n,'returned':s['exact_response'] if s['exact_response'] is not None else '—','top1':s['top1'],'top5':s['top5'],'top20':s['top20'],'groups':item.get('exact_product_groups'),'macro':round(item['product_macro_top1']*100,1) if item.get('product_macro_top1') is not None else '—'}
            for key in ('familiar12','newly_reviewed88'):
                subset=item['by_prior_seen'].get(key,{})
                row[key]=f"{subset.get('top1',0)}/{subset.get('exact_denominator',0)}"
            real_rows.append(row)
        annotation_tables.append(table('Только подтверждённые ответы',[('model','Решение'),('returned','Верный конечный ответ'),('top1','Top‑1'),('top5','Top‑5'),('top20','Top‑20'),('familiar12','Top‑1: уже были в v1'),('newly_reviewed88','Top‑1: остальные фото'),('macro','Средний Top‑1 по винам, %')],real_rows,note=f"Одинаковая выборка: {audit['exact_images']} фото, {audit['exact_product_groups']} разных wine ID. Все значения Top‑K — число верных среди этих фото." if audit else ''))
    sections.append({'id':'real-photos','title':'100 реальных фотографий организаторов','status':'ready' if comparison else 'partial',
      'summary':'103 исходных файла содержат 100 разных изображений. Разметка проверяется по оригиналам и полным метаданным; ошибочный первый черновик отозван и не участвует в метриках.',
      'tables':annotation_tables,'notes':['Локальные агентские ответы не являются официальным ключом организаторов. Неоднозначные или неразрешённые изображения остаются в учёте покрытия, но не превращаются в выдуманный точный ответ.',
      'Повторные фото одного вина не являются новыми независимыми винами. Поэтому рядом с обычной точностью приведено среднее с равным весом каждого подтверждённого wine ID.',
      'DeepSeek OCR используется как дополнительное наблюдение; его согласие не заменяет проверку. Такой аудит не полностью независим от DeepSeek-бейзлайна.',
      'Top‑1 относится к списку кандидатов; конечный ответ дополнительно зависит от выбора цели и отказа. Эти показатели показаны раздельно.',
      'У кешированных композиций и offline-абляций ответ пересчитан из сохранённых данных. Это проверка качества, а не новое измерение обслуженного HTTP-запроса.']})
    extra=read(root/'public-extra-sections.json')
    if extra:sections.extend(extra)
    sections.append({'id':'licenses','title':'Что можно переносить в основную ветку','status':'ready',
      'summary':'Лицензионные условия оцениваются отдельно от качества. Эти эксперименты не означают автоматический выбор модели для закрытого сервиса.',
      'tables':[table('Код и веса',[('model','Компонент'),('terms','Условия'),('scope','Роль сейчас')],[{'model':'OWLv2 / SigLIP2 / RT-DETR R18','terms':'Apache 2.0','scope':'Основы композиции и дополнительный детектор'},{'model':'YOLOE-26 / YOLO26','terms':'AGPL-3.0 или Enterprise','scope':'Сравнительный эксперимент'},{'model':'MobileCLIP2 в текстовой подготовке YOLOE','terms':'Веса: некоммерческие исследования; код MIT','scope':'Отдельное ограничение зависимости'}])],
      'sources':[{'label':'Ultralytics','url':'https://www.ultralytics.com/license'},{'label':'OWLv2','url':'https://huggingface.co/google/owlv2-base-patch16-ensemble'},{'label':'RT-DETR R18','url':'https://huggingface.co/PekingU/rtdetr_r18vd'},{'label':'MobileCLIP2 weights','url':'https://github.com/apple/ml-mobileclip/blob/main/LICENSE_MODELS'}]})
    return {'schema_version':1,'updated_at':datetime.now(timezone.utc).isoformat(),'sections':sections}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--previous',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--private-gold',type=Path,help='Reviewer-only input. Only aggregate outcome counts are published.')
    a=p.parse_args();obj=report(a.root,a.previous,read(a.private_gold) if a.private_gold else None);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'sections':len(obj['sections']),'status':[s['status'] for s in obj['sections']]}))
if __name__=='__main__':main()
