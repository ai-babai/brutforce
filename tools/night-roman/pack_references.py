"""Pack SHA-verified public catalog reference bytes from their source paths."""
import argparse
import hashlib
import json
import tarfile
from pathlib import Path


def hash_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    rows = [json.loads(line) for line in a.manifest.open(encoding='utf-8')]
    if len(rows) != 2060:
        raise ValueError('2060 gate-valid reference rows required')
    seen = set()
    with tarfile.open(a.out, 'w') as archive:
        for row in rows:
            digest = row['sha256']
            if digest in seen:
                continue
            path = Path(row['source_path'])
            if not path.is_file() or hash_file(path) != digest:
                raise ValueError('Missing/mismatched reference ' + row['slug'])
            info = archive.gettarinfo(str(path), arcname=digest + '.webp')
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            with path.open('rb') as source:
                archive.addfile(info, source)
            seen.add(digest)
    print(json.dumps(dict(rows=len(rows),distinct_sha=len(seen),archive_sha256=hash_file(a.out))))


if __name__ == '__main__':
    main()
