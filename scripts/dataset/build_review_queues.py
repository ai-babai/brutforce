#!/usr/bin/env python3
"""Build explicit manual-review queues for every unresolved dataset gate."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from common import stable_id, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "Dataset/92_reports"
SOURCE_DATASETS = [
    "01_svoe_vino_catalog",
    "02_rvk_telegram",
    "03_manual_store",
    "04_svoe_vino_web_enrichment",
    "05_retail_alcohol_detection",
    "06_wine_images_126k",
    "07_x_wines",
    "08_winesensed",
    "09_rf100_wine_labels",
    "10_open_food_facts_wine_ru",
    "11_mavt_ru_wines",
    "12_krasnoe_i_beloe_ru_wines",
    "13_winelab_ru_wines",
    "14_simplewine_ru_wines",
    "15_aromatny_mir_ru_wines",
    "16_alkoteka_ru_wines",
    "17_luding_ru_wines",
    "18_russian_wine_master",
]


def load(path: str) -> list[dict]:
    target = ROOT / path
    if not target.is_file():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]


def with_review_identity(dataset: str, state: str, rows: list[dict]) -> list[dict]:
    materialized = []
    for row in rows:
        stable_key = next((str(row[key]) for key in (
            "media_id", "association_id", "product_id", "dhash64", "queue"
        ) if row.get(key)), json.dumps(row, ensure_ascii=False, sort_keys=True))
        materialized.append({
            "review_item_id": stable_id("review", f"{dataset}:{state}:{stable_key}"),
            "source_dataset": dataset,
            "review_state": state,
            **row,
        })
    return materialized


def materialize_review_workspaces(routes: dict[str, dict[str, list[dict]]]) -> dict[str, dict[str, int]]:
    result = {}
    for dataset in SOURCE_DATASETS:
        review_root = ROOT / "Dataset" / dataset / "review"
        for human_state in ("verified", "rejected"):
            (review_root / human_state).mkdir(parents=True, exist_ok=True)

        # A source-specific collector may own richer queues.  Preserve them when
        # this aggregate builder has no explicit route for the dataset.
        existing_status_path = review_root / "STATUS.json"
        if dataset not in routes and existing_status_path.is_file():
            existing_status = json.loads(existing_status_path.read_text(encoding="utf-8"))
            existing_counts = existing_status.get("generated_queues") or existing_status
            result[dataset] = {
                "needs_verification": int(existing_counts.get("needs_verification", 0)),
                "needs_annotation": int(existing_counts.get("needs_annotation", 0)),
            }
            continue

        verification = with_review_identity(
            dataset, "needs_verification", routes.get(dataset, {}).get("needs_verification", [])
        )
        annotation = with_review_identity(
            dataset, "needs_annotation", routes.get(dataset, {}).get("needs_annotation", [])
        )
        write_jsonl(review_root / "needs_verification/queue.jsonl", verification)
        write_jsonl(review_root / "needs_annotation/queue.jsonl", annotation)
        status = {
            "contract_version": "1.0.0",
            "source_dataset": dataset,
            "generated_queues": {
                "needs_verification": len(verification),
                "needs_annotation": len(annotation),
            },
            "human_decision_logs": {
                "verified": "verified/decisions.jsonl",
                "rejected": "rejected/decisions.jsonl",
            },
            "media_copy_policy": "reference_by_media_id_and_relative_path_only",
        }
        write_json(review_root / "STATUS.json", status)
        result[dataset] = status["generated_queues"]
    return result


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)

    telegram_media = load("Dataset/02_rvk_telegram/tables/media.jsonl")
    telegram = []
    for row in telegram_media:
        if row.get("source_role") not in {"telegram_photo", "telegram_file_image"}:
            continue
        telegram.append({
            "queue": "telegram_scene_annotation",
            "priority": 1 if row.get("label_status") == "candidate_from_caption_unverified" else 2,
            "media_id": row["media_id"],
            "path": row["relative_path"],
            "label_status": row.get("label_status"),
            "bbox_status": row.get("bbox_status"),
            "message_ids": row.get("message_ids", []),
            "product_candidates": row.get("product_candidates", []),
            "required_action": "identify every visible bottle; draw bottle bbox for multi-object scenes; verify SKU against label/table",
        })
    telegram.sort(key=lambda row: (row["priority"], row["path"]))
    write_jsonl(REPORTS / "review_queue_telegram.jsonl", telegram)

    svoe_media = load("Dataset/01_svoe_vino_catalog/tables/media.jsonl")
    svoe_ambiguous = [{
        "queue": "svoe_shared_asset_resolution",
        "media_id": row["media_id"],
        "path": row["relative_path"],
        "product_candidates": row.get("product_candidates", []),
        "label_status": row.get("label_status"),
        "required_action": "resolve exact product identity or keep excluded",
    } for row in svoe_media if row.get("label_status") == "ambiguous_shared_catalog_asset"]
    write_jsonl(REPORTS / "review_queue_svoe_shared_assets.jsonl", svoe_ambiguous)

    live = load("Dataset/04_svoe_vino_web_enrichment/tables/live_associations.jsonl")
    live_shared = [{**row, "queue": "svoe_live_shared_primary", "required_action": "confirm whether one generic image legitimately represents multiple SKUs"}
                   for row in live if row.get("shared_live_primary_image")]
    write_jsonl(REPORTS / "review_queue_svoe_live_shared.jsonl", live_shared)

    rf_media = load("Dataset/09_rf100_wine_labels/tables/media.jsonl")
    dhash_groups = defaultdict(list)
    for row in rf_media:
        if row.get("dhash64"):
            dhash_groups[row["dhash64"]].append(row)
    rf_queue = []
    for dhash, group in sorted(dhash_groups.items()):
        if len({row["source_split"] for row in group}) < 2:
            continue
        rf_queue.append({
            "queue": "rf100_cross_split_near_duplicate",
            "dhash64": dhash,
            "source_splits": sorted({row["source_split"] for row in group}),
            "media": [{"media_id": row["media_id"], "path": row["path"], "sha256": row["sha256"]} for row in group],
            "required_action": "visual near-duplicate review; group before assigning frozen split",
        })
    write_jsonl(REPORTS / "review_queue_rf100_cross_split.jsonl", rf_queue)

    off = load("Dataset/10_open_food_facts_wine_ru/tables/candidates.jsonl")
    off_queue = [{
        "queue": "open_food_facts_russian_origin",
        "product_id": row["product_id"],
        "code": row.get("code"),
        "product_name": row.get("product_name"),
        "brands": row.get("brands"),
        "status": row.get("russian_wine_status"),
        "reasons": row.get("russian_wine_status_reasons"),
        "required_action": "verify Russian production from front/back label or producer source",
    } for row in off if row.get("russian_wine_status", "").startswith(("silver_", "bronze_probable_"))]
    write_jsonl(REPORTS / "review_queue_open_food_facts.jsonl", off_queue)

    cross_source_dhash = load("Dataset/92_reports/review_queue_cross_source_dhash.jsonl")

    summary = {
        "telegram_scene_images": len(telegram),
        "telegram_caption_first_priority": sum(row["priority"] == 1 for row in telegram),
        "svoe_ambiguous_media": len(svoe_ambiguous),
        "svoe_live_shared_associations": len(live_shared),
        "rf100_cross_split_dhash_groups": len(rf_queue),
        "open_food_facts_russian_origin_candidates": len(off_queue),
        "cross_source_same_dhash_candidates": len(cross_source_dhash),
    }
    routes = {
        "01_svoe_vino_catalog": {"needs_verification": svoe_ambiguous},
        "02_rvk_telegram": {"needs_annotation": telegram},
        "04_svoe_vino_web_enrichment": {"needs_verification": live_shared},
        "09_rf100_wine_labels": {"needs_verification": rf_queue},
        "10_open_food_facts_wine_ru": {"needs_verification": off_queue},
    }
    summary["per_dataset_review_workspaces"] = materialize_review_workspaces(routes)
    write_json(REPORTS / "REVIEW-QUEUES-SUMMARY.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
