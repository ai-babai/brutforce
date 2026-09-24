"""Score only manual organizer matches and QC-qualified pilot outputs.

Private label files enter this analysis stage after all standalone inference.
They are never imported by OCR runners or the catalog matcher.
"""
import collections
import hashlib
import json
import os
import statistics
from pathlib import Path

ROOT=Path(os.environ.get('BRUTFORCE_AUDIT_ROOT', '/Users/skif/ml-data/brutforce/vision-retrieval-20260924/organizer-audit'))
PILOT=Path(os.environ.get('BRUTFORCE_PILOT_ROOT', '/Users/skif/ml-data/brutforce/vision-pilot-20260924'))
MODELS=('deepseek','qwen','paddle')


def read_jsonl(path):return [json.loads(x) for x in path.read_text().splitlines()]
def clean(row):return row['status']=='ok' and row['total_latency_ms']<=10000 and row.get('prediction') is not None

def evaluate(rows,labels,allow):
    out=[]
    for x in rows:
        l=labels.get(x['case_id'])
        if not l or not allow(l):continue
        pred=x['prediction'].get('slug') if clean(x) else None
        expected=l.get('expected_slug') or l.get('target_slug')
        ranks=[r['slug'] for r in x.get('ranked',[])]
        rank=ranks.index(expected)+1 if expected in ranks else None
        status='deadline_timeout' if x['status']=='ok' and x['total_latency_ms']>10000 else x['status']
        out.append({'case_id':x['case_id'],'status':status,'expected_slug':expected,'predicted_slug':pred,
                    'top1':pred==expected,'rank':rank,'qc_status':l.get('qc_status'),
                    'latency_ms':x['total_latency_ms'],'source_set':x.get('source_set')})
    return out

def aggregate(r):
    return {'count':len(r),'top1':sum(x['top1'] for x in r),'top5':sum(x['rank'] is not None and x['rank']<=5 and x['status']=='ok' for x in r),
            'top20':sum(x['rank'] is not None and x['rank']<=20 and x['status']=='ok' for x in r),
            'deadline_timeouts':sum(x['status']=='deadline_timeout' for x in r),
            'model_timeouts':sum(x['status']=='timeout' for x in r),
            'errors':sum(x['status'] not in ('ok','deadline_timeout','timeout') for x in r),
            'median_latency_ms':round(statistics.median(x['latency_ms'] for x in r)) if r else None}

def coverage(rows):
    unique={x['image_sha256']:x for x in rows if x.get('source_set')=='real-photos.zip'}
    vals=list(unique.values())
    return {'unique_images':len(vals),
            'completed_under_10s':sum(clean(x) for x in vals),
            'completed_under_3s':sum(x['status']=='ok' and x['total_latency_ms']<=3000 for x in vals),
            'model_timeouts':sum(x['status']=='timeout' for x in vals),
            'late_successes_over_10s':sum(x['status']=='ok' and x['total_latency_ms']>10000 for x in vals),
            'errors':sum(x['status']=='error' for x in vals),
            'median_latency_ms':round(statistics.median(x['total_latency_ms'] for x in vals)) if vals else None}

