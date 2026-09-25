#!/usr/bin/env python3
"""Export public suite inputs or submit predictions to private server scoring."""

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile


def request(url, data=None, token=None):
    headers = {'Content-Type': 'application/json'} if data is not None else {}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urlopen(Request(url, data=data, headers=headers), timeout=60) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='https://cv.ops.dzap.pw')
    commands = parser.add_subparsers(dest='command', required=True)
    export = commands.add_parser('export', help='download public inputs only')
    export.add_argument('--version', default='v2')
    export.add_argument('--output', type=Path, required=True)
    score = commands.add_parser('score', help='submit a local predictions JSON for private scoring')
    score.add_argument('--input', type=Path, required=True)
    args = parser.parse_args()
    base = args.base.rstrip('/')
    if args.command == 'export':
        data = request(f'{base}/api/baskets/{args.version}/download')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('xb') as handle:
            handle.write(data)
        with ZipFile(args.output) as archive:
            names = archive.namelist()
            if any(name.startswith('private/') or 'gold' in name.lower() for name in names):
                args.output.unlink()
                raise SystemExit('archive contains a private path')
            manifest = json.loads(archive.read(f'baskets/{args.version}.json'))
        print(json.dumps({'version': manifest['version'], 'suite_hash': manifest['suite_hash'], 'cases': len(manifest['cases']), 'archive': str(args.output)}))
        return
    token = os.environ.get('LCT_EVAL_PARTICIPANT_TOKEN')
    if not token:
        raise SystemExit('LCT_EVAL_PARTICIPANT_TOKEN required')
    submission = json.loads(args.input.read_text())
    suites = json.loads(request(f'{base}/api/baskets'))
    suite = next((s for s in suites if s['version'] == submission['suite_version']), None)
    if suite is None or submission['suite_hash'] != suite['suite_hash']:
        raise SystemExit('submission suite version/hash does not match server')
    data = json.dumps(submission, separators=(',', ':')).encode()
    try:
        report = json.loads(request(f'{base}/api/submissions', data=data, token=token))
    except HTTPError as exc:
        raise SystemExit(f'scoring rejected submission: HTTP {exc.code}') from exc
    print(json.dumps({'run_id': report['run_id'], 'suite_version': submission['suite_version'], 'track': submission['track'], 'overall': report['overall']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
