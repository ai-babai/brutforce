#!/usr/bin/env python3
"""Trusted-host-only, SHA-paired CPU evidence scorer; never run on inference nodes."""

import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def percentile(values, q):
    values = sorted(values)
    return round(values[math.ceil(q * len(values)) - 1], 2) if values else None


def load_run(path, manifest, manifest_hash, organizer=False):
    cases = manifest['cases']
    indexed = {c['case_id']: c for c in cases}
    assert len(indexed) == len(cases) == (103 if organizer else 213)
    rows = jsonl(path)
    by_id = {r['case_id']: r for r in rows}
    assert len(by_id) == len(rows) and set(by_id) == set(indexed), path
    profiles = set()
    for case_id, row in by_id.items():
        case = indexed[case_id]
        image_sha = case['sha256'] if organizer else case['image_sha256']
        track = case['track'] if organizer else case['tracks'][0]
        assert row['track'] == track and row['query_sha256'] == image_sha, case_id
        assert row['manifest_sha256'] == manifest_hash, case_id
        assert row['phase'] == 'full-http' and row['elapsed_ms'] >= 0, case_id
        profiles.add((row['variant'], row['run_id'], row['url']))
        if row['http_status'] == 200 and row['elapsed_ms'] <= 10000:
            result = row['result']
            assert result['image_sha256'] == image_sha, case_id
            assert result['catalog_version'] == 'organizer-catalog-20260919', case_id
            assert result['index_version'] == 'so400m384-owlv2-v2-crops-reference-gated-20260925', case_id
            profiles.add(('response', result['model_version'], result['serving_profile']))
            ranks = result.get('ranked_slugs') or []
            assert len(ranks) == len(set(ranks)) and len(ranks) <= 20, case_id
            if track == 'retrieval':
                assert ranks, case_id
                continue
            action = result.get('action') or ('match' if result.get('slug') else None)
            assert action in ('match', 'no_match', 'insufficient_information'), case_id
            assert (action == 'match' and ranks and result.get('slug') == ranks[0]) or (
                action != 'match' and not ranks and not result.get('slug')), case_id
    assert len([profile for profile in profiles if profile[0] != 'response']) == 1, path
    assert len([profile for profile in profiles if profile[0] == 'response']) <= 1, path
    return by_id


def success(row):
    return row['http_status'] == 200 and row['elapsed_ms'] <= 10000


def signature(row):
    if not success(row):
        return {'http_status': row['http_status'], 'deadline': row['elapsed_ms'] > 10000}
    result = row['result']
    return {'action': result.get('action') or ('match' if result.get('slug') or result.get('ranked_slugs') else None),
            'slug': result.get('slug'), 'ranked_slugs': result.get('ranked_slugs') or []}


def latency(rows):
    ok = [r['elapsed_ms'] for r in rows.values() if success(r)]
    all_elapsed = [r['elapsed_ms'] for r in rows.values()]
    return {'timely': len(ok), 'total': len(rows),
            'timely_only_p50_ms': percentile(ok, .5),
            'timely_only_p95_ms': percentile(ok, .95),
            'timely_only_max_ms': percentile(ok, 1),
            'all_p50_ms': percentile(all_elapsed, .5),
            'all_p95_ms': percentile(all_elapsed, .95),
            'all_max_ms': percentile(all_elapsed, 1),
            'over_3s': sum(r['elapsed_ms'] > 3000 for r in rows.values()),
            'over_8_5s': sum(r['elapsed_ms'] > 8500 for r in rows.values()),
            'over_10s': sum(r['elapsed_ms'] > 10000 for r in rows.values()),
            'http_status': dict(collections.Counter(str(r['http_status']) for r in rows.values())),
            'deadline_failures': sorted(k for k, r in rows.items() if not success(r))}


def runtime_identity(rows):
    return {(r['result']['model_version'], r['result']['serving_profile'])
            for r in rows.values() if success(r)}


