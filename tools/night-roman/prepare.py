"""Build a gold-blind Roman comparison bundle from frozen B predictions."""
import argparse
import hashlib
import json
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def rows(path):
    return [json.loads(line) for line in path.open(encoding='utf-8')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = Path('/Users/skif/ml-data/brutforce/integration-20260925-1700/model')
    roman = Path('/Users/skif/ml-data/brutforce/night-20260925/roman/roman-source')
    catalog = Path('/Users/skif/ml-data/brutforce/eval-v1/private/catalog-source/organizer-catalog-20260919.jsonl')
    cards = {x['canonical_slug']: x for x in rows(roman / 'wines.jsonl') if not x['is_alias']}
    organizer = {x['slug']: x for x in rows(catalog)}
    locations = {x['slug']: x for x in json.loads((roman / 'reference-locations.json').read_text())}
    gate = json.loads((roman / 'gatev2-availability.json').read_text())
    sources = [
        ('frozen', Path('/Users/skif/ml-data/brutforce/night-20260925/common/eval-public-v2.json'), source / 'softgate-B-eval.jsonl'),
        ('organizer', source / 'organizer-public.json', source / 'softgate-B-organizer.jsonl'),
    ]
    result = []
    refs = {}
    paths = {'roman_project': '/srv/lct/data/roman/vino/experiment-handoff-20260925/project',
             'catalog_media': '/srv/lct/data/catalog/media/original'}
    for basket, public_path, prediction_path in sources:
        public = json.loads(public_path.read_text(encoding='utf-8'))
        cases = {x['case_id']: x for x in public['cases']}
        predictions = rows(prediction_path)
        if len(predictions) != len(cases) or len({x['case_id'] for x in predictions}) != len(cases):
            raise ValueError('B rows do not cover public input manifest')
        for row in predictions:
            case = cases[row['case_id']]
            if case['sha256'] != row['query_sha256'] or case['track'] != row['track']:
                raise ValueError('B/public input mismatch')
            image = source / 'input-stage' / case['path']
            if not image.is_file() or sha256(image) != case['sha256']:
                raise ValueError('Missing or mutated query ' + row['case_id'])
            response = row.get('result') or {}
            ranked = response.get('ranked_slugs') or []
            scored = response.get('variants_top20', {}).get('all') or []
            if ranked and [x['slug'] for x in scored[:len(ranked)]] != ranked:
                raise ValueError('B scores/ranks mismatch ' + row['case_id'])
            if len(ranked) not in (0, 20):
                raise ValueError('Unexpected B pool length')
            for slug in ranked:
                if slug not in organizer:
                    raise ValueError('Candidate outside organizer catalog')
                if slug in refs:
                    continue
                if not gate[slug]:
                    refs[slug] = dict(source='excluded_reference', sha256=None, remote_path=None)
                    continue
                card = cards.get(slug)
                if card and card.get('reference'):
                    ref = card['reference']
                    refs[slug] = dict(source='roman_gallery', sha256=ref['sha256'],
                        remote_path=paths['roman_project'] + '/artifacts/transfer/svoe-db-20260922-v2/' + ref['path'])
                else:
                    location = locations[slug]
                    digest = location['sha256'] if location['available'] else None
                    refs[slug] = dict(source='organizer_exact' if digest else 'missing',
                        sha256=digest, remote_path=location['source'] if digest else None)
            result.append(dict(basket=basket, case_id=row['case_id'], track=row['track'],
                query_sha256=case['sha256'], query_path=str(image),
                b_status=row.get('http_status'), b_error=row.get('error'),
                b_action=response.get('action'), b_slug=response.get('slug'),
                ranked_slugs=ranked, ranked_scores=[x['score'] for x in scored[:len(ranked)]],
                b_elapsed_ms=row.get('elapsed_ms')))
    if len(result) != 316 or sum(x['basket'] == 'frozen' for x in result) != 213:
        raise ValueError('Full frozen+organizer coverage required')
    files = {'requests.jsonl': result, 'references.jsonl': [dict(slug=s, **refs[s]) for s in sorted(refs)],
             'cards.jsonl': [dict(slug=s, card=cards.get(s), organizer=organizer[s]) for s in sorted(refs)]}
    for name, records in files.items():
        with (out / name).open('w', encoding='utf-8') as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
    provenance = dict(protocol='roman-on-B-20260925-v1', gold_present=False,
        frozen_requests=213, organizer_requests=103,
        frozen_suite_version='v2', frozen_suite_hash='0691d98b19d92647a41fe4fccd92a36ab23255c02ed65c37830d38a15f379daa',
        frozen_public_manifest_sha256=sha256(sources[0][1]),
        b_eval_sha256=sha256(sources[0][2]), b_organizer_sha256=sha256(sources[1][2]),
        roman_cards_sha256=sha256(roman / 'wines.jsonl'), organizer_catalog_sha256=sha256(catalog),
        reference_locations_sha256=sha256(roman / 'reference-locations.json'),
        reference_gate_sha256=sha256(roman / 'gatev2-availability.json'),
        files={name: sha256(out / name) for name in files},
        references=dict(total=len(refs), unavailable=sum(not r['sha256'] for r in refs.values()),
            excluded=sum(r['source'] == 'excluded_reference' for r in refs.values())))
    (out / 'provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(provenance, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
