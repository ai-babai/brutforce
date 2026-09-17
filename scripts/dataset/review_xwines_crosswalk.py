#!/usr/bin/env python3
"""Record the completed manual X-Wines ↔ Svoe Vino visual crosswalk review."""

from __future__ import annotations

import json
from pathlib import Path

from common import write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "Dataset/07_x_wines/tables"

# These determinations concern cross-source identity only.  Every X-Wines row
# keeps its own exact WineID label even when no current Svoe product matches.
DECISIONS = {
    193764: ("same_product_line_different_vintage_or_packaging", "product_svoe_7cd1327d0438eba337cb", "Golubitskoe Estate Reserve Cabernet Sauvignon; X-Wines label is vintage 2018"),
    193765: ("no_exact_current_svoe_match", None, "Chateau Tamagne Molodoe 2021 is absent from current Svoe sitemap"),
    193783: ("no_exact_current_svoe_match", None, "Chateau Tamagne Reserve Cabernet 2016 is absent from current Svoe sitemap"),
    193856: ("same_product_line_different_vintage_or_packaging", "product_svoe_b090db466958f8413d78", "Vedernikov Krasnostop Zolotovskiy; X-Wines label is vintage 2013"),
    193941: ("no_exact_current_svoe_match", None, "Old Gai-Kodzor Shiraz label is not either current Terroir line"),
    195476: ("same_product_line_different_vintage_or_packaging", "product_svoe_f6183bdec01653f0619f", "Aristov Cuvee Alexander Rose de Pinot; vintage/label differs"),
    196718: ("no_exact_current_svoe_match", None, "Select Rose Brut is not current Select Blanc Brut"),
}


def main() -> int:
    source = TABLES / "slim_russian_products.jsonl"
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    reviewed = []
    for row in rows:
        wine_id = int(row["external_wine_id"])
        decision, product_id, note = DECISIONS[wine_id]
        reviewed.append({
            "external_wine_id": wine_id,
            "xwines_product_id": row["product_id"],
            "xwines_media_id": row["media_id"],
            "wine_name": row["wine_name"],
            "winery": row["winery"],
            "source_label_status": "gold_exact_xwines_wine_id",
            "svoe_crosswalk_status": decision,
            "svoe_product_id": product_id,
            "review_method": "manual_visual_label_comparison_2026-09-15",
            "review_note": note,
            "safe_for_xwines_sku_training": True,
            "safe_to_merge_as_same_svoe_sku": False,
        })
    write_jsonl(TABLES / "russian_crosswalk_review.jsonl", reviewed)
    summary = json.loads((TABLES / "SLIM-SUMMARY.json").read_text(encoding="utf-8"))
    summary["counts"]["russian_crosswalk_reviewed"] = len(reviewed)
    summary["counts"]["same_product_line_crosswalks"] = sum(1 for row in reviewed if row["svoe_product_id"])
    summary["counts"]["exact_svoe_sku_crosswalks"] = 0
    summary["gates"].update({
        "catalog_crosswalk_review_complete": True,
        "russian_source_labels_ready": True,
        "svoe_crosswalk_review_complete": True,
        "safe_to_merge_cross_source_as_exact_sku": False,
    })
    write_json(TABLES / "SLIM-SUMMARY.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
