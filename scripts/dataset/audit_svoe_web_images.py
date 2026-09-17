#!/usr/bin/env python3
"""Audit newly captured Svoe Vino hero images and link them to live pages."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from common import image_probe, relative_posix, sha256_file, stable_id, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "Dataset"
CAPTURE = DATASET / "00_raw/04_svoe_vino_web_snapshots/2026-09-15"
TABLES = DATASET / "04_svoe_vino_web_enrichment/tables"


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    live_rows = read_jsonl(TABLES / "live_products.jsonl")
    live = {row["slug"]: row for row in live_rows}
    archive_products = {row["slug"]: row for row in read_jsonl(DATASET / "01_svoe_vino_catalog/tables/products.jsonl")}
    archive_media_rows = read_jsonl(DATASET / "01_svoe_vino_catalog/tables/media.jsonl")
    archive_media_by_id = {row["media_id"]: row for row in archive_media_rows}
    downloaded = json.loads((CAPTURE / "downloaded_images_manifest.json").read_text(encoding="utf-8-sig"))
    media = []
    products = []
    for source in downloaded:
        path = CAPTURE / "images" / f"{source['slug']}.webp"
        page = live[source["slug"]]
        product_id = stable_id("product_svoe_live", page["slug"])
        probe = image_probe(path, calculate_dhash=True)
        digest = sha256_file(path)
        if digest != source["sha256"]:
            raise RuntimeError(f"checksum mismatch after capture: {source['slug']}")
        products.append({
            "manifest_version": "1.0.0", "source_id": "svoe-vino-live-2026-09-15",
            "product_id": product_id, "slug": page["slug"], "wine_name": page["title"],
            "winery": page["manufacturer"], "description": page["meta_description"],
            "source_page_url": page["page_url"], "quality_status": "live_page_partial_metadata",
        })
        media.append({
            "manifest_version": "1.0.0", "source_id": "svoe-vino-live-2026-09-15",
            "media_id": stable_id("media_svoe_live", source["slug"]),
            "product_id": product_id, "slug": source["slug"],
            "relative_path": relative_posix(path, DATASET), "source_url": source["source_url"],
            "bytes": path.stat().st_size, "sha256": digest,
            "label_status": "gold_live_product_page_primary_image",
            "bbox_status": "not_required_single_product_reference",
            "training_candidate": probe["decode_status"] == "ok", **probe,
        })
    write_jsonl(TABLES / "new_live_products.jsonl", products)
    write_jsonl(TABLES / "new_live_media.jsonl", media)

    new_media_by_slug = {row["slug"]: row for row in media}
    associations = []
    unresolved = []
    for page in live_rows:
        product = archive_products.get(page["slug"])
        product_id = product["product_id"] if product else stable_id("product_svoe_live", page["slug"])
        media_id = None
        method = None
        exact_name_matches = [
            archive_media_by_id[item]
            for item in page["archive_media_matches"]
            if item in archive_media_by_id and archive_media_by_id[item]["filename"] == page["primary_upload_name"]
        ]
        originals = [row for row in exact_name_matches if row["variant"] == "original"]
        if len(originals) == 1:
            media_id = originals[0]["media_id"]
            method = "exact_live_page_upload_filename_to_archive_original"
        elif page["slug"] in new_media_by_slug:
            media_id = new_media_by_slug[page["slug"]]["media_id"]
            method = "captured_live_page_primary_image"
        else:
            unresolved.append({
                "slug": page["slug"], "primary_upload_name": page["primary_upload_name"],
                "archive_media_matches": page["archive_media_matches"],
                "exact_name_original_count": len(originals),
            })
            continue
        associations.append({
            "association_id": stable_id("assoc_svoe_live", f"{page['slug']}:{media_id}"),
            "source_id": "svoe-vino-live-2026-09-15", "slug": page["slug"],
            "product_id": product_id, "media_id": media_id, "grade": "gold",
            "method": method, "eligible_for_supervised_sku_training": None,
        })
    media_use = Counter(row["media_id"] for row in associations)
    for row in associations:
        row["eligible_for_supervised_sku_training"] = media_use[row["media_id"]] == 1
        row["shared_live_primary_image"] = media_use[row["media_id"]] > 1
    write_jsonl(TABLES / "live_associations.jsonl", associations)
    write_jsonl(TABLES / "unresolved_live_associations.jsonl", unresolved)

    summary_path = TABLES / "SUMMARY.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["counts"].update({
        "new_primary_images_downloaded": len(media),
        "new_primary_images_decode_ok": sum(row["decode_status"] == "ok" for row in media),
        "live_products_with_primary_asset_in_archive_or_web_capture": (
            summary["counts"]["live_products_with_archive_asset"] + sum(row["decode_status"] == "ok" for row in media)
        ),
        "live_product_image_associations": len(associations),
        "unresolved_live_product_image_associations": len(unresolved),
        "live_associations_eligible_for_sku_training": sum(row["eligible_for_supervised_sku_training"] for row in associations),
        "live_associations_with_shared_primary_image": sum(row["shared_live_primary_image"] for row in associations),
    })
    summary["gates"]["all_live_primary_assets_available_after_enrichment"] = (
        summary["counts"]["live_products_with_primary_asset_in_archive_or_web_capture"]
        == summary["counts"]["sitemap_urls"]
    )
    summary["gates"]["all_new_primary_images_decode"] = all(row["decode_status"] == "ok" for row in media)
    summary["gates"]["all_live_products_have_image_association"] = len(associations) == len(live_rows) and not unresolved
    write_json(summary_path, summary)
    print(json.dumps(summary["counts"], ensure_ascii=False, indent=2))
    return 0 if summary["gates"]["all_live_primary_assets_available_after_enrichment"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
