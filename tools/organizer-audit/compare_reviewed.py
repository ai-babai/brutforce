"""Compare frozen predictions on a separately reviewed real-photo set.

This evaluator runs after predictions are exported; it cannot alter inference.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from score_reviewed import read_jsonl, score, normalized


def compare(labels, specs):
    results=[]
    for spec in specs:
        path=Path(spec['path']);predictions=read_jsonl(path)
        by_id={r['case_id']:r for r in predictions}
        for variant in spec.get('variants',[None]):
            summary,traces=score(labels,predictions,variant)
            groups=defaultdict(list)
            for trace in traces:
                if trace['annotation_status']=='exact':groups[trace['scene_group']].append(trace)
            exact=[r for r in traces if r['annotation_status']=='exact']
            errors={
                'missing_or_error':sum(r['status']!='ok' for r in exact),
                'correct_not_in_top20':sum(r['status']=='ok' and r['rank'] is None for r in exact),
                'correct_in_top20_not_top1':sum(r['rank'] is not None and r['rank']>1 for r in exact),
                'top1_correct':sum(r['rank']==1 for r in exact),
            }
            summary['name']=spec['name'];summary['family']=spec.get('family','unknown')
            summary['prediction_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            summary['exact_scene_groups']=len(groups)
            summary['scene_macro_top1']=sum(sum(r['rank']==1 for r in rows)/len(rows) for rows in groups.values())/len(groups) if groups else None
            summary['rank_error_breakdown']=errors
            results.append(summary)
    return {'scope':'Post-hoc diagnostic, no inference or weight fitting. Reviewed subset and repeated identities can bias accuracy.', 'models':results}


def main():
    p=argparse.ArgumentParser();p.add_argument('--labels',type=Path,required=True);p.add_argument('--specs',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=compare(read_jsonl(a.labels),json.loads(a.specs.read_text()))
    result['labels_sha256']=hashlib.sha256(a.labels.read_bytes()).hexdigest()
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'models':len(result['models']),'labels_sha256':result['labels_sha256']}))
if __name__=='__main__':main()
