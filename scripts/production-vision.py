#!/usr/bin/env python3
"""Verify the observed PROD release; explicitly serve its unchanged C16 source."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / 'deploy/production.json'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def verify(manifest, data):
    for item in manifest['sources']:
        if sha(ROOT / item['path']) != item['sha256']:
            raise ValueError('Production source differs: ' + item['path'])
    if data is not None:
        for item in manifest['externalAssets']:
            if sha(data / item['path']) != item['sha256']:
                raise ValueError('Production asset differs: ' + item['path'])


def prepare(manifest, data, runtime):
    """Relocate machine bindings; never rewrite the frozen Python implementation."""
    for name, expected in manifest['pythonPackages'].items():
        if importlib.metadata.version(name) != expected:
            raise ValueError('Production Python package differs: ' + name)
    source = ROOT / 'apps/vision/c16'
    candidate = runtime / 'c16'
    base = runtime / 'base'
    candidate.mkdir(parents=True)
    base.mkdir()
    for p in source.iterdir():
        if p.is_file():
            shutil.copy2(p, candidate / p.name)
    (candidate / 'assets').symlink_to(data / 'c16/assets', target_is_directory=True)
    (candidate / 'CANDIDATE-FREEZE.json').symlink_to(data / 'metadata/CANDIDATE-FREEZE.json')
    for name in ['boost_runtime.py', 'boost_policy.py']:
        shutil.copy2(ROOT / 'apps/vision/boost' / name, base / name)
    policy = json.loads((ROOT / 'apps/vision/boost/boost-policy.json').read_text())
    policy['gallery_sources']['legacy_label']['path'] = str(data / 'index/index.npz')
    write(base / 'boost-policy.json', policy)
    assets = {a['path']: a for a in manifest['externalAssets']}
    binding = {
        'model_id': 'batch32-4744-pass2',
        'checkpoint_sha256': manifest['checkpointSHA256'],
        'files': [dict(role=role, path=str(data / name), sha256=assets[name]['sha256'])
                  for role, name in [('index', 'index/index.npz'),
                                     ('onnx_external_weights', 'onnx/vision.onnx.data')]],
        'boost': dict(manifest_path=str(base / 'boost-policy.json'),
                      manifest_sha256=sha(base / 'boost-policy.json')),
    }
    write(base / 'binding.json', binding)
    cfg = dict(model_id=binding['model_id'], boost=1, host='127.0.0.1', threads=6,
               index_dir=str(data / 'index'), onnx_dir=str(data / 'onnx'),
               catalog=str(data / 'catalog/catalog-bundle.json'),
               base_code=str(ROOT / 'apps/vision/parent'), hf_home=str(data / 'models'),
               ort_lib=str(Path(importlib.metadata.distribution('onnxruntime').locate_file(''))),
               runtime=str(base / 'runtime'),
               model_version=manifest['model']['model_version'],
               serving_index_version=manifest['model']['index_version'],
               serving_profile=manifest['model']['serving_profile'])
    write(base / 'config.json', cfg)
    write(base / 'runtime/workflow-config.json', {'workflow_trace': 1})
    parent = {str(ROOT / i['path']): i['sha256'] for i in manifest['sources']
              if i['path'].startswith('apps/vision/parent/')}
    readonly = dict(parent)
    readonly.update({str(data / i['path']): i['sha256'] for i in manifest['externalAssets']
                     if i['role'] in {'index_dir', 'onnx_dir', 'organizer_catalog'}})
    write(base / 'readonly-source-pins.json', readonly)
    write(base / 'SOURCE-PINS.json', {p.name: sha(p) for p in base.iterdir() if p.is_file()})
    ocr = dict(tesseract=str(data / 'ocr/tesseract'), tessdata_dir=str(data / 'ocr'),
               metadata_path=str(data / 'metadata/catalog-attributes.json'),
               files={str(data / i['path']): i['sha256'] for i in manifest['externalAssets']
                      if i['role'] in {'ocr', 'catalog_attributes'}})
    write(candidate / 'OCR-ASSETS.json', ocr)
    pins = json.loads((candidate / 'TRACE-SOURCE-PINS.json').read_text())
    pins['OCR-ASSETS.json'] = sha(candidate / 'OCR-ASSETS.json')
    write(candidate / 'TRACE-SOURCE-PINS.json', pins)
    write(runtime / 'RELOCATION.json', {
        'productionManifestSHA256': sha(MANIFEST),
        'modelVersion': cfg['model_version'],
        'pythonSourceBytesChanged': False,
        'machineBindingsRelocated': True,
        'sigmaActivationReceiptsCopied': False,
    })
    for name, expected in pins.items():
        if sha(candidate / name) != expected:
            raise ValueError('Relocated C16 pin differs: ' + name)
    return candidate, base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, help='Existing C16 data layout, outside Git')
    parser.add_argument('--serve', action='store_true', help='Explicitly start the loopback model')
    parser.add_argument('--runtime', type=Path, help='New private runtime directory outside Git')
    parser.add_argument('--port', type=int, default=8137)
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    data = args.data_root.resolve() if args.data_root else None
    if data is not None and (data == ROOT or ROOT in data.parents):
        parser.error('Model data must be outside the code checkout')
    verify(manifest, data)
    if not args.serve:
        print(json.dumps(dict(sources_verified=True, source_files=len(manifest['sources']),
                              assets_verified=data is not None,
                              external_files=len(manifest['externalAssets']),
                              server_started=False)))
        return
    if data is None or args.runtime is None:
        parser.error('--serve requires --data-root and a new --runtime directory')
    if sys.version_info[:2] != (3, 12) or sys.platform != 'linux':
        parser.error('Observed production uses Linux and Python 3.12; other-host parity is unverified')
    runtime = args.runtime.resolve()
    if runtime == ROOT or ROOT in runtime.parents or runtime.exists():
        parser.error('--runtime must be a new directory outside the code checkout')
    runtime.mkdir(parents=True, mode=0o700)
    candidate, base = prepare(manifest, data, runtime)
    os.execv(sys.executable, [sys.executable, str(candidate / 'serve_v7.py'),
                             '--serve-private', '--port', str(args.port),
                             '--runtime', str(runtime / 'live'), '--base', str(base)])


if __name__ == '__main__':
    main()
