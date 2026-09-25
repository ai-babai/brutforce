"""Read-only Sigma release check; never writes to the live dataset or service.

Capture before a report-only release, then compare with --before after it.
New submissions may append; the old history prefix and sealed files must match.
"""
import argparse
import hashlib
import json
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def request(path, data=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                'http://127.0.0.1:8124' + path, data=data), timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--before', type=Path)
    args = parser.parse_args()
    root = Path('/srv/lct/data/eval')
    current = Path('/srv/lct/maks/eval/current').resolve()
    sealed = {}
    for name in ('baskets', 'catalog', 'private'):
        for path in sorted((root / name).rglob('*')):
            if path.is_file():
                sealed[str(path.relative_to(root))] = sha(path.read_bytes())
    history = (root / 'runs.jsonl').read_bytes()
    code, body = request('/api/runs')
    assert code == 200
    runs = json.loads(body)
    ids = [run['submission']['submission_id'] for run in runs]
    assert len(ids) == len(set(ids)), 'duplicate submission IDs'
    forbidden = {'prediction', 'expected', 'expected_slug', 'expected_action',
                 'ranked_slugs', 'acceptable_slugs', 'ungraded_reason'}

    def populated(value):
        if isinstance(value, dict):
            return any(populated(item) for item in value.values())
        if isinstance(value, list):
            return any(populated(item) for item in value)
        return value not in (None, '', False)

    def check_public(value):
        if isinstance(value, dict):
            assert not any(populated(value[key]) for key in forbidden.intersection(value)), 'private field in public report'
            for item in value.values():
                check_public(item)
        elif isinstance(value, list):
            for item in value:
                check_public(item)

    check_public(runs)
    checks = {}
    for path, expected in [('/healthz', 200), ('/private/gold-v2.json', 404),
                           ('/data/private/gold-v2.json', 404)]:
        checks[path] = request(path)[0]
        assert checks[path] == expected, path
    checks['anonymous_submission'] = request('/api/submissions', b'{}')[0]
    assert checks['anonymous_submission'] == 401
    state = {'at': datetime.now(timezone.utc).isoformat(), 'release': str(current),
             'binary_sha256': sha((current / 'lct-eval').read_bytes()),
             'sealed_sha256': sealed, 'history_bytes': len(history),
             'history_sha256': sha(history), 'public_runs': len(runs),
             'submission_ids': ids, 'checks': checks,
             'test_pid': subprocess.check_output(
                 ['systemctl', 'show', 'lct-vision-test', '-p', 'MainPID', '--value'],
                 text=True).strip()}
    if args.before:
        before = json.loads(args.before.read_text())
        assert sealed == before['sealed_sha256'], 'sealed data changed'
        assert state['binary_sha256'] == before['binary_sha256'], 'binary changed'
        assert sha(history[:before['history_bytes']]) == before['history_sha256'], 'history rewritten'
        assert state['test_pid'] == before['test_pid'], 'TEST process changed'
        assert set(before['submission_ids']).issubset(ids), 'old runs missing'
        state['invariants_preserved'] = True
    args.out.write_text(json.dumps(state, indent=2) + '\n')
    print(json.dumps({key: state[key] for key in
                     ('at', 'release', 'public_runs', 'history_bytes', 'checks')}))


if __name__ == '__main__':
    main()
