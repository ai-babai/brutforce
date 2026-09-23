"""Fixed public-catalog lexical matcher shared by all OCR baselines.

Only the public organizer CSV and sealed allowed-slug list are inputs. No case
labels, gold, or source-image mappings are read here.
"""

import csv
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


DATA = Path('/Users/skif/ml-data/brutforce/eval-v1')
CSV = Path('/Users/skif/ml-data/brutforce/materials/2026-09-19-organizers/dataset/strapi_output0709.csv')
RU = str.maketrans({'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'i','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ы':'y','э':'e','ю':'yu','я':'ya','ь':'','ъ':''})
GENERIC = {'vino','wine','beloe','krasnoe','suhoe','polusuhoe','polusladkoe','sovinion','cabernet','kaberne','bryut','brut','reserve','rezerv','vinodelnia','rossiya','russia','vinograd','vintage','alkogol','proizvedeno','cru','estate'}


def norm(s):
    s = unicodedata.normalize('NFKC', str(s or '')).lower().translate(RU)
    return ' '.join(re.findall(r'[a-z0-9]+', s))


def grams(s):
    s = '  ' + norm(s) + '  '
    return Counter(s[i:i + 3] for i in range(len(s) - 2))


class Matcher:
    def __init__(self):
        allowed = set(json.loads((DATA / 'catalog/slugs.json').read_text()))
        rows = {}
        with CSV.open(encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                slug = row['Slug'].strip()
                if slug in allowed and slug not in rows:
                    rows[slug] = row
        if len(rows) != len(allowed):
            raise ValueError('Public catalog and organizer CSV do not align')
        self.rows = rows
        self.docs = {}
        df = Counter()
        for slug, row in rows.items():
            title = norm(row['Название вина'])
            winery = norm(row['Винодельня'])
            # Title and producer dominate; slug retains transliterated aliases.
            doc = f'{winery} {winery} {title} {title} {norm(slug)}'
            g = grams(doc)
            self.docs[slug] = (g, set((winery + ' ' + title).split()), row)
            df.update(g.keys())
        self.idf = {g: math.log(1 + len(rows) / (1 + n)) for g, n in df.items()}
        self.doc_norm = {s: math.sqrt(sum((v * self.idf.get(k, 1)) ** 2 for k, v in g.items())) for s, (g, _, _) in self.docs.items()}

    def rank(self, obj, limit=20):
        raw = str(obj.get('raw_text') or '')
        producer = str(obj.get('producer') or '')
        name = str(obj.get('wine_name') or '')
        variety = str(obj.get('variety') or '')
        vintage = str(obj.get('vintage') or '')
        query = f'{producer} {producer} {name} {name} {raw} {variety} {vintage}'
        q = grams(query)
        if len(norm(query)) < 4:
            return []
        qnorm = math.sqrt(sum((v * self.idf.get(k, 1)) ** 2 for k, v in q.items())) or 1
        query_terms = {w for w in norm(' '.join([producer, name, raw])).split() if len(w) >= 3 and w not in GENERIC}
        out = []
        for slug, (dg, dtokens, row) in self.docs.items():
            cosine = sum(v * dg.get(k, 0) * self.idf.get(k, 1) ** 2 for k, v in q.items()) / (qnorm * self.doc_norm[slug])
            overlap = len(query_terms & dtokens) / max(1, len(query_terms))
            score = .72 * cosine + .28 * overlap
            out.append((score, slug))
        out.sort(reverse=True)
        return [{'slug': slug, 'score': round(score, 4), 'title': self.rows[slug]['Название вина'].strip(), 'producer': self.rows[slug]['Винодельня'].strip()} for score, slug in out[:limit]]
