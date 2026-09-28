#!/usr/bin/env python3
"""Export/verify F8 data assets; CPU Python code lives in apps/vision/."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile

MANIFEST = Path(__file__).resolve().parent.parent / "deploy/assets/f8-cpu.sha256"
GROUPS = {"overlay", "onnx", "index", "catalog", "models", "ocr"}


def entries():
    result = []
    for line in MANIFEST.read_text().splitlines():
        sha, rel = line.split("  ", 1)
        path = PurePosixPath(rel)
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("invalid checksum")
        if path.is_absolute() or ".." in path.parts or path.parts[0] not in GROUPS:
            raise ValueError("unsafe bundle path")
        result.append((sha, path))
    if len(result) != len({str(p) for _, p in result}):
        raise ValueError("duplicate bundle path")
    return result


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def check(root):
    root = root.resolve(strict=True)
    inventory = entries()
    expected_paths = {str(rel) for _, rel in inventory}
    for candidate in root.rglob("*"):
        if candidate.is_symlink() or (candidate.is_file() and candidate.relative_to(root).as_posix() not in expected_paths):
            raise ValueError("bundle contains unlisted file or symlink")
    for expected, rel in inventory:
        candidate = root.joinpath(*rel.parts)
        if not candidate.is_file() or not candidate.resolve().is_relative_to(root):
            raise ValueError(f"missing or escaping bundle file: {rel}")
        if digest(candidate) != expected:
            raise ValueError(f"SHA mismatch: {rel}")
    print(f"F8 bundle verified: {len(inventory)} files; manifest SHA256 {digest(MANIFEST)}")


def export(sources, out):
    mapping = json.loads(sources.read_text())
    if set(mapping) != GROUPS or any(not isinstance(v, str) for v in mapping.values()):
        raise ValueError("source map must specify overlay,onnx,index,catalog,models,ocr")
    roots = {group: Path(source).resolve(strict=True) for group, source in mapping.items()}
    if out.exists():
        raise ValueError("output already exists; choose a new directory")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".f8-bundle-", dir=out.parent) as tmp:
        stage = Path(tmp)
        for expected, rel in entries():
            group = rel.parts[0]
            tail = rel.parts[1:]
            # The HF hub is the only source group whose logical prefix differs.
            if group == "models" and tail[0] == "hub":
                tail = tail[1:]
            original = roots[group].joinpath(*tail)
            if not original.is_file() or not original.resolve().is_relative_to(roots[group]):
                raise ValueError(f"missing or escaping source: {rel}")
            if digest(original) != expected:
                raise ValueError(f"source SHA mismatch: {rel}")
            target = stage.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)  # dereference HF cache snapshot symlinks
            target.chmod(0o444)
        check(stage)
        stage.rename(out)
        # macOS refuses to rename a directory after its write bit was removed.
        for directory, _, _ in os.walk(out):
            Path(directory).chmod(0o555)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    copy = sub.add_parser("export")
    copy.add_argument("--sources", type=Path, required=True, help="operator-owned JSON group-to-directory map")
    copy.add_argument("--out", type=Path, required=True, help="new directory outside the repository")
    args = parser.parse_args()
    try:
        if args.action == "verify":
            check(args.bundle)
        else:
            export(args.sources, args.out)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        # Never print the operator's private source path or secret contents.
        print(f"F8 asset {args.action} failed: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
