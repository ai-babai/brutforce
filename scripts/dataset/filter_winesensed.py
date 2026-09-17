#!/usr/bin/env python3
"""Extract and audit Russian rows from the local WineSensed Parquet snapshot."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

from common import image_probe, sha256_file, stable_id, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "Dataset/00_raw/08_winesensed"
SHARDS = RAW / "shards"
OUT = ROOT / "Dataset/08_winesensed"
TABLES = OUT / "tables"
MEDIA = OUT / "media/source_extract"
TREE = RAW / "hf_tree_root.json"
SNAPSHOT_SHA = "b6d1f4d0ed58184e2f3787a1720de2a207860681"
KNOWN_RUSSIAN_WINE_MARKERS = (
    "abrau", "aristov", "fanagor", "massandra", "inkerman", "tamagne",
    "golubitskoe", "vedernikov", "gai-kodzor", "gai kodzor", "gaï-kodzor",
    "alma valley", "sikory", "lefkadia", "divnomorskoe", "zolotaya balka",
    "kuban-vino", "kuban vino", "novy svet", "novyi svet",
)


def expected_shards() -> dict[str, int]:
    rows = json.loads(TREE.read_text(encoding="utf-8"))
    return {
        Path(row["path"]).name: int(row["size"])
        for row in rows
        if row.get("type") == "file" and row.get("path", "").startswith("data/wines/") and row["path"].endswith(".parquet")
    }


def as_jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): as_jsonable(v) for k, v in value.items() if k != "bytes"}
    if isinstance(value, (list, tuple)):
        return [as_jsonable(v) for v in value]
    return str(value)


def main() -> int:
    TABLES.mkdir(parents=True, exist_ok=True)
    MEDIA.mkdir(parents=True, exist_ok=True)
    expected = expected_shards()
    actual = {path.name: path.stat().st_size for path in SHARDS.glob("*.parquet")}
    missing = sorted(name for name in expected if name not in actual)
    incomplete = sorted(name for name, size in expected.items() if actual.get(name) != size)
    if missing or incomplete:
        summary = {
            "manifest_version": "1.0.0",
            "source_id": "winesensed",
            "upstream_snapshot_sha": SNAPSHOT_SHA,
            "counts": {"expected_shards": len(expected), "present_shards": len(actual), "complete_shards": len(expected) - len(incomplete)},
            "missing_shards": missing,
            "incomplete_shards": incomplete,
            "gates": {"raw_snapshot_complete": False, "russian_filter_complete": False, "images_audited": False},
        }
        write_json(TABLES / "SUMMARY.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    glob_path = str((SHARDS / "*.parquet").resolve()).replace("\\", "/")
    connection = duckdb.connect()
    schema_rows = connection.execute("DESCRIBE SELECT * FROM read_parquet(?)", [glob_path]).fetchall()
    schema = [{"name": row[0], "type": row[1], "nullable": row[2]} for row in schema_rows]
    write_json(TABLES / "source_schema.json", {"source_glob": glob_path, "columns": schema})

    columns = {row[0] for row in schema_rows}
    if not {"image", "wine", "country", "region"}.issubset(columns):
        raise RuntimeError(f"unexpected WineSensed schema: {sorted(columns)}")

    total_rows = connection.execute("SELECT count(*) FROM read_parquet(?)", [glob_path]).fetchone()[0]
    geographic_predicate = """
        lower(coalesce(country, '')) IN ('russia', 'russian federation')
        OR lower(coalesce(country, '')) LIKE '%russia%'
        OR lower(coalesce(region, '')) LIKE '%crimea%'
        OR lower(coalesce(region, '')) LIKE '%krasnodar%'
        OR lower(coalesce(region, '')) LIKE '%kuban%'
        OR lower(coalesce(region, '')) LIKE '%rostov%'
        OR lower(coalesce(region, '')) LIKE '%dagestan%'
        OR lower(coalesce(region, '')) LIKE '%taman%'
    """
    brand_predicate = " OR ".join(f"lower(coalesce(wine, '')) LIKE '%{marker}%'" for marker in KNOWN_RUSSIAN_WINE_MARKERS)
    predicate = f"({geographic_predicate}) OR ({brand_predicate})"
    projection = [name for name in (
        "wine", "year", "wine_alcohol", "country", "region", "price", "rating", "grape",
        "vintage_id", "vintage_page_url", "experiment_id", "winery_id", "image",
    ) if name in columns]
    matched_rows = connection.execute(f"SELECT count(*) FROM read_parquet(?) WHERE {predicate}", [glob_path]).fetchone()[0]
    cursor = connection.execute(
        f"""
        SELECT {', '.join(projection)}
        FROM read_parquet(?)
        WHERE {predicate}
        QUALIFY row_number() OVER (
            PARTITION BY coalesce(cast(vintage_id AS varchar), vintage_page_url, concat(wine, '|', cast(year AS varchar)))
            ORDER BY rating DESC NULLS LAST
        ) = 1
        """,
        [glob_path],
    )
    names = [item[0] for item in cursor.description]
    rows = cursor.fetchall()

    products = []
    media_rows = []
    associations = []
    for index, values in enumerate(rows):
        row = dict(zip(names, values))
        image_value = row.pop("image", None)
        vintage_key = str(row.get("vintage_id") or row.get("vintage_page_url") or f"row-{index}")
        product_id = stable_id("product_winesensed", vintage_key)
        product = {"product_id": product_id, **{key: as_jsonable(value) for key, value in row.items()}}
        geographic_text = f"{row.get('country') or ''} {row.get('region') or ''}".casefold()
        explicit_geo = any(marker in geographic_text for marker in ("russia", "russian federation", "crimea", "krasnodar", "kuban", "rostov", "dagestan", "taman"))
        product["russian_wine_status"] = "gold_explicit_winesensed_country_or_region" if explicit_geo else "silver_known_russian_brand_name"
        products.append(product)

        image_bytes = None
        source_path = None
        if isinstance(image_value, dict):
            image_bytes = image_value.get("bytes")
            source_path = image_value.get("path")
        elif isinstance(image_value, (bytes, bytearray, memoryview)):
            image_bytes = bytes(image_value)
        extension = Path(str(source_path or "image.jpg")).suffix.lower() or ".jpg"
        destination = MEDIA / f"{product_id}{extension}"
        if image_bytes:
            temporary = destination.with_suffix(destination.suffix + ".part")
            temporary.write_bytes(bytes(image_bytes))
            temporary.replace(destination)
        media_id = stable_id("media_winesensed", vintage_key)
        probe = image_probe(destination, calculate_dhash=True) if destination.is_file() else {
            "decode_status": "missing_embedded_bytes", "decode_error": "image struct has no bytes",
            "image_format": None, "width": None, "height": None, "mode": None, "dhash64": None,
        }
        media_rows.append({
            "media_id": media_id,
            "product_id": product_id,
            "relative_path": destination.relative_to(ROOT).as_posix(),
            "embedded_source_path": source_path,
            "bytes": destination.stat().st_size if destination.is_file() else None,
            "sha256": sha256_file(destination) if destination.is_file() else None,
            **probe,
        })
        associations.append({
            "association_id": stable_id("assoc_winesensed", vintage_key),
            "media_id": media_id,
            "product_id": product_id,
            "grade": "gold",
            "method": "same_winesensed_record",
            "eligible_for_supervised_sku_training": probe["decode_status"] == "ok" and explicit_geo,
            "bbox_status": "not_applicable_single_product_source_image",
        })

    write_jsonl(TABLES / "russian_products.jsonl", products)
    write_jsonl(TABLES / "media.jsonl", media_rows)
    write_jsonl(TABLES / "associations.jsonl", associations)
    duplicates = defaultdict(list)
    for item in media_rows:
        if item.get("sha256"):
            duplicates[item["sha256"]].append(item["media_id"])
    country_counts = Counter(str(row.get("country") or "") for row in products)
    summary = {
        "manifest_version": "1.0.0",
        "source_id": "winesensed",
        "upstream_snapshot_sha": SNAPSHOT_SHA,
        "license": "CC BY-NC-ND 4.0",
        "counts": {
            "expected_shards": len(expected), "complete_shards": len(expected), "source_rows": total_rows,
            "russian_candidate_source_rows": matched_rows,
            "russian_candidate_unique_vintages": len(products),
            "explicit_russian_geography_vintages": sum(row["russian_wine_status"].startswith("gold_") for row in products),
            "known_russian_brand_only_vintages": sum(row["russian_wine_status"].startswith("silver_") for row in products),
            "decoded_images": sum(item["decode_status"] == "ok" for item in media_rows),
            "image_errors": sum(item["decode_status"] != "ok" for item in media_rows),
            "exact_duplicate_groups": sum(len(group) > 1 for group in duplicates.values()),
        },
        "country_distribution": dict(country_counts),
        "gates": {
            "raw_snapshot_complete": True,
            "russian_filter_complete": True,
            "images_audited": all(item["decode_status"] == "ok" for item in media_rows),
            "license_restricted_noncommercial_only": True,
            "cross_source_sku_identity_verified": False,
        },
    }
    write_json(TABLES / "SUMMARY.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["counts"]["image_errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
