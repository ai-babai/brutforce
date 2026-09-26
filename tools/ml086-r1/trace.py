"""Public-only per-request decision traces from sealed R1 raw; no inference or gold."""
import argparse
import hashlib
import json
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--scorer-raw', type=Path, nargs='+', required=True)
    p.add_argument('--timing-receipt', type=Path, required=True)
    p.add_argument('--variant', choices=['gpu', 'cpu'], required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    inputs = read(a.inputs)
    output_rows = [r for path in a.scorer_raw for r in read(path)]
    scored = {r['case_id']: r for r in output_rows}
    if len(inputs) != len(scored) or len(output_rows) != len(scored):
        raise ValueError('full R1 input and distinct scored IDs required')
    hardware_runs = json.loads(a.timing_receipt.read_text())['runs']
    reader_hardware = next(r['hardware'] for r in hardware_runs
                           if r['run'] == ('gpu_reader_initial_partial' if a.variant == 'gpu'
                                           else 'cpu_paddle_initial_partial'))
    matcher_hardware = next(r['hardware'] for r in hardware_runs
                            if r['run'] == 'offline_matcher_' + a.variant + '_full')
    input_hash = sha(a.inputs)
    raw_hashes = [sha(path) for path in a.scorer_raw]
    timing_hash = sha(a.timing_receipt)
    traces = []
    for row in inputs:
        raw = scored[row['case_id']]
        if (raw['query_sha256'] != row['query_sha256'] or
                raw['target_crop_sha256'] != row['crop_sha256'] or
                raw['fixed_top20'] != row['fixed_top20'] or
                raw['target_box'] != row['target_box']):
            raise ValueError('R1 decision raw differs from input provenance')
        observations = raw['observations']
        status = raw['reader_status']
        if status != 'ok' and observations:
            raise ValueError('no-target/error reader must not invent observations')
        before = raw['fixed_top20']
        after = raw['ranked_slugs']
        result = raw['result']
        traces.append({'case_id': row['case_id'], 'dataset': row['dataset'],
                       'track': row['track'], 'public_query_sha256': row['query_sha256'],
                       'target': {'status': row['target_metadata_state'],
                                  'selected_box': row['target_box'],
                                  'origin_target_png_sha256': row['origin_target_png_sha256'],
                                  'reader_crop_sha256': row['crop_sha256'],
                                  'missing_reason': None if row['crop'] else 'confirmed_no_target'},
                       'reader': {'kind': a.variant, 'status': status, 'observations': observations,
                                  'polygon_missing_reason': 'Qwen has no token localization' if a.variant == 'gpu'
                                                             else None,
                                  'confidence_missing_reason': 'Qwen text is not calibrated per token' if a.variant == 'gpu'
                                                               else None},
                       'pool': {'id': raw['candidate_pool_id'],
                                'sha256': raw['candidate_pool_sha256'], 'fixed_top20': before},
                       'matcher': {'candidate_evidence': raw['candidate_evidence'],
                                   'rerank_reason': 'same_top1_producer_family_evidence_sort'
                                                    if before != after else 'no_rank_change',
                                   'ranked_top20': after,
                                   'explicit_contradiction_count': sum(
                                       x['grape_relation'] == 'contradiction'
                                       for x in raw['candidate_evidence'])},
                       'final': {'action': result.get('action'), 'slug': result.get('slug'),
                                 'no_match': result.get('action') == 'no_match',
                                 'evaluation_status': raw['evaluation_status']},
                       'timing': {'scope': 'cached offline reader + matcher, not HTTP',
                                  'reader_ms': raw['reader_elapsed_ms'],
                                  'matcher_ms': raw['matcher_elapsed_ms'],
                                  'original_ort6_http_ms': raw['original_ort6_elapsed_ms']},
                       'hardware': {'reader': reader_hardware, 'matcher': matcher_hardware},
                       'source_sha256': {'input_manifest': input_hash,
                                         'scorer_raw': raw_hashes,
                                         'timing_receipt': timing_hash},
                       'gold_loaded': False})
    a.out.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in traces))
    receipt = {'rows': len(traces), 'unique_ids': len(scored), 'variant': a.variant,
               'gold_loaded': False, 'timing_scope': 'offline only',
               'raw_sha256': sha(a.out), 'source_sha256': sha(Path(__file__)),
               'input_sha256': input_hash, 'scorer_raw_sha256': raw_hashes}
    a.out.with_suffix('.receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
