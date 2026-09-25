"""Gold-blind paired B/Roman output and timing comparison for a full HTTP variant."""
import argparse
import collections
import hashlib
import json
import statistics
from pathlib import Path


def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def summarize_ms(items,field):
    values=sorted(x[field] for x in items)
    return {'p50':round(statistics.median(values),3),'p95':values[int(.95*(len(values)-1))],
        'max':values[-1]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--variant-client',type=Path,required=True)
    p.add_argument('--variant-server',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    baseline_client={r['case_id']:r for r in rows(a.root/'online-http-316.jsonl')}
    baseline_server={r['case_id']:r for r in rows(a.root/'online-server-records.jsonl')}
    variant_client={r['case_id']:r for r in rows(a.variant_client)}
    variant_server={r['case_id']:r for r in rows(a.variant_server)}
    assert len(baseline_client)==len(baseline_server)==len(variant_client)==len(variant_server)==316
    assert set(baseline_client)==set(baseline_server)==set(variant_client)==set(variant_server)
    original={}
    for name in ('softgate-B-eval.jsonl','softgate-B-organizer.jsonl'):
        for row in rows(Path('/Users/skif/ml-data/brutforce/integration-20260925-1700/model')/name):
            assert row['case_id'] not in original
            original[row['case_id']]=row
    assert len(original)==316
    differences=[]
    for case_id in baseline_client:
        old=baseline_server[case_id];new=variant_server[case_id]
        b=original[case_id]['result']
        assert original[case_id]['query_sha256']==new['query_sha256']==old['query_sha256']
        assert [r['slug'] for r in b['variants_top20']['all']]==old['b_ranked']
        target=b.get('selection') or {}
        changes={
            'target_box':target.get('selected_box')!=new.get('b_selected_box'),
            'target_reason':target.get('selection_reason')!=new.get('b_selection_reason'),
            'label_box':(b.get('label_selection') or {}).get('box')!=new.get('b_label_box'),
            'ocr_text':b.get('ocr_text')!=new.get('b_ocr_text'),
            'b_action':(b.get('action'),b.get('slug'))!=(new.get('b_action'),new.get('b_slug')),
            'b_rank':old['b_ranked']!=new['b_ranked'],
            'b_top1':old['b_ranked'][:1]!=new['b_ranked'][:1],
            'roman5_rank':old['roman5_ranked']!=new['roman5_ranked'],
            'roman5_top1':old['roman5_ranked'][:1]!=new['roman5_ranked'][:1],
            'roman20_rank':old['roman20_ranked']!=new['roman20_ranked'],
            'roman20_top1':old['roman20_ranked'][:1]!=new['roman20_ranked'][:1],
            'client_status':baseline_client[case_id]['status']!=variant_client[case_id]['status']}
        differences.append({'case_id':case_id,'basket':baseline_client[case_id]['basket'],
            'track':baseline_client[case_id]['track'],'changes':changes,
            'old_client_status':baseline_client[case_id]['status'],
            'new_client_status':variant_client[case_id]['status'],
            'old_b_ms':old['b_http_ms'],'new_b_ms':new['b_http_ms'],
            'old_roman_ms':old['roman_wall_ms'],'new_roman_ms':new['roman_wall_ms'],
            'old_server_ms':old['total_server_ms'],'new_server_ms':new['total_server_ms']})
    summary={'rows':316,'source_sha256':{
        'baseline_client':hashlib.sha256((a.root/'online-http-316.jsonl').read_bytes()).hexdigest(),
        'variant_client':hashlib.sha256(a.variant_client.read_bytes()).hexdigest(),
        'baseline_server':hashlib.sha256((a.root/'online-server-records.jsonl').read_bytes()).hexdigest(),
        'variant_server':hashlib.sha256(a.variant_server.read_bytes()).hexdigest()},
        'changes':{key:sum(row['changes'][key] for row in differences)
            for key in differences[0]['changes']},
        'changed_case_ids':{key:[row['case_id'] for row in differences if row['changes'][key]]
            for key in ('target_box','ocr_text','b_top1','roman20_top1','client_status')},
        'status_transition':dict(collections.Counter(
            row['old_client_status']+'->'+row['new_client_status'] for row in differences)),
        'latency_ms':{stage:{'baseline':summarize_ms(differences,'old_'+stage+'_ms'),
                              'variant':summarize_ms(differences,'new_'+stage+'_ms')}
            for stage in ('b','roman','server')},'cases':differences}
    a.out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='cases'},ensure_ascii=False))


if __name__=='__main__':
    main()
