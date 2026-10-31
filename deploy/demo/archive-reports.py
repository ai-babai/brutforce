#!/usr/bin/env python3
"""Adapt the copied historical report roots to this read-only archive."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
old_hosts = {
    'reps.maks.dzap.pw': '/reports/maks',
    'reps.roman.dzap.pw': '/reports/roman',
    'train.maks.dzap.pw': '/reports/maks/training',
    'cv.ops.dzap.pw': '/reports/maks/vision',
    'app.dzap.pw': '',
    'brutforce.dzap.pw': '/reports/project',
}
report_roots = ['view', 'behavior', 'mascots', 'wine-after-scan', 'v2', 'v3', 'vision',
                'solution-audit-20260927', 'prod-readiness-20260928']
changed = 0
for p in root.rglob('*'):
    if p.suffix not in ('.html', '.js', '.css', '.json') or not p.is_file():
        continue
    s = p.read_text(errors='strict')
    new = s
    for host, prefix in old_hosts.items():
        new = new.replace('https://' + host, prefix).replace('http://' + host, prefix)
    for name in report_roots:
        new = re.sub(r'([\x22\x27\x60])/' + re.escape(name) + r'(?=[/#?\x22\x27\x60])',
                     lambda m: m[1] + '/reports/maks/' + ('index.html' if name == 'view' else name), new)
    if p.relative_to(root).as_posix().startswith('maks/vision/'):
        new = re.sub(r'([\x22\x27\x60])/data(?=[/\x22\x27\x60])', lambda m: m[1] + '/reports/maks/vision/gallery', new)
        for name in ['style.css', 'app.js', 'guide.html', 'requirements.html', 'requirements.css', 'requirements.js']:
            new = re.sub(r'([\x22\x27\x60])/' + re.escape(name) + r'(?=[?\x22\x27\x60])', lambda m: m[1] + '/reports/maks/vision/' + name, new)
        new = re.sub(r'([\x22\x27\x60])/(?=[?\x22\x27\x60])', lambda m: m[1] + '/reports/maks/vision/', new)
    if 'project' in p.relative_to(root).parts:
        new = new.replace('/api-status', '/v2/catalog?limit=1').replace('PROD API работает', 'Демо API работает').replace('PROD API недоступен', 'Демо API недоступен').replace('каталога PROD', 'каталога демо')
        for name in ['icons', 'files', 'icon.png', 'contest-glass-010.png', 'mascot-hold-2d-alpha.webp', 'svoe-vino-logo.svg', 'PlayfairDisplay-VariableFont_wght.woff2', 'onest-2.woff2', 'app-home-preview.webp', 'app-home-preview-source.png', 'ui-demo.mp4']:
            new = re.sub(r'([\x22\x27\x60])/' + re.escape(name) + r'(?=[/\x22\x27\x60])',
                         lambda m: m[1] + '/reports/project/' + name, new)
        new = re.sub(r'<a\b[^>]*href=[\x22\x27][^\x22\x27]*brutforce-data\.tar[\x22\x27][\s\S]*?</a>', '', new)
    new = new.replace('/reports/maks/v2/catalog', '/v2/catalog').replace('/reports/maks/mascots/baseline/mascot.html', '/reports/maks/mascots/v1/mascot.html')
    if p.relative_to(root).as_posix() == 'maks/mascots/baseline/index.html':
        new = new.replace('href="mascot.html"', 'href="../v1/mascot.html"')
    if p.relative_to(root).as_posix() == 'maks/index.html':
        new = new.replace('BrutForce · архив отчётов</a>', 'Все отчёты BrutForce · полный каталог →</a>')
    if p.suffix == '.html' and 'brut-demo-archive-notice' not in new:
        notice = '<aside id="brut-demo-archive-notice" style="padding:10px 16px;background:#faf8f3;color:#694657;border-bottom:1px solid #d8cdd2;font:13px/1.5 system-ui"><a href="/reports/" style="color:inherit">BrutForce · архив отчётов</a> · Сохранённое состояние. Распознавание, загрузки и новые прогоны отключены.</aside>'
        new = re.sub(r'(<body\b[^>]*>)', lambda m: m[0] + notice, new, count=1, flags=re.I)
        new = re.sub(r'(<input\b[^>]*type=[\x22\x27]file[\x22\x27])', r'\1 disabled', new, flags=re.I)
    if p.name == 'app.js' and p.parent.name == 'roman':
        new = new.replace('refreshReferenceLive(); setInterval(refreshReferenceLive,30000);', '// Live collector retired; report remains a frozen archive.')
    if p.name == 'index.html' and p.parent.name == 'roman':
        new = re.sub(r'<a\b[^>]*href=[\x22\x27]review.html[\x22\x27][^>]*>[\s\S]*?</a>', '<span>07 Проверка референсов · завершена</span>', new)
    if new != s:
        p.write_text(new)
        changed += 1
print('REPORT_FILES_ADAPTED', changed)

# Saved review snapshots originally lived alongside the current report.
for name in ['previous', 'previous-v3.2']:
    p = root / 'maks/v3' / name / 'index.html'
    if not p.exists():
        continue
    s = p.read_text()
    for attr, url in re.findall(r'(href|src)="([^"#]+)"', s):
        if url.startswith(('/', 'http', 'data:')) or (p.parent / url).exists():
            continue
        if url.startswith(name + '/') and (p.parent / url[len(name) + 1:]).exists():
            target = url[len(name) + 1:]
        elif (p.parent.parent / url).exists():
            target = '../' + url
        else:
            continue
        s = s.replace(attr + '="' + url + '"', attr + '="' + target + '"')
    p.write_text(s)

vision = root / 'maks/vision'
if vision.is_dir():
    import shutil
    shutil.copyfile(Path(__file__).with_name('archived-image.svg'), vision / 'archived-image.svg')
    p = vision / 'index.html'
    if p.exists():
        p.write_text(p.read_text().replace('<button id="download"', '<button disabled title="Input package is not included in this archive" id="download"'))
