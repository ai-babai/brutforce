#!/usr/bin/env python3
"""Gold-blind two-client HTTP probe of the isolated CPU service."""
import argparse
import concurrent.futures
import hashlib
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from run_http import multipart


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--image-root', type=Path, required=True)
    parser.add_argument('--case-ids', nargs=2, required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    cases = {case['case_id']: case for case in manifest['cases']}
    barrier = threading.Barrier(2)

    def request(case_id):
        case = cases[case_id]
        image = args.image_root / (case.get('image_path') or case['path'])
        expected_sha = case.get('image_sha256') or case['sha256']
        assert hashlib.sha256(image.read_bytes()).hexdigest() == expected_sha
        payload, boundary = multipart(image)
        track = case.get('track') or case['tracks'][0]
        req = urllib.request.Request(args.url + '?track=' + track, data=payload,
                                     method='POST', headers={
                                         'Content-Type': f'multipart/form-data; boundary={boundary}'})
        barrier.wait(timeout=10)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                status = response.status
                body = json.load(response)
        except urllib.error.HTTPError as error:
            status = error.code
            try:
                body = json.load(error)
            except (OSError, ValueError):
                body = {'error': str(error)}
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as error:
            status = None
            body = {'error': str(error)}
        return {'case_id': case_id, 'track': track, 'http_status': status,
                'elapsed_ms': round((time.monotonic()-started)*1000, 2), 'result': body}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(request, case_id) for case_id in args.case_ids]
        rows = [future.result() for future in futures]
    args.out.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows))
    print(json.dumps([{'case_id': row['case_id'], 'http_status': row['http_status'],
                       'elapsed_ms': row['elapsed_ms']} for row in rows]))


if __name__ == '__main__':
    main()
