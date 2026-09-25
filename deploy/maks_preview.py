#!/usr/bin/env python3
"""Install one CI artifact into the Maks preview, without the TEST/PROD controller.

Run on Sigma as root after obtaining the exact successful main CI archive and
its published SHA-256. This tool never runs migrations or changes catalog data.
"""

import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ROOT = pathlib.Path('/srv/lct/maks/behavior-demo')
SERVICE = 'brutforce-demo.service'
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(path):
    h = hashlib.sha256()
    with pathlib.Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(pathlib.Path(path).read_text())


def write(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def safe_member(member):
    name = pathlib.PurePosixPath(member.name)
    return (not name.is_absolute() and '..' not in name.parts and
            (member.isfile() or member.isdir()))


def migration_hashes(folder):
    root = pathlib.Path(folder) / 'migrations'
    require(root.is_dir(), 'Migration directory is missing')
    return {str(path.relative_to(root)): digest(path) for path in root.rglob('*.sql')}


def validate_package(folder, revision, current):
    folder = pathlib.Path(folder)
    manifest = read(folder / 'manifest.json')
    require(manifest.get('revision') == revision and
            (folder / 'REVISION').read_text().strip() == revision,
            'Package revision differs from the requested main SHA')
    files = manifest.get('files')
    require(isinstance(files, list) and files, 'Package manifest has no files')
    names = [entry.get('path') for entry in files]
    actual = {str(path.relative_to(folder)) for path in folder.rglob('*') if path.is_file()}
    require(len(names) == len(set(names)) and set(names) == actual - {'manifest.json'},
            'Manifest must cover every package file exactly once')
    require({'brutforce-api', 'REVISION', 'web/index.html', 'web/release.json',
             'evidence/checks.json', 'evidence/release-gate.json',
             'evidence/fast-report-exceptions.json'} <= actual,
            'Preview package is incomplete')
    for entry in files:
        name = pathlib.PurePosixPath(entry['path'])
        require(not name.is_absolute() and '..' not in name.parts and
                HEX64.fullmatch(entry.get('sha256', '')) and
                digest(folder / name) == entry['sha256'],
                'Manifest checksum mismatch')
    checks = read(folder / 'evidence/checks.json')
    gate = read(folder / 'evidence/release-gate.json')
    policy_file = folder / 'evidence/fast-report-exceptions.json'
    policy = read(policy_file)
    require(checks.get('revision') == revision and checks.get('status') == 'passed' and
            checks.get('targetScope') == 'maks-demo-only' and
            checks.get('bddCoverageStatus') == 'partial',
            'CI evidence is not a passed Maks-only partial BDD gate')
    require(gate.get('revision') == revision and gate.get('status') == 'passed' and
            gate.get('targetScope') == checks['targetScope'] and
            gate.get('bddCoverageStatus') == checks['bddCoverageStatus'] and
            gate.get('coverageExceptions') == checks.get('coverageExceptions'),
            'Release gate differs from checks.json')
    require(policy.get('targetScope') == 'maks-demo-only' and
            digest(policy_file) == checks.get('policySHA256') == gate.get('policySHA256'),
            'Coverage exception policy differs from CI evidence')
    policy_ids = [case_id for item in policy.get('exceptions', [])
                  for case_id in item.get('ids', [])]
    deferred = checks.get('coverageExceptions')
    require(isinstance(deferred, list) and len(policy_ids) == len(deferred) == 20 and
            len(set(policy_ids)) == 20 and
            set(policy_ids) == {item.get('id') for item in deferred} and
            all(item.get('status') in ('skipped', 'not_run') for item in deferred),
            'The 20 named BDD exceptions do not match CI evidence')
    require(migration_hashes(folder) == migration_hashes(current),
            'SQL migrations changed; preview-only deploy must stop')
    return checks


def unpack_verified(archive, checksum, stage):
    archive = pathlib.Path(archive)
    require(archive.is_file() and archive.stat().st_size <= 300 * 1024 * 1024,
            'CI archive is missing or too large')
    require(HEX64.fullmatch(checksum) and digest(archive) == checksum,
            'CI archive SHA-256 mismatch')
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        names = [str(pathlib.PurePosixPath(m.name)) for m in members if m.isfile()]
        require(all(safe_member(m) for m in members) and len(names) == len(set(names)) and
                sum(m.size for m in members) < 1024 * 1024 * 1024,
                'Unsafe or oversized CI archive')
        source.extractall(stage, filter='data')
    pathlib.Path(stage).chmod(0o755)
    for path in pathlib.Path(stage).rglob('*'):
        if path.is_dir():
            path.chmod(0o755)
        elif path.is_file():
            path.chmod(0o755 if path.name in ('brutforce-api', 'catalog-import',
                       'catalog-migrate', 'reference-engine', 'roman-conformance') else 0o644)


def current_release():
    current = ROOT / 'current'
    require(current.is_symlink(), 'Preview current is not a symlink')
    target = current.resolve(strict=True)
    require(target.parent == (ROOT / 'releases').resolve() and HEX40.fullmatch(target.name),
            'Preview current does not point to a known immutable release')
    return target


def switch_to(target):
    current = ROOT / 'current'
    temporary = ROOT / '.current-next'
    require(not temporary.exists() and not temporary.is_symlink(),
            'An unfinished preview switch needs inspection')
    temporary.symlink_to(target)
    temporary.replace(current)
    subprocess.run(['systemctl', 'restart', SERVICE], check=True)


def smoke(revision, catalog_version):
    deadline = time.monotonic() + 10
    while True:
        try:
            for path, expected in (('/v1/health', None), ('/release.json', revision),
                                   ('/v2/catalog?limit=1', catalog_version)):
                with urllib.request.urlopen('http://127.0.0.1:8097' + path, timeout=2) as response:
                    payload = json.load(response)
                if path == '/v1/health':
                    require(payload.get('ok') is True, 'Preview health check failed')
                elif path == '/release.json':
                    require(payload.get('revision') == expected, 'Preview revision differs')
                else:
                    require(payload.get('catalogVersion') == expected, 'Preview catalog changed')
            return
        except (OSError, ValueError, RuntimeError) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError('Preview smoke failed after 10 seconds: ' + str(error)) from error
            time.sleep(0.25)


def install(args):
    require(HEX40.fullmatch(args.revision), 'Expected full 40-character main SHA')
    previous = current_release()
    require(previous.name != args.revision, 'This revision is already live')
    target = ROOT / 'releases' / args.revision
    require(not target.exists(), 'Release already exists; inspect it before retrying')
    with urllib.request.urlopen('http://127.0.0.1:8097/v2/catalog?limit=1', timeout=12) as response:
        catalog_version = json.load(response)['catalogVersion']
    stage = pathlib.Path(tempfile.mkdtemp(prefix='.preview-stage-', dir=ROOT / 'releases'))
    try:
        unpack_verified(args.archive, args.sha256, stage)
        validate_package(stage, args.revision, previous)
        stage.replace(target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    state_file = ROOT / 'preview-deployments' / (args.revision + '.json')
    write(state_file, {'revision': args.revision, 'previous': str(previous),
                       'archiveSHA256': args.sha256, 'catalogVersion': catalog_version,
                       'status': 'staged'})
    try:
        switch_to(target)
        smoke(args.revision, catalog_version)
    except Exception:
        try:
            if current_release() == target:
                switch_to(previous)
                smoke(previous.name, catalog_version)
            write(state_file, {**read(state_file), 'status': 'rolled-back-after-failure'})
        except Exception as rollback_error:
            raise RuntimeError('Preview failed and rollback needs operator review') from rollback_error
        raise
    write(state_file, {**read(state_file), 'status': 'active'})
    print(json.dumps({'status': 'active', 'revision': args.revision,
                      'previous': previous.name, 'catalogVersion': catalog_version}))


def preflight(args):
    require(HEX40.fullmatch(args.revision), 'Expected full 40-character main SHA')
    previous = current_release()
    with tempfile.TemporaryDirectory(prefix='maks-preview-check-') as stage:
        unpack_verified(args.archive, args.sha256, stage)
        checks = validate_package(stage, args.revision, previous)
    print(json.dumps({'status': 'passed', 'revision': args.revision,
                      'current': previous.name, 'targetScope': checks['targetScope'],
                      'bddCoverageStatus': checks['bddCoverageStatus']}))


def rollback(args):
    require(HEX40.fullmatch(args.revision), 'Expected full 40-character release SHA')
    require(current_release().name == args.revision, 'Only the active preview can be rolled back')
    state_file = ROOT / 'preview-deployments' / (args.revision + '.json')
    state = read(state_file)
    previous = pathlib.Path(state['previous']).resolve(strict=True)
    require(previous.parent == (ROOT / 'releases').resolve() and
            migration_hashes(previous) == migration_hashes(current_release()),
            'Previous release or schema is unsafe for automatic rollback')
    switch_to(previous)
    smoke(previous.name, state['catalogVersion'])
    write(state_file, {**state, 'status': 'rolled-back'})
    print(json.dumps({'status': 'rolled-back', 'revision': args.revision,
                      'active': previous.name}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('preflight')
    check.add_argument('archive', type=pathlib.Path)
    check.add_argument('sha256')
    check.add_argument('revision')
    new = commands.add_parser('install')
    new.add_argument('archive', type=pathlib.Path)
    new.add_argument('sha256')
    new.add_argument('revision')
    old = commands.add_parser('rollback')
    old.add_argument('revision')
    args = parser.parse_args()
    if args.command == 'preflight':
        preflight(args)
        return
    require(os.geteuid() == 0, 'Run as root on Sigma')
    with (ROOT / '.preview-deploy.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        (install if args.command == 'install' else rollback)(args)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Maks preview deployment failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
