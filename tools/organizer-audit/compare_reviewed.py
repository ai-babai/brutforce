"""Compare frozen predictions on a separately reviewed real-photo set.

This evaluator runs after predictions are exported; it cannot alter inference.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from score_reviewed import read_jsonl, score, normalized


def adapt_completed_offline(rows, version):
    """Legacy ablation writer emits a row only after completion, without status.

    This opt-in adapter requires its exact recorded version and full output
    structure. An explicit error is never promoted to success.
    """
    output=[]
    for row in rows:
        if (row.get('version') != version or 'result' in row or 'http_status' in row
                or not isinstance(row.get('variants_top20'),dict)
                or not isinstance(row.get('predictions'),dict)
                or set(row['variants_top20']) != set(row['predictions'])
                or not row['variants_top20']):
            raise ValueError('offline adapter version or structure mismatch')
        output.append({**row,'status':row.get('status','error' if row.get('error') else 'ok')})
    return output


def compare(labels, specs):
    results=[]
    for spec in specs:
        path=Path(spec['path']);predictions=read_jsonl(path)
        if spec.get('completed_offline_version'):
            predictions=adapt_completed_offline(predictions,spec['completed_offline_version'])
        by_id={r['case_id']:r for r in predictions}
        for variant in spec.get('variants',[None]):
            summary,traces=score(labels,predictions,variant)
            groups=defaultdict(list)
            for trace in traces:
                if trace['annotation_status']=='exact':groups[trace['expected_slug']].append(trace)
            exact=[r for r in traces if r['annotation_status']=='exact']
            errors={
                'missing_or_error':sum(r['status']!='ok' for r in exact),
                'correct_not_in_top20':sum(r['status']=='ok' and r['rank'] is None for r in exact),
                'correct_in_top20_not_top1':sum(r['rank'] is not None and r['rank']>1 for r in exact),
                'top1_correct':sum(r['rank']==1 for r in exact),
            }
            summary['name']=spec['name'];summary['family']=spec.get('family','unknown')
            summary['prediction_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            if spec.get('completed_offline_version'):
                summary['normalization']={'completed_offline_version':spec['completed_offline_version'],
                  'missing_status':'ok only for completed rows from this known offline writer; explicit errors retained'}
            summary['exact_product_groups']=len(groups)
            summary['product_macro_top1']=sum(sum(r['rank']==1 for r in rows)/len(rows) for rows in groups.values())/len(groups) if groups else None
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
