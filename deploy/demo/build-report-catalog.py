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
    note = 'Предыдущая версия' if '/previous' in rel else 'Базовая версия' if '/baseline/' in rel else 'Первая итерация' if '/mascots/v1/' in rel else 'Исторический документ' if 'prod-readiness-' in rel and p.name != 'index.html' else 'Сохранённый материал проекта'
    items.append({'path': rel, 'title': title, 'group': group, 'note': note})
(root / 'report-catalog.json').write_text(json.dumps({
    'generatedAt': datetime.now(timezone.utc).isoformat(),
    'groups': [{'id': key, 'title': title} for key, title in groups],
    'items': items,
}, ensure_ascii=False, indent=2) + '\n')
print('REPORT_CATALOG_PAGES', len(items))
