from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

from common import IMAGE_EXTENSIONS, image_probe, relative_posix, sha256_file, stable_id, write_json, write_jsonl


COLUMN_MAP = {
    "Название вина": "wine_name",
    "Категория": "category",
    "Цвет": "color",
    "Регион": "region",
    "Сорт винограда": "grapes",
    "Описание": "description",
    "Винодельня": "winery",
    "Slug": "slug",
    "Название фото": "photo_filename",
}
VARIANT_PREFIXES = ("thumbnail_", "small_", "medium_", "large_")
STRAPI_HASH_RE = re.compile(r"_[0-9a-f]{10}$", re.IGNORECASE)


def photo_key(filename: str | None) -> str | None:
    if not filename:
        return None
    stem = Path(filename.strip()).stem
    return re.sub(r"[^a-zA-Z0-9]", "", stem).lower() or None


def asset_parts(filename: str) -> tuple[str, str, str | None]:
    stem = Path(filename).stem
    variant = "original"
    for prefix in VARIANT_PREFIXES:
        if stem.lower().startswith(prefix):
            variant = prefix[:-1]
            stem = stem[len(prefix) :]
            break
    hash_match = STRAPI_HASH_RE.search(stem)
    strapi_hash = hash_match.group(0)[1:].lower() if hash_match else None
    logical_stem = STRAPI_HASH_RE.sub("", stem)
    normalized = re.sub(r"[^a-zA-Z0-9]", "", logical_stem).lower()
    return normalized, variant, strapi_hash


