"""Create or verify a SHA receipt for experiment artifacts outside Git/web-root.

The receipt excludes local environments and the trusted private scorer's gold.
It contains filenames, sizes and hashes, never file contents or secret values.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

EXCLUDED = {'venv', '.venv', '__pycache__', '.scorer', '.git'}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--dirs', nargs='+')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.verify:
        manifest = json.loads(args.manifest.read_text())
        failures = []
        for item in manifest['files']:
            path = (root/item['path']).resolve()
            if root not in path.parents or not path.is_file():
                failures.append({'path':item['path'],'reason':'missing or unsafe'})
            elif path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
                failures.append({'path':item['path'],'reason':'size or SHA mismatch'})
        receipt = {'verified_at':datetime.now(timezone.utc).isoformat(),
            'manifest_sha256':digest(args.manifest),'files':len(manifest['files']),
            'bytes':sum(f['bytes'] for f in manifest['files']),
            'ok':not failures,'failures':failures}
        if args.receipt:
            args.receipt.write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(receipt))
        if failures: raise SystemExit(1)
    else:
        if not args.dirs: raise ValueError('Explicit artifact directories required')
        files = []
        for name in args.dirs:
            directory = (root/name).resolve()
            assert root in directory.parents and directory.is_dir()
            for path in sorted(directory.rglob('*')):
                relative = path.relative_to(root)
                if any(part in EXCLUDED for part in relative.parts): continue
                if path.is_symlink(): raise ValueError('Unexpected symlink '+str(relative))
                if not path.is_file(): continue
                if path.name == '.env' or path.suffix in ('.pem','.key'):
                    raise ValueError('Unexpected possible secret '+str(relative))
                files.append({'path':str(relative),'bytes':path.stat().st_size,'sha256':digest(path)})
        assert len(files) == len({f['path'] for f in files})
        manifest = {'created_at':datetime.now(timezone.utc).isoformat(),
            'excluded_components':sorted(EXCLUDED),'files':files}
        args.manifest.write_text(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps({'files':len(files),'bytes':sum(f['bytes'] for f in files),'manifest':str(args.manifest)}))


if __name__ == '__main__': main()
