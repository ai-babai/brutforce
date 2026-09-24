"""Seal a separate locally reviewed photo set; never edit the frozen suite gold."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from score_reviewed import read_jsonl, validate_labels


def build(queries, suite, catalog, reviews):
    unique={r['case_id']:r for r in queries['cases'] if not r.get('duplicate_of')}
    old_hashes={r['image_sha256'] for r in suite['cases']}
    allowed={r['slug'] for r in catalog['references']}
    validate_labels(reviews, allowed)
    if {r['image_id'] for r in reviews} != set(unique):
        raise ValueError('review coverage differs from unique organizer manifest')
    output=[]
    for row in sorted(reviews,key=lambda r:r['image_id']):
        row=json.loads(json.dumps(row))
        query=unique[row['image_id']]
        if row['sha256'] != query['sha256']:
            raise ValueError('review SHA differs from organizer manifest')
        if not row.get('evidence_text') or not row.get('scene_group'):
            raise ValueError('each photo needs evidence and scene grouping')
        if not row.get('review',{}).get('reviewer') or not row['review'].get('method'):
            raise ValueError('reviewer and review method required')
        row['review']['prior_seen_group']='familiar12' if row['sha256'] in old_hashes else 'newly_reviewed88'
        row['review']['annotation_origin']='local_agent_review_not_organizer_gold'
        output.append(row)
    counts=Counter(r['status'] for r in output)
    summary={'scope':'Local agent review, separate from immutable v1 gold',
             'unique_images':len(output),'source_files':len(queries['cases']),
             'duplicate_files':len(queries['cases'])-len(output),
             'status_counts':dict(counts),'exact_images':counts['exact'],
             'exact_scene_groups':len({r['scene_group'] for r in output if r['status']=='exact'}),
             'all_scene_groups':len({r['scene_group'] for r in output}),
             'prior_seen_counts':dict(Counter(r['review']['prior_seen_group'] for r in output)),
             'limitations':['Agent-reviewed labels are not the organizer answer key.',
                           'Catalog-unresolved is not evidence that a wine is absent.',
                           'Verified-only accuracy is subject to selection bias; report total coverage.',
                           'Repeated photos of one wine are not independent product identities.',
                           'DeepSeek OCR-assisted verification is not fully independent of the DeepSeek baseline.']}
    return output,summary


def main():
    p=argparse.ArgumentParser()
    for name in ('queries','suite','catalog','out','summary'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--review',type=Path,action='append',required=True)
    a=p.parse_args()
    if a.out.exists() or a.summary.exists():
        p.error('sealed outputs already exist; select new version paths')
    paths=[a.queries,a.suite,a.catalog,*a.review]
    inputs={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    rows,summary=build(json.loads(a.queries.read_text()),json.loads(a.suite.read_text()),json.loads(a.catalog.read_text()),[r for path in a.review for r in read_jsonl(path)])
    content=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows)
    summary['annotations_sha256']=hashlib.sha256(content.encode()).hexdigest()
    summary['input_hashes']=inputs
    a.out.parent.mkdir(parents=True,exist_ok=True);a.summary.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(content);a.summary.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='input_hashes'},ensure_ascii=False))

if __name__=='__main__':main()
