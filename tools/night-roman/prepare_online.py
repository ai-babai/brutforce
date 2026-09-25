"""Prepare public, gold-blind full-HTTP B→Roman inputs for every request/catalog row."""
import argparse
import hashlib
import json
from pathlib import Path


def rows(path):
    return [json.loads(line) for line in path.open(encoding='utf-8')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_rows(path, items):
    with path.open('w', encoding='utf-8') as stream:
        for item in items:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    a = p.parse_args()
    root = a.root.resolve()
    source = root / 'roman-source'
    output = root / 'online-input-v1'
    output.mkdir(exist_ok=True)
    input_rows = rows(root/'input-v1/requests.jsonl')
    if len(input_rows) != 316:
        raise ValueError('316 public request rows required')
    requests = [dict(case_id=x['case_id'],basket=x['basket'],track=x['track'],
        query_sha256=x['query_sha256'],query_path=x['query_path']) for x in input_rows]
    cards = {x['canonical_slug']:x for x in rows(source/'wines.jsonl') if not x['is_alias']}
    organizer_path = Path('/Users/skif/ml-data/brutforce/eval-v1/private/catalog-source/organizer-catalog-20260919.jsonl')
    organizer = {x['slug']:x for x in rows(organizer_path)}
    gate = json.loads((source/'gatev2-availability.json').read_text())
    locations = {x['slug']:x for x in json.loads((source/'reference-locations.json').read_text())}
    if len(organizer) != len(gate) or set(organizer) != set(gate) or set(gate) != set(locations):
        raise ValueError('Catalog/gate/reference slug mismatch')
    refs = []
    ref_sources = []
    for slug in sorted(organizer):
        location = locations[slug]
        valid = bool(gate[slug])
        digest = location['sha256'] if valid else None
        if valid and (not location['available'] or not digest or not location['source']):
            raise ValueError('Missing valid reference '+slug)
        card_ref = (cards.get(slug) or {}).get('reference')
        if valid and card_ref and card_ref['sha256'] != digest:
            raise ValueError('Roman/reference SHA mismatch '+slug)
        refs.append(dict(slug=slug, sha256=digest, source='gatev2_exact' if valid else 'excluded_reference'))
        if valid:
            ref_sources.append(dict(slug=slug, sha256=digest, source_path=location['source']))
    card_rows = [dict(slug=s,card=cards.get(s),organizer=organizer[s]) for s in sorted(organizer)]
    files = {'requests.jsonl':requests,'references.jsonl':refs,'cards.jsonl':card_rows,
        'reference-sources.jsonl':ref_sources}
    for name, items in files.items():
        write_rows(output/name,items)
    provenance = dict(protocol='fresh-B-HTTP-to-Roman-20260925-v1',gold_present=False,
        public_requests=316, frozen_requests=213,organizer_requests=103,
        catalog_slugs=len(organizer),valid_reference_slugs=len(ref_sources),
        source_sha256=dict(wines=sha(source/'wines.jsonl'),gate=sha(source/'gatev2-availability.json'),
            locations=sha(source/'reference-locations.json'),organizer_catalog=sha(organizer_path)),
        files={name:sha(output/name) for name in files})
    (output/'provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(provenance,ensure_ascii=False))


if __name__ == '__main__':
    main()
