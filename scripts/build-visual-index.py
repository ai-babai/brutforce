#!/usr/bin/env python3
"""Check inputs and run the frozen SO400M visual-index builder offline.

Requires verified organizer reference photos and the original SO400M PyTorch
checkpoint in addition to the serving bundle; the ONNX graph alone is not an
input to this historical builder.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True, help="verified f8-bundle")
    parser.add_argument("--code-root", type=Path, required=True, help="repository apps/vision directory")
    parser.add_argument("--inputs", type=Path, required=True, help="visual-build-inputs directory")
    parser.add_argument("--image-dir", type=Path, required=True, help="root containing images/<slug>.webp")
    parser.add_argument("--out", type=Path, required=True, help="new index directory outside Git")
    parser.add_argument("--device", default="cuda", choices=("cpu", "cuda"))
    parser.add_argument("--batch", default=16, type=int)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    catalog = args.bundle / "catalog/catalog-bundle.json"
    v2 = args.inputs / "v2-index"
    regions = args.inputs / "label-regions.jsonl"
    decisions = args.inputs / "reference-decisions.json"
    current_info = json.loads((args.bundle / "index/index-info.json").read_text())
    source_info = json.loads((v2 / "index-info.json").read_text())
    for expected, file in (
        (current_info["catalog_manifest_sha256"], catalog),
        (current_info["v2_index_sha256"], v2 / "index.npz"),
        (current_info["v2_regions_sha256"], regions),
        (current_info["reference_decisions_sha256"], decisions),
    ):
        if sha(file) != expected:
            parser.error("source mismatch: " + file.name)
    if source_info["catalog_manifest_sha256"] != sha(catalog):
        parser.error("v2 index belongs to a different catalog")
    refs = json.loads(catalog.read_text())["references"]
    excluded = {row["slug"] for row in json.loads(decisions.read_text())["excluded"]}
    missing = []
    for row in refs:
        if not row.get("sha256") or row["slug"] in excluded:
            continue
        relative = Path(row["path"])
        path = (args.image_dir / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(args.image_dir.resolve()) or not path.is_file():
            missing.append(row["slug"])
        elif sha(path) != row["sha256"]:
            parser.error("reference image SHA mismatch: " + row["slug"])
    if missing:
        parser.error(f"missing {len(missing)} required reference photos (first: {missing[0]})")
    print(f"verified {len(refs) - len(excluded) - sum(not row.get('sha256') for row in refs if row['slug'] not in excluded)} photo inputs", flush=True)
    if args.check_only:
        return
    if args.out.exists():
        parser.error("output already exists")
    env = os.environ.copy()
    env.setdefault("HF_HUB_OFFLINE", "1")
    subprocess.run([
        sys.executable, str(args.code_root / "parent/so400m_ablation.py"),
        "--phase", "index", "--catalog", str(catalog),
        "--image-dir", str(args.image_dir), "--regions", str(regions),
        "--decisions", str(decisions), "--v2-index", str(v2),
        "--out", str(args.out), "--device", args.device,
        "--model", "so400m384", "--batch", str(args.batch),
    ], check=True, env=env)
    print(f"index SHA256 {sha(args.out / 'index.npz')}")


if __name__ == "__main__":
    main()