def score_frozen(cases, gold, baseline, candidate):
    labels = {c['case_id']: c for c in gold['cases']}
    assert len(labels) == len(cases) == 213 and set(labels) == {c['case_id'] for c in cases}
    counts = collections.defaultdict(lambda: collections.Counter())
    flips = []
    negative_breaks = []
    for case in cases:
        case_id = case['case_id']
        g = labels[case_id]
        track = case['tracks'][0]
        gradeable = bool(g['verified'] and track in g)

        def rank(row):
            if not gradeable or not success(row) or track != 'retrieval':
                return None
            ranks = row['result'].get('ranked_slugs') or []
            return ranks.index(g[track]['expected_slug']) + 1 if g[track]['expected_slug'] in ranks else None

        def outcome(row):
            if not gradeable or not success(row):
                return False
            result = row['result']
            if track == 'retrieval':
                return rank(row) == 1
            answer = g[track]
            action = answer.get('expected_action') or ('match' if answer.get('expected_slug') else '')
            return signature(row)['action'] == action and (
                action != 'match' or result.get('slug') == answer.get('expected_slug'))

        before, after = outcome(baseline[case_id]), outcome(candidate[case_id])
        if gradeable:
            counts[track]['total'] += 1
            counts[track]['baseline'] += before
            counts[track]['candidate'] += after
            counts[track]['fixed'] += after and not before
            counts[track]['broken'] += before and not after
            if track == 'retrieval':
                for name, row in (('baseline', baseline[case_id]), ('candidate', candidate[case_id])):
                    position = rank(row)
                    counts['retrieval'][name + '_top5'] += position is not None and position <= 5
                    counts['retrieval'][name + '_top20'] += position is not None and position <= 20
                    counts['retrieval'][name + '_reciprocal_sum'] += 1 / position if position else 0
            if track == 'service' and (g[track].get('expected_action') in
                                       ('no_match', 'insufficient_information')):
                category = g[track]['expected_action']
                counts[category]['total'] += 1
                counts[category]['baseline'] += before
                counts[category]['candidate'] += after
                counts[category]['fixed'] += after and not before
                counts[category]['broken'] += before and not after
                if before and not after:
                    negative_breaks.append(case_id)
        left, right = signature(baseline[case_id]), signature(candidate[case_id])
        if left != right:
            flips.append({'case_id': case_id, 'track': track,
                          'scene_group_id': case.get('scene_group_id'),
                          'graded': gradeable, 'baseline_correct': before if gradeable else None,
                          'candidate_correct': after if gradeable else None,
                          'baseline': left, 'candidate': right})
    assert counts['service']['total'] == 141 and counts['retrieval']['total'] == 62
    assert counts['no_match']['total'] == 22 and counts['insufficient_information']['total'] == 10
    for name in ('baseline', 'candidate'):
        counts['retrieval'][name + '_mrr'] = round(
            counts['retrieval'].pop(name + '_reciprocal_sum') / 62, 6)
    return {k: dict(v) for k, v in counts.items()}, flips, negative_breaks


