"""Reviewer-side scoring of versioned local annotations, never on inference hosts.

Exact labels and ambiguity coverage are separate. Missing/error predictions remain
in the denominator; cached-stage timing is never a live deadline measurement.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_labels(labels, allowed=None):
    ids=set(); hashes=set()
    for row in labels:
        case_id=row['image_id']; sha=row['sha256']
        if case_id in ids or sha in hashes:
            raise ValueError('duplicate annotation ID or image SHA')
        ids.add(case_id); hashes.add(sha)
        if row['status'] not in ('exact','ambiguous','insufficient','out_of_catalog','catalog_unresolved'):
            raise ValueError('unknown annotation status')
        slug=row.get('exact_slug')
        if row['status']=='exact' and not slug:
            raise ValueError('exact annotation requires a slug')
        if row['status']!='exact' and slug:
            raise ValueError('non-exact annotation must not assert exact_slug')
        if allowed is not None:
            candidates=row.get('acceptable_slugs',[])+([slug] if slug else [])
            if any(s not in allowed for s in candidates):
                raise ValueError('annotation slug outside catalog')


def normalized(row, variant):
    if variant is None:
        ranking=row.get('ranked',[])
        prediction=row.get('prediction') or {}
    else:
        ranking=row.get('variants_top20',{}).get(variant,[])
        prediction=row.get('predictions',{}).get(variant) or {}
    slugs=[r['slug'] if isinstance(r,dict) else r for r in ranking]
    if len(set(slugs))!=len(slugs):
        raise ValueError('duplicate ranked slug')
    return slugs[:20],prediction


def score(labels, predictions, variant=None):
    validate_labels(labels)
    by_id={}
    for row in predictions:
        case_id=row['case_id']
        if case_id in by_id:
            raise ValueError('duplicate prediction ID')
        by_id[case_id]=row
    traces=[]
    for label in labels:
        row=by_id.get(label['image_id'])
        if row:
            if row.get('query_sha256',row.get('image_sha256'))!=label['sha256']:
                raise ValueError('prediction and annotation SHA mismatch')
            ranks,pred=normalized(row,variant)
            status=row.get('status','error')
        else:
            ranks,pred,status=[],{},'missing'
        expected=label.get('exact_slug')
        rank=(ranks.index(expected)+1) if status=='ok' and expected in ranks else None
        predicted=pred.get('slug') if status=='ok' else None
        wall=row.get('total_latency_ms') if row and variant is None else None
        traces.append({'image_id':label['image_id'],'sha256':label['sha256'],
          'annotation_status':label['status'],'prior_seen_group':label.get('review',{}).get('prior_seen_group','unknown'),
          'scene_group':label.get('scene_group'), 'status':status,
          'expected_slug':expected,'predicted_slug':predicted,
          'rank':rank,'exact_response':bool(expected and predicted==expected),
          'measured_wall_ms':wall,
          'exact_response_under_10s':bool(expected and predicted==expected and wall is not None and wall<=10000)})
    def aggregate(subset):
        exact=[x for x in subset if x['annotation_status']=='exact']
        return {'images':len(subset),'annotation_status_counts':dict(collections.Counter(x['annotation_status'] for x in subset)),
                'exact_denominator':len(exact),
                'exact_response':sum(x['exact_response'] for x in exact),
                **{f'top{k}':sum(x['rank'] is not None and x['rank']<=k for x in exact) for k in (1,5,20)},
                'mrr20':sum(1/x['rank'] if x['rank'] else 0 for x in exact)/len(exact) if exact else None,
                'prediction_status_counts_exact':dict(collections.Counter(x['status'] for x in exact)),
                'wall_measured_exact':sum(x['measured_wall_ms'] is not None for x in exact),
                'exact_response_under_10s':sum(x['exact_response_under_10s'] for x in exact) if any(x['measured_wall_ms'] is not None for x in exact) else None}
    public={'scope':'Local agent-reviewed annotations, not organizer gold. Selection of verified subset may bias accuracy; show coverage.',
            'variant':variant or 'standalone',
            'all':aggregate(traces),
            'by_prior_seen':{name:aggregate([x for x in traces if x['prior_seen_group']==name]) for name in sorted({x['prior_seen_group'] for x in traces})},
            'timing_note':'Only total_latency_ms from standalone is a measured wall duration; cached composition timings are not scored as deadlines.'}
    return public,traces


def main():
    p=argparse.ArgumentParser();p.add_argument('--labels',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True)
    p.add_argument('--variant');p.add_argument('--out',type=Path,required=True);p.add_argument('--private-out',type=Path,required=True)
    a=p.parse_args();summary,trace=score(read_jsonl(a.labels),read_jsonl(a.predictions),a.variant)
    summary['provenance']={'labels_sha256':digest(a.labels),'predictions_sha256':digest(a.predictions),'scorer_sha256':digest(__file__)}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.private_out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    a.private_out.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in trace))
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
