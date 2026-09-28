#!/usr/bin/env python3
"""Make a private, purpose-split transfer from already verified local assets."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_CATALOG = "d88c4454a46802490ee2f69e32d2fb28fd8816d23a6d4d554356697632f845ef"
EXPECTED_RECOMMENDATIONS = "f05f16c7790782ec3c1b50047bba4e29f1d906217f63846c217d5516e6ef8e7f"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def file_at(root, relative):
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts:
        raise ValueError("unsafe manifest path")
    path = root.joinpath(*name.parts)
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("missing or linked input: " + str(name))
    return path


def archive(out, name, rows, compressed=True):
    path = out / (name + (".tar.gz" if compressed else ".tar"))
    with tarfile.open(path, "w:gz" if compressed else "w", dereference=True) as writer:
        for source, target in rows:
            writer.add(source, arcname=target, recursive=False)
    print(f"{path.name}: {len(rows)} files, {path.stat().st_size} bytes", flush=True)
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("bundle", "catalog", "media", "recommendations", "v2-index", "regions", "decisions", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    if a.out.exists():
        p.error("output already exists")
    subprocess.run([sys.executable, str(ROOT / "scripts/asset-bundle.py"), "verify", str(a.bundle)], check=True)
    manifest_file = file_at(a.catalog, "manifest.json")
    if digest(manifest_file) != EXPECTED_CATALOG or digest(a.recommendations) != EXPECTED_RECOMMENDATIONS:
        p.error("catalog or recommendation index differs from the pinned release")
    manifest = json.loads(manifest_file.read_text())
    package = [(manifest_file, "catalog-package/manifest.json")]
    for item in manifest["files"]:
        source = file_at(a.catalog, item["path"])
        if source.stat().st_size != item["bytes"] or digest(source) != item["sha256"]:
            p.error("catalog file checksum mismatch: " + item["path"])
        package.append((source, "catalog-package/" + item["path"]))
    media = []
    for item in manifest["media"]:
        source = file_at(a.media, item["path"])
        if source.stat().st_size != item["bytes"] or digest(source) != item["sha256"]:
            p.error("media checksum mismatch: " + item["path"])
        media.append((source, "catalog-media/" + item["path"]))
    info = json.loads(file_at(a.bundle, "index/index-info.json").read_text())
    for source, sha in (
        (file_at(a.v2_index, "index.npz"), info["v2_index_sha256"]),
        (a.regions, info["v2_regions_sha256"]),
        (a.decisions, info["reference_decisions_sha256"]),
    ):
        if digest(source) != sha:
            p.error("visual rebuild input SHA mismatch: " + source.name)
    manifest_lines = (ROOT / "deploy/assets/f8-cpu.sha256").read_text().splitlines()
    data, weights = [], []
    for line in manifest_lines:
        _, relative = line.split("  ", 1)
        if relative.endswith(".py") or relative == "overlay/spec/lexicon.json":
            p.error("code/config must be checked into apps/vision, not archived")
        source = file_at(a.bundle, relative)
        (weights if relative.startswith(("onnx/", "models/")) else data).append(
            (source, "f8-bundle/" + relative)
        )
    index_inputs = [
        (file_at(a.v2_index, "index.npz"), "visual-build-inputs/v2-index/index.npz"),
        (file_at(a.v2_index, "index-info.json"), "visual-build-inputs/v2-index/index-info.json"),
        (a.regions, "visual-build-inputs/label-regions.jsonl"),
        (a.decisions, "visual-build-inputs/reference-decisions.json"),
    ]
    a.out.mkdir(parents=True)
    shutil.copyfile(ROOT / "docs/ASSET-TRANSFER.ru.md", a.out / "README.ru.md")
    outputs = [
        archive(a.out, "01-recognition-data", data),
        archive(a.out, "02-recognition-weights", weights, compressed=False),
        archive(a.out, "03-display-catalog", package),
        archive(a.out, "04-display-media", media, compressed=False),
        archive(a.out, "05-text-recommendations", [(a.recommendations, "recommendations/index.json")]),
        archive(a.out, "06-visual-index-inputs", index_inputs),
    ]
    (a.out / "SHA256SUMS").write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in [a.out / "README.ru.md", *outputs])
    )
    print("SHA256SUMS written; source data left untouched", flush=True)


if __name__ == "__main__":
    main()
