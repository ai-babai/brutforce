"""Measure HTTP end-to-end latency on a fixed, unlabeled public image set.

Use the same manifest and exact request bytes on each host. The first request
is reported separately; warm statistics use distinct subsequent images only.
"""
import argparse
import hashlib
import json
import math
import platform
import signal
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def percentile(values, pct):
    if not values:return None
    ordered=sorted(values)
    rank=(len(ordered)-1)*pct
    low=math.floor(rank);high=math.ceil(rank)
    return round(ordered[low]+(ordered[high]-ordered[low])*(rank-low),2)


def _deadline(_signum,_frame):raise TimeoutError('hard total HTTP request deadline')


def health(url,timeout):
    parts=urllib.parse.urlsplit(url)
    health_url=urllib.parse.urlunsplit((parts.scheme,parts.netloc,'/healthz','',''))
    with urllib.request.urlopen(health_url,timeout=timeout) as response:
        return json.load(response)


def send(url,path,sha,track,timeout):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError(f'image SHA mismatch: {path}')
    boundary='codex-benchmark-fixed-20260924'
    head=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
          f'Content-Type: application/octet-stream\r\n\r\n').encode()
    body=head+raw+f'\r\n--{boundary}--\r\n'.encode()
    parts=urllib.parse.urlsplit(url)
    query=urllib.parse.parse_qsl(parts.query,keep_blank_values=True)
    query=[(key,value) for key,value in query if key!='track']+[('track',track)]
    request_url=urllib.parse.urlunsplit((parts.scheme,parts.netloc,parts.path,urllib.parse.urlencode(query),''))
    req=urllib.request.Request(request_url,data=body,headers={'Content-Type':f'multipart/form-data; boundary={boundary}'},method='POST')
    start=time.perf_counter();prior=signal.signal(signal.SIGALRM,_deadline)
    signal.setitimer(signal.ITIMER_REAL,timeout)
    try:
        try:
            with urllib.request.urlopen(req,timeout=timeout) as resp:
                status=resp.status;content=resp.read(262144)
            error=None
        except urllib.error.HTTPError as exc:
            status=exc.code;content=exc.read(262144);error=f'HTTP {exc.code}'
        except Exception as exc:
            status=None;content=b'';error=f'{type(exc).__name__}: {exc}'
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,prior)
    elapsed=round((time.perf_counter()-start)*1000,2)
    try:parsed=json.loads(content) if content else None
    except Exception:parsed={'response_text':content.decode('utf-8','replace')[:1000]}
    timings=parsed.get('timings_ms') if isinstance(parsed,dict) else None
    response_sha=parsed.get('image_sha256') if isinstance(parsed,dict) else None
    prediction=({key:parsed[key] for key in ('slug','action','ranked_slugs') if key in parsed}
                if isinstance(parsed,dict) and status==200 else None)
    if status==200 and response_sha!=sha:
        error='server image SHA mismatch'
    return {'http_status':status,'elapsed_ms':elapsed,'error':error,'response_image_sha256':response_sha,
            'prediction':prediction,
            'server_timings_ms':timings,'ocr_error':parsed.get('ocr_error') if isinstance(parsed,dict) and status==200 else None,
            'ocr_executed':bool(timings and timings.get('ocr_ms',0)>0),
            'selection_reason':parsed.get('selection',{}).get('selection_reason') if isinstance(parsed,dict) and status==200 else None}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--manifest',type=Path,required=True)
    ap.add_argument('--image-root',type=Path,required=True)
    ap.add_argument('--url',required=True)
    ap.add_argument('--hardware-label',required=True)
    ap.add_argument('--device',required=True)
    ap.add_argument('--cpu-threads',type=int,required=True,help='OCR CPU thread count')
    ap.add_argument('--omp-threads',type=int,required=True,help='OMP_NUM_THREADS used by the server')
    ap.add_argument('--code-sha256')
    ap.add_argument('--index-sha256')
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--limit',type=int,default=24)
    ap.add_argument('--timeout',type=float,default=120)
    args=ap.parse_args()
    manifest_bytes=args.manifest.read_bytes();cases=json.loads(manifest_bytes)['cases'][:args.limit]
    if len({x['sha256'] for x in cases})!=len(cases):raise ValueError('benchmark cases must have unique image SHA')
    health_status=health(args.url,min(args.timeout,10))
    if health_status.get('status')!='ready':raise RuntimeError('server is not ready')
    rows=[]
    for index,case in enumerate(cases):
        rel=Path(case['path'])
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('manifest paths must be relative and safe')
        path=args.image_root/rel
        result=send(args.url,path,case['sha256'],case['track'],args.timeout)
        result.update({'case_id':case['case_id'],'image_sha256':case['sha256'],'track':case['track'],'sequence':index+1,'phase':'first_request_after_ready' if index==0 else 'warm_distinct'})
        rows.append(result)
        print(json.dumps({k:result[k] for k in ('case_id','http_status','elapsed_ms','error','phase')}),flush=True)
    warm=[x['elapsed_ms'] for x in rows[1:] if x['http_status']==200 and x['error'] is None]
    full=[x['elapsed_ms'] for x in rows[1:] if x['http_status']==200 and x['error'] is None
          and x['ocr_executed'] and x['ocr_error'] is None]
    summary={'version':'pipeline-http-benchmark-20260924','at_utc':datetime.now(timezone.utc).isoformat(),
             'hardware_label':args.hardware_label,'device':args.device,'host_platform':platform.platform(),
             'url':args.url,'ocr_cpu_threads':args.cpu_threads,'omp_threads':args.omp_threads,
             'code_sha256':args.code_sha256,
             'index_sha256':args.index_sha256,'healthz':health_status,
             'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
             'cases_total':len(rows),'distinct_image_sha256':len({x['image_sha256'] for x in rows}),
             'first_request_ms':rows[0]['elapsed_ms'] if rows else None,
             'warm_successes':len(warm),'warm_failures':len(rows)-1-len(warm),
             'ocr_error_count':sum(x['ocr_error'] is not None for x in rows),
             'ocr_not_executed_count':sum(not x['ocr_executed'] for x in rows if x['http_status']==200),
             'full_pipeline_successes':sum(x['http_status']==200 and x['error'] is None and x['ocr_executed']
                                           and x['ocr_error'] is None for x in rows),
             'full_pipeline_warm_successes':len(full),
             'full_pipeline_warm_p50_ms':percentile(full,.5),
             'full_pipeline_warm_p95_ms':percentile(full,.95),
             'full_pipeline_warm_max_ms':round(max(full),2) if full else None,
             'warm_p50_ms':percentile(warm,.50),'warm_p95_ms':percentile(warm,.95),
             'warm_max_ms':round(max(warm),2) if warm else None,
             'under_3000_ms':sum(x<=3000 for x in warm),'under_10000_ms':sum(x<=10000 for x in warm),
             'server_stage_p50_ms':{name:percentile([x['server_timings_ms'][name] for x in rows[1:]
                                                  if x['http_status']==200 and x['error'] is None and x['server_timings_ms']
                                                  and name in x['server_timings_ms']],.5)
                                    for name in ('decode_ms','detect_ms','class_ms','label_detect_ms','whole_embedding_ms',
                                                 'label_embedding_ms','ocr_ms','rank_ms','fusion_ms','total_ms')},
             'results':rows}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
