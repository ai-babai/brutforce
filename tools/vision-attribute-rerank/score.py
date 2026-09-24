#!/usr/bin/env python3
"""Score already-frozen rerank outputs; never called during gold-blind generation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique(rows: list[dict], key: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        value = row[key]
        if value in result:
            raise ValueError(f'duplicate {key}: {value}')
        result[value] = row
    return result


def score_service(action: str, slug: str | None, expected: dict) -> bool:
    wanted = expected.get('expected_action') or ('match' if expected.get('expected_slug') else '')
    if action != wanted:
        return False
    return action != 'match' or slug == expected.get('expected_slug')


def rank(slugs: list[str], target: str) -> int:
    return slugs.index(target) + 1 if target in slugs else 0


def score_run(name: str, input_path: Path, output_path: Path,
              frozen: dict[str, dict], organizer: dict[str, dict]) -> tuple[dict, list[dict]]:
    sources = unique([json.loads(x) for x in input_path.read_text().splitlines()], 'case_id')
    results = unique([json.loads(x) for x in output_path.read_text().splitlines()], 'case_id')
    if set(sources) != set(results):
        raise ValueError(f'case set mismatch: {name}')
    is_frozen = name.startswith('frozen-')
    labels = frozen if is_frozen else organizer
    count = {'input_rows': len(sources), 'graded': 0, 'baseline_top1': 0, 'rerank_top1': 0,
             'baseline_top5': 0, 'rerank_top5': 0, 'baseline_top20': 0, 'rerank_top20': 0,
             'changed_rank_lists': 0, 'changed_top1': 0, 'fixed': 0, 'regressed': 0,
             'candidate_rank_improved': 0, 'candidate_rank_worsened': 0}
    cases = []
    for cid, source in sources.items():
        result = results[cid]
        if result['changed']:
            count['changed_rank_lists'] += 1
        if result['before'] != result['after'] and not result['changed']:
            raise ValueError(f'changed flag mismatch: {cid}')
        if sorted(result['before']) != sorted(result['after']):
            raise ValueError(f'candidate set changed: {cid}')
        if result['before'] and result['before'][0] != result['after'][0]:
            count['changed_top1'] += 1
        label = labels.get(cid)
        if not label:
            continue
        if is_frozen:
            if not label['verified']:
                continue
            expected = label.get(source['track'])
            if not expected:
                continue
        else:
            if label['status'] != 'exact':
                continue
            expected = {'expected_action': 'match', 'expected_slug': label['exact_slug']}
        count['graded'] += 1
        if source['track'] == 'service':
            payload = source.get('result') or source
            prediction = payload.get('prediction') or payload.get('predictions', {}).get('all') or payload
            action = prediction.get('action') or ('match' if prediction.get('slug') else '')
            old_slug = result['before_prediction_slug']
            new_slug = result['after_prediction_slug']
            old_correct = score_service(action, old_slug, expected)
            new_correct = score_service(action, new_slug, expected)
            old_rank = rank(result['before'], expected.get('expected_slug', '')) if expected.get('expected_slug') else 0
            new_rank = rank(result['after'], expected.get('expected_slug', '')) if expected.get('expected_slug') else 0
            count['baseline_top5'] += 0 < old_rank <= 5
            count['rerank_top5'] += 0 < new_rank <= 5
            count['baseline_top20'] += old_rank > 0
            count['rerank_top20'] += new_rank > 0
        else:
            old_rank = rank(result['before'], expected['expected_slug'])
            new_rank = rank(result['after'], expected['expected_slug'])
            old_correct, new_correct = old_rank == 1, new_rank == 1
            count['baseline_top5'] += 0 < old_rank <= 5
            count['rerank_top5'] += 0 < new_rank <= 5
            count['baseline_top20'] += old_rank > 0
            count['rerank_top20'] += new_rank > 0
        count['baseline_top1'] += old_correct
        count['rerank_top1'] += new_correct
        count['fixed'] += new_correct and not old_correct
        count['regressed'] += old_correct and not new_correct
        count['candidate_rank_improved'] += old_rank > 0 and 0 < new_rank < old_rank
        count['candidate_rank_worsened'] += old_rank > 0 and new_rank > old_rank
        if result['changed']:
            cases.append({'case_id': cid, 'track': source['track'], 'expected': expected,
                          'old_rank': old_rank, 'new_rank': new_rank,
                          'old_correct': old_correct, 'new_correct': new_correct,
                          'before_prediction_slug': result['before_prediction_slug'],
                          'after_prediction_slug': result['after_prediction_slug'],
                          'attributes': result['attributes'], 'groups': result['groups']})
    count['delta_top1'] = count['rerank_top1'] - count['baseline_top1']
    count['delta_top5'] = count['rerank_top5'] - count['baseline_top5']
    count['delta_top20'] = count['rerank_top20'] - count['baseline_top20']
    return count, cases


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold-blind-dir', type=Path, required=True)
    parser.add_argument('--frozen-gold', type=Path, required=True)
    parser.add_argument('--frozen-erratum', type=Path, required=True)
    parser.add_argument('--organizer-seal', type=Path, required=True)
    parser.add_argument('--private-out', type=Path, required=True)
    parser.add_argument('--public-out', type=Path, required=True)
    args = parser.parse_args()
    if args.private_out.exists() or args.public_out.exists():
        raise FileExistsError('diagnostic outputs already exist')
    manifest_path = args.gold_blind_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    frozen_gold = json.loads(args.frozen_gold.read_text())
    frozen = unique(frozen_gold['cases'], 'case_id')
    erratum = json.loads(args.frozen_erratum.read_text())
    if erratum['source_gold_file_sha256'] != sha(args.frozen_gold):
        raise ValueError('erratum source gold hash mismatch')
    for item in erratum['corrections']:
        cid, track = item['case_id'], item['track']
        if frozen[cid][track] != item['old_gold']:
            raise ValueError(f'erratum old gold mismatch: {cid}')
        frozen[cid][track] = item['new_gold']
    organizer = unique([json.loads(x) for x in args.organizer_seal.read_text().splitlines()], 'image_id')
    public_rows, private_rows = [], []
    for run in manifest['runs']:
        source, output = Path(run['input']), Path(run['output'])
        if sha(source) != run['input_sha256'] or sha(output) != run['output_sha256']:
            raise ValueError(f'input/output changed after gold-blind freeze: {run["name"]}')
        summary, cases = score_run(run['name'], source, output, frozen, organizer)
        public_rows.append({'name': run['name'], **summary})
        private_rows.append({'name': run['name'], 'cases': cases})
    args.private_out.parent.mkdir(parents=True, exist_ok=True)
    args.private_out.write_text(json.dumps({'schema_version': 1, 'gold_blind_manifest_sha256': sha(manifest_path),
        'frozen_gold_sha256': sha(args.frozen_gold), 'erratum_sha256': sha(args.frozen_erratum),
        'organizer_seal_sha256': sha(args.organizer_seal), 'runs': private_rows},
        ensure_ascii=False, indent=2) + '\n')
    args.public_out.parent.mkdir(parents=True, exist_ok=True)
    args.public_out.write_text(json.dumps({'schema_version': 1,
        'kind': 'POST-HOC DEVELOPMENT: offline Top-20 attribute rerank, not independent validation or full HTTP timing',
        'gold_blind_manifest_sha256': sha(manifest_path),
        'frozen_gold_view': 'separate case-000137 lineage erratum overlay',
        'runs': public_rows}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'runs': len(public_rows), 'net_top1': sum(x['delta_top1'] for x in public_rows),
                      'fixed': sum(x['fixed'] for x in public_rows),
                      'regressed': sum(x['regressed'] for x in public_rows)}))


if __name__ == '__main__':
    main()
