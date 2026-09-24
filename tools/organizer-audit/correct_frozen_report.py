# coding: utf-8
"""Apply a private frozen-gold erratum to copies of historical evaluation reports.

The public summary contains aggregate deltas only. Original suite, gold, and
reports are read-only inputs; corrected case-level reports stay in --out-dir.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def index_unique(rows: list[dict], key: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        value = row[key]
        if value in result:
            raise ValueError(f'duplicate {key}: {value}')
        result[value] = row
    return result


def validate_erratum(suite: dict, gold: dict, provenance: dict, erratum: dict,
                     suite_path: Path, gold_path: Path, provenance_path: Path,
                     image_root: Path) -> dict[str, dict]:
    if erratum['schema_version'] != 1 or suite['version'] != erratum['source_suite_version']:
        raise ValueError('unsupported erratum or suite version')
    if suite['suite_hash'] != gold['suite_hash'] or suite['suite_hash'] != erratum['source_suite_hash']:
        raise ValueError('suite hash mismatch')
    for key, path in [('source_suite_file_sha256', suite_path),
                      ('source_gold_file_sha256', gold_path),
                      ('source_provenance_file_sha256', provenance_path)]:
        if erratum[key] != digest(path):
            raise ValueError(f'{key} mismatch')
    cases = index_unique(suite['cases'], 'case_id')
    labels = index_unique(gold['cases'], 'case_id')
    lineage = index_unique(provenance['cases'], 'case_id')
    corrections = index_unique(erratum['corrections'], 'case_id')
    for case_id, correction in corrections.items():
        if case_id not in cases or case_id not in labels or case_id not in lineage:
            raise ValueError(f'erratum case absent: {case_id}')
        case = cases[case_id]
        track = correction['track']
        if track not in case['tracks'] or track not in ('service', 'retrieval'):
            raise ValueError(f'wrong track: {case_id}')
        if case['image_sha256'] != correction['image_sha256']:
            raise ValueError(f'image SHA mismatch: {case_id}')
        image_path = image_root / case['image_path']
        if not image_path.is_file() or digest(image_path) != correction['image_sha256']:
            raise ValueError(f'image bytes mismatch: {case_id}')
        if correction['old_gold'] != labels[case_id].get(track):
            raise ValueError(f'old gold mismatch: {case_id}')
        old, new = correction['old_gold'], correction['new_gold']
        if not labels[case_id].get('verified') or old.get('expected_slug') == new.get('expected_slug'):
            raise ValueError(f'not a verified slug correction: {case_id}')
        if track == 'service' and (old.get('expected_action') != 'match' or new.get('expected_action') != 'match'):
            raise ValueError(f'service action changed: {case_id}')
        if correction['scene_group_id'] != case['scene_group_id'] or correction['scene_group_id'] != lineage[case_id]['scene_group_id']:
            raise ValueError(f'lineage scene mismatch: {case_id}')
        if correction['lineage']['parent_case_id'] != lineage[case_id].get('parent_case_id'):
            raise ValueError(f'lineage parent mismatch: {case_id}')
        if correction['lineage']['transformation'] != lineage[case_id].get('transformation'):
            raise ValueError(f'lineage transform mismatch: {case_id}')
    return corrections


def rank_for(case: dict, track: str, expected: dict) -> int:
    if not case['graded'] or case['status'] != 'ok':
        return 0
    prediction = case.get('prediction') or {}
    if track == 'service':
        action = prediction.get('action') or ('match' if prediction.get('slug') else '')
        wanted = expected.get('expected_action') or ('match' if expected.get('expected_slug') else '')
        return int(action == wanted and (action != 'match' or prediction.get('slug') == expected.get('expected_slug')))
    ranked = prediction.get('ranked_slugs') or []
    slug = expected.get('expected_slug')
    return ranked.index(slug) + 1 if slug in ranked else 0


def stats(cases: list[dict]) -> dict:
    graded = [x for x in cases if x['graded']]
    n = len(graded)
    return {'graded': n,
            'correct_top1': sum(x.get('rank', 0) == 1 for x in graded),
            'correct_top5': sum(0 < x.get('rank', 0) <= 5 for x in graded),
            'correct_top20': sum(0 < x.get('rank', 0) <= 20 for x in graded),
            'mrr': sum(1 / x['rank'] for x in graded if x.get('rank', 0) > 0) / n if n else 0,
            'missing': sum(x['status'] == 'not_run' for x in graded),
            'ungraded': len(cases) - n}


def recompute(report: dict) -> dict:
    cases = report['cases']
    result = {'overall': stats(cases),
              'by_origin': {key: stats([x for x in cases if x['origin_kind'] == key]) for key in report['by_origin']},
              'by_reference': {key: stats([x for x in cases if ('reference_derived' if x['reference_derived'] else 'independent') == key]) for key in report['by_reference']},
              'by_basket': {key: stats([x for x in cases if key in x['basket_ids']]) for key in report['by_basket']}}
    return result


def assert_same_stats(report: dict, computed: dict) -> None:
    for section, value in computed.items():
        old = report[section]
        if set(old) != set(value):
            raise ValueError(f'{section} keys mismatch')
        for group in old:
            expected = old[group] if section != 'overall' else old[group]
            actual = value[group]
            if section == 'overall':
                if group == 'mrr':
                    if not math.isclose(expected, actual, abs_tol=1e-10):
                        raise ValueError('historical overall mrr mismatch')
                elif expected != actual:
                    raise ValueError(f'historical overall {group} mismatch')
            else:
                if set(expected) != set(actual):
                    raise ValueError(f'historical {section}/{group} keys mismatch')
                for metric in expected:
                    if metric == 'mrr':
                        if not math.isclose(expected[metric], actual[metric], abs_tol=1e-10):
                            raise ValueError(f'historical {section}/{group} mrr mismatch')
                    elif expected[metric] != actual[metric]:
                        raise ValueError(f'historical {section}/{group}/{metric} mismatch')


def correct_report(report: dict, corrections: dict[str, dict], suite_hash: str,
                   source_sha: str, erratum_sha: str) -> tuple[dict, dict]:
    submission = report['submission']
    track = submission['track']
    if track not in ('service', 'retrieval') or submission['suite_hash'] != suite_hash:
        raise ValueError('report track or suite hash mismatch')
    if str(report.get('scoring_version')) != '1':
        raise ValueError('unsupported scorer version')
    index_unique(report['cases'], 'case_id')
    assert_same_stats(report, recompute(report))
    corrected = copy.deepcopy(report)
    changes = []
    for case in corrected['cases']:
        item = corrections.get(case['case_id'])
        if not item or item['track'] != track:
            continue
        if not case['graded']:
            raise ValueError(f'erratum case ungraded in report: {case["case_id"]}')
        old_rank = rank_for(case, track, item['old_gold'])
        if case.get('rank', 0) != old_rank or case['correct'] != (old_rank == 1):
            raise ValueError(f'historical case score conflicts with old gold: {case["case_id"]}')
        new_rank = rank_for(case, track, item['new_gold'])
        case['rank'] = new_rank
        case['correct'] = new_rank == 1
        changes.append({'case_id': case['case_id'], 'old_rank': old_rank, 'new_rank': new_rank,
                        'old_correct': old_rank == 1, 'new_correct': new_rank == 1})
    if not changes:
        raise ValueError('report contains no erratum cases')
    expected_ids = {case_id for case_id, item in corrections.items() if item['track'] == track}
    if {item['case_id'] for item in changes} != expected_ids:
        raise ValueError('report is missing one or more erratum cases for its track')
    corrected.update(recompute(corrected))
    corrected['diagnostic_erratum'] = {'erratum_sha256': erratum_sha,
        'source_report_sha256': source_sha, 'kind': 'private corrected interpretation; historical report unchanged'}
    before, after = report['overall'], corrected['overall']
    public = {'run_id': report['run_id'], 'solution': submission['solution']['name'],
              'track': track, 'corrected_cases': len(changes),
              'before': {key: before[key] for key in ('graded', 'correct_top1', 'correct_top5', 'correct_top20', 'mrr')},
              'after': {key: after[key] for key in ('graded', 'correct_top1', 'correct_top5', 'correct_top20', 'mrr')},
              'delta': {key: after[key] - before[key] for key in ('correct_top1', 'correct_top5', 'correct_top20', 'mrr')},
              'source_report_sha256': source_sha}
    private = {'run_id': report['run_id'], 'source_report_sha256': source_sha,
               'erratum_sha256': erratum_sha, 'changes': changes,
               'aggregate_delta': public['delta'], 'corrected_report_sha256': None}
    return corrected, {'public': public, 'private': private}


def discover_reports(roots: list[Path], all_branches: bool) -> list[Path]:
    paths = []
    selected_names = {'all-service.json', 'all-retrieval.json',
                      'report-all-service.json', 'report-all-retrieval.json'}
    for root in roots:
        for path in root.rglob('*.json'):
            if path.parent.name != 'reports':
                continue
            if all_branches:
                data = load(path)
                if not all(key in data for key in ('scoring_version', 'cases', 'submission')):
                    continue
            elif path.name not in selected_names:
                continue
            paths.append(path)
    return sorted(set(paths))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('suite', 'gold', 'provenance', 'erratum', 'image_root', 'out_dir', 'public_out'):
        parser.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
    parser.add_argument('--reports-root', type=Path, action='append', default=[])
    parser.add_argument('--all-branches', action='store_true',
                        help='select every valid scorer report in each reports directory')
    parser.add_argument('--report', type=Path, action='append', default=[])
    args = parser.parse_args()
    paths = list(args.report)
    paths.extend(discover_reports(args.reports_root, args.all_branches))
    paths = sorted(set(paths))
    if not paths:
        raise ValueError('no reports supplied')
    suite, gold, provenance, erratum = map(load, (args.suite, args.gold, args.provenance, args.erratum))
    corrections = validate_erratum(suite, gold, provenance, erratum,
                                   args.suite, args.gold, args.provenance, args.image_root)
    if args.out_dir.exists() or args.public_out.exists():
        raise FileExistsError('diagnostic outputs already exist; choose a new versioned path')
    results = []
    prepared = []
    index = {}
    for path in paths:
        source_sha = digest(path)
        if source_sha in index:
            raise ValueError(f'duplicate source report bytes: {path}')
        corrected, info = correct_report(load(path), corrections, suite['suite_hash'], source_sha, digest(args.erratum))
        name = f'{path.parent.parent.name}-{path.parent.name}-{path.stem}-{source_sha[:12]}'
        corrected_path = args.out_dir / (name + '.json')
        provenance_path = args.out_dir / (name + '.provenance.json')
        info['private']['corrected_report_sha256'] = hashlib.sha256((json.dumps(corrected, ensure_ascii=False, indent=2) + '\n').encode()).hexdigest()
        prepared.append((corrected_path, provenance_path, corrected, info['private']))
        index[source_sha] = {'source_report': str(path), 'corrected_report': corrected_path.name,
                             'provenance': provenance_path.name,
                             'corrected_report_sha256': info['private']['corrected_report_sha256']}
        results.append(info['public'])
    args.out_dir.mkdir(parents=True)
    for report_path, provenance_path, report, private in prepared:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        provenance_path.write_text(json.dumps(private, ensure_ascii=False, indent=2) + '\n')
    (args.out_dir / 'index.json').write_text(json.dumps({'schema_version': 1,
        'erratum_sha256': digest(args.erratum), 'by_source_report_sha256': index},
        ensure_ascii=False, indent=2) + '\n')
    summary = {'schema_version': 1, 'kind': 'diagnostic frozen-v1 erratum aggregate; historical scores preserved',
               'suite_hash': suite['suite_hash'], 'erratum_sha256': digest(args.erratum),
               'corrected_cases_by_track': {track: sum(item['track'] == track for item in corrections.values())
                                            for track in ('service', 'retrieval')},
               'reports': results}
    args.public_out.parent.mkdir(parents=True, exist_ok=True)
    args.public_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'reports': len(results), 'tracks': {x: sum(r['track'] == x for r in results) for x in ('service', 'retrieval')},
                      'public_out': str(args.public_out)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