def cleaned_row(raw: dict[str, str], row_number: int) -> dict[str, object]:
    row: dict[str, object] = {"source_row": row_number}
    for source_name, target_name in COLUMN_MAP.items():
        value = (raw.get(source_name) or "").strip()
        row[target_name] = value or None
    row["photo_key"] = photo_key(row["photo_filename"] if isinstance(row["photo_filename"], str) else None)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse and audit the caseholder Svoe Vino archive extraction.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    dataset_root = project_root / "Dataset"
    dataset_dir = dataset_root / "01_svoe_vino_catalog"
    csv_path = dataset_dir / "cache" / "outer" / "Датасет" / "strapi_output0709.csv"
    extraction_root = dataset_dir / "media" / "source_extract"
    uploads_candidates = list(extraction_root.rglob("uploads"))
    if not csv_path.is_file():
        raise FileNotFoundError(csv_path)
    if len(uploads_candidates) != 1:
        raise RuntimeError(f"Expected one uploads directory, found {len(uploads_candidates)}")
    uploads_dir = uploads_candidates[0]
    tables_dir = dataset_dir / "tables"

    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        missing_columns = set(COLUMN_MAP) - set(reader.fieldnames or [])
        if missing_columns:
            raise RuntimeError(f"CSV misses columns: {sorted(missing_columns)}")
        catalog_rows = [cleaned_row(raw, index) for index, raw in enumerate(reader, start=2)]

    by_slug: dict[str, list[dict[str, object]]] = defaultdict(list)
    rows_without_slug: list[dict[str, object]] = []
    for row in catalog_rows:
        slug = row.get("slug")
        if isinstance(slug, str) and slug:
            by_slug[slug].append(row)
        else:
            rows_without_slug.append(row)

    products: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []
    key_to_products: dict[str, set[str]] = defaultdict(set)
    comparison_fields = tuple(COLUMN_MAP.values())

    for slug in sorted(by_slug):
        group = by_slug[slug]
        first = group[0]
        conflict_fields = [
            field
            for field in comparison_fields
            if len({row.get(field) for row in group}) > 1
        ]
        product_id = stable_id("product_svoe", slug)
        keys = sorted({str(row["photo_key"]) for row in group if row.get("photo_key")})
        product = {
            "manifest_version": "1.0.0",
            "source_id": "caseholder-svoe-vino-2026-09",
            "product_id": product_id,
            "slug": slug,
            "wine_name": first.get("wine_name"),
            "category": first.get("category"),
            "color": first.get("color"),
            "region": first.get("region"),
            "grapes": first.get("grapes"),
            "description": first.get("description"),
            "winery": first.get("winery"),
            "photo_filenames": sorted({str(row["photo_filename"]) for row in group if row.get("photo_filename")}),
            "photo_keys": keys,
            "source_rows": [int(row["source_row"]) for row in group],
            "duplicate_row_count": len(group),
            "quality_status": "conflict" if conflict_fields else "clean",
            "conflict_fields": conflict_fields,
        }
        products.append(product)
        for key in keys:
            key_to_products[key].add(product_id)
        if conflict_fields:
            conflicts.append(
                {
                    "product_id": product_id,
                    "slug": slug,
                    "conflict_fields": conflict_fields,
                    "source_rows": [int(row["source_row"]) for row in group],
                    "values": {field: sorted({str(row.get(field)) for row in group}) for field in conflict_fields},
                }
            )

    media_files = sorted(
        path for path in uploads_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    asset_meta: dict[Path, tuple[str, str, str | None]] = {path: asset_parts(path.name) for path in media_files}
    originals_by_key: dict[str, list[Path]] = defaultdict(list)
    for path, (key, variant, _) in asset_meta.items():
        if variant == "original":
            originals_by_key[key].append(path)

    media_records: list[dict[str, object]] = []
    media_id_by_path: dict[Path, str] = {}
    hash_to_media: dict[str, list[str]] = defaultdict(list)

    for index, path in enumerate(media_files, start=1):
        relative_path = relative_posix(path, dataset_root)
        media_id = stable_id("media_svoe", relative_path)
        media_id_by_path[path] = media_id
        key, variant, strapi_hash = asset_meta[path]
        digest = sha256_file(path)
        probe = image_probe(path, calculate_dhash=(variant == "original"))
        pixel_count = (
            int(probe["width"]) * int(probe["height"])
            if probe["width"] is not None and probe["height"] is not None
            else None
        )
        resource_status = "oversized_dimensions" if pixel_count and pixel_count > 50_000_000 else "ok"
        product_ids = sorted(key_to_products.get(key, set()))
        if len(product_ids) == 1:
            label_status = "gold_exact_asset_key"
            product_id = product_ids[0]
            bbox_status = "not_required_single_product_reference"
        elif len(product_ids) > 1:
            label_status = "ambiguous_shared_catalog_asset"
            product_id = None
            bbox_status = "not_required_label_conflict"
        else:
            label_status = "out_of_scope_site_media"
            product_id = None
            bbox_status = "not_applicable"
        parent_candidates = originals_by_key.get(key, []) if variant != "original" else []
        record = {
            "manifest_version": "1.0.0",
            "source_id": "caseholder-svoe-vino-2026-09",
            "media_id": media_id,
            "relative_path": relative_path,
            "filename": path.name,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "asset_group_id": stable_id("asset_svoe", key) if key else None,
            "asset_key": key or None,
            "strapi_hash": strapi_hash,
            "variant": variant,
            "parent_media_id": None,
            "parent_resolution_status": "pending" if variant != "original" else "not_applicable",
            "product_id": product_id,
            "product_candidates": product_ids,
            "association_grade": "gold" if label_status == "gold_exact_asset_key" else None,
            "label_status": label_status,
            "bbox_status": bbox_status,
            "training_candidate": bool(
                variant == "original" and product_id and probe["decode_status"] == "ok" and resource_status == "ok"
            ),
            "pixel_count": pixel_count,
            "resource_status": resource_status,
            "quarantine_reason": (
                "decode_error" if probe["decode_status"] != "ok" else
                ("oversized_dimensions" if resource_status != "ok" else None)
            ),
            **probe,
        }
        if variant != "original":
            if len(parent_candidates) == 1:
                record["parent_resolution_status"] = "resolved"
            elif len(parent_candidates) == 0:
                record["parent_resolution_status"] = "missing_original"
            else:
                record["parent_resolution_status"] = "ambiguous_original"
        media_records.append(record)
        hash_to_media[digest].append(media_id)
        if index % 1000 == 0:
            print(f"Audited {index}/{len(media_files)} images", flush=True)

    for path, record in zip(media_files, media_records):
        key, variant, _ = asset_meta[path]
        if variant != "original":
            candidates = originals_by_key.get(key, [])
            if len(candidates) == 1:
                record["parent_media_id"] = media_id_by_path[candidates[0]]
        duplicate_ids = hash_to_media[str(record["sha256"])]
        record["exact_duplicate_group_id"] = (
            stable_id("exact", str(record["sha256"])) if len(duplicate_ids) > 1 else None
        )

    product_by_id = {str(product["product_id"]): product for product in products}
    labeled_original_product_ids = {
        str(record["product_id"])
        for record in media_records
        if record["variant"] == "original" and record["label_status"] == "gold_exact_asset_key"
    }
    cross_product_duplicate_groups = 0
    for duplicate_media_ids in hash_to_media.values():
        product_ids = {
            str(record["product_id"])
            for record in media_records
            if record["media_id"] in duplicate_media_ids and record["product_id"]
        }
        if len(product_ids) > 1:
            cross_product_duplicate_groups += 1
    associations: list[dict[str, object]] = []
    for record in media_records:
        for product_id in record["product_candidates"]:
            associations.append(
                {
                    "association_id": stable_id("assoc", f"{record['media_id']}:{product_id}"),
                    "media_id": record["media_id"],
                    "product_id": product_id,
                    "slug": product_by_id[product_id]["slug"],
                    "grade": "gold" if len(record["product_candidates"]) == 1 else "bronze",
                    "method": "normalized_caseholder_photo_key_to_strapi_asset_key",
                    "eligible_for_supervised_training": len(record["product_candidates"]) == 1,
                }
            )

    eval_root = dataset_dir / "cache" / "eval_extract"
    eval_records: list[dict[str, object]] = []
    checksums: dict[str, str] = {}
    checksum_path = eval_root / "checksums.sha256"
    if checksum_path.is_file():
        for line in checksum_path.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                checksums[parts[1].replace("\\", "/")] = parts[0].lower()
    query_map: dict[str, str] = {}
    query_table = eval_root / "queries.tsv"
    if query_table.is_file():
        with query_table.open("r", encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream, delimiter="\t"):
                query_map[str(row["image_path"])] = str(row["query_id"])
    for image_name, query_id in sorted(query_map.items(), key=lambda item: item[1]):
        path = eval_root / "queries" / image_name
        digest = sha256_file(path)
        probe = image_probe(path, calculate_dhash=True)
        expected_digest = checksums.get(f"queries/{image_name}")
        eval_records.append(
            {
                "manifest_version": "1.0.0",
                "source_id": "caseholder-svoe-vino-2026-09",
                "media_id": stable_id("media_case_eval", query_id),
                "query_id": query_id,
                "relative_path": relative_posix(path, dataset_root),
                "bytes": path.stat().st_size,
                "sha256": digest,
                "checksum_status": "verified" if expected_digest == digest else "mismatch",
                "role": "caseholder_eval",
                "expected_slug": None,
                "label_status": "ground_truth_hidden_by_organizer",
                "bbox_status": "not_provided",
                "training_candidate": False,
                **probe,
            }
        )

    quarantine_records = [
        {
            "media_id": record["media_id"],
            "relative_path": record["relative_path"],
            "reason": record["quarantine_reason"],
            "action": "exclude_from_training_keep_source_extract_for_reproducibility",
        }
        for record in media_records
        if record["quarantine_reason"]
    ]

    output_counts = {
        "catalog_rows": write_jsonl(tables_dir / "catalog_rows.jsonl", catalog_rows),
        "products": write_jsonl(tables_dir / "products.jsonl", products),
        "product_conflicts": write_jsonl(tables_dir / "product_conflicts.jsonl", conflicts),
        "media": write_jsonl(tables_dir / "media.jsonl", media_records),
        "associations": write_jsonl(tables_dir / "associations.jsonl", associations),
        "caseholder_eval": write_jsonl(tables_dir / "caseholder_eval.jsonl", eval_records),
        "quarantine": write_jsonl(tables_dir / "quarantine.jsonl", quarantine_records),
    }

    summary = {
        "manifest_version": "1.0.0",
        "source_id": "caseholder-svoe-vino-2026-09",
        "inputs": {
            "catalog_csv": relative_posix(csv_path, dataset_root),
            "uploads": relative_posix(uploads_dir, dataset_root),
        },
        "counts": {
            **output_counts,
            "rows_without_slug": len(rows_without_slug),
            "products_clean": sum(product["quality_status"] == "clean" for product in products),
            "products_conflict": len(conflicts),
            "unique_photo_keys": len(key_to_products),
            "shared_photo_keys": sum(len(product_ids) > 1 for product_ids in key_to_products.values()),
            "images_decode_ok": sum(record["decode_status"] == "ok" for record in media_records),
            "images_decode_error": sum(record["decode_status"] != "ok" for record in media_records),
            "images_gold_labeled": sum(record["label_status"] == "gold_exact_asset_key" for record in media_records),
            "images_ambiguous": sum(record["label_status"] == "ambiguous_shared_catalog_asset" for record in media_records),
            "images_out_of_scope": sum(record["label_status"] == "out_of_scope_site_media" for record in media_records),
            "training_candidate_originals": sum(bool(record["training_candidate"]) for record in media_records),
            "products_with_gold_original": len(labeled_original_product_ids),
            "products_without_gold_original": len(products) - len(labeled_original_product_ids),
            "exact_duplicate_groups": sum(len(ids) > 1 for ids in hash_to_media.values()),
            "cross_product_exact_duplicate_groups": cross_product_duplicate_groups,
            "derivatives_missing_original": sum(record["parent_resolution_status"] == "missing_original" for record in media_records),
            "oversized_images": sum(record["resource_status"] != "ok" for record in media_records),
        },
        "distributions": {
            "variants": Counter(str(record["variant"]) for record in media_records),
            "formats": Counter(str(record["image_format"]) for record in media_records),
            "label_status": Counter(str(record["label_status"]) for record in media_records),
        },
        "gates": {
            "all_media_accounted_for": len(media_records) == len(media_files),
            "all_catalog_rows_accounted_for": len(catalog_rows) == 4147,
            "all_caseholder_eval_checksums_verified": bool(eval_records) and all(record["checksum_status"] == "verified" for record in eval_records),
            "split_ready": False,
            "split_blockers": [
                "manual review of shared photo keys",
                "near-duplicate graph across original assets",
                "training rights confirmation",
                "caseholder evaluation isolation manifest",
            ],
        },
    }
    write_json(tables_dir / "SUMMARY.json", summary)
    print(f"PASS: parsed {len(products)} products and audited {len(media_records)} images", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
