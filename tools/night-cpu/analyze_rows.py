#!/usr/bin/env python3
"""Summarize complete raw HTTP timings without dropping failures."""
import argparse
import collections
import json
import math
import statistics
from pathlib import Path


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values)-1, math.ceil(q*len(values))-1)], 2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('rows', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    rows = [json.loads(line) for line in a.rows.read_text().splitlines() if line.strip()]
    successes = [r for r in rows if r['http_status'] == 200 and r['elapsed_ms'] <= 10000]
    elapsed = [r['elapsed_ms'] for r in successes]
    stages = collections.defaultdict(list)
    for row in successes:
        for k, v in row['result']['timings_ms'].items():
            stages[k].append(v)
    report = {'rows': len(rows),
              'http_status': dict(collections.Counter(str(r['http_status']) for r in rows)),
              'latency_ms_success_only': {k: percentile(elapsed, q) for k, q in
                                          [('p50', .5), ('p95', .95), ('p99', .99), ('max', 1)]},
              'over_3s_all_requests': sum(r['elapsed_ms'] > 3000 for r in rows),
              'over_10s_all_requests': sum(r['elapsed_ms'] > 10000 for r in rows),
              'strict_deadline_success': len(successes),
              'failures': [{'case_id': r['case_id'], 'http_status': r['http_status'],
                            'elapsed_ms': r['elapsed_ms'], 'error': r['result'].get('error')}
                           for r in rows if r['http_status'] != 200 or r['elapsed_ms'] > 10000],
              'stage_ms_success_only': {k: {'p50': percentile(v, .5), 'p95': percentile(v, .95),
                                            'max': percentile(v, 1)} for k, v in stages.items()}}
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'rows': report['rows'], 'status': report['http_status'],
                      'latency': report['latency_ms_success_only'],
                      'failures': report['failures']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
