"""Gold-blind strict-10s client for fresh local B→Roman HTTP cascade."""
import argparse
import hashlib
import json
import socket
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PREFIX = Path('/Users/skif/ml-data/brutforce/integration-20260925-1700/model/input-stage')


def rows(path):
    return [json.loads(line) for line in path.open(encoding='utf-8')]


def wait_ready(base, seconds=90):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            with urlopen(base+'/healthz',timeout=2) as response:
                if response.status==200:
                    return
        except (OSError,URLError):
            pass
        time.sleep(1)
    raise TimeoutError('Cascade server did not become ready after a timed-out request')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--base-url',default='http://127.0.0.1:8092')
    p.add_argument('--output',default='online-http-316.jsonl')
    p.add_argument('--limit',type=int,default=0)
    p.add_argument('--indices',default='')
    p.add_argument('--mode',choices=('five','twenty'),default='twenty')
    a=p.parse_args()
    root=a.root.resolve()
    requests=rows(root/'online-input-v1/requests.jsonl')
    if len(requests)!=316 or len({r['case_id'] for r in requests})!=316:
        raise ValueError('All 316 public requests required')
    selected=set(int(s) for s in a.indices.split(',') if s) if a.indices else None
    output=root/a.output
    prior=rows(output) if output.exists() else []
    done={r['case_id'] for r in prior}
    if len(done)!=len(prior):
        raise ValueError('Duplicate output case')
    wait_ready(a.base_url)
    with output.open('a',encoding='utf-8') as stream:
        for index,case in enumerate(requests):
            if selected is not None and index not in selected:
                continue
            if a.limit and index>=a.limit:
                break
            if case['case_id'] in done:
                continue
            path=root/'input-stage'/Path(case['query_path']).relative_to(PREFIX)
            body=path.read_bytes()
            if hashlib.sha256(body).hexdigest()!=case['query_sha256']:
                raise ValueError('Query SHA changed '+case['case_id'])
            req=Request(a.base_url+'/v1/eval/predict?track='+case['track']+'&mode='+a.mode,
                data=body,method='POST',headers={'Content-Type':'image/jpeg','X-Case-ID':case['case_id']})
            t0=time.perf_counter()
            response=None;http_status=None;error=None
            try:
                with urlopen(req,timeout=10) as handle:
                    http_status=handle.status
                    response=json.load(handle)
                elapsed=round((time.perf_counter()-t0)*1000,3)
                if (http_status!=200 or response.get('case_id')!=case['case_id'] or
                        response.get('track')!=case['track'] or
                        response.get('query_sha256')!=case['query_sha256']):
                    raise ValueError('Cascade response/case mismatch')
                status='ok' if elapsed<=10000 else 'timeout'
            except HTTPError as exc:
                elapsed=round((time.perf_counter()-t0)*1000,3)
                http_status=exc.code
                error='HTTPError: '+exc.read(500).decode(errors='replace')
                status='error'
            except (TimeoutError,socket.timeout,URLError) as exc:
                elapsed=round((time.perf_counter()-t0)*1000,3)
                error=type(exc).__name__+': '+str(exc)[:300]
                status='timeout'
            record=dict(case_id=case['case_id'],basket=case['basket'],track=case['track'],
                query_sha256=case['query_sha256'],status=status,http_status=http_status,
                elapsed_ms=elapsed,error=error,response=response)
            stream.write(json.dumps(record,ensure_ascii=False)+'\n');stream.flush()
            print(f'{index+1}/316 {case["case_id"]} {status} {elapsed}ms',flush=True)
            if status!='ok':
                wait_ready(a.base_url)
    finished=rows(output)
    print(json.dumps(dict(rows=len(finished),ok=sum(r['status']=='ok' for r in finished),
        timeout=sum(r['status']=='timeout' for r in finished),
        error=sum(r['status']=='error' for r in finished))))


if __name__=='__main__':
    main()
