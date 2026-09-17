#!/usr/bin/env python3
"""Filter the official Open Food Facts Parquet snapshot for Russian-wine candidates.

Only metadata columns are read from the remote columnar file.  Image files are
downloaded in a separate, auditable step after candidate confidence is assigned.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

import duckdb

from common import stable_id, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT / "Dataset/10_open_food_facts_wine_ru/tables"
REMOTE = "https://huggingface.co/datasets/openfoodfacts/product-database/resolve/main/food.parquet?download=true"
LOCAL = ROOT / "Dataset/00_raw/10_open_food_facts_wine_ru/food.parquet"
WINE_TAGS = (
    "en:wines", "en:red-wines", "en:white-wines", "en:rose-wines",
    "en:sparkling-wines", "en:sweet-wines", "en:fortified-wines",
)

KNOWN_RUSSIAN_BRAND_MARKERS = (
    "château tamagne", "chateau tamagne", "голубиц", "golubits",
    "зори тамани", "букет кубани", "кадряночка", "каспийская коллекция",
    "кубанская винная компания",
)
FOREIGN_MARKERS = (
    "france", "франц", "spain", "испан", "italy", "итал",
    "chile", "чили", "argentina", "аргент", "south-africa", "юар",
    "portugal", "португал", "germany", "герман", "australia", "австрал",
    "new-zealand", "новая зеланд", "georgia", "грузи", "armenia", "армени",
)
OBVIOUS_NON_WINE_MARKERS = (
    "томат", "бамидор", "стихи и сказки", "machaon",
    "гараж", "garage", "hard drink",
)


def texts(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                result.extend(str(v) for v in item.values() if v is not None)
            elif item is not None:
                result.append(str(item))
        return result
    return [str(value)]


def classify_candidate(row: dict) -> tuple[str, list[str]]:
    """Assign a conservative Russian-wine status without treating EAN as origin proof."""
    searchable_fields = (
        row.get("product_name"), row.get("brands"), row.get("brands_tags"),
        row.get("origins"), row.get("origins_tags"), row.get("manufacturing_places"),
        row.get("manufacturing_places_tags"), row.get("categories"), row.get("categories_tags"),
    )
    combined = " ".join(text for field in searchable_fields for text in texts(field)).casefold()
    reasons = []

    if any(marker in combined for marker in OBVIOUS_NON_WINE_MARKERS):
        return "rejected_obvious_category_error", ["metadata describes an obvious non-wine item"]

    explicit_russian = contains_russia(row.get("origins_tags")) or contains_russia(row.get("manufacturing_places_tags"))
    explicit_foreign = any(marker in combined for marker in FOREIGN_MARKERS)
    russian_brand = any(marker in combined for marker in KNOWN_RUSSIAN_BRAND_MARKERS)
    gs1_russia_prefix = str(row.get("code") or "").startswith("46")
    has_cyrillic = bool(re.search(r"[А-Яа-яЁё]", combined))

    if explicit_foreign and not explicit_russian:
        return "rejected_explicit_foreign_origin", ["foreign origin/manufacturing/category marker"]
    if explicit_russian:
        reasons.append("explicit Russia origin/manufacturing tag")
        return "silver_explicit_russian_origin", reasons
    if russian_brand and gs1_russia_prefix:
        reasons.extend(["known Russian producer/brand marker", "GS1 company prefix 46"])
        return "silver_russian_brand_candidate", reasons
    if gs1_russia_prefix and has_cyrillic:
        reasons.extend(["GS1 company prefix 46", "Cyrillic product/brand metadata", "no explicit foreign marker"])
        return "bronze_probable_russian_needs_review", reasons
    return "bronze_sold_in_russia_only", ["country-of-sale Russia only"]


def as_jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): as_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_jsonable(v) for v in value]
    return str(value)


def contains_russia(values) -> bool:
    return any("russia" in str(value).casefold() or "росси" in str(value).casefold() for value in (values or []))


def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    source = str(LOCAL) if LOCAL.is_file() else REMOTE
    if source == REMOTE:
        connection.execute("INSTALL httpfs")
        connection.execute("LOAD httpfs")
        connection.execute("SET http_timeout=300000")
        connection.execute("SET http_retries=5")

    schema_rows = connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [source]).fetchall()
    schema = [{"name": row[0], "type": row[1], "nullable": row[2]} for row in schema_rows]
    write_json(TABLES / "source_schema.json", {"source": source, "columns": schema})

    wine_predicate = " OR ".join(f"list_contains(categories_tags, '{tag}')" for tag in WINE_TAGS)
    russian_predicate = " OR ".join((
        "list_contains(origins_tags, 'en:russia')",
        "list_contains(origins_tags, 'ru:rossiya')",
        "list_contains(manufacturing_places_tags, 'en:russia')",
        "list_contains(manufacturing_places_tags, 'ru:rossiya')",
        "list_contains(countries_tags, 'en:russia')",
        "list_contains(countries_tags, 'ru:rossiya')",
    ))
    query = f"""
        SELECT code, product_name, brands, brands_tags, categories, categories_tags,
               origins, origins_tags, manufacturing_places, manufacturing_places_tags,
               countries_tags, images, last_modified_t
        FROM read_parquet(?)
        WHERE ({wine_predicate}) AND ({russian_predicate})
    """
    cursor = connection.execute(query, [source])
    columns = [item[0] for item in cursor.description]
    rows = []
    for values in cursor.fetchall():
        raw = {key: as_jsonable(value) for key, value in zip(columns, values)}
        origin_evidence = contains_russia(raw.get("origins_tags"))
        manufacturing_evidence = contains_russia(raw.get("manufacturing_places_tags"))
        sale_country_evidence = contains_russia(raw.get("countries_tags"))
        confidence, confidence_reasons = classify_candidate(raw)
        raw.update({
            "product_id": stable_id("product_off", str(raw.get("code") or len(rows))),
            "russian_evidence": {
                "origin": origin_evidence,
                "manufacturing_place": manufacturing_evidence,
                "country_of_sale": sale_country_evidence,
            },
            "russian_wine_status": confidence,
            "russian_wine_status_reasons": confidence_reasons,
            "sku_label_status": "metadata_candidate_unverified",
        })
        rows.append(raw)
    rows.sort(key=lambda row: str(row.get("code") or ""))
    write_jsonl(TABLES / "candidates.jsonl", rows)

    confidence_counts = Counter(row["russian_wine_status"] for row in rows)
    image_key_count = 0
    for row in rows:
        image_key_count += len(row.get("images") or [])
    summary = {
        "manifest_version": "1.0.0",
        "source_id": "open-food-facts-product-database",
        "upstream_snapshot_sha": "cb3a359d7064c1ec535faa58ee1ea965c61a345c",
        "counts": {
            "candidate_products": len(rows),
            "strong_russian_origin_or_manufacturing": confidence_counts["silver_explicit_russian_origin"],
            "russian_brand_candidates": confidence_counts["silver_russian_brand_candidate"],
            "probable_russian_needs_review": confidence_counts["bronze_probable_russian_needs_review"],
            "sold_in_russia_only_needs_review": confidence_counts["bronze_sold_in_russia_only"],
            "rejected_explicit_foreign_origin": confidence_counts["rejected_explicit_foreign_origin"],
            "rejected_obvious_category_error": confidence_counts["rejected_obvious_category_error"],
            "embedded_image_metadata_records": image_key_count,
        },
        "method": {
            "wine_filter": list(WINE_TAGS),
            "russian_filter": "origins/manufacturing_places/country-of-sale tags",
            "important_caveat": "country-of-sale Russia does not prove Russian production",
        },
        "gates": {
            "metadata_filter_complete": True,
            "all_candidates_are_verified_russian_wines": False,
            "images_downloaded_and_audited": False,
        },
    }
    write_json(TABLES / "SUMMARY.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
