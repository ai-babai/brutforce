"""Gold-blind fresh B HTTP parity check against previously saved B output."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen


def rows(path):
    return [json.loads(line) for line in path.open(encoding='utf-8')]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--url', default='http://127.0.0.1:8091/v1/eval/predict')
    p.add_argument('--indices',default='0,14,20,69,104,144,151,158,213,267')
    p.add_argument('--output',default='b-parity-smoke.json')
    a = p.parse_args()
    root = a.root.resolve()
    public = rows(root/'online-input-v1/requests.jsonl')
    saved = {r['case_id']:r for r in rows(root/'input-v1/requests.jsonl')}
    indices = [int(x) for x in a.indices.split(',') if x]
    out = []
    for index in indices:
        case = public[index]
        path = root/'input-stage'/Path(case['query_path']).relative_to(
            '/Users/skif/ml-data/brutforce/integration-20260925-1700/model/input-stage')
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != case['query_sha256']:
            raise ValueError('Query SHA mismatch '+case['case_id'])
        req = Request(a.url+'?track='+case['track'],data=body,method='POST',
            headers={'Content-Type':'image/jpeg'})
        t0 = time.perf_counter()
        with urlopen(req,timeout=60) as response:
            status = response.status
            result = json.load(response)
        elapsed = round((time.perf_counter()-t0)*1000,2)
        ranked = [x['slug'] for x in result.get('variants_top20',{}).get('all',[])]
        prior = saved[case['case_id']]
        same_rank = ranked==prior['ranked_slugs']
        same_action = (result.get('action')==prior['b_action'] and result.get('slug')==prior['b_slug'])
        out.append(dict(case_id=case['case_id'],basket=case['basket'],track=case['track'],
            status=status,elapsed_ms=elapsed,image_sha_match=result.get('image_sha256')==case['query_sha256'],
            same_rank=same_rank,same_action=same_action,old_top1=prior['ranked_slugs'][:1],
            new_top1=ranked[:1],new_ocr_error=result.get('ocr_error'),
            timings_ms=result.get('timings_ms')))
        print(f'{case["case_id"]} {elapsed}ms rank={same_rank} action={same_action}',flush=True)
    (root/a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(rows=len(out),http_200=sum(x['status']==200 for x in out),
        rank_equal=sum(x['same_rank'] for x in out),action_equal=sum(x['same_action'] for x in out))))


if __name__ == '__main__':
    main()
