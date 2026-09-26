"""Isolated full-frame ORT6 -> target reader -> frozen matcher HTTP experiment."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from PIL import Image, ImageOps

from match import lines, rerank


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def reader_view(content: bytes, box: list[int]) -> tuple[Image.Image, str]:
    with Image.open(io.BytesIO(content)) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB')
    target = image.crop(box)
    scale = min(1, 768 / max(target.size))
    if scale < 1:
        target = target.resize(tuple(max(1, round(n * scale)) for n in target.size),
                               Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    target.save(buffer, format='JPEG', quality=90, subsampling=0)
    view = buffer.getvalue()
    with Image.open(io.BytesIO(view)) as encoded:
        reader_image = encoded.convert('RGB')
    return reader_image, sha(view)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ort6-source', type=Path, required=True)
    p.add_argument('--catalog', type=Path, required=True)
    p.add_argument('--index-dir', type=Path, required=True)
    p.add_argument('--onnx-dir', type=Path, required=True)
    p.add_argument('--cards', type=Path, required=True)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--port', type=int, required=True)
    p.add_argument('--threads', type=int, default=6)
    args = p.parse_args()
    if args.port in (8125, 8129):
        p.error('TEST ports forbidden')
    os.environ['NIGHT_SO_ONNX_DIR'] = str(args.onnx_dir)
    os.environ['NIGHT_SO_ONNX_THREADS'] = str(args.threads)
    os.environ.setdefault('OMP_NUM_THREADS', str(args.threads))
    sys.path.insert(0, str(args.ort6_source))

    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    from night_server import CPUPipeline

    input_rows = [json.loads(line) for line in args.inputs.read_text().splitlines() if line.strip()]
    cases = {row['case_id']: row for row in input_rows}
    if len(cases) != len(input_rows) or len(cases) != 316 or any(
            r['target_metadata_state'] != 'confirmed_ort6' for r in cases.values()):
        raise ValueError('full 316-input manifest or target metadata incomplete')
    cards = json.loads(args.cards.read_text())
    started_load = time.perf_counter()
    ort6 = CPUPipeline(args.catalog, args.index_dir, args.threads,
                       'so400m', route='onnx640').engine
    ort6_load_s = time.perf_counter() - started_load
    started_gpu = time.perf_counter()
    model_id = 'Qwen/Qwen3-VL-2B-Instruct'
    revision = '89644892e4d85e24eaac8bacfd4f463576704203'
    prompt = ('Задача OCR: выпиши только надписи, которые видны на этикетке, по строкам. '
              'Никаких вступлений, описаний, исправлений и догадок. '
              'Если ни одной надписи не читается, напиши ровно <EMPTY>.')
    processor = AutoProcessor.from_pretrained(model_id, revision=revision)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_id, revision=revision, torch_dtype=torch.bfloat16,
        device_map='cuda:0', attn_implementation='sdpa').eval()
    torch.cuda.synchronize()
    gpu_load_s = time.perf_counter() - started_gpu
    cpu_model = next((line.split(':', 1)[1].strip() for line in
                      Path('/proc/cpuinfo').read_text().splitlines()
                      if line.startswith('model name')), 'unknown')
    cpu_quota_path = Path('/sys/fs/cgroup/cpu.max')
    cpu_quota = cpu_quota_path.read_text().strip() if cpu_quota_path.exists() else None
    memory_limit_path = Path('/sys/fs/cgroup/memory.max')
    memory_limit = memory_limit_path.read_text().strip() if memory_limit_path.exists() else None
    gpu_total_bytes = torch.cuda.get_device_properties(0).total_memory

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != '/healthz':
                self.send_json(404, {'error': 'not_found'})
                return
            self.send_json(200, {'ready': True, 'ort6_load_s': ort6_load_s,
                                 'gpu_load_s': gpu_load_s, 'inputs': len(cases),
                                 'model': model_id, 'revision': revision,
                                  'ort6_threads': args.threads,
                                  'cpu': 'ORT6 ONNXRuntime CPUExecutionProvider',
                                  'cpu_model': cpu_model, 'host_visible_logical_cpu': os.cpu_count(),
                                  'cgroup_cpu_max': cpu_quota, 'cgroup_memory_max': memory_limit,
                                  'gpu': torch.cuda.get_device_name(0),
                                  'gpu_total_bytes': gpu_total_bytes,
                                  'gpu_memory_allocated_bytes': torch.cuda.memory_allocated(0),
                                  'gpu_peak_allocated_bytes': torch.cuda.max_memory_allocated(0),
                                  'gpu_peak_reserved_bytes': torch.cuda.max_memory_reserved(0)})

        def do_POST(self):
            if self.path != '/infer':
                self.send_json(404, {'error': 'not_found'})
                return
            t0 = time.perf_counter()
            case_id = self.headers.get('X-Case-ID')
            row = cases.get(case_id)
            content = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            if not row or sha(content) != row['query_sha256']:
                self.send_json(400, {'error': 'public_input_sha_mismatch', 'case_id': case_id})
                return
            try:
                raw = ort6.predict(content, row['track'])
                t_ort6 = time.perf_counter()
                rank = [x['slug'] for x in raw['branches_top20']['whole']]
                if row['track'] == 'service' and raw.get('action'):
                    rank = []
                box = raw['selection']['selected_box']
                if box is not None:
                    box = list(box)
                if rank != row['fixed_top20'] or box != row['target_box']:
                    raise ValueError('ORT6 rank/selected box changed from fixed input')
                observations = []
                reader_ms = 0.0
                if box is not None:
                    image, view_sha = reader_view(content, box)
                    if view_sha != row['crop_sha256']:
                        raise ValueError('target reader JPEG SHA differs from fixed input')
                    messages = [{'role': 'user', 'content': [
                        {'type': 'image', 'image': image}, {'type': 'text', 'text': prompt}]}]
                    start_reader = time.perf_counter()
                    inputs = processor.apply_chat_template(messages, add_generation_prompt=True,
                                                           tokenize=True, return_dict=True,
                                                           return_tensors='pt').to(model.device)
                    with torch.inference_mode():
                        generated = model.generate(**inputs, do_sample=False,
                                                   max_new_tokens=128, use_cache=True)
                    torch.cuda.synchronize()
                    tail = generated[0, inputs['input_ids'].shape[-1]:]
                    text = processor.decode(tail, skip_special_tokens=True).strip()
                    reader_ms = (time.perf_counter() - start_reader) * 1000
                    observations = lines(text, view_sha, 'gpu_qwen_http')
                t_reader = time.perf_counter()
                ranked, evidence = rerank(rank, observations, cards) if observations else (rank, [])
                if sorted(ranked) != sorted(rank):
                    raise ValueError('matcher changed candidate pool')
                prediction = ({'ranked_slugs': ranked} if row['track'] == 'retrieval' else
                              {'slug': ranked[0]} if ranked else row['baseline_prediction'])
                result = {**prediction, 'ranked_slugs': ranked}
                t_end = time.perf_counter()
                affected = {rank[i] for i in range(len(rank)) if rank[i] != ranked[i]}
                if rank:
                    affected.add(rank[0])
                relevant = [entry for entry in evidence if entry['slug'] in affected or
                            entry['grape_relation'] == 'contradiction']
                self.send_json(200, {'case_id': case_id, 'track': row['track'],
                                     'query_sha256': row['query_sha256'],
                                     'result': result, 'target_crop_sha256': row['crop_sha256'],
                                     'decision_trace': {
                                         'selected_box': box, 'reader_observations': observations,
                                         'polygon_confidence_state': 'unknown_unlocalized_qwen',
                                         'fixed_top20': rank, 'relevant_candidate_evidence': relevant,
                                         'explicit_contradiction_count': sum(
                                             x['grape_relation'] == 'contradiction' for x in evidence),
                                         'rerank_reason': 'same_top1_producer_family_evidence_sort'
                                                          if rank != ranked else 'no_rank_change',
                                         'final_action': result.get('action'),
                                         'final_slug': result.get('slug'),
                                         'no_match': result.get('action') == 'no_match',
                                         'missing_reason': None if box else 'confirmed_no_target'},
                                     'timings_ms': {'ort6': (t_ort6-t0)*1000,
                                                    'reader': reader_ms,
                                                    'crop_and_reader': (t_reader-t_ort6)*1000,
                                                    'matcher_and_response': (t_end-t_reader)*1000,
                                                    'server_total': (t_end-t0)*1000}})
            except Exception as exc:
                self.send_json(500, {'case_id': case_id, 'error': type(exc).__name__ + ': ' + str(exc)[:200]})

    print(json.dumps({'ready': True, 'port': args.port, 'ort6_load_s': ort6_load_s,
                      'gpu_load_s': gpu_load_s, 'count': len(cases)}), flush=True)
    HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
