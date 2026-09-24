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


def validate_identity(source: dict, expected_sha: str, suite_hash: str | None) -> None:
    observed = source.get('image_sha256') or source.get('query_sha256')
    nested = (source.get('result') or {}).get('image_sha256')
    if observed:
        if observed != expected_sha:
            raise ValueError(f'query image SHA mismatch: {source["case_id"]}')
    elif not suite_hash or source.get('suite_hash') != suite_hash:
        raise ValueError(f'missing/mismatched suite identity: {source["case_id"]}')
    if nested and nested != expected_sha:
        raise ValueError(f'nested image SHA mismatch: {source["case_id"]}')


def score_run(name: str, input_path: Path, output_path: Path,
              frozen: dict[str, dict], organizer: dict[str, dict],
              frozen_images: dict[str, str], organizer_images: dict[str, str],
              suite_hash: str, track_filter: str | None = None) -> tuple[dict, list[dict]]:
    sources = unique([json.loads(x) for x in input_path.read_text().splitlines()], 'case_id')
    results = unique([json.loads(x) for x in output_path.read_text().splitlines()], 'case_id')
    if set(sources) != set(results):
        raise ValueError(f'case set mismatch: {name}')
    is_frozen = name.startswith('frozen-')
    expected_images = frozen_images if is_frozen else organizer_images
    if set(sources) != set(expected_images):
        raise ValueError(f'input case coverage mismatch: {name}')
    labels = frozen if is_frozen else organizer
    count = {'input_rows': sum(not track_filter or source['track'] == track_filter for source in sources.values()),
             'graded': 0, 'baseline_top1': 0, 'rerank_top1': 0,
             'baseline_top5': 0, 'rerank_top5': 0, 'baseline_top20': 0, 'rerank_top20': 0,
             'changed_rank_lists': 0, 'changed_top1': 0, 'fixed': 0, 'regressed': 0,
             'candidate_rank_improved': 0, 'candidate_rank_worsened': 0}
    cases = []
    for cid, source in sources.items():
        validate_identity(source, expected_images[cid], suite_hash if is_frozen else None)
        if track_filter and source['track'] != track_filter:
            continue
        result = results[cid]
        if result['track'] != source['track']:
            raise ValueError(f'output track mismatch: {cid}')
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
        transport_ok = source.get('status', 'ok') == 'ok' and source.get('http_status', 200) == 200
        if source['track'] == 'service':
            payload = source.get('result') or source
            prediction = payload.get('prediction') or payload.get('predictions', {}).get('all') or payload
            action = prediction.get('action') or ('match' if prediction.get('slug') else '')
            old_slug = result['before_prediction_slug']
            new_slug = result['after_prediction_slug']
            old_correct = transport_ok and score_service(action, old_slug, expected)
            new_correct = transport_ok and score_service(action, new_slug, expected)
            old_rank = rank(result['before'], expected.get('expected_slug', '')) if transport_ok and expected.get('expected_slug') else 0
            new_rank = rank(result['after'], expected.get('expected_slug', '')) if transport_ok and expected.get('expected_slug') else 0
            count['baseline_top5'] += 0 < old_rank <= 5
            count['rerank_top5'] += 0 < new_rank <= 5
            count['baseline_top20'] += old_rank > 0
            count['rerank_top20'] += new_rank > 0
        else:
            old_rank = rank(result['before'], expected['expected_slug']) if transport_ok else 0
            new_rank = rank(result['after'], expected['expected_slug']) if transport_ok else 0
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
    parser.add_argument('--frozen-suite', type=Path, required=True)
    parser.add_argument('--organizer-seal', type=Path, required=True)
    parser.add_argument('--organizer-manifest', type=Path, required=True)
    parser.add_argument('--private-out', type=Path, required=True)
    parser.add_argument('--public-out', type=Path, required=True)
    args = parser.parse_args()
    if args.private_out.exists() or args.public_out.exists():
        raise FileExistsError('diagnostic outputs already exist')
    manifest_path = args.gold_blind_dir / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    frozen_gold = json.loads(args.frozen_gold.read_text())
    frozen = unique(frozen_gold['cases'], 'case_id')
    suite = json.loads(args.frozen_suite.read_text())
    if suite['suite_hash'] != frozen_gold['suite_hash']:
        raise ValueError('frozen suite/gold hash mismatch')
    frozen_images = {cid: row['image_sha256'] for cid, row in
                     unique(suite['cases'], 'case_id').items()}
    erratum = json.loads(args.frozen_erratum.read_text())
    if erratum['source_gold_file_sha256'] != sha(args.frozen_gold):
        raise ValueError('erratum source gold hash mismatch')
    for item in erratum['corrections']:
        cid, track = item['case_id'], item['track']
        if frozen[cid][track] != item['old_gold']:
            raise ValueError(f'erratum old gold mismatch: {cid}')
        frozen[cid][track] = item['new_gold']
    organizer = unique([json.loads(x) for x in args.organizer_seal.read_text().splitlines()], 'image_id')
    organizer_manifest = json.loads(args.organizer_manifest.read_text())
    organizer_images = {cid: row['sha256'] for cid, row in
                        unique(organizer_manifest['cases'], 'case_id').items()}
    for cid, label in organizer.items():
        if organizer_images[cid] != label['sha256']:
            raise ValueError(f'organizer seal image SHA mismatch: {cid}')
    public_rows, private_rows = [], []
    for run in manifest['runs']:
        source, output = Path(run['input']), Path(run['output'])
        if sha(source) != run['input_sha256'] or sha(output) != run['output_sha256']:
            raise ValueError(f'input/output changed after gold-blind freeze: {run["name"]}')
        summary, cases = score_run(run['name'], source, output, frozen, organizer,
                                   frozen_images, organizer_images, suite['suite_hash'])
        if run['name'].startswith('frozen-'):
            by_track = {track: score_run(run['name'], source, output, frozen, organizer,
                                         frozen_images, organizer_images, suite['suite_hash'], track)[0]
                        for track in ('service', 'retrieval')}
            public_rows.append({'name': run['name'], 'input_rows': summary['input_rows'],
                                'ungraded': summary['input_rows'] - summary['graded'],
                                'changed_rank_lists': summary['changed_rank_lists'],
                                'by_track': by_track})
        else:
            public_rows.append({'name': run['name'], **summary})
        private_rows.append({'name': run['name'], 'cases': cases})
    args.private_out.parent.mkdir(parents=True, exist_ok=True)
    args.private_out.write_text(json.dumps({'schema_version': 1, 'gold_blind_manifest_sha256': sha(manifest_path),
        'frozen_gold_sha256': sha(args.frozen_gold), 'erratum_sha256': sha(args.frozen_erratum),
        'organizer_seal_sha256': sha(args.organizer_seal),
        'frozen_suite_sha256': sha(args.frozen_suite),
        'organizer_manifest_sha256': sha(args.organizer_manifest), 'runs': private_rows},
        ensure_ascii=False, indent=2) + '\n')
    args.public_out.parent.mkdir(parents=True, exist_ok=True)
    args.public_out.write_text(json.dumps({'schema_version': 1,
        'kind': 'POST-HOC DEVELOPMENT: offline Top-20 attribute rerank, not independent validation or full HTTP timing',
        'gold_blind_manifest_sha256': sha(manifest_path),
        'frozen_gold_view': 'separate case-000137 lineage erratum overlay',
        'runs': public_rows}, ensure_ascii=False, indent=2) + '\n')
    organizer_rows = [x for x in public_rows if x['name'].startswith('organizer-')]
    print(json.dumps({'runs': len(public_rows),
                      'organizer_system_case_top1_fixes': sum(x['fixed'] for x in organizer_rows),
                      'organizer_system_case_top1_regressions': sum(x['regressed'] for x in organizer_rows)}))


if __name__ == '__main__':
    main()
