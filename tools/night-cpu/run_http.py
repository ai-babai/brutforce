#!/usr/bin/env python3
"""Gold-blind, resumable HTTP runner for the isolated Sigma CPU service.

Each input gets one request with a strict 10 second client deadline. After a
timeout, wait for the single inference slot to clear before the next input.
"""

import argparse
import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path


def read_health(base):
    with urllib.request.urlopen(base + '/healthz', timeout=3) as response:
        return json.load(response)


def wait_idle(base, max_seconds=120):
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        try:
            health = read_health(base)
            if health.get('status') == 'ready' and health.get('busy') is False:
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise TimeoutError('inference slot did not become idle within 120 seconds')


def multipart(image):
    boundary = 'cpu-public-benchmark-20260925'
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
            f'filename="{image.name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
    return data + image.read_bytes() + f'\r\n--{boundary}--\r\n'.encode(), boundary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--image-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--url', default='http://127.0.0.1:8125/v1/eval/predict')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--variant', required=True)
    args = parser.parse_args()
    assert args.limit is None or args.limit > 0
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    cases = manifest['cases'][:args.limit]
    existing = {}
    if args.out.exists():
        for line in args.out.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                assert row['case_id'] not in existing, 'duplicate output case'
                assert row['manifest_sha256'] == manifest_sha, 'manifest mismatch'
                assert row['url'] == args.url, 'URL mismatch'
                existing[row['case_id']] = row
    assert set(existing) <= {c['case_id'] for c in manifest['cases']}
    base = args.url.split('/v1/', 1)[0]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('a') as output:
        for case in cases:
            if case['case_id'] in existing:
                continue
            image = args.image_root / (case.get('image_path') or case['path'])
            expected_sha = case.get('image_sha256') or case['sha256']
            image_bytes = image.read_bytes()
            assert hashlib.sha256(image_bytes).hexdigest() == expected_sha, image
            wait_idle(base)
            payload, boundary = multipart(image)
            track = case.get('track') or case['tracks'][0]
            request = urllib.request.Request(
                args.url + '?track=' + track, data=payload, method='POST',
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
            started = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    status = response.status
                    result = json.load(response)
            except urllib.error.HTTPError as error:
                status = error.code
                try:
                    result = json.load(error)
                except (ValueError, OSError):
                    result = {'error': str(error)}
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as error:
                status = None
                result = {'error': str(error)}
            elapsed_ms = round((time.monotonic() - started) * 1000, 2)
            row = {'case_id': case['case_id'], 'track': track,
                   'query_sha256': expected_sha, 'manifest_sha256': manifest_sha,
                   'variant': args.variant,
                   'run_id': args.run_id,
                   'phase': 'full-http', 'device': 'cpu', 'url': args.url,
                   'http_status': status, 'elapsed_ms': elapsed_ms, 'result': result}
            output.write(json.dumps(row, ensure_ascii=False) + '\n')
            output.flush()
            os.fsync(output.fileno())
            print(json.dumps({'case_id': row['case_id'], 'http_status': status,
                              'elapsed_ms': elapsed_ms}), flush=True)
            # A timed-out client leaves the server doing inference. Its eventual
            # completion must not turn subsequent public inputs into busy 503s.
            wait_idle(base)


if __name__ == '__main__':
    main()
