#!/usr/bin/env python3
"""Parse and audit the complete Kaggle X-Wines Slim 1K image edition."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from common import image_probe, relative_posix, sha256_file, stable_id, write_json, write_jsonl
from parse_xwines import catalog_candidates, load_svoe_products, parse_list


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "Dataset"
SOURCE = DATASET / "07_x_wines/cache/slim_extract"
CSV_PATH = SOURCE / "XWines_Slim_1K_wines.csv"
IMAGE_ROOT = SOURCE / "XWines_Slim_1K_labels-80/XWines_Slim_1K_labels-80"
TABLES = DATASET / "07_x_wines/tables"


def main() -> int:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    catalog = load_svoe_products(DATASET / "01_svoe_vino_catalog/tables/products.jsonl")
    products = []
    media = []
    russian = []
    hash_groups = defaultdict(list)
    missing = []

    for row in source_rows:
        wine_id = row["WineID"].strip()
        product_id = f"product_xwines_{wine_id}"
        is_russian = (row.get("Code") or "").upper() == "RU" or (row.get("Country") or "").casefold() == "russia"
        product = {
            "manifest_version": "1.0.0", "source_id": "x-wines",
            "edition": "XWines_Slim_1K", "product_id": product_id,
            "external_wine_id": int(wine_id), "wine_name": row.get("WineName") or None,
            "type": row.get("Type") or None, "elaborate": row.get("Elaborate") or None,
            "grapes": parse_list(row.get("Grapes", "")), "harmonize": parse_list(row.get("Harmonize", "")),
            "abv": float(row["ABV"]) if row.get("ABV") else None,
            "body": row.get("Body") or None, "acidity": row.get("Acidity") or None,
            "country_code": row.get("Code") or None, "country": row.get("Country") or None,
            "region": row.get("RegionName") or None, "winery": row.get("WineryName") or None,
            "website": row.get("Website") or None, "vintages": parse_list(row.get("Vintages", "")),
            "is_russian": is_russian,
        }
        products.append(product)
        image_path = IMAGE_ROOT / f"{wine_id}.jpeg"
        if not image_path.exists():
            missing.append(wine_id)
            continue
        relative = relative_posix(image_path, DATASET)
        media_id = stable_id("media_xwines_slim", relative)
        digest = sha256_file(image_path)
        probe = image_probe(image_path, calculate_dhash=True)
        media_row = {
            "manifest_version": "1.0.0", "source_id": "x-wines",
            "edition": "XWines_Slim_1K_labels-80", "media_id": media_id,
            "relative_path": relative, "bytes": image_path.stat().st_size,
            "sha256": digest, "product_id": product_id,
            "label_status": "gold_external_wine_id", "bbox_status": "not_required_single_label_image",
            "training_candidate": probe["decode_status"] == "ok", **probe,
        }
        media.append(media_row)
        hash_groups[digest].append(media_id)
        if is_russian:
            russian.append({
                **product, "media_id": media_id,
                "catalog_match_candidates": catalog_candidates(row, catalog),
                "catalog_match_status": "pending_visual_crosswalk_review",
            })

    for row in media:
        ids = hash_groups[row["sha256"]]
        row["exact_duplicate_group_id"] = stable_id("exact", row["sha256"]) if len(ids) > 1 else None
    unexpected_images = sorted(path.stem for path in IMAGE_ROOT.glob("*.jpeg") if path.stem not in {row["WineID"].strip() for row in source_rows})

    write_jsonl(TABLES / "slim_products.jsonl", products)
    write_jsonl(TABLES / "slim_media.jsonl", media)
    write_jsonl(TABLES / "slim_russian_products.jsonl", russian)
    summary = {
        "source_archive_sha256": "163b544f613e0bd11038cb3cd92d123f42ae99b62017e274a6cb401101e2aa16",
        "edition": "XWines_Slim_1K",
        "counts": {
            "products": len(products), "media": len(media), "russian_products": len(russian),
            "missing_images": len(missing), "unexpected_images": len(unexpected_images),
            "decode_errors": sum(row["decode_status"] != "ok" for row in media),
            "exact_duplicate_groups": sum(len(ids) > 1 for ids in hash_groups.values()),
        },
        "missing_image_ids": missing, "unexpected_image_ids": unexpected_images,
        "country_distribution": dict(Counter(row["country"] for row in products)),
        "gates": {
            "all_products_have_image_level_label": not missing and not unexpected_images,
            "all_images_decode": all(row["decode_status"] == "ok" for row in media),
            "russian_subset_present": bool(russian),
            "catalog_crosswalk_review_complete": False,
        },
    }
    write_json(TABLES / "SLIM-SUMMARY.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not missing and not unexpected_images and summary["gates"]["all_images_decode"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
