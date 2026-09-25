"""Export full-basket submissions and paired predictions after gold-blind inference."""
import argparse
import hashlib
import json
from pathlib import Path


def rows(path):
    return [json.loads(line) for line in path.open(encoding='utf-8')]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--raw', default='raw-predictions.jsonl')
    parser.add_argument('--modes', nargs='+', choices=('base5', 'roman5', 'roman20'),
        default=('base5', 'roman5', 'roman20'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = Path('/Users/skif/ml-data/brutforce/integration-20260925-1700/model')
    public_v2 = json.loads(Path('/Users/skif/ml-data/brutforce/night-20260925/cpu/public-v2.json').read_text())
    expected = rows(args.input / 'input-v1/requests.jsonl')
    raw = rows(args.input / args.raw)
    lookup = {r['case_id']: r for r in raw}
    if len(expected) != 316 or len(lookup) != 316 or len(raw) != 316:
        raise ValueError('All 316 request rows required before full-basket export')
    config = json.loads((args.input / 'run-config.json').read_text())
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    modes = tuple(args.modes)
    paired = []
    for original in expected:
        case = lookup[original['case_id']]
        if case['query_sha256'] != original['query_sha256'] or case['b_ranked'] != original['ranked_slugs']:
            raise ValueError('Output/input mismatch ' + original['case_id'])
        pair = dict(case_id=case['case_id'], basket=case['basket'], track=case['track'],
            query_sha256=case['query_sha256'], b_ranked=case['b_ranked'],
            b_action=case['b_action'], b_slug=case['b_slug'], status=case['status'],
            missing_references=case['missing_references'],
            b_elapsed_ms=case['b_elapsed_ms'], roman_elapsed_ms=case['roman_elapsed_ms'])
        judge_ms = {
            'base5': case.get('base5', {}).get('elapsed_ms', 0),
            'roman5': case.get('adapter5', {}).get('elapsed_ms', 0),
            'roman20': sum(g['elapsed_ms'] for g in case.get('groups20', [])) +
                (0 if case.get('final20_reused') else case.get('final20', {}).get('elapsed_ms', 0)),
        }
        for mode in modes:
            field = {'base5':'base5_ranked','roman5':'roman5_ranked','roman20':'roman20_ranked'}[mode]
            rank = case.get(field) or case['b_ranked']
            pair[mode] = dict(ranked_slugs=rank,
                chosen_slug=rank[0] if rank else None,
                fallback=field not in case,
                fallback_reason=case['status'] if field not in case else None,
                judge_elapsed_ms=round(judge_ms[mode], 3) if field in case else 0)
        paired.append(pair)
    with (args.output / 'paired-predictions.jsonl').open('w', encoding='utf-8') as stream:
        for row in paired:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    submission_ids = set()
    for mode in modes:
        for track in ('service', 'retrieval'):
            template = json.loads((source / 'softgate-B-v2' / (track + '.json')).read_text())
            template['basket_ids'] = [b['basket_id'] for b in public_v2['baskets'] if b['track'] == track]
            chosen = {r['case_id']: r for r in paired if r['basket'] == 'frozen' and r['track'] == track}
            if len(chosen) != len(template['results']):
                raise ValueError('Track case count mismatch')
            template['submission_id'] = 'night-roman-' + mode + '-' + track + '-v2-20260925'
            if template['submission_id'] in submission_ids:
                raise ValueError('Duplicate submission ID')
            submission_ids.add(template['submission_id'])
            display = ('pinned Qwen base5' if mode == 'base5' else 'Roman ' + mode)
            weights = ('Qwen3.5-4B@851bf6e8 without LoRA' if mode == 'base5' else
                'Qwen3.5-4B@851bf6e8 + Roman fullframe-qlora-lr1e-4-v1')
            template['solution'] = dict(name='Cached B → ' + display + ' runtime-linear (processor+model timing)',
                version='roman-on-B-20260925-v1-' + mode, commit=None,
                config_hash=config_hash,
                weights_version=weights,
                catalog_version='organizer-catalog-20260919')
            template['submitted_by'] = 'N4 night experiment; full inputs with explicit B fallback'
            for result in template['results']:
                row = chosen[result['case_id']]
                rank = row[mode]['ranked_slugs']
                if track == 'retrieval':
                    result['prediction'] = dict(ranked_slugs=rank)
                elif rank:
                    result['prediction'] = dict(slug=rank[0])
                else:
                    result['prediction'] = dict(action=row['b_action'] or 'no_match')
                result['latency_ms'] = round(row[mode]['judge_elapsed_ms'])
            if any(result['latency_ms'] != round(chosen[result['case_id']][mode]['judge_elapsed_ms'])
                    for result in template['results']):
                raise ValueError('Submission latency differs from paired judge timer')
            (args.output / f'{mode}-{track}.json').write_text(
                json.dumps(template, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            if json.loads((args.output / f'{mode}-{track}.json').read_text())['submission_id'] != template['submission_id']:
                raise ValueError('Written submission ID mismatch')
        with (args.output / f'{mode}-organizer.jsonl').open('w', encoding='utf-8') as stream:
            for row in paired:
                if row['basket'] != 'organizer':
                    continue
                rank = row[mode]['ranked_slugs']
                result = dict(action='match' if rank else (row['b_action'] or 'no_match'),
                    slug=rank[0] if rank else None, ranked_slugs=rank)
                stream.write(json.dumps(dict(case_id=row['case_id'],
                    query_sha256=row['query_sha256'], http_status=200, result=result),
                    ensure_ascii=False) + '\n')
    summary = {mode: dict(full_rows=316, roman_applied=sum(not r[mode]['fallback'] for r in paired),
        b_fallback=sum(r[mode]['fallback'] for r in paired),
        changed_top1=sum(r[mode]['chosen_slug'] != (r['b_ranked'][0] if r['b_ranked'] else None) for r in paired))
        for mode in modes}
    if len(submission_ids) != 2 * len(modes):
        raise ValueError('Submission ID uniqueness failure')
    summary['statuses'] = {status:sum(r['status']==status for r in paired) for status in set(r['status'] for r in paired)}
    (args.output / 'coverage.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
