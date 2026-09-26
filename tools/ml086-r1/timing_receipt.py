"""Gold-blind per-run timing and machine provenance; never substitute stage sum for wall."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def summary(values):
    ordered = sorted(values)
    return {'measured_input_count': len(ordered),
            'p50_ms': round(statistics.median(ordered), 3),
            'p95_ms': round(ordered[min(len(ordered)-1, int(len(ordered)*.95))], 3),
            'max_ms': round(ordered[-1], 3),
            'over_3000_ms': sum(x > 3000 for x in ordered),
            'over_8500_ms': sum(x > 8500 for x in ordered),
            'over_10000_ms': sum(x > 10000 for x in ordered),
            'sum_stage_ms_not_wall': round(sum(ordered), 3)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gpu-partial', type=Path, required=True)
    p.add_argument('--gpu-delta', type=Path, required=True)
    p.add_argument('--cpu-partial', type=Path, required=True)
    p.add_argument('--cpu-delta', type=Path, required=True)
    p.add_argument('--gpu-match', type=Path, required=True)
    p.add_argument('--cpu-match', type=Path, required=True)
    p.add_argument('--cpu-partial-receipt', type=Path, required=True)
    p.add_argument('--cpu-delta-receipt', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    specs = [
        ('gpu_reader_initial_partial', a.gpu_partial, 'elapsed_ms', 'status', 'ok',
         'Pod A Qwen3-VL GPU per eligible target JPEG, excludes model startup/transfer/HTTP', 12.714),
        ('gpu_reader_delta19', a.gpu_delta, 'elapsed_ms', 'status', 'ok',
         'Pod A Qwen3-VL GPU per new eligible target JPEG, excludes model startup/transfer/HTTP', 4.791),
        ('cpu_paddle_initial_partial', a.cpu_partial, 'ocr_ms', None, None,
         'Pod A Paddle OCR CPU2 per eligible target JPEG, excludes startup/transfer/HTTP', None),
        ('cpu_paddle_delta19', a.cpu_delta, 'ocr_ms', None, None,
         'Pod A Paddle OCR CPU2 per new eligible target JPEG, excludes startup/transfer/HTTP', None),
        ('offline_matcher_gpu_full', a.gpu_match, 'matcher_elapsed_ms', 'reader_status', 'ok',
         'Mac CPU frozen matcher stage after cached Qwen text; excludes parse/serialization/HTTP', None),
        ('offline_matcher_cpu_full', a.cpu_match, 'matcher_elapsed_ms', 'reader_status', 'ok',
         'Mac CPU frozen matcher stage after cached Paddle text; excludes parse/serialization/HTTP', None),
    ]
    hardware_pod = {'pod_id': 'caewvjrhqw54id', 'cpu_lscpu_model': 'AMD EPYC 7443 24-Core Processor',
                    'host_visible_logical_cpu': 48, 'cgroup_cpu_quota_cores': 10.2,
                    'cgroup_memory_limit_bytes': 61999996928,
                    'gpu': 'NVIDIA RTX PRO 4500 Blackwell', 'gpu_total_mib': 32623,
                    'driver': '580.173.02'}
    outputs = []
    for name, path, key, status_key, allowed, scope, cold in specs:
        dataset = rows(path)
        measured = [r[key] for r in dataset if not status_key or r[status_key] == allowed]
        info = {'run': name, 'raw_path': str(path), 'raw_sha256': sha(path),
                'input_rows': len(dataset), 'eligible_stage_rows': len(measured),
                'timing_scope': scope, 'cold_load_s': cold,
                'wall_total_ms': None, 'wall_total_status': 'not_recorded_by_original_runner',
                **summary(measured)}
        if name.startswith('gpu_'):
            info['hardware'] = {**hardware_pod, 'reader_concurrency': 1}
        elif name.startswith('cpu_paddle'):
            info['hardware'] = {**hardware_pod, 'cpu_ocr_threads': 2, 'ocr_concurrency': 1}
        else:
            info['hardware'] = {'machine': 'Mac16,8', 'cpu': 'Apple M4 Pro',
                                'logical_cpu': 14, 'memory_bytes': 51539607552,
                                'matcher_concurrency': 1}
        outputs.append(info)
    receipt = {'run_family': 'ML-086 R1 v6', 'gold_loaded': False,
               'http_status': 'not_measured',
               'gpu_cpu_overlap': 'Initial partial266 Paddle CPU2 and Qwen GPU ran concurrently on Pod A; delta19 scheduling also shared Pod A',
               'cpu_partial_receipt_sha256': sha(a.cpu_partial_receipt),
               'cpu_delta_receipt_sha256': sha(a.cpu_delta_receipt),
               'r1_config_sha256': sha(a.config), 'source_sha256': sha(Path(__file__)),
               'runs': outputs}
    a.out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'runs': len(outputs), 'receipt_sha256': sha(a.out)}))


if __name__ == '__main__':
    main()
