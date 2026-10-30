"""Generic OCR catalog-attribute guard; no evaluation answers or identifiers."""
import csv
import io
import json
import os
from pathlib import Path
import re
import subprocess
import unicodedata

RU = str.maketrans(dict(zip('абвгдеёжзийклмнопрстуфхцчшщыэюяьъ',
    ['a','b','v','g','d','e','e','zh','z','i','y','k','l','m','n','o','p','r','s','t','u','f','h','ts','ch','sh','sch','y','e','yu','ya','',''])))
ALIASES = {'cabernet':'kaberne','sauvignon':'sovinon','chardonnay':'shardone','merlot':'merlo',
    'muscat':'muskat','muscatel':'muskatel','riesling':'risling','pinot':'pino','noir':'nuar',
    'syrah':'sira','white':'beloe','red':'krasnoe','rose':'rozovoe','rosado':'rozovoe',
    'dry':'suhoe','sweet':'sladkoe','semisweet':'polusladkoe','semidry':'polusuhoe','brut':'bryut'}


def norm(text):
    value = unicodedata.normalize('NFKD', str(text).lower().translate(RU))
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(ALIASES.get(w, w) for w in re.findall('[a-z0-9]+', value))


def attributes(text):
    tokens = set(norm(text).split())
    colors = set()
    for value, forms in [('white', {'beloe','belyy','belyj','belye'}),
                         ('red', {'krasnoe','krasnyy','krasnyj','krasnye'}),
                         ('rose', {'rozovoe','rozovyy','rozovyj','rozovye'})]:
        if tokens & forms:
            colors.add(value)
    sugar = set()
    for value, forms in [('semi_sweet', {'polusladkoe','polusladkiy'}),
                         ('semi_dry', {'polusuhoe','polusuhoj'}),
                         ('sweet', {'sladkoe','sladkiy'}),
                         ('dry', {'suhoe','suhoj','suhoy'}), ('brut', {'bryut'})]:
        if tokens & forms:
            sugar.add(value)
    return colors, sugar


class CatalogAttributes:
    def __init__(self, path, slugs):
        payload = json.loads(Path(path).read_text())
        rows = payload['rows']
        if [r['slug'] for r in rows] != list(slugs[:len(rows)]):
            raise ValueError('OCR catalog slug order mismatch')
        self.rows = [{key: set(r[key]) for key in ('grape','color','sugar')} for r in rows]
        self.rows.extend(dict(grape=set(), color=set(), sugar=set()) for _ in slugs[len(rows):])
        self.vocab = set().union(*(r['grape'] for r in self.rows))

    def query(self, text):
        value = ' ' + norm(text) + ' '
        color, sugar = attributes(text)
        grape = {g for g in self.vocab if ' ' + g + ' ' in value}
        return dict(grape=grape, color=color if len(color) == 1 else set(),
                    sugar=sugar if len(sugar) == 1 else set())

    def eligible(self, text, baseline, candidates):
        query = self.query(text)
        base = self.rows[int(baseline)]
        conflicts = {key for key, q in query.items()
                     if q and base[key] and not (q & base[key])}
        if not conflicts:
            return []
        result = []
        for pos in candidates:
            candidate = self.rows[int(pos)]
            if not any(query[k] & candidate[k] for k in conflicts):
                continue
            if any(q and candidate[k] and not (q & candidate[k]) for k, q in query.items()):
                continue
            result.append(int(pos))
        return result


def recognize(image, assets, preprocess=False, timeout=4, psm=11, return_words=False):
    from PIL import Image, ImageOps
    if preprocess:
        image = ImageOps.autocontrast(image.convert('L'))
        factor = min(2, 2000 / max(image.size))
        image = image.resize((round(image.width * factor), round(image.height * factor)),
                             Image.Resampling.LANCZOS)
    scale = min(1, 2000 / max(image.size))
    if scale < 1:
        image = image.resize((round(image.width * scale), round(image.height * scale)),
                             Image.Resampling.LANCZOS)
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    env = dict(os.environ, TESSDATA_PREFIX=assets['tessdata_dir'], OMP_THREAD_LIMIT='1', OMP_NUM_THREADS='1')
    result = subprocess.run([assets['tesseract'], 'stdin', 'stdout', '-l', 'rus+eng',
                             '--psm', str(psm), '-c', 'tessedit_create_tsv=1'],
                            input=stream.getvalue(), capture_output=True, timeout=timeout, env=env)
    if result.returncode:
        raise ValueError('OCR process failed')
    words = []
    for row in csv.DictReader(io.StringIO(result.stdout.decode()), delimiter='\t',
                              quoting=csv.QUOTE_NONE):
        if len(row) != 12 or None in row or any(v is None for v in row.values()):
            raise ValueError('Invalid OCR TSV columns')
        confidence = float(row['conf'])
        if not -1 <= confidence <= 100:
            raise ValueError('Invalid OCR confidence')
        if int(row['level']) == 5 and row['text'].strip() and confidence >= 60:
            words.append(dict(text=row['text'],confidence=confidence))
    return words if return_words else ' '.join(w['text'] for w in words)


def rerank(scores, text, catalog):
    import numpy as np
    order = np.argsort(-scores)
    matches = catalog.eligible(text, order[0], order[:5])
    if matches and scores[order[0]] - scores[matches[0]] <= .01:
        winner = matches[0]
        order[:5] = np.array([winner] + [int(v) for v in order[:5] if v != winner])
    return order
