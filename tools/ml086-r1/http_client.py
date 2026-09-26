"""Gold-blind sequential full-frame HTTP wall-time capture for isolated R1."""
import argparse
import hashlib
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path


def sha(content):
    return hashlib.sha256(content).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', required=True)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--image-root', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--server-source', type=Path, required=True)
    p.add_argument('--matcher-source', type=Path, required=True)
    p.add_argument('--reader-source', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--ort-config', type=Path, required=True)
    p.add_argument('--sealed-gpu', type=Path, nargs='+', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    if a.url != 'http://127.0.0.1:8786/infer':
        raise ValueError('only owner-approved isolated loopback HTTP path allowed')
    rows = [json.loads(x) for x in a.inputs.read_text().splitlines() if x.strip()]
    if len(rows) != 316 or len({r['case_id'] for r in rows}) != 316:
        raise ValueError('full frozen+organizer input required')
    sealed_rows = [json.loads(x) for path in a.sealed_gpu
                   for x in path.read_text().splitlines() if x.strip()]
    sealed = {r['case_id']: r for r in sealed_rows}
    if len(sealed) != len(sealed_rows):
        raise ValueError('duplicate sealed case ID')
    if set(sealed) != {r['case_id'] for r in rows}:
        raise ValueError('sealed GPU predictions must cover same 316 IDs')
    with urllib.request.urlopen(a.url.replace('/infer', '/healthz'), timeout=10) as response:
        health = json.loads(response.read())
    if not health.get('ready') or health.get('inputs') != 316:
        raise ValueError('isolated ORT6 + reader HTTP service not ready')
    result = []
    run_start = time.perf_counter()
    with a.out.open('w') as output:
        for row in rows:
            image = (a.image_root / row['query_path']).read_bytes()
            if sha(image) != row['query_sha256']:
                raise ValueError('public query SHA mismatch ' + row['case_id'])
            request = urllib.request.Request(a.url, data=image, method='POST',
                                             headers={'Content-Type': 'image/jpeg',
                                                      'X-Case-ID': row['case_id']})
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    status = response.status
                    payload = json.loads(response.read())
            except urllib.error.HTTPError as exc:
                status = exc.code
                payload = json.loads(exc.read())
            except Exception as exc:
                status = None
                payload = {'error': type(exc).__name__ + ': ' + str(exc)[:200]}
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            if status == 200:
                if (payload.get('case_id') != row['case_id'] or
                        payload.get('query_sha256') != row['query_sha256'] or
                        payload.get('target_crop_sha256') != row['crop_sha256']):
                    raise ValueError('HTTP response query/crop mismatch ' + row['case_id'])
                ranks = payload['result']['ranked_slugs']
                if sorted(ranks) != sorted(row['fixed_top20']):
                    raise ValueError('HTTP changed fixed Top20 pool')
            item = {'case_id': row['case_id'], 'dataset': row['dataset'], 'track': row['track'],
                    'query_sha256': row['query_sha256'], 'target_crop_sha256': row['crop_sha256'],
                    'fixed_top20_sha256': sha(json.dumps(row['fixed_top20'], ensure_ascii=False,
                                                       separators=(',', ':')).encode()),
                    'http_status': status, 'elapsed_ms': elapsed,
                    'result': payload.get('result'), 'stage_timings_ms': payload.get('timings_ms'),
                    'decision_trace': payload.get('decision_trace'),
                    'error': payload.get('error'),
                    'matches_sealed_offline_prediction':
                    payload.get('result') == sealed[row['case_id']]['result'] if status == 200 else None}
            output.write(json.dumps(item, ensure_ascii=False) + '\n')
            output.flush()
            result.append(item)
            if len(result) % 20 == 0:
                print(json.dumps({'processed': len(result), 'total': len(rows),
                                  'case_id': row['case_id'], 'elapsed_ms': elapsed}), flush=True)
    run_wall_total_ms = round((time.perf_counter() - run_start) * 1000, 3)
    timings = [x['elapsed_ms'] for x in result]
    timings_sorted = sorted(timings)
    percentile = lambda q: round(timings_sorted[min(len(timings)-1, int(len(timings)*q))], 3)
    first_reader_index = next(i for i, row in enumerate(rows) if row['crop'])
    warm = sorted(t for i, t in enumerate(timings) if i not in {0, first_reader_index})
    with urllib.request.urlopen(a.url.replace('/infer', '/healthz'), timeout=10) as response:
        health_after = json.loads(response.read())
    receipt = {'rows': len(result), 'unique_case_ids': len({r['case_id'] for r in result}),
               'http_status_counts': {str(s): sum(r['http_status'] == s for r in result)
                                      for s in set(r['http_status'] for r in result)},
               'hardware_scope': 'isolated host loopback full-frame POST; not TEST',
               'timing_scope': 'full request upload + ORT6 + JPEG crop + GPU reader + matcher + response',
               'run_wall_total_ms': run_wall_total_ms,
               'cold_load_excluded': True, 'p50_ms': round(statistics.median(timings), 3),
               'cold_first_request_ms': timings[0],
               'cold_first_reader_request': {'case_id': rows[first_reader_index]['case_id'],
                                             'elapsed_ms': timings[first_reader_index]},
               'warm_p50_ms': round(statistics.median(warm), 3),
               'warm_p95_ms': warm[min(len(warm)-1, int(len(warm)*.95))],
               'warm_max_ms': warm[-1],
               'cold_load_s': {'ort6': health['ort6_load_s'], 'gpu_reader': health['gpu_load_s']},
                'hardware': {'cpu': health['cpu'], 'cpu_model': health['cpu_model'],
                             'host_visible_logical_cpu': health['host_visible_logical_cpu'],
                             'cgroup_cpu_max': health['cgroup_cpu_max'],
                             'cgroup_memory_max': health['cgroup_memory_max'],
                             'ort6_threads': health['ort6_threads'], 'gpu': health['gpu'],
                             'gpu_total_bytes': health['gpu_total_bytes'],
                             'gpu_memory_allocated_at_start_bytes': health['gpu_memory_allocated_bytes'],
                             'gpu_peak_allocated_bytes': health_after['gpu_peak_allocated_bytes'],
                             'gpu_peak_reserved_bytes': health_after['gpu_peak_reserved_bytes']},
               'p95_ms': percentile(.95), 'max_ms': max(timings),
               'over_3000_ms': sum(x > 3000 for x in timings),
               'over_8500_ms': sum(x > 8500 for x in timings),
               'over_10000_ms': sum(x > 10000 for x in timings),
               'sealed_prediction_mismatches': sum(x['matches_sealed_offline_prediction'] is False
                                                   for x in result),
               'raw_sha256': sha(a.out.read_bytes()), 'source_sha256': sha(a.source.read_bytes()),
               'server_source_sha256': sha(a.server_source.read_bytes()),
               'matcher_source_sha256': sha(a.matcher_source.read_bytes()),
               'reader_source_sha256': sha(a.reader_source.read_bytes()),
               'config_sha256': sha(a.config.read_bytes()),
               'ort_config_sha256': sha(a.ort_config.read_bytes()),
               'input_sha256': sha(a.inputs.read_bytes()), 'gold_loaded': False}
    receipt['sealed_gpu_sha256'] = [sha(path.read_bytes()) for path in a.sealed_gpu]
    a.out.with_suffix('.receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
