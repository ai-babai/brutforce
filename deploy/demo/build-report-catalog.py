#!/usr/bin/env python3
"""Index the published read-only archive; never copy report data into Git."""
from pathlib import Path
import json
import re
import sys
from datetime import datetime, timezone

root = Path(sys.argv[1])
groups = [
    ('catalog', 'Каталог и синтетика'),
    ('quality', 'Качество и эксперименты'),
    ('product', 'Продуктовые исследования'),
    ('design', 'Дизайн и макеты'),
    ('delivery', 'Готовность и сдача'),
    ('project', 'Материалы проекта'),
]
overrides = {
    'BB-INSTRUCTION.html': 'Инструкция BB · исторический документ',
    'PROMPT.html': 'Задание следующему исполнителю · исторический документ',
    'REPOSITORY-PUBLICATION.html': 'Публикация репозитория · историческое решение',
}
items = []
for p in sorted(root.rglob('*.html')):
    rel = p.relative_to(root).as_posix()
    if rel == 'index.html' or '/data/runs/' in rel:
        continue
    source = p.read_text()
    match = re.search(r'<title[^>]*>(.*?)</title>', source, re.S | re.I)
    title = re.sub(r'\s+', ' ', match[1]).strip() if match else rel
    title = overrides.get(p.name, title) if 'prod-readiness-' in rel else title
    if '/catalog-' in rel:
        group = 'catalog'
    elif '/prod-readiness-' in rel or '/solution-audit-' in rel:
        group = 'delivery'
    elif any(part in rel for part in ['/mascots/', '/v2/', '/v3/']):
        group = 'design'
    elif any(part in rel for part in ['/vision/', '/fast-gpu-', '/training/', '/siglip-', '/prompt-camera-']) or rel in ['roman/index.html', 'roman/stage2.html']:
        group = 'quality'
    elif rel.startswith('project/') or rel.startswith('roman/overview/'):
        group = 'project'
    else:
        group = 'product'
    topic = 'Обзор'
    label = title.replace('—', '·')
    short = {
        'maks/fast-gpu-20260927/index.html': ('CPU и GPU', 'Общий срез'),
        'maks/fast-gpu-20260927/cpu/index.html': ('CPU и GPU', 'Быстрый CPU'),
        'maks/fast-gpu-20260927/gpu/index.html': ('CPU и GPU', 'Качество GPU'),
        'maks/fast-gpu-20260927/final/index.html': ('CPU и GPU', 'Итоговое сравнение CPU F9 и GPU G3'),
        'maks/fast-gpu-20260927/primary-vs-best/index.html': ('CPU и GPU', 'Прод и сильнейшие кандидаты'),
        'maks/vision/gallery/detectors.html': ('Компьютерное зрение', 'Методы без обучения'),
        'maks/vision/gallery/integration.html': ('Компьютерное зрение', 'Интеграция поиска'),
        'maks/vision/gallery/night.html': ('Компьютерное зрение', 'CPU, геометрия и Qwen'),
        'maks/vision/gallery/report.html': ('Компьютерное зрение', 'Пилот на 100 изображениях'),
        'maks/vision/gallery/next.html': ('Компьютерное зрение', 'Следующий эксперимент'),
        'maks/vision/gallery/index.html': ('Компьютерное зрение', 'Данные обучения и пилота'),
        'maks/vision/index.html': ('Проверки и стенд', 'Проверка поиска вина'),
        'maks/vision/guide.html': ('Проверки и стенд', 'Как запускали стенд'),
        'maks/vision/requirements.html': ('Проверки и стенд', 'Требования и источники'),
        'roman/index.html': ('Исследования Романа', 'Журнал исследований'),
        'roman/stage2.html': ('Исследования Романа', 'Полный цикл, этап 2'),
        'maks/training/index.html': ('Обучение и аугментации', 'Прогресс SigLIP'),
        'maks/siglip-augmentation-20261001/index.html': ('Обучение и аугментации', 'Вариации каталожных сцен'),
        'maks/prompt-camera-pilot10-20261001/index.html': ('Обучение и аугментации', 'Пять ракурсов смартфона'),
        'maks/catalog-repair-20260927/index.html': ('Данные каталога', 'Аудит и ремонт каталога'),
        'maks/catalog-synthetic-gallery-20261001/index.html': ('Данные каталога', 'Галерея синтетических вин'),
    }
    if rel in short:
        topic, label = short[rel]
    elif group == 'design':
        if '/icons/' in rel:
            topic = 'Иконка приложения'
            label = {'index.html': 'Восемь направлений', 'round2.html': 'Вторая серия', 'round3.html': 'Третья серия', 'export-check.html': 'Проверка экспорта'}.get(p.name, label)
        elif '/v2/' in rel:
            topic = 'Интерфейс v2'
            label = 'Предыдущий вариант' if '/previous/' in rel else 'Основной макет'
        elif '/air35/' in rel or '/air/' in rel:
            topic = 'Варианты Air'
            label = ('Air 3.5' if '/air35/' in rel else 'Air 3.4') + (' · обзор' if p.name == 'review.html' else ' · макет')
        elif '/v3/' in rel:
            topic = 'Интерфейс v3'
            label = 'Предыдущий вариант 3.2' if '/previous-v3.2/' in rel else 'Предыдущий вариант' if '/previous/' in rel else 'Сравнение 3.2 на iPhone' if p.name == 'review-v3.2.html' else 'Обзор дизайна 3.3' if p.name == 'review.html' else 'Основной макет'
        elif '/baseline/' in rel or '/mascots/v1/index.html' in rel:
            topic = 'Ранние референсы'
            label = 'Базовая версия Atlas' if '/baseline/' in rel else 'Первая версия Atlas'
        else:
            topic = 'Маскоты и сцены'
            label = {'index.html': 'Лаборатория маскотов', 'glass.html': 'Прозрачность и мобильные элементы', 'journey-prototype.html': 'Макет пути пользователя', 'journeys.html': 'Путь в винной истории', 'physical.html': 'Фото становится предметом', 'prototype.html': 'Композиция с маскотом', 'mascot.html': 'Первая итерация маскота'}.get(p.name, label)
    elif group == 'product':
        topic = 'Сценарии и гипотезы' if any(v in rel for v in ['/scenarios/', '/hypotheses/', '/sigma-ux-']) else 'Макеты и поведение' if any(v in rel for v in ['/prototypes/', '/behavior/']) else 'Референсы и навигация'
        label = {'maks/index.html': 'Wine UX Atlas', 'maks/behavior/index.html': 'Карта поведения', 'maks/wine-after-scan/index.html': 'Референсы после сканирования', 'maks/wine-after-scan/hub/index.html': 'Навигатор исследований', 'maks/wine-after-scan/scenarios/index.html': 'Зачем фотографируют вино', 'maks/wine-after-scan/hypotheses/index.html': 'Пять первых гипотез', 'maks/wine-after-scan/prototypes/index.html': 'Компактные макеты', 'maks/wine-after-scan/sigma-ux-20260927/index.html': 'Карта гипотез и примерки', 'maks/wine-after-scan/sigma-ux-20260927/previous.html': 'Предыдущая волна гипотез'}.get(rel, label)
    elif group == 'delivery':
        topic = 'Исторические задания' if p.name in overrides else 'Планы и обзоры' if p.name in ['PLAN.html', 'REMAINING-PLAN.html', 'PRO-REVIEW.html', 'AUDIT-STATUS.html'] else 'Готовность проекта'
        label = {'index.html': 'Прод и сдача', 'CHECKLIST.html': 'Чек-лист готовности', 'RECHECK.html': 'Повторная проверка', 'REQUIREMENTS.html': 'Обязательные требования', 'PLAN.html': 'План сдачи', 'REMAINING-PLAN.html': 'Остаточный план', 'PRO-REVIEW.html': 'Два раунда Pro', 'AUDIT-STATUS.html': 'Исторический аудит', 'BB-INSTRUCTION.html': 'Инструкция BB', 'PROMPT.html': 'Задание следующему исполнителю', 'REPOSITORY-PUBLICATION.html': 'Решение о публикации'}.get(p.name, label)
        if '/solution-audit-' in rel:
            label = 'Светофор готовности'
    elif group == 'project':
        topic = 'Презентация и прототип'
        label = 'Презентация проекта' if rel.startswith('project/') else 'Версия Романа'
    items.append({'path': rel, 'title': title, 'label': label, 'group': group, 'topic': topic})
(root / 'report-catalog.json').write_text(json.dumps({
    'generatedAt': datetime.now(timezone.utc).isoformat(),
    'groups': [{'id': key, 'title': title} for key, title in groups],
    'items': items,
}, ensure_ascii=False, indent=2) + '\n')
print('REPORT_CATALOG_PAGES', len(items))
