from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from common import image_probe, relative_posix, sha256_file, stable_id, write_json, write_jsonl


REVIEWED_CROSSWALK = {
    195476: {
        "catalog_match_status": "silver_same_product_line_different_vintage",
        "catalog_product_id": "product_svoe_f6183bdec01653f0619f",
        "catalog_slug": "kuban-vino-aristov-kyuve-aleksandr-rose-de-pinot-pino-nuar-rozovoe-ekstra-bryut-12",
        "review_evidence": "visual label review: same Aristov Cuvée Alexander Rose de Pinot Extra Brut line; X-Wines label is 2017 and Svoe reference is 2020",
    },
    196718: {
        "catalog_match_status": "verified_no_exact_svoe_match",
        "catalog_product_id": None,
        "catalog_slug": None,
        "review_evidence": "visual label review: X-Wines is Select Rosé Brut; Svoe candidates are Select Blanc and are not the same wine",
    },
}


def parse_list(value: str) -> list[object]:
    try:
        parsed = ast.literal_eval(value)
        return parsed if isinstance(parsed, list) else [parsed]
    except (ValueError, SyntaxError):
        return [value] if value else []


def normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-zа-яё0-9]+", value.lower().replace("ё", "е")))


def load_svoe_products(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def catalog_candidates(row: dict[str, str], products: list[dict[str, object]]) -> list[dict[str, object]]:
    winery = normalize(row.get("WineryName", ""))
    wine_name = normalize(row.get("WineName", ""))
    x_tokens = set((winery + " " + wine_name).split())
    aliases = {
        "aristov": {"аристов", "aristov"},
        "chateau tamagne": {"шато тамань", "кубань вино", "chateau tamagne"},
    }
    expected_winery_aliases = aliases.get(winery, {winery})
    candidates: list[dict[str, object]] = []
    for product in products:
        candidate_winery = normalize(str(product.get("winery") or ""))
        candidate_name = normalize(str(product.get("wine_name") or ""))
        winery_match = any(alias and alias in candidate_winery for alias in expected_winery_aliases)
        name_tokens = {token for token in candidate_name.split() if len(token) >= 4}
        overlap = x_tokens & name_tokens
        if winery_match or len(overlap) >= 2:
            score = (0.65 if winery_match else 0.0) + min(0.3, len(overlap) * 0.1)
            candidates.append(
                {
                    "product_id": product.get("product_id"),
                    "slug": product.get("slug"),
                    "score": round(score, 3),
                    "winery_match": winery_match,
                    "name_token_overlap": sorted(overlap),
                }
            )
    candidates.sort(key=lambda item: (-float(item["score"]), str(item["slug"])))
    return candidates[:20]


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse X-Wines test edition and isolate Russian wines.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    dataset_root = project_root / "Dataset"
    raw_repo = dataset_root / "00_raw" / "07_x_wines" / "X-Wines"
    csv_path = raw_repo / "Dataset" / "last" / "XWines_Test_100_wines.csv"
    image_root = dataset_root / "07_x_wines" / "media" / "source_extract" / "XWines_Test_100_labels"
    output_dir = dataset_root / "07_x_wines" / "tables"
    if not csv_path.is_file() or not image_root.is_dir():
        raise FileNotFoundError("X-Wines inputs are incomplete")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        source_rows = list(csv.DictReader(stream))
    svoe_products = load_svoe_products(dataset_root / "01_svoe_vino_catalog" / "tables" / "products.jsonl")

    products: list[dict[str, object]] = []
    media: list[dict[str, object]] = []
    russian_products: list[dict[str, object]] = []
    missing_images: list[str] = []
    hash_to_media: dict[str, list[str]] = defaultdict(list)
    for row in source_rows:
        wine_id = row["WineID"].strip()
        product_id = f"product_xwines_{wine_id}"
        image_path = image_root / f"{wine_id}.jpeg"
        record = {
            "manifest_version": "1.0.0",
            "source_id": "x-wines",
            "edition": "XWines_Test_100",
            "product_id": product_id,
            "external_wine_id": int(wine_id),
            "wine_name": row.get("WineName") or None,
            "type": row.get("Type") or None,
            "grapes": parse_list(row.get("Grapes", "")),
            "abv": float(row["ABV"]) if row.get("ABV") else None,
            "country_code": row.get("Code") or None,
            "country": row.get("Country") or None,
            "region": row.get("RegionName") or None,
            "winery": row.get("WineryName") or None,
            "website": row.get("Website") or None,
            "vintages": parse_list(row.get("Vintages", "")),
            "is_russian": (row.get("Code") or "").upper() == "RU" or (row.get("Country") or "").lower() == "russia",
        }
        products.append(record)
        if not image_path.is_file():
            missing_images.append(wine_id)
            continue
        relative = relative_posix(image_path, dataset_root)
        media_id = stable_id("media_xwines", relative)
        digest = sha256_file(image_path)
        probe = image_probe(image_path, calculate_dhash=True)
        media_record = {
            "manifest_version": "1.0.0",
            "source_id": "x-wines",
            "edition": "XWines_Test_100_labels",
            "media_id": media_id,
            "relative_path": relative,
            "bytes": image_path.stat().st_size,
            "sha256": digest,
            "product_id": product_id,
            "label_status": "gold_external_wine_id",
            "bbox_status": "not_required_single_label_image",
            "training_candidate": probe["decode_status"] == "ok",
            **probe,
        }
        media.append(media_record)
        hash_to_media[digest].append(media_id)
        if record["is_russian"]:
            review = REVIEWED_CROSSWALK.get(int(wine_id), {
                "catalog_match_status": "pending_manual_verification",
                "catalog_product_id": None,
                "catalog_slug": None,
                "review_evidence": None,
            })
            russian_products.append(
                {
                    **record,
                    "media_id": media_id,
                    "catalog_match_candidates": catalog_candidates(row, svoe_products),
                    **review,
                }
            )

    for record in media:
        ids = hash_to_media[str(record["sha256"])]
        record["exact_duplicate_group_id"] = stable_id("exact", str(record["sha256"])) if len(ids) > 1 else None

    counts = {
        "products": write_jsonl(output_dir / "products.jsonl", products),
        "media": write_jsonl(output_dir / "media.jsonl", media),
        "russian_products": write_jsonl(output_dir / "russian_products.jsonl", russian_products),
    }
    summary = {
        "source_commit": "5e43c7f38ff4abaee1815f84dbdd2b54aa873b1d",
        "edition": "XWines_Test_100",
        "counts": {
            **counts,
            "missing_images": len(missing_images),
            "decode_errors": sum(record["decode_status"] != "ok" for record in media),
            "russian_images": len(russian_products),
            "russian_crosswalk_matches": sum(item["catalog_product_id"] is not None for item in russian_products),
            "russian_crosswalk_reviewed": sum(item["catalog_match_status"] != "pending_manual_verification" for item in russian_products),
            "exact_duplicate_groups": sum(len(ids) > 1 for ids in hash_to_media.values()),
        },
        "missing_image_ids": missing_images,
        "gates": {
            "all_products_have_image_level_label": not missing_images,
            "all_images_decode": not any(record["decode_status"] != "ok" for record in media),
            "russian_subset_present": bool(russian_products),
            "catalog_crosswalk_review_complete": all(item["catalog_match_status"] != "pending_manual_verification" for item in russian_products),
        },
    }
    write_json(output_dir / "SUMMARY.json", summary)
    print(f"PASS: parsed {len(products)} wines, including {len(russian_products)} Russian wines", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
