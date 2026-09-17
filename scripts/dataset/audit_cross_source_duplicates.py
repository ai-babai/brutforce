#!/usr/bin/env python3
"""Build an exact-hash and same-dHash graph across normalized sources."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from common import stable_id, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "Dataset/92_reports"
MANIFESTS = (
    ("svoe_archive", "Dataset/01_svoe_vino_catalog/tables/media.jsonl"),
    ("svoe_live_new", "Dataset/04_svoe_vino_web_enrichment/tables/new_live_media.jsonl"),
    ("telegram", "Dataset/02_rvk_telegram/tables/media.jsonl"),
    ("retail", "Dataset/05_retail_alcohol_detection/tables/media.jsonl"),
    ("xwines_slim", "Dataset/07_x_wines/tables/slim_media.jsonl"),
    ("winesensed_ru", "Dataset/08_winesensed/tables/media.jsonl"),
    ("rf100", "Dataset/09_rf100_wine_labels/tables/media.jsonl"),
    ("open_food_facts", "Dataset/10_open_food_facts_wine_ru/tables/media.jsonl"),
    ("mavt_ru", "Dataset/11_mavt_ru_wines/tables/media.jsonl"),
    ("amwine_ru", "Dataset/15_aromatny_mir_ru_wines/tables/media.jsonl"),
    ("alkoteka_ru", "Dataset/16_alkoteka_ru_wines/tables/media.jsonl"),
)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    rows = []
    counts = {}
    for source, relative in MANIFESTS:
        path = ROOT / relative
        source_rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []
        counts[source] = len(source_rows)
        for row in source_rows:
            rows.append({
                "source": source,
                "media_id": row.get("media_id"),
                "product_id": row.get("product_id"),
                "path": row.get("relative_path") or row.get("path") or row.get("raw_path"),
                "sha256": row.get("sha256"),
                "dhash64": row.get("dhash64"),
                "training_candidate": row.get("training_candidate") or row.get("eligible_for_supervised_training"),
            })

    exact = defaultdict(list)
    dhash = defaultdict(list)
    for row in rows:
        if row["sha256"]:
            exact[row["sha256"]].append(row)
        if row["dhash64"]:
            dhash[row["dhash64"]].append(row)

    exact_cross = [{"sha256": key, "members": group} for key, group in exact.items() if len({row["source"] for row in group}) > 1]
    dhash_cross = [{"dhash64": key, "members": group} for key, group in dhash.items() if len({row["source"] for row in group}) > 1]
    exact_cross.sort(key=lambda row: row["sha256"])
    dhash_cross.sort(key=lambda row: row["dhash64"])
    write_jsonl(REPORTS / "cross_source_exact_duplicates.jsonl", exact_cross)
    write_jsonl(REPORTS / "cross_source_same_dhash_candidates.jsonl", dhash_cross)
    review_rows = [
        {
            "review_item_id": stable_id("review_cross_dhash", row["dhash64"]),
            "source_dataset": "cross_source",
            "review_state": "needs_verification",
            "group_id": row["dhash64"],
            "required_action": "visually verify same-dHash cross-source group; assign shared identity/near-duplicate group only when supported",
            "evidence": {"dhash64": row["dhash64"], "members": row["members"]},
            "candidates": [member.get("media_id") for member in row["members"]],
        }
        for row in dhash_cross
    ]
    write_jsonl(REPORTS / "review_queue_cross_source_dhash.jsonl", review_rows)
    summary = {
        "manifest_rows_by_source": counts,
        "total_media_rows": len(rows),
        "cross_source_exact_duplicate_groups": len(exact_cross),
        "cross_source_same_dhash_candidate_groups": len(dhash_cross),
        "cross_source_same_dhash_review_items": len(review_rows),
        "same_dhash_is_not_proof": True,
        "split_gate": "all exact groups and visually confirmed near-duplicate groups must stay in one split",
    }
    write_json(REPORTS / "CROSS-SOURCE-DUPLICATES-SUMMARY.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
