#!/usr/bin/env python3
"""Bounded no-calibration dynamic INT8 probe for the pinned FP32 SO400M graph."""
import argparse
import hashlib
import json
import resource
import time
from pathlib import Path

from onnxruntime.quantization import QuantType, quantize_dynamic


EXPECTED_FP32_SHA = 'd98c21ec54cda834d57fe2ad3151eb19d4d23b211ecad713844a10263828bd80'


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    if sha256(args.source) != EXPECTED_FP32_SHA:
        raise ValueError('FP32 graph SHA mismatch')
    args.out_dir.mkdir(parents=True, exist_ok=True)
    model = args.out_dir / 'vision-dynamic-int8.onnx'
    if model.exists():
        raise FileExistsError(model)
    started = time.monotonic()
    quantize_dynamic(args.source, model, op_types_to_quantize=['MatMul', 'Gemm'],
                     weight_type=QuantType.QInt8, use_external_data_format=True)
    files = {path.name: {'bytes': path.stat().st_size, 'sha256': sha256(path)}
             for path in args.out_dir.iterdir() if path.is_file()}
    receipt = {'source_sha256': EXPECTED_FP32_SHA,
               'method': 'ORT dynamic INT8 MatMul/Gemm; no calibration images or labels',
               'weight_type': 'QInt8', 'per_channel': False,
               'elapsed_s': round(time.monotonic()-started, 2),
               'peak_rss_kb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               'files': files}
    (args.out_dir / 'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
