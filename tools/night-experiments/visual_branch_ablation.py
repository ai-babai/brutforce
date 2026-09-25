"""Blind cached-B visual branches; no inference or full-HTTP timing claim."""
import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    for arg in ('source','code','suite','out'):
        parser.add_argument('--'+arg, type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.code))
    from fuse import rank_fuse
    suite = json.loads(args.suite.read_text())
    profiles = {'whole': ('whole',), 'label': ('label',), 'whole-label': ('whole','label')}
    for mode, branches in profiles.items():
        out = args.out / mode
        out.mkdir(parents=True, exist_ok=True)
        by_id = {}
        for ds, expected in [('eval',213),('organizer',103)]:
            inputs = [json.loads(l) for l in (args.source/f'softgate-B-{ds}.jsonl').read_text().splitlines()]
            assert len(inputs) == expected
            output = []
            for original in inputs:
                row = copy.deepcopy(original)
                result = row['result']
                start = time.perf_counter()
                ranking = rank_fuse({b: result['branches_top20'][b] for b in branches})
                if result.get('ranked_slugs'):
                    assert ranking, row['case_id']
                    result.update(slug=ranking[0]['slug'],ranked_slugs=[v['slug'] for v in ranking])
                row['elapsed_ms'] = (time.perf_counter()-start)*1000
                row['timing_scope'] = 'cached_B_rank_merge_only'
                result['visual_branch_trace'] = {'branches': branches, 'selection': 'unchanged B'}
                output.append(row)
                if ds == 'eval':
                    by_id[row['case_id']] = row
            (out/f'{ds}.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in output))
        assert len(by_id) == 213
        for track in ('service','retrieval'):
            results = []
            for case in suite['cases']:
                if case['tracks'] != [track]: continue
                row = by_id[case['case_id']]
                assert row['query_sha256'] == case['image_sha256']
                res = row['result']; rank = res.get('ranked_slugs',[])
                pred = ({'slug':rank[0]} if rank else {'action':res.get('action','insufficient_information')}) if track == 'service' else {'ranked_slugs':rank}
                results.append({'case_id':case['case_id'],'status':'ok' if row['http_status']==200 else 'error','prediction':pred,'latency_ms':round(row['elapsed_ms'])})
            submission = {'submission_id':f'night-cached-B-visual-{mode}-{track}',
                'suite_version':suite['version'],'suite_hash':suite['suite_hash'],'track':track,
                'basket_ids':[b['basket_id'] for b in suite['baskets'] if b['track']==track],
                'solution':{'name':f'SigLIP2 SO400M / B {mode} (cached rank merge timing only)',
                    'version':f'night-visual-{mode}','config_hash':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'weights_version':'B fixed SigLIP2 SO400M384','catalog_version':'organizer-catalog-20260919'},
                'submitted_by':'night-coordinator','results':results}
            (out/f'{track}.json').write_text(json.dumps(submission,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__': main()
