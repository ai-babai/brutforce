"""Gold-blind fixed-Top20 DISK + LightGlue experiment. See README.md."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image, ImageOps

VERSION = "disk-depth-lightglue-fixed20-v1"
REPO_COMMIT = "eb42fee2d71449efb0aa5c10549752b5d75384d8"
KEYPOINTS = 1024
INLIER_PX = 3.0
MIN_INLIERS = 8
MIN_COVERAGE = 0.02


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def load_lightglue(repo: Path):
    sys.path.insert(0, str(repo))
    from lightglue import DISK, LightGlue
    from lightglue.utils import load_image

    return DISK, LightGlue, load_image


def models(repo: Path, device: str):
    DISK, LightGlue, load_image = load_lightglue(repo)
    extractor = DISK(max_num_keypoints=KEYPOINTS).eval().to(device)
    matcher = LightGlue(features="disk").eval().to(device)
    return extractor, matcher, load_image


def extract(path: Path, extractor, load_image, device: str) -> dict:
    with torch.inference_mode():
        image = load_image(path).to(device)
        result = extractor.extract(image)
    return {key: value.detach().cpu() if isinstance(value, torch.Tensor) else value
            for key, value in result.items()}


def to_device(features: dict, device: str) -> dict:
    return {key: value.to(device) if isinstance(value, torch.Tensor) else value
            for key, value in features.items()}


def make_index(args):
    catalog = json.loads(args.catalog.read_text())
    entries = catalog["references"]
    availability = json.loads(args.availability.read_text())
    args.cache.mkdir(parents=True, exist_ok=True)
    extractor, _, load_image = models(args.lightglue_repo, args.device)
    rows = []
    start = time.perf_counter()
    for i, ref in enumerate(entries, 1):
        slug = ref["slug"]
        expected = ref.get("sha256")
        path = args.reference_root / ref["path"] if ref.get("path") else None
        row = {"slug": slug, "reference_sha256": expected, "status": "missing"}
        if not availability.get(slug, False):
            row["status"] = "excluded_by_b_index"
        elif expected and path and path.is_file():
            observed = sha(path)
            if observed == expected:
                feature_path = args.cache / (expected + ".pt")
                if not feature_path.is_file():
                    try:
                        feats = extract(path, extractor, load_image, args.device)
                        torch.save(feats, feature_path)
                    except Exception as exc:
                        row["status"] = "extract_error"
                        row["error"] = type(exc).__name__ + ": " + str(exc)[:200]
                if feature_path.is_file():
                    row["status"] = "ready"
                    row["feature_path"] = str(feature_path)
            else:
                row["status"] = "sha_mismatch"
                row["observed_sha256"] = observed
        rows.append(row)
        if i % 100 == 0:
            print(json.dumps({"indexed": i, "total": len(entries),
                              "ready": sum(r["status"] == "ready" for r in rows)}), flush=True)
    manifest = {"version": VERSION, "catalog_sha256": sha(args.catalog),
                "b_index_availability_sha256": sha(args.availability),
                "lightglue_commit": REPO_COMMIT, "disk_weights": "depth",
                "lightglue_weights": "disk_lightglue", "keypoints": KEYPOINTS,
                "device": args.device, "elapsed_seconds": round(time.perf_counter()-start, 3),
                "references": rows}
    (args.cache / "meta.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({"index_done": True, "ready": sum(r["status"] == "ready" for r in rows),
                      "missing": sum(r["status"] != "ready" for r in rows),
                      "seconds": manifest["elapsed_seconds"]}), flush=True)


def query_crop(path: Path, expected_sha: str, result: dict, out: Path) -> tuple[Path | None, str]:
    if sha(path) != expected_sha:
        return None, "query_sha_mismatch"
    box = (result.get("selection") or {}).get("selected_box")
    if not box:
        return None, "no_target"
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
    x1, y1, x2, y2 = [int(v) for v in box]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(image.width, x2), min(image.height, y2)
    if x2 <= x1 or y2 <= y1:
        return None, "invalid_target_box"
    target = image.crop((x1, y1, x2, y2))
    label = result.get("label_context_box")
    if label:
        a, b, c, d = [int(v) for v in label]
        a, b, c, d = max(0, a), max(0, b), min(target.width, c), min(target.height, d)
        if c <= a or d <= b:
            return None, "invalid_label_box"
        target = target.crop((a, b, c, d))
    out.parent.mkdir(parents=True, exist_ok=True)
    target.save(out, format="PNG")
    return out, "ready"


def geometry(feats0: dict, feats1: dict, matcher, device: str) -> dict:
    from lightglue.utils import rbd
    with torch.inference_mode():
        match = matcher({"image0": to_device(feats0, device),
                         "image1": to_device(feats1, device)})
    match = rbd(match)
    indices = match["matches"].detach().cpu().numpy()
    result = {"matches": int(len(indices)), "inliers": 0,
              "coverage": 0.0, "score": 0.0, "valid": False}
    if len(indices) < MIN_INLIERS:
        return result
    p0 = rbd(feats0)["keypoints"].numpy()[indices[:, 0]].astype(np.float32)
    p1 = rbd(feats1)["keypoints"].numpy()[indices[:, 1]].astype(np.float32)
    _, mask = cv2.findHomography(p0, p1, cv2.RANSAC, INLIER_PX)
    if mask is None:
        return result
    inlier_points = p0[mask.reshape(-1).astype(bool)]
    count = len(inlier_points)
    size = rbd(feats0)["image_size"].numpy().reshape(-1)
    area = max(float(size[0] * size[1]), 1.0)
    coverage = float(cv2.contourArea(cv2.convexHull(inlier_points)) / area) if count >= 3 else 0.0
    coverage = max(0.0, min(1.0, coverage))
    valid = count >= MIN_INLIERS and coverage >= MIN_COVERAGE
    result.update(inliers=int(count), coverage=round(coverage, 6),
                  score=round(float(count * math.sqrt(coverage)), 6) if valid else 0.0,
                  valid=valid)
    return result


def rerank(pool: list[str], evidence: list[dict]) -> tuple[list[str], list[str]]:
    scores = {e["slug"]: e["geometry"]["score"] for e in evidence}
    valid = {slug: score for slug, score in scores.items() if score > 0}
    if not valid:
        return pool[:], pool[:]
    rank_b = {slug: i for i, slug in enumerate(pool, 1)}
    local = sorted(pool, key=lambda slug: (-scores.get(slug, 0), rank_b[slug]))
    rank_g = {slug: i for i, slug in enumerate(local, 1) if slug in valid}
    n = max(len(pool), 1)
    # Fixed score; no per-query normalization by a potentially unstable max inlier count.
    def fused(slug):
        b = 0.50 * (n + 1 - rank_b[slug]) / n
        g = 0.50 * (n + 1 - rank_g[slug]) / n if slug in rank_g else 0.0
        return b + g
    fusion = sorted(pool, key=lambda slug: (-fused(slug), rank_b[slug]))
    return local, fusion


def run(args):
    baseline = read_jsonl(args.baseline)
    manifest = json.loads(args.manifest.read_text())
    case_by_id = {row["case_id"]: row for row in manifest["cases"]}
    index = json.loads((args.cache / "meta.json").read_text())
    if index["catalog_sha256"] != sha(args.catalog):
        raise ValueError("catalog SHA differs from indexed catalog")
    by_slug = {r["slug"]: r for r in index["references"]}
    extractor, matcher, load_image = models(args.lightglue_repo, args.device)
    @lru_cache(maxsize=1024)
    def cached_feature(feature_path: str):
        return torch.load(feature_path, map_location="cpu", weights_only=True)
    scratch = args.out.parent / "query-crops"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as stream:
        for i, row in enumerate(baseline, 1):
            start = time.perf_counter()
            case = case_by_id.get(row["case_id"])
            if case is None:
                raise ValueError("missing manifest case " + row["case_id"])
            if case["sha256"] != row["query_sha256"]:
                raise ValueError("query hash mismatch " + row["case_id"])
            result = row.get("result") or {}
            pool = result.get("ranked_slugs") or []
            evidence = []
            status = "no_candidates"
            if pool:
                image_path = args.query_root / case["path"]
                crop_path, status = query_crop(image_path, case["sha256"], result,
                                               scratch / (row["case_id"] + ".png"))
                if crop_path:
                    qfeats = extract(crop_path, extractor, load_image, args.device)
                    for slug in pool:
                        reference = by_slug.get(slug)
                        if not reference or reference["status"] != "ready":
                            evidence.append({"slug": slug, "status": "missing_reference",
                                             "geometry": {"score": 0.0, "valid": False}})
                            continue
                        try:
                            rfeats = cached_feature(reference["feature_path"])
                            geo = geometry(qfeats, rfeats, matcher, args.device)
                            evidence.append({"slug": slug, "status": "ready", "geometry": geo,
                                             "reference_sha256": reference["reference_sha256"]})
                        except Exception as exc:
                            evidence.append({"slug": slug, "status": "match_error",
                                             "error": type(exc).__name__ + ": " + str(exc)[:200],
                                             "geometry": {"score": 0.0, "valid": False}})
            local, fusion = rerank(pool, evidence)
            elapsed = round((time.perf_counter() - start) * 1000, 3)
            output = {"case_id": row["case_id"], "track": row["track"],
                      "query_sha256": row["query_sha256"], "baseline_action": result.get("action"),
                      "baseline_top20": pool, "local_top20": local, "fusion_top20": fusion,
                      "status": status, "evidence": evidence, "rerank_elapsed_ms": elapsed,
                      "baseline_elapsed_ms": row.get("elapsed_ms"),
                      "query_crop_sha256": sha(crop_path) if pool and crop_path else None,
                      "selected_box": (result.get("selection") or {}).get("selected_box"),
                      "label_context_box": result.get("label_context_box")}
            stream.write(json.dumps(output, ensure_ascii=False) + "\n")
            stream.flush()
            if i % 25 == 0:
                print(json.dumps({"processed": i, "total": len(baseline)}), flush=True)
    print(json.dumps({"run_done": True, "rows": len(baseline), "output": str(args.out)}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="phase", required=True)
    idx = sub.add_parser("index")
    idx.add_argument("--catalog", type=Path, required=True)
    idx.add_argument("--reference-root", type=Path, required=True)
    idx.add_argument("--availability", type=Path, required=True)
    idx.add_argument("--cache", type=Path, required=True)
    idx.add_argument("--lightglue-repo", type=Path, required=True)
    idx.add_argument("--device", default="cuda")
    runner = sub.add_parser("run")
    runner.add_argument("--baseline", type=Path, required=True)
    runner.add_argument("--manifest", type=Path, required=True)
    runner.add_argument("--query-root", type=Path, required=True)
    runner.add_argument("--catalog", type=Path, required=True)
    runner.add_argument("--cache", type=Path, required=True)
    runner.add_argument("--lightglue-repo", type=Path, required=True)
    runner.add_argument("--out", type=Path, required=True)
    runner.add_argument("--device", default="cuda")
    args = parser.parse_args()
    if args.phase == "index":
        make_index(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
