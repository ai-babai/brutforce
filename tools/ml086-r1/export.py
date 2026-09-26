"""Seal gold-blind, explicitly offline R1 raw for an independent scorer."""
import argparse
import hashlib
import json
from pathlib import Path


MODEL = {'gpu_reader': {'model': 'Qwen/Qwen3-VL-2B-Instruct',
                        'revision': '89644892e4d85e24eaac8bacfd4f463576704203'},
         'cpu_reader': {'model': 'PaddleOCR', 'revision': 'runtime_owner_receipt_pending'}}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--matched', type=Path, required=True)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--public', type=Path, required=True)
    p.add_argument('--original-ort6', type=Path, required=True)
    p.add_argument('--ort-config', type=Path, required=True)
    p.add_argument('--cards', type=Path, required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--reader-raw', type=Path, required=True)
    p.add_argument('--cpu-receipt', type=Path)
    p.add_argument('--variant', choices=MODEL, required=True)
    p.add_argument('--dataset', choices=['eval', 'organizer'], required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError(a.out)
    if a.variant == 'cpu_reader' and not a.cpu_receipt:
        raise ValueError('CPU reader requires runtime owner provenance receipt')
    inputs = {r['case_id']: r for r in jsonl(a.inputs) if r['dataset'] == a.dataset}
    matched = [r for r in jsonl(a.matched) if r['dataset'] == a.dataset]
    baseline = {r['case_id']: r for r in jsonl(a.original_ort6)}
    if len(inputs) != len(matched) or len(inputs) != len(baseline) or len(set(inputs)) != len(inputs):
        raise ValueError('case count/IDs mismatch')
    pub_sha = sha(a.public)
    input_sha = sha(a.inputs)
    raw = []
    for item in matched:
        case_id = item['case_id']
        inp = inputs[case_id]
        before = baseline[case_id]
        assert item['before'] == inp['fixed_top20'] == before['result'].get('ranked_slugs', [])
        assert item['crop_sha256'] == inp['crop_sha256']
        assert item['query_sha256'] == before['query_sha256']
        pool_sha = hashlib.sha256(json.dumps(inp['fixed_top20'], ensure_ascii=False,
                                               separators=(',', ':')).encode()).hexdigest()
        result = item['result']
        raw.append({'case_id': case_id, 'track': item['track'], 'dataset': item['dataset'],
                    'query_sha256': item['query_sha256'], 'manifest_sha256': pub_sha,
                    'reader_input_manifest_sha256': input_sha, 'target_crop_sha256': item['crop_sha256'],
                    'target_box': item['target_box'], 'candidate_pool_id': 'ORT6_FIXED_TOP20',
                    'candidate_pool_sha256': pool_sha, 'fixed_top20': inp['fixed_top20'],
                    'http_status': None, 'elapsed_ms': None, 'timing_scope': 'offline_cached_stages_only',
                    'original_ort6_http_status': before['http_status'],
                    'original_ort6_elapsed_ms': before['elapsed_ms'],
                    'reader_elapsed_ms': item['reader_elapsed_ms'],
                    'matcher_elapsed_ms': item['matcher_elapsed_ms'],
                    'reader_status': item['reader_status'],
                    'target_metadata_state': inp['target_metadata_state'],
                    'evaluation_status': item['evaluation_status'],
                    'status': 'metadata_missing' if item['evaluation_status'] == 'not_run' else 'offline_prediction',
                    'action': result.get('action'), 'slug': result.get('slug'),
                    'ranked_slugs': result['ranked_slugs'], 'result': result,
                    'observations': item['observations'],
                    'candidate_evidence': item['candidate_evidence']})
    if len(raw) != len({r['case_id'] for r in raw}):
        raise ValueError('duplicate case ID')
    a.out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in raw))
    ort_config = json.loads(a.ort_config.read_text())
    local_config = json.loads(a.config.read_text())
    if local_config['candidate_pool'] != 'historical ORT6 fixed Top20; never extended':
        raise ValueError('unexpected R1 candidate pool config')
    cpu_receipt = json.loads(a.cpu_receipt.read_text()) if a.cpu_receipt else None
    model = ({'name': 'PaddleOCR', 'packages': cpu_receipt['packages'],
              'engine': cpu_receipt['engine'], 'detector': cpu_receipt['detector'],
              'recognizer': cpu_receipt['recognizer']} if cpu_receipt else MODEL[a.variant])
    receipt = {'variant': a.variant, 'model': model, 'rows': len(raw),
               'unique_case_ids': len({r['case_id'] for r in raw}),
               'missing_target_metadata': sum(r['target_metadata_state'] == 'missing' for r in inputs.values()),
               'case_ids_sha256': hashlib.sha256('\n'.join(sorted(r['case_id'] for r in raw)).encode()).hexdigest(),
               'unscored': True, 'gold_loaded': False, 'http_timing_proven': False,
               'source_commit': ort_config['source_commit'],
               'ort6_config': {'route': ort_config['route'], 'onnx_sha256': ort_config['onnx_sha256'],
                               'index_version': ort_config['index_version'],
                               'catalog_version': ort_config['catalog_version']},
               'r1_config_version': local_config['config_version'],
               'raw_sha256': sha(a.out), 'sources_sha256': {
                   'export': sha(Path(__file__)), 'match': sha(Path(__file__).with_name('match.py')),
                   'reader': sha(Path(__file__).parent.parent / 'night-reader' / 'read.py') if a.variant == 'gpu_reader' else None,
                   'cpu_adapter': sha(Path(__file__).with_name('cpu_input.py')) if cpu_receipt else None,
                   'cpu_runner': cpu_receipt['runner_sha256'] if cpu_receipt else None,
                   'cpu_receipt': sha(a.cpu_receipt) if cpu_receipt else None,
                   'ort6_config': sha(a.ort_config), 'catalog_cards': sha(a.cards),
                   'r1_config': sha(a.config),
                   'public': pub_sha, 'reader_inputs': input_sha,
                   'matched': sha(a.matched), 'original_ort6': sha(a.original_ort6),
                   'reader_raw': sha(a.reader_raw)}}
    a.out.with_suffix('.receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