def score_organizer(cases, labels, overlay, baseline, candidate):
    by_sha = {row['sha256']: row for row in labels}
    assert len(by_sha) == len(labels) == 100
    changes = {row['sha256'] for row in overlay['changes']}
    assert len(changes) == 1
    unique = {}
    duplicate_disagreements = []
    for case in cases:
        cid, image_sha = case['case_id'], case['sha256']
        label = by_sha[image_sha]
        status = 'out_of_catalog' if image_sha in changes else label['status']
        assert status in ('exact', 'out_of_catalog', 'catalog_unresolved', 'ambiguous')

        def outcome(row):
            if not success(row):
                return False
            if status == 'exact':
                return row['result'].get('slug') == label['exact_slug']
            if status == 'out_of_catalog':
                return signature(row)['action'] == 'no_match'
            return False

        def rank(row):
            if not success(row) or status != 'exact':
                return None
            ranks = row['result'].get('ranked_slugs') or []
            return ranks.index(label['exact_slug']) + 1 if label['exact_slug'] in ranks else None

        entry = {'case_id': cid, 'sha256': image_sha, 'status': status,
                 'scene_group': label.get('scene_group'),
                 'baseline_correct': outcome(baseline[cid]),
                 'candidate_correct': outcome(candidate[cid]),
                 'baseline_rank': rank(baseline[cid]),
                 'candidate_rank': rank(candidate[cid]),
                 'baseline': signature(baseline[cid]), 'candidate': signature(candidate[cid])}
        if image_sha in unique:
            prior = unique[image_sha]
            if (entry['baseline'], entry['candidate']) != (prior['baseline'], prior['candidate']):
                duplicate_disagreements.append([prior['case_id'], cid])
        else:
            unique[image_sha] = entry
    assert len(unique) == 100
    exact = [r for r in unique.values() if r['status'] == 'exact']
    ood = [r for r in unique.values() if r['status'] == 'out_of_catalog']
    assert len(exact) == 54 and len(ood) == 1
    fixed = [r for r in exact if r['candidate_correct'] and not r['baseline_correct']]
    broken = [r for r in exact if r['baseline_correct'] and not r['candidate_correct']]
    flips = [r for r in unique.values() if r['baseline'] != r['candidate']]
    return {'exact_baseline': sum(r['baseline_correct'] for r in exact),
            'exact_candidate': sum(r['candidate_correct'] for r in exact),
            'baseline_top5': sum(r['baseline_rank'] is not None and r['baseline_rank'] <= 5 for r in exact),
            'candidate_top5': sum(r['candidate_rank'] is not None and r['candidate_rank'] <= 5 for r in exact),
            'baseline_top20': sum(r['baseline_rank'] is not None and r['baseline_rank'] <= 20 for r in exact),
            'candidate_top20': sum(r['candidate_rank'] is not None and r['candidate_rank'] <= 20 for r in exact),
            'exact_total': len(exact), 'fixed': len(fixed), 'broken': len(broken),
            'fixed_scene_groups': len({r['scene_group'] for r in fixed}),
            'fixed_scene_groups_named': all(r['scene_group'] for r in fixed),
            'ood_baseline': bool(ood[0]['baseline_correct']),
            'ood_candidate': bool(ood[0]['candidate_correct']),
            'unique_total': len(unique), 'duplicate_disagreements': duplicate_disagreements,
            'status_counts': dict(collections.Counter(r['status'] for r in unique.values()))}, flips


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('frozen_manifest', 'organizer_manifest', 'frozen_gold', 'organizer_labels',
                 'organizer_overlay', 'baseline_frozen', 'baseline_organizer',
                 'candidate_frozen', 'candidate_organizer', 'out'):
        p.add_argument('--' + name.replace('_', '-'), type=Path, required=True)
    p.add_argument('--timing-control', choices=('historical', 'paired'), required=True)
    args = p.parse_args()
    paths = {name: value for name, value in vars(args).items() if isinstance(value, Path) and name != 'out'}
    digests = {name: sha(path) for name, path in paths.items()}
    frozen = json.loads(args.frozen_manifest.read_text())
    organizer = json.loads(args.organizer_manifest.read_text())
    gold = json.loads(args.frozen_gold.read_text())
    assert frozen['version'] == gold['version'] == 'v2'
    assert frozen['suite_hash'] == gold['suite_hash']
    assert digests['organizer_labels'] == 'f0362a9ebf6e2060148c401799c0bcba299b4f56a294b15ec219f6368e2b2589'
    assert digests['organizer_overlay'] == '1f225185848441098eb5dbe9bdc8013b67a10d250db6b8fe94e0fecb4f0ed21f'
    a = load_run(args.baseline_frozen, frozen, digests['frozen_manifest'])
    b = load_run(args.candidate_frozen, frozen, digests['frozen_manifest'])
    c = load_run(args.baseline_organizer, organizer, digests['organizer_manifest'], True)
    d = load_run(args.candidate_organizer, organizer, digests['organizer_manifest'], True)
    assert len(runtime_identity(a) | runtime_identity(c)) <= 1, 'baseline model/route mismatch'
    assert len(runtime_identity(b) | runtime_identity(d)) <= 1, 'candidate model/route mismatch'
    frozen_scores, frozen_flips, negative_breaks = score_frozen(frozen['cases'], gold, a, b)
    organizer_scores, organizer_flips = score_organizer(
        organizer['cases'], jsonl(args.organizer_labels),
        json.loads(args.organizer_overlay.read_text()), c, d)
    timings = {name: latency(rows) for name, rows in [('baseline_frozen', a),
                ('candidate_frozen', b), ('baseline_organizer', c), ('candidate_organizer', d)]}
    no_new_timeouts = all(not set(timings['candidate_' + track]['deadline_failures']) -
                              set(timings['baseline_' + track]['deadline_failures'])
                          for track in ('frozen', 'organizer'))
    p95_within = all(timings['candidate_' + track]['all_p95_ms'] is not None and
                     timings['baseline_' + track]['all_p95_ms'] is not None and
                     timings['candidate_' + track]['all_p95_ms'] <=
                     timings['baseline_' + track]['all_p95_ms'] + 1000
                     for track in ('frozen', 'organizer'))
    gate = {'exact_net_win': organizer_scores['exact_candidate'] > organizer_scores['exact_baseline'],
            'two_scene_groups': organizer_scores['fixed_scene_groups'] >= 2 and
                                organizer_scores['fixed_scene_groups_named'],
            'duplicate_rank_action_consistency': not organizer_scores['duplicate_disagreements'],
            'frozen_service_no_drop': frozen_scores['service']['candidate'] >= frozen_scores['service']['baseline'],
            'frozen_retrieval_no_drop': frozen_scores['retrieval']['candidate'] >= frozen_scores['retrieval']['baseline'],
            'no_new_negative_errors': not negative_breaks and
                                      (not organizer_scores['ood_baseline'] or organizer_scores['ood_candidate']),
            'no_new_timeout': no_new_timeouts, 'p95_within_1s': p95_within}
    report = {'schema_version': 1, 'timing_control': args.timing_control,
              'file_sha256': digests, 'frozen': frozen_scores, 'organizer': organizer_scores,
              'latency': timings, 'gate': gate,
              'gate_proven': args.timing_control == 'paired' and all(gate.values()),
              'negative_breaks': negative_breaks, 'frozen_flips': frozen_flips,
              'organizer_unique_flips': organizer_flips,
              'limits': ['Organizer 54 exact are reused development labels, not holdout.',
                         'Historical latency cannot satisfy the paired timing gate.',
                         'Paired flag requires independent runtime receipt review of quotas and timing scope.',
                         'Private case-level truth and flips stay outside Git and web root.']}
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(args.out, flags, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({'frozen': frozen_scores, 'organizer': organizer_scores,
                      'latency': timings, 'gate': gate, 'gate_proven': report['gate_proven'],
                      'frozen_flip_count': len(frozen_flips),
                      'organizer_unique_flip_count': len(organizer_flips)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
