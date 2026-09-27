#!/usr/bin/env python3
"""Discover existing transparent originals for catalog_alpha.py, without fetching URLs.

Reads the dated audited display decisions and 2026-09-15 media index. Optional
output is a private selection JSONL (outside the release and Git); each entry
must still be reviewed before preparing a release. Nothing is downloaded.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from PIL import Image

from catalog_alpha import HEX, REPO, verify_alpha
from catalog_data import safe_file


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def inventory(release, base_sha, vino_root, output):
    if vino_root.resolve() != vino_root.absolute():
        raise ValueError("source root is a symlink")
    manifest = safe_file(release, "manifest.json").read_bytes()
    if not HEX.fullmatch(base_sha) or hashlib.sha256(manifest).hexdigest() != base_sha:
        raise ValueError("base release manifest SHA256 mismatch")
    wines = rows(safe_file(release, "wines.jsonl"))
    raw = {r["canonical_slug"]: r for r in rows(safe_file(vino_root, "catalog-display-20260922/internal/raw-source-wines.jsonl")) if not r["is_alias"]}
    indexed = {r["media_id"]: r for r in rows(safe_file(vino_root, "2026-09-17/Dataset/01_svoe_vino_catalog/tables/media.jsonl"))}
    decisions = {r["slug"]: r for r in json.loads(safe_file(vino_root, "catalog-display-20260922/internal/photo-decisions.json").read_bytes())}
    if len(wines) != len(raw) or len(decisions) != 26:
        raise ValueError("source/card counts differ from the audited package; inspect manually")
    counts, selected, missing, unusable = Counter(), [], [], []
    for row in wines:
        wine_id = row["id"]
        source = raw.get(row["slug"])
        if source is None:
            raise ValueError("unmatched canonical slug")
        decision = decisions.get(row["slug"])
        if decision:
            path = "catalog-display-20260922/internal/" + decision["selected_path"]
            expected = decision["selected_sha256"]
            ref = "photo-decision:" + decision["slug"]
        else:
            original = source.get("reference") or {}
            entry = indexed.get(original.get("source_media_id"))
            if not entry:
                counts["unmapped"] += 1
                missing.append(wine_id)
                continue
            path = "2026-09-17/Dataset/" + entry["relative_path"]
            expected = entry["sha256"]
            ref = "source-media:" + entry["media_id"]
        file = safe_file(vino_root, path)
        if not HEX.fullmatch(expected) or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise ValueError("source SHA mismatch for " + wine_id)
        with Image.open(file) as im:
            if "A" not in im.getbands():
                counts["opaque"] += 1
                continue
            try:
                verify_alpha(im)
            except ValueError:
                counts["alpha_unusable"] += 1
                unusable.append(wine_id)
                continue
        selected.append({"id": wine_id, "path": path, "sha256": expected, "source_ref": ref})
        counts["ready_alpha"] += 1
    if output:
        if output.absolute().is_relative_to(REPO):
            raise ValueError("private selection must be outside Git")
        if output.exists() or output.is_symlink():
            raise ValueError("selection already exists; do not overwrite provenance")
        output.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in selected))
    return {"canonical": len(wines), **counts, "unmappedIDs": missing, "alphaUnusableIDs": unusable,
            "uniqueSelectedSHA256": len({x["sha256"] for x in selected}),
            "selectionSHA256": hashlib.sha256(("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in selected)).encode()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--base-manifest-sha256", required=True)
    parser.add_argument("--vino-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="new private JSONL; omit for read-only inventory")
    args = parser.parse_args()
    print(json.dumps(inventory(args.release, args.base_manifest_sha256, args.vino_root,
                               args.output), ensure_ascii=False))