def main():
    query=json.loads((ROOT/'queries-public.json').read_text())['cases']
    strict={x['case_id']:x for x in json.loads((ROOT/'labels-private.json').read_text())['labels'] if x['expected_slug']}
    synthetic={x['case_id']:x for x in json.loads((ROOT/'synthetic-private-targets.json').read_text())['labels']}
    pilot={x['image_id']:x for x in read_jsonl(PILOT/'manifest.jsonl') if x['origin']=='ai_edited'}
    audits={x['image_id']:x for name in ('visual-audit-coordinator.jsonl','visual-audit-sol.jsonl','visual-audit-extension-sol.jsonl') for x in read_jsonl(PILOT/name)}
    audit_stats={k:dict(collections.Counter(x.get(k) for x in audits.values())) for k in ('identity','realistic','scenario_fulfilled')}
    scenarios=collections.defaultdict(lambda:collections.Counter())
    for image_id,m in pilot.items():
        s=m['scenario_ids'][0];scenarios[s][audits[image_id]['scenario_fulfilled']]+=1
    result={'version':'organizer-audit-20260924','provenance':{'organizer_source_url':'https://mostech-cloud.mos.ru/s/FxZekMZWXMjq9rN','label_provenance':'local agent visual/catalog matches; no organizer answer key','synthetic_qc_provenance':'prior agent visual reviews and DeepSeek QA; accepted does not certify all label text','organizer_archive_sha256':'5ffa77f7c8fdc82e1f9aa123ded91cdb2df435b7e3990ce074cba53b6be0e4c9','eval_archive_sha256':'dadcac05b8495697b2a84b2a9a123d5797cbf9687a7f7e5726548ea0eb663458','catalog_csv_sha256':'12a1b0b620db7a2264b094446861e83940a927708d65a1b7ccffda7ec3aeffee','query_rows':len(query),'unique_query_sha256':len({x['sha256'] for x in query}),'eval_duplicates':{x['case_id']:x['duplicate_of'] for x in query if x.get('duplicate_of')},'agent_labeled_rows':len(strict),'agent_labeled_exact_overlap_frozen_v1':10,'real_photo_exact_overlap_frozen_v1':12,'catalog_identity_ambiguous_rows':sum(bool(x.get('catalog_identity_ambiguity')) for x in strict.values()),'catalog_ref_verified':2080,'catalog_ref_missing':23},'synthetic_agent_visual_audit':audit_stats,'synthetic_scenario_fulfillment':{k:dict(v) for k,v in sorted(scenarios.items())},'methods':{}}
    private={'version':'organizer-audit-20260924','methods':{}}
    for model in MODELS:
        org=ROOT/f'{model}-standalone.jsonl';syn=ROOT/f'{model}-synthetic.jsonl'
        if not org.exists() or not syn.exists():continue
        orows=read_jsonl(org);srows=read_jsonl(syn)
        o=evaluate(orows,strict,lambda _:True)
        a=evaluate(srows,synthetic,lambda x:x['qc_status']=='accepted')
        allsyn=evaluate(srows,synthetic,lambda _:True)
        byqc={status:aggregate([x for x in allsyn if x['qc_status']==status]) for status in ('accepted','pending','rejected')}
        result['methods'][model]={'organizer_attempted_rows':len(orows),'organizer_unique_images':len({x['image_sha256'] for x in orows}),'organizer_coverage':coverage(orows),
                                  'organizer_local_exact_slug':aggregate(o),'organizer_unambiguous_sensitivity':aggregate([x for x in o if x['case_id']!='organizer-real-081']),'synthetic_attempted':len(srows),'synthetic_qc':byqc,
                                  'synthetic_all_target_agreement':aggregate(allsyn)}
        effective=ROOT/f'{model}-organizer-effective.jsonl'
        if effective.exists():
            erows=read_jsonl(effective)
            e=evaluate(erows,strict,lambda _:True)
            result['methods'][model]['organizer_effective_reuse']={
                'local_exact_slug':aggregate(e),
                'unambiguous_sensitivity':aggregate([x for x in e if x['case_id']!='organizer-real-081']),
                'coverage':coverage(erows),
                'provenance_counts':dict(collections.Counter(x['reuse'] for x in erows))}
        if model in ('deepseek','qwen'):
            v2=ROOT/f'{model}-standalone-matcher-v2.jsonl'
            if v2.exists():
                v2rows=evaluate(read_jsonl(v2),strict,lambda _:True)
                result['methods'][model]['cached_v2_development']={
                    'organizer_local_exact_slug':aggregate(v2rows),
                    'note':'Existing cultivar-alias rerank on cached OCR; same previously viewed scenes, no independent validation.'}
        private['methods'][model]={'organizer_local_exact_slug':o,'synthetic':allsyn}
    (ROOT/'error-report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (ROOT/'error-cases-private.json').write_text(json.dumps(private,ensure_ascii=False,indent=2))
    print(json.dumps(result['methods'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
