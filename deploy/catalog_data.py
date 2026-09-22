#!/usr/bin/env python3
"""Materialize an audited display package as immutable shared media + metadata.

This does not import a database or grant release approval. Run catalog-import's
data gate afterwards. Source packages are read-only; existing files are verified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


ROLES = {"thumbnail": "400", "card": "800", "original": "original"}


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def directory(path):
    if path.resolve() != path.absolute():
        raise ValueError("symlinked directory is not supported: " + str(path))
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o755)


def safe_file(root, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("unsafe input path")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink input is not supported")
    if not current.is_file():
        raise ValueError("missing input file: " + relative)
    return current


def publish_asset(source, target, expected):
    if sha(source) != expected:
        raise ValueError("source checksum mismatch: " + str(source))
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or sha(target) != expected:
            raise ValueError("existing media content differs: " + str(target))
        return
    directory(target.parent)
    fd, name = tempfile.mkstemp(prefix=".copy-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as inp:
            shutil.copyfileobj(inp, out)
        temp = Path(name)
        if sha(temp) != expected:
            raise ValueError("copied media checksum mismatch")
        temp.chmod(0o644)
        # Caller serializes installation; immutable existing destinations checked above.
        temp.replace(target)
    finally:
        Path(name).unlink(missing_ok=True)


def materialize(source, root, version):
    source, root = source.absolute(), root.absolute()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", version):
        raise ValueError("invalid catalog version")
    public = source / "public"
    if source.resolve() != source or public.is_symlink() or root.resolve() != root:
        raise ValueError("source directory must not be a symlink")
    catalog = json.loads(safe_file(public, "catalog.json").read_text())
    if catalog.get("schema_version") != "svoe-display-catalog-2.0.0":
        raise ValueError("expected audited display v2 schema")
    rows = [json.loads(line) for line in safe_file(public, "wines.jsonl").read_text().splitlines() if line]
    if not rows or len({r["slug"] for r in rows}) != len(rows):
        raise ValueError("empty catalog or duplicate slug")
    assets, origins = {}, {}
    for row in rows:
        image = row["image"]
        variants = image["variants"]
        if len(variants) != 3 or {v["role"] for v in variants} != set(ROLES):
            raise ValueError("missing/duplicate image role: " + row["slug"])
        row.setdefault("id", row["slug"])
        for variant in variants:
            digest = variant["sha256"]
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("invalid SHA-256")
            origin = safe_file(public, variant["path"])
            key = f'{ROLES[variant["role"]]}/{digest}.webp'
            spec = {k: variant[k] for k in ("sha256", "bytes", "width", "height", "mime_type")}
            spec["path"] = key
            if key in assets and assets[key] != spec:
                raise ValueError("inconsistent declarations for " + key)
            if key not in assets:
                if sha(origin) != digest or origin.stat().st_size != spec["bytes"]:
                    raise ValueError("source checksum/bytes mismatch: " + str(origin))
                assets[key], origins[key] = spec, origin
            variant["path"] = key
        original = next(v for v in variants if v["role"] == "original")
        row["image"] = {k: v for k, v in original.items() if k != "role"}
        row["image"]["variants"] = variants
    rows.sort(key=lambda row: row["id"])
    catalog["catalog_version"] = version
    suppressions = json.loads(safe_file(source, "internal/accepted-text-suppressions.json").read_text())
    policy = {
        "schema_version": "catalog-display-policy-1",
        "source_manifest_sha256": sha(safe_file(source, "validation-manifest.json")),
        "suppressed_fields": [{"slug": x["slug"], "field": x["field"]} for x in suppressions["entries"]],
        "purpose": "display-only; not an ML reference approval",
    }
    files = {
        "wines.jsonl": ("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)).encode(),
        "aliases.json": safe_file(public, "aliases.json").read_bytes(),
        "catalog.json": json_bytes(catalog),
        "internal/display-policy.json": json_bytes(policy),
        "PREPARATION.md": ("# Runtime catalogue\n\nPrepared from the audited display-v2 package. "
                           "Each role has its own directory, including small originals without upscaling. "
                           "Media files retain their original bytes and SHA-256. Run the data gate before import. "
                           "Raw evidence remains in the source package; do not serve metadata/internal via HTTP.\n").encode(),
    }
    manifest = {
        "schema_version": "catalog-release-1", "catalog_version": version,
        "files": [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in sorted(files.items())],
        "media": [assets[key] for key in sorted(assets)],
    }
    manifest_data = json_bytes(manifest)
    target = root / "releases" / version
    if target.resolve() != target or (root / "media").resolve() != root / "media":
        raise ValueError("symlinked output directories are not supported")
    if target.exists():
        if target.is_symlink() or (target / "manifest.json").read_bytes() != manifest_data:
            raise ValueError("version already exists with different content")
        for name, data in files.items():
            if safe_file(target, name).read_bytes() != data:
                raise ValueError("existing metadata was changed: " + name)
    # All input metadata and the version identity have been checked before writing.
    # An interrupted copy can leave unreferenced immutable files; rerun safely reuses them.
    directory(root / "media")
    for folder in ROLES.values():
        directory(root / "media" / folder)
    for key in assets:
        publish_asset(origins[key], root / "media" / key, assets[key]["sha256"])
    if not target.exists():
        stage_root = root / "staging"
        directory(stage_root)
        with tempfile.TemporaryDirectory(prefix=version + "-", dir=stage_root) as stage:
            stage = Path(stage)
            for name, data in files.items():
                path = stage / name
                directory(path.parent)
                path.write_bytes(data)
                path.chmod(0o644)
            (stage / "manifest.json").write_bytes(manifest_data)
            stage.chmod(0o755)
            directory(target.parent)
            stage.rename(target)
    directory(target)
    for name in [*files, "manifest.json"]:
        path = target / name
        directory(path.parent)
        path.chmod(0o644)
    return {"version": version, "path": str(target), "cards": len(rows), "media": len(assets),
            "manifestSHA256": hashlib.sha256(manifest_data).hexdigest(), "status": "materialized-not-approved"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    # Serialize writes to the common media store, without another service.
    import fcntl
    directory(args.root)
    with (args.root / ".prepare.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(materialize(args.source, args.root, args.version), ensure_ascii=False))
