#!/usr/bin/env python3
"""Build the deterministic Russian-wine open-world master index.

The builder is an aggregation layer, not an identity resolver.  Every upstream
catalog product remains a separate master product/member record.  Matching
normalized producer/brand/title signatures only create provisional family
candidates and review tasks.  Images are referenced by their upstream paths;
no media bytes are copied into Dataset/18_russian_wine_master.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from common import sha256_file, stable_id, write_json, write_jsonl


SCRIPT_VERSION = "1.0.0"
MANIFEST_VERSION = "1.0.0"
DATASET_VERSION = "2026-09-15.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "Dataset" / "18_russian_wine_master"

CYRILLIC = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
        "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k",
        "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
        "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya",
    }
)

TOKEN_ALIASES = {
    "kaberne": "cabernet",
    "sovinion": "sauvignon",
    "sovinon": "sauvignon",
    "shardone": "chardonnay",
    "risling": "riesling",
    "rkatsiteli": "rkaciteli",
    "pino": "pinot",
    "nuar": "noir",
    "roze": "rose",
    "kyuve": "cuvee",
    "shato": "chateau",
    "usadba": "estate",
    "vinodelnya": "winery",
}

GENERIC_TITLE_TOKENS = {
    "vino", "wine", "tihoe", "tikhoye", "quiet", "igristoe", "sparkling",
    "krasnoe", "red", "beloe", "white", "rozovoe", "rose", "orange",
    "suhoe", "dry", "polusuhoe", "semidry", "polusladkoe", "semisweet",
    "sladkoe", "sweet", "brut", "ekstra", "extra", "napitok", "rossiya",
    "russia", "alkogolnyi", "vinnyi", "vinnyy",
}

SELECTED_OFF_STATUSES = {
    "silver_russian_brand_candidate",
    "bronze_probable_russian_needs_review",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed JSONL {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected object in {path}:{line_number}")
            rows.append(value)
    return rows


def jsonl_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8-sig") as stream:
        return sum(1 for line in stream if line.strip())


def source_fingerprint(path: Path) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(PROJECT_ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "rows": jsonl_count(path) if path.suffix == ".jsonl" else None,
        "sha256": sha256_file(path),
    }


def values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(values(item))
        return result
    if isinstance(value, dict):
        for key in ("name", "text", "value", "title"):
            if key in value:
                return values(value[key])
    return []


def unique_strings(value: Any) -> list[str]:
    return sorted(set(values(value)), key=lambda item: item.casefold())


def first_text(*candidates: Any) -> str | None:
    for candidate in candidates:
        items = values(candidate)
        if items:
            return items[0]
    return None


def localized_product_name(value: Any) -> str | None:
    if isinstance(value, list):
        preferred = {"ru": 0, "main": 1, "en": 2}
        candidates = []
        for index, item in enumerate(value):
            if isinstance(item, dict) and item.get("text"):
                candidates.append((preferred.get(str(item.get("lang")), 9), index, str(item["text"])))
        if candidates:
            return sorted(candidates)[0][2]
    return first_text(value)


def transliterate(value: str) -> str:
    value = unicodedata.normalize("NFKD", html.unescape(value).casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return value.translate(CYRILLIC)


def normalized_tokens(value: str | None, *, family_title: bool = False) -> list[str]:
    if not value:
        return []
    text = transliterate(re.sub(r"<[^>]+>", " ", value))
    text = re.sub(r"\b(?:19|20)\d{2}\b", " ", text)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:ml|мл|l|л)\b", " ", text)
    tokens = re.findall(r"[a-z0-9]+", text)
    normalized = [TOKEN_ALIASES.get(token, token) for token in tokens]
    if family_title:
        normalized = [token for token in normalized if token not in GENERIC_TITLE_TOKENS]
    return normalized


def normalize_text(value: str | None, *, family_title: bool = False) -> str | None:
    tokens = normalized_tokens(value, family_title=family_title)
    return " ".join(tokens) or None


def normalize_entities(value: Any) -> list[str]:
    return sorted({item for raw in values(value) if (item := normalize_text(raw))})


def extract_vintages(*items: Any) -> list[int]:
    years: set[int] = set()
    for item in items:
        if isinstance(item, (int, float)) and 1900 <= int(item) <= 2100:
            years.add(int(item))
            continue
        for text in values(item):
            years.update(int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", text))
    return sorted(years)


def maybe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:[.,]\d+)?", str(value))
    return float(match.group(0).replace(",", ".")) if match else None


def dict_field(mapping: Any, names: Iterable[str]) -> Any:
    if not isinstance(mapping, dict):
        return None
    folded = {str(key).casefold(): value for key, value in mapping.items()}
    for name in names:
        if name.casefold() in folded:
            return folded[name.casefold()]
    return None


def canonical_relative_path(row: dict[str, Any]) -> str | None:
    result = first_text(row.get("relative_path"), row.get("raw_path"))
    if result:
        return result.replace("\\", "/")
    return None


def referenced_media_path_exists(relative_path: str | None) -> bool:
    if not relative_path:
        return False
    candidate = Path(relative_path)
    if candidate.is_absolute():
        return False
    return (PROJECT_ROOT / candidate).is_file() or (PROJECT_ROOT / "Dataset" / candidate).is_file()


class MasterBuilder:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.products: list[dict[str, Any]] = []
        self.memberships: list[dict[str, Any]] = []
        self.media: dict[str, dict[str, Any]] = {}
        self.associations: list[dict[str, Any]] = []
        self.review: dict[str, dict[str, Any]] = {}
        self.product_lookup: dict[tuple[str, str], str] = {}
        self.media_lookup: dict[tuple[str, str], str] = {}
        self.media_global_lookup: dict[str, list[str]] = defaultdict(list)
        self.sources: dict[str, dict[str, Any]] = {}
        self.input_files: dict[str, dict[str, Any]] = {}

    def register_source(self, dataset: str, files: Iterable[Path]) -> None:
        paths = list(files)
        present = [path for path in paths if path.is_file()]
        self.sources.setdefault(
            dataset,
            {
                "status": "available" if present else "temporarily_unavailable",
                "expected_files": [path.relative_to(PROJECT_ROOT).as_posix() for path in paths],
                "present_files": [path.relative_to(PROJECT_ROOT).as_posix() for path in present],
            },
        )
        for path in present:
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            self.input_files[relative] = source_fingerprint(path)

    def add_product(
        self,
        *,
        source_dataset: str,
        source_id: str,
        source_capture_id: str | None,
        source_product_id: Any,
        catalog_id: str,
        external_product_id: Any,
        title: Any,
        producer: Any = None,
        brand: Any = None,
        country: Any = None,
        region: Any = None,
        vintage: Any = None,
        reported_vintages: Any = None,
        volume_l: Any = None,
        color: Any = None,
        sugar: Any = None,
        grapes: Any = None,
        source_family_id: Any = None,
        source_variant_id: Any = None,
        source_design_id: Any = None,
        source_url: Any = None,
        russian_origin_status: str,
        russian_origin_evidence: Any,
        rights_status: str,
        quality_status: str,
        exact_current_svoe_slug: str | None = None,
        exact_current_svoe_slug_evidence: Any = None,
        source_linked_product_id: Any = None,
    ) -> str:
        source_product_id = str(source_product_id)
        lookup_key = (source_dataset, source_product_id)
        if lookup_key in self.product_lookup:
            raise ValueError(f"Duplicate source product key: {lookup_key}")
        master_product_id = stable_id("master_product", f"{source_dataset}|{source_product_id}")
        producer_values = unique_strings(producer)
        brand_values = unique_strings(brand)
        title_text = first_text(title) or source_product_id
        producer_norm = normalize_entities(producer_values)
        brand_norm = normalize_entities(brand_values)
        title_norm = normalize_text(title_text)
        title_family_tokens = normalized_tokens(title_text, family_title=True)
        entity_tokens: set[str] = set()
        for entity in producer_norm + brand_norm:
            entity_tokens.update(entity.split())
        stripped = [token for token in title_family_tokens if token not in entity_tokens]
        title_family_norm = " ".join(stripped or title_family_tokens) or title_norm
        vintages = extract_vintages(vintage, reported_vintages, title_text)
        record = {
            "manifest_version": MANIFEST_VERSION,
            "dataset_version": DATASET_VERSION,
            "master_product_id": master_product_id,
            "source_dataset": source_dataset,
            "source_id": source_id,
            "source_capture_id": source_capture_id,
            "source_product_id": source_product_id,
            "source_linked_product_id": None if source_linked_product_id is None else str(source_linked_product_id),
            "catalog_id": catalog_id,
            "external_product_id": None if external_product_id is None else str(external_product_id),
            "title": title_text,
            "producer": producer_values,
            "brand": brand_values,
            "country": first_text(country),
            "region": unique_strings(region),
            "vintage": vintages[0] if len(vintages) == 1 else None,
            "reported_vintages": vintages,
            "volume_l": maybe_float(volume_l),
            "color": unique_strings(color),
            "sugar": unique_strings(sugar),
            "grapes": unique_strings(grapes),
            "source_wine_family_id": first_text(source_family_id),
            "source_bottle_variant_id": first_text(source_variant_id),
            "source_label_design_id": first_text(source_design_id),
            "normalized_identity": {
                "producer": producer_norm,
                "brand": brand_norm,
                "title": title_norm,
                "family_title": title_family_norm,
            },
            "provisional_family_candidate_id": None,
            "identity_status": "source_product_separate_no_cross_source_merge",
            "russian_origin_status": russian_origin_status,
            "russian_origin_evidence": russian_origin_evidence,
            "exact_current_svoe_slug": exact_current_svoe_slug,
            "exact_current_svoe_slug_evidence": exact_current_svoe_slug_evidence,
            "source_url": first_text(source_url),
            "rights_status": rights_status,
            "quality_status": quality_status,
        }
        self.products.append(record)
        self.product_lookup[lookup_key] = master_product_id
        return master_product_id

    def add_membership(
        self,
        *,
        source_dataset: str,
        source_product_id: Any,
        catalog_id: str,
        snapshot_id: Any,
        external_product_id: Any,
        source_url: Any = None,
        membership_status: str = "listed",
        exact_current_svoe_slug: str | None = None,
        exact_current_svoe_slug_verified: bool = False,
        upstream_membership_id: Any = None,
    ) -> str:
        master_product_id = self.product_lookup[(source_dataset, str(source_product_id))]
        material = f"{source_dataset}|{snapshot_id}|{external_product_id}|{source_product_id}"
        membership_id = stable_id("master_membership", material)
        self.memberships.append(
            {
                "manifest_version": MANIFEST_VERSION,
                "dataset_version": DATASET_VERSION,
                "master_catalog_membership_id": membership_id,
                "master_product_id": master_product_id,
                "source_dataset": source_dataset,
                "catalog_id": catalog_id,
                "snapshot_id": None if snapshot_id is None else str(snapshot_id),
                "external_product_id": None if external_product_id is None else str(external_product_id),
                "source_url": first_text(source_url),
                "membership_status": membership_status,
                "exact_current_svoe_slug": exact_current_svoe_slug if exact_current_svoe_slug_verified else None,
                "exact_current_svoe_slug_verified": bool(exact_current_svoe_slug_verified),
                "upstream_membership_id": first_text(upstream_membership_id),
            }
        )
        return membership_id

    def add_media(self, *, source_dataset: str, row: dict[str, Any]) -> str:
        source_media_id = str(row.get("media_id") or stable_id("source_media", json.dumps(row, sort_keys=True)))
        lookup_key = (source_dataset, source_media_id)
        existing = self.media_lookup.get(lookup_key)
        if existing:
            return existing
        master_media_id = stable_id("master_media", f"{source_dataset}|{source_media_id}")
        path = canonical_relative_path(row)
        media_record = {
            "manifest_version": MANIFEST_VERSION,
            "dataset_version": DATASET_VERSION,
            "master_media_id": master_media_id,
            "source_dataset": source_dataset,
            "source_id": first_text(row.get("source_id")),
            "source_capture_id": first_text(row.get("source_capture_id")),
            "source_media_id": source_media_id,
            "relative_path": path,
            "source_url": first_text(row.get("source_url")),
            "sha256": first_text(row.get("sha256")),
            "bytes": row.get("bytes"),
            "media_type": first_text(row.get("media_type"), row.get("image_format")),
            "width": row.get("width"),
            "height": row.get("height"),
            "decode_status": first_text(row.get("decode_status")) or ("ok" if row.get("decode_ok") is True else None),
            "dhash64": first_text(row.get("dhash64")),
            "source_label_design_id": first_text(row.get("label_design_id")),
            "source_bottle_variant_id": first_text(row.get("bottle_variant_id")),
            "rights_status": first_text(row.get("rights_status")),
            "quality_status": first_text(row.get("quality_status")),
            "media_storage": "upstream_reference_no_copy",
        }
        self.media[master_media_id] = media_record
        self.media_lookup[lookup_key] = master_media_id
        self.media_global_lookup[source_media_id].append(master_media_id)
        return master_media_id

    def resolve_media(self, source_dataset: str, source_media_id: Any, *fallback_datasets: str) -> str | None:
        if source_media_id is None:
            return None
        source_media_id = str(source_media_id)
        for dataset in (source_dataset, *fallback_datasets):
            result = self.media_lookup.get((dataset, source_media_id))
            if result:
                return result
        candidates = self.media_global_lookup.get(source_media_id, [])
        return candidates[0] if len(candidates) == 1 else None

    def add_association(
        self,
        *,
        source_dataset: str,
        source_product_id: Any,
        master_media_id: str | None,
        upstream_association_id: Any,
        grade: Any,
        method: Any,
        source_sku_exact: bool,
        identity_eligible: bool,
        exact_current_svoe_slug: str | None = None,
        exact_current_svoe_slug_verified: bool = False,
    ) -> str:
        master_product_id = self.product_lookup[(source_dataset, str(source_product_id))]
        material = f"{source_dataset}|{upstream_association_id}|{source_product_id}|{master_media_id}"
        association_id = stable_id("master_association", material)
        self.associations.append(
            {
                "manifest_version": MANIFEST_VERSION,
                "dataset_version": DATASET_VERSION,
                "master_association_id": association_id,
                "master_product_id": master_product_id,
                "master_media_id": master_media_id,
                "source_dataset": source_dataset,
                "upstream_association_id": None if upstream_association_id is None else str(upstream_association_id),
                "association_grade": first_text(grade),
                "association_method": method,
                "source_sku_exact": bool(source_sku_exact),
                "identity_eligible": bool(identity_eligible and master_media_id),
                "exact_current_svoe_slug": exact_current_svoe_slug if exact_current_svoe_slug_verified else None,
                "exact_current_svoe_slug_verified": bool(exact_current_svoe_slug_verified),
            }
        )
        return association_id

    def add_review(
        self,
        *,
        key: str,
        required_action: str,
        master_product_ids: Iterable[str] = (),
        master_media_ids: Iterable[str] = (),
        evidence: Any = None,
        candidates: Any = None,
        priority: str = "normal",
        review_state: str = "needs_verification",
    ) -> None:
        if review_state not in {"needs_verification", "needs_annotation"}:
            raise ValueError(f"Unsupported review state: {review_state}")
        review_item_id = stable_id("review_master", key)
        self.review[review_item_id] = {
            "review_item_id": review_item_id,
            "source_dataset": "18_russian_wine_master",
            "review_state": review_state,
            "required_action": required_action,
            "master_product_ids": sorted(set(master_product_ids)),
            "master_media_ids": sorted(set(master_media_ids)),
            "evidence": evidence,
            "candidates": candidates or [],
            "priority": priority,
        }


def ingest_svoe(builder: MasterBuilder) -> None:
    archive = PROJECT_ROOT / "Dataset" / "01_svoe_vino_catalog" / "tables"
    live = PROJECT_ROOT / "Dataset" / "04_svoe_vino_web_enrichment" / "tables"
    archive_files = [archive / name for name in ("products.jsonl", "media.jsonl", "associations.jsonl")]
    live_files = [live / name for name in ("live_products.jsonl", "live_associations.jsonl", "new_live_media.jsonl")]
    builder.register_source("01_svoe_vino_catalog", archive_files)
    builder.register_source("04_svoe_vino_web_enrichment", live_files)
    if not archive_files[0].is_file():
        return

    archive_products = read_jsonl(archive_files[0])
    archive_associations = read_jsonl(archive_files[2])
    live_products = read_jsonl(live_files[0])
    live_associations = read_jsonl(live_files[1])
    live_assoc_by_slug = {str(row["slug"]): row for row in live_associations if row.get("slug")}
    needed_media_ids = {str(row["media_id"]) for row in archive_associations + live_associations if row.get("media_id")}
    for media in read_jsonl(archive_files[1]):
        if str(media.get("media_id")) in needed_media_ids:
            builder.add_media(source_dataset="01_svoe_vino_catalog", row=media)
    for media in read_jsonl(live_files[2]):
        builder.add_media(source_dataset="04_svoe_vino_web_enrichment", row=media)

    for row in archive_products:
        source_product_id = row["product_id"]
        builder.add_product(
            source_dataset="01_svoe_vino_catalog",
            source_id=str(row.get("source_id") or "caseholder-svoe-vino-2026-09"),
            source_capture_id="caseholder-svoe-vino-2026-09",
            source_product_id=source_product_id,
            catalog_id="svoe_vino_archive",
            external_product_id=row.get("slug"),
            title=row.get("wine_name"),
            producer=row.get("winery"),
            country="Россия",
            region=row.get("region"),
            vintage=extract_vintages(row.get("slug"), row.get("wine_name")),
            color=[row.get("category"), row.get("color")],
            grapes=row.get("grapes"),
            source_url=None,
            russian_origin_status="gold_catalog_scope_russian_wine",
            russian_origin_evidence="caseholder Svoe Vino catalog scope",
            rights_status="provided_for_case_pending_written_confirmation",
            quality_status=str(row.get("quality_status") or "source_metadata"),
        )
        builder.add_membership(
            source_dataset="01_svoe_vino_catalog",
            source_product_id=source_product_id,
            catalog_id="svoe_vino_archive",
            snapshot_id="caseholder-svoe-vino-2026-09",
            external_product_id=row.get("slug"),
            membership_status="archive_snapshot",
        )

    for row in archive_associations:
        source_product_id = row.get("product_id")
        if ("01_svoe_vino_catalog", str(source_product_id)) not in builder.product_lookup:
            continue
        master_media_id = builder.resolve_media("01_svoe_vino_catalog", row.get("media_id"))
        builder.add_association(
            source_dataset="01_svoe_vino_catalog",
            source_product_id=source_product_id,
            master_media_id=master_media_id,
            upstream_association_id=row.get("association_id"),
            grade=row.get("grade"),
            method=row.get("method"),
            source_sku_exact=row.get("grade") == "gold",
            identity_eligible=row.get("eligible_for_supervised_training") is True,
        )

    for row in live_products:
        slug = str(row.get("slug"))
        association = live_assoc_by_slug.get(slug, {})
        verified = (
            association.get("grade") == "gold"
            and association.get("eligible_for_supervised_sku_training") is True
            and bool(association.get("media_id"))
        )
        source_product_id = slug
        builder.add_product(
            source_dataset="04_svoe_vino_web_enrichment",
            source_id=str(row.get("source_id") or "svoe-vino-live-2026-09-15"),
            source_capture_id="2026-09-15",
            source_product_id=source_product_id,
            source_linked_product_id=association.get("product_id"),
            catalog_id="svoe_vino_current",
            external_product_id=slug,
            title=first_text(row.get("title"), row.get("og_title")),
            producer=row.get("manufacturer"),
            country="Россия",
            vintage=extract_vintages(slug, row.get("title")),
            source_url=row.get("page_url"),
            russian_origin_status="gold_catalog_scope_russian_wine",
            russian_origin_evidence={"page_url": row.get("page_url"), "page_sha256": row.get("page_sha256")},
            rights_status="terms_and_asset_rights_review_required",
            quality_status=str(row.get("parse_status") or "source_page"),
            exact_current_svoe_slug=slug if verified else None,
            exact_current_svoe_slug_evidence=association.get("association_id") if verified else None,
        )
        builder.add_membership(
            source_dataset="04_svoe_vino_web_enrichment",
            source_product_id=source_product_id,
            catalog_id="svoe_vino_current",
            snapshot_id="2026-09-15",
            external_product_id=slug,
            source_url=row.get("page_url"),
            membership_status="current_snapshot",
            exact_current_svoe_slug=slug,
            exact_current_svoe_slug_verified=verified,
            upstream_membership_id=association.get("association_id"),
        )
        if not verified:
            master_product_id = builder.product_lookup[("04_svoe_vino_web_enrichment", source_product_id)]
            builder.add_review(
                key=f"svoe-live-slug|{slug}",
                required_action="verify_current_svoe_product_to_primary_media_identity_before_exact_slug_use",
                master_product_ids=[master_product_id],
                evidence={"slug": slug, "association": association.get("association_id")},
                priority="high",
            )

    for row in live_associations:
        slug = str(row.get("slug"))
        if ("04_svoe_vino_web_enrichment", slug) not in builder.product_lookup:
            continue
        verified = (
            row.get("grade") == "gold"
            and row.get("eligible_for_supervised_sku_training") is True
            and bool(row.get("media_id"))
        )
        media_id = builder.resolve_media(
            "04_svoe_vino_web_enrichment",
            row.get("media_id"),
            "01_svoe_vino_catalog",
        )
        builder.add_association(
            source_dataset="04_svoe_vino_web_enrichment",
            source_product_id=slug,
            master_media_id=media_id,
            upstream_association_id=row.get("association_id"),
            grade=row.get("grade"),
            method=row.get("method"),
            source_sku_exact=verified,
            identity_eligible=verified,
            exact_current_svoe_slug=slug,
            exact_current_svoe_slug_verified=verified,
        )


def ingest_xwines(builder: MasterBuilder) -> None:
    tables = PROJECT_ROOT / "Dataset" / "07_x_wines" / "tables"
    files = [tables / "slim_russian_products.jsonl", tables / "slim_media.jsonl"]
    builder.register_source("07_x_wines", files)
    products = read_jsonl(files[0])
    if not products:
        return
    wanted_media = {str(row.get("media_id")) for row in products if row.get("media_id")}
    media_rows = {str(row.get("media_id")): row for row in read_jsonl(files[1]) if str(row.get("media_id")) in wanted_media}
    for row in media_rows.values():
        builder.add_media(source_dataset="07_x_wines", row=row)
    for row in products:
        source_product_id = row["product_id"]
        media = media_rows.get(str(row.get("media_id")), {})
        design_id = stable_id("xwines_design", str(media.get("sha256"))) if media.get("sha256") else None
        variant_id = stable_id("xwines_variant", str(row.get("external_wine_id")))
        builder.add_product(
            source_dataset="07_x_wines",
            source_id=str(row.get("source_id") or "x-wines"),
            source_capture_id=str(row.get("edition") or "XWines_Slim_1K"),
            source_product_id=source_product_id,
            catalog_id="x_wines_slim",
            external_product_id=row.get("external_wine_id"),
            title=row.get("wine_name"),
            producer=row.get("winery"),
            brand=row.get("winery"),
            country=row.get("country"),
            region=row.get("region"),
            reported_vintages=row.get("vintages"),
            color=row.get("type"),
            grapes=row.get("grapes"),
            source_variant_id=variant_id,
            source_design_id=design_id,
            source_url=row.get("website"),
            russian_origin_status="gold_source_country_ru",
            russian_origin_evidence={"country_code": row.get("country_code"), "country": row.get("country")},
            rights_status="edition_specific_review",
            quality_status="gold_external_wine_id",
        )
        builder.add_membership(
            source_dataset="07_x_wines",
            source_product_id=source_product_id,
            catalog_id="x_wines_slim",
            snapshot_id=row.get("edition") or "XWines_Slim_1K",
            external_product_id=row.get("external_wine_id"),
            source_url=row.get("website"),
            membership_status="dataset_record",
        )
        master_media_id = builder.resolve_media("07_x_wines", row.get("media_id"))
        builder.add_association(
            source_dataset="07_x_wines",
            source_product_id=source_product_id,
            master_media_id=master_media_id,
            upstream_association_id=f"xwines:{row.get('external_wine_id')}",
            grade="gold",
            method="exact_XWines_WineID_image_filename",
            source_sku_exact=True,
            identity_eligible=bool(master_media_id),
        )


def ingest_off(builder: MasterBuilder) -> None:
    tables = PROJECT_ROOT / "Dataset" / "10_open_food_facts_wine_ru" / "tables"
    files = [tables / name for name in ("candidates.jsonl", "media.jsonl", "associations.jsonl")]
    builder.register_source("10_open_food_facts_wine_ru", files)
    products = [row for row in read_jsonl(files[0]) if row.get("russian_wine_status") in SELECTED_OFF_STATUSES]
    if not products:
        return
    product_ids = {str(row["product_id"]) for row in products}
    media_rows = [row for row in read_jsonl(files[1]) if str(row.get("product_id")) in product_ids]
    for row in media_rows:
        builder.add_media(source_dataset="10_open_food_facts_wine_ru", row=row)
    for row in products:
        source_product_id = row["product_id"]
        name = localized_product_name(row.get("product_name")) or str(row.get("code"))
        builder.add_product(
            source_dataset="10_open_food_facts_wine_ru",
            source_id="open-food-facts-product-database",
            source_capture_id="hf-product-database-cb3a359d7064c1ec535faa58ee1ea965c61a345c",
            source_product_id=source_product_id,
            catalog_id="open_food_facts",
            external_product_id=row.get("code"),
            title=name,
            brand=row.get("brands"),
            country="Россия",
            source_url=f"https://world.openfoodfacts.org/product/{row.get('code')}",
            russian_origin_status=str(row.get("russian_wine_status")),
            russian_origin_evidence=row.get("russian_evidence"),
            rights_status="CC-BY-SA_images_ODbL_database",
            quality_status="origin_needs_verification",
        )
        builder.add_membership(
            source_dataset="10_open_food_facts_wine_ru",
            source_product_id=source_product_id,
            catalog_id="open_food_facts",
            snapshot_id="cb3a359d7064c1ec535faa58ee1ea965c61a345c",
            external_product_id=row.get("code"),
            source_url=f"https://world.openfoodfacts.org/product/{row.get('code')}",
            membership_status="metadata_candidate",
        )
        master_product_id = builder.product_lookup[("10_open_food_facts_wine_ru", str(source_product_id))]
        builder.add_review(
            key=f"off-origin|{row.get('code')}",
            required_action="verify_Russian_production_and_wine_category_from_label_or_authoritative_product_evidence",
            master_product_ids=[master_product_id],
            evidence={"barcode": row.get("code"), "status": row.get("russian_wine_status")},
            priority="high" if row.get("russian_wine_status", "").startswith("bronze") else "normal",
        )
    for row in read_jsonl(files[2]):
        source_product_id = row.get("product_id")
        if str(source_product_id) not in product_ids:
            continue
        master_media_id = builder.resolve_media("10_open_food_facts_wine_ru", row.get("media_id"))
        builder.add_association(
            source_dataset="10_open_food_facts_wine_ru",
            source_product_id=source_product_id,
            master_media_id=master_media_id,
            upstream_association_id=row.get("association_id"),
            grade="gold",
            method=row.get("association_status"),
            source_sku_exact=row.get("association_status") == "exact_off_barcode_record",
            identity_eligible=row.get("safe_for_supervised_sku") is True,
        )


def ingest_structured_retailer(
    builder: MasterBuilder,
    *,
    source_dataset: str,
    catalog_default: str,
    associations_filename: str,
) -> None:
    tables = PROJECT_ROOT / "Dataset" / source_dataset / "tables"
    files = [
        tables / "products.jsonl",
        tables / "catalog_memberships.jsonl",
        tables / "media.jsonl",
        tables / associations_filename,
    ]
    builder.register_source(source_dataset, files)
    products = read_jsonl(files[0])
    if not products:
        builder.sources[source_dataset]["status"] = "temporarily_unavailable_or_empty"
        return
    products = [
        row
        for row in products
        if first_text(row.get("country"), row.get("country_name")).casefold().startswith(
            ("россия", "russia", "russian federation")
        )
    ]
    upstream_product_ids = {str(row.get("product_id")) for row in products}
    upstream_memberships = {
        str(row.get("product_id")): row
        for row in read_jsonl(files[1])
        if str(row.get("product_id")) in upstream_product_ids
    }
    media_rows = read_jsonl(files[2])
    association_rows = [
        row for row in read_jsonl(files[3]) if str(row.get("product_id")) in upstream_product_ids
    ]
    needed_media = {str(row.get("media_id")) for row in association_rows if row.get("media_id")}
    for row in media_rows:
        if str(row.get("media_id")) in needed_media:
            builder.add_media(source_dataset=source_dataset, row=row)

    for row in products:
        source_product_id = str(row["product_id"])
        membership = upstream_memberships.get(source_product_id, {})
        properties = row.get("properties") or row.get("stats") or {}
        producer = first_text(
            row.get("producer"),
            row.get("manufacturer"),
            dict_field(properties, ("Производитель", "Бренд", "Винодельня")),
        )
        brand = first_text(row.get("brand"), dict_field(properties, ("Бренд", "Марка")))
        volume = first_text(row.get("volume_l"), dict_field(properties, ("Объем", "Объём")))
        source_id = str(row.get("source_id") or membership.get("source_id") or source_dataset)
        capture_id = first_text(row.get("source_capture_id"), membership.get("source_capture_id"), membership.get("snapshot_id"), membership.get("snapshot_date"))
        title = first_text(row.get("name"), row.get("title"))
        russian_status = first_text(row.get("russian_origin_status")) or "gold_source_product_country_explicit"
        russian_evidence = row.get("country_evidence")
        if russian_evidence is None:
            russian_evidence = membership.get("country_evidence")
        if russian_evidence is None:
            russian_evidence = {"country": first_text(row.get("country"), row.get("country_name"))}
        builder.add_product(
            source_dataset=source_dataset,
            source_id=source_id,
            source_capture_id=capture_id,
            source_product_id=source_product_id,
            catalog_id=str(membership.get("catalog_id") or catalog_default),
            external_product_id=first_text(row.get("external_product_id"), membership.get("external_product_id"), row.get("external_article")),
            title=title,
            producer=producer,
            brand=brand,
            country=first_text(row.get("country"), row.get("country_name")),
            region=row.get("region"),
            vintage=first_text(row.get("vintage"), dict_field(properties, ("Год урожая", "Винтаж"))),
            volume_l=volume,
            color=first_text(row.get("color"), dict_field(properties, ("Цвет",))),
            sugar=first_text(row.get("sugar"), dict_field(properties, ("Содержание сахара", "Сахар"))),
            grapes=first_text(row.get("grapes"), dict_field(properties, ("Сортовой состав", "Сорта винограда"))),
            source_family_id=row.get("wine_family_id"),
            source_variant_id=first_text(row.get("bottle_variant_id"), membership.get("bottle_variant_id")),
            source_design_id=first_text(row.get("label_design_id"), membership.get("label_design_id")),
            source_url=first_text(row.get("canonical_url"), row.get("page_url"), row.get("source_url"), membership.get("source_url")),
            russian_origin_status=russian_status,
            russian_origin_evidence=russian_evidence,
            rights_status=str(row.get("rights_status") or "internal_noncommercial_research_pending_terms_review"),
            quality_status=str(row.get("quality_status") or row.get("primary_media_status") or "source_metadata"),
        )
        builder.add_membership(
            source_dataset=source_dataset,
            source_product_id=source_product_id,
            catalog_id=str(membership.get("catalog_id") or catalog_default),
            snapshot_id=capture_id,
            external_product_id=first_text(row.get("external_product_id"), membership.get("external_product_id"), row.get("external_article")),
            source_url=first_text(membership.get("source_url"), membership.get("page_url"), row.get("canonical_url"), row.get("page_url")),
            membership_status=str(membership.get("membership_status") or "listed"),
            upstream_membership_id=membership.get("catalog_membership_id"),
        )

    associated_product_ids: set[str] = set()
    ineligible_associations: list[tuple[str, str | None, str]] = []
    for index, row in enumerate(association_rows):
        source_product_id = str(row.get("product_id"))
        associated_product_ids.add(source_product_id)
        master_media_id = builder.resolve_media(source_dataset, row.get("media_id"))
        exact = row.get("source_sku_exact") is True or first_text(row.get("association_grade")) == "gold"
        if "eligible_for_source_sku_supervision_by_identity" in row:
            identity_eligible = row.get("eligible_for_source_sku_supervision_by_identity") is True
        else:
            identity_eligible = (
                exact
                and row.get("decode_ok") is not False
                and row.get("image_decode_ok") is not False
                and row.get("download_status") not in {"http_error", "robots_disallowed", "not_downloaded"}
                and not str(row.get("quality_status") or "").startswith("needs_verification")
            )
        association_id = first_text(row.get("association_id")) or f"{source_dataset}:{index}:{source_product_id}:{row.get('media_id')}"
        builder.add_association(
            source_dataset=source_dataset,
            source_product_id=source_product_id,
            master_media_id=master_media_id,
            upstream_association_id=association_id,
            grade=row.get("association_grade"),
            method=first_text(row.get("association_evidence"), row.get("evidence"), row.get("association_role")),
            source_sku_exact=exact,
            identity_eligible=identity_eligible,
        )
        if not identity_eligible:
            ineligible_associations.append((source_product_id, master_media_id, association_id))

    source_review_root = PROJECT_ROOT / "Dataset" / source_dataset / "review"
    covered_product_ids: set[str] = set()
    covered_master_media_ids: set[str] = set()
    for review_state in ("needs_verification", "needs_annotation"):
        for row in read_jsonl(source_review_root / review_state / "queue.jsonl"):
            source_product_ids: set[str] = set()
            if row.get("product_id") is not None:
                source_product_ids.add(str(row["product_id"]))
            for candidate in row.get("candidates") or []:
                if isinstance(candidate, dict) and candidate.get("product_id") is not None:
                    source_product_ids.add(str(candidate["product_id"]))
                elif isinstance(candidate, str):
                    source_product_ids.add(candidate)
            evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
            for value in evidence.get("product_ids") or []:
                source_product_ids.add(str(value))
            source_product_ids &= upstream_product_ids
            if not source_product_ids:
                continue
            source_media_ids: set[str] = set()
            if row.get("media_id") is not None:
                source_media_ids.add(str(row["media_id"]))
            for value in evidence.get("media_ids") or []:
                source_media_ids.add(str(value))
            master_product_ids = [
                builder.product_lookup[(source_dataset, source_product_id)]
                for source_product_id in sorted(source_product_ids)
            ]
            master_media_ids = sorted(
                {
                    resolved
                    for source_media_id in source_media_ids
                    if (resolved := builder.resolve_media(source_dataset, source_media_id))
                }
            )
            builder.add_review(
                key=f"source-review|{source_dataset}|{row.get('review_item_id') or '|'.join(sorted(source_product_ids))}|{review_state}",
                required_action=first_text(row.get("required_action")) or "review_source_product_media_gap",
                master_product_ids=master_product_ids,
                master_media_ids=master_media_ids,
                evidence={
                    "source_review_item_id": row.get("review_item_id"),
                    "source_group_id": row.get("group_id"),
                    "source_evidence": row.get("evidence"),
                },
                candidates=row.get("candidates"),
                priority=first_text(row.get("priority")) or "normal",
                review_state=review_state,
            )
            covered_product_ids.update(source_product_ids)
            covered_master_media_ids.update(master_media_ids)

    for source_product_id, master_media_id, association_id in ineligible_associations:
        if source_product_id in covered_product_ids or (
            master_media_id is not None and master_media_id in covered_master_media_ids
        ):
            continue
        master_product_id = builder.product_lookup[(source_dataset, source_product_id)]
        builder.add_review(
            key=f"retailer-association|{source_dataset}|{association_id}",
            required_action="verify_retailer_product_image_identity_or_placeholder/shared_asset_status",
            master_product_ids=[master_product_id],
            master_media_ids=[master_media_id] if master_media_id else [],
            evidence={"upstream_association_id": association_id},
        )


class DisjointSet:
    def __init__(self, members: Iterable[str]) -> None:
        self.parent = {member: member for member in members}

    def find(self, item: str) -> str:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            parent = self.parent[item]
            self.parent[item] = root
            item = parent
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        keep, merge = sorted((left_root, right_root))
        self.parent[merge] = keep


def build_family_candidates(builder: MasterBuilder) -> list[dict[str, Any]]:
    product_by_id = {row["master_product_id"]: row for row in builder.products}
    signatures_by_product: dict[str, set[str]] = defaultdict(set)
    products_by_signature: dict[str, list[str]] = defaultdict(list)
    for product in builder.products:
        identity = product["normalized_identity"]
        title = identity.get("family_title")
        if not title or len(title) < 3:
            continue
        entities = [("producer", item) for item in identity.get("producer", [])]
        entities += [("brand", item) for item in identity.get("brand", [])]
        for kind, entity in entities:
            if len(entity) < 3:
                continue
            signature = f"{kind}:{entity}|title:{title}"
            signatures_by_product[product["master_product_id"]].add(signature)
            products_by_signature[signature].append(product["master_product_id"])

    dsu = DisjointSet(product_by_id)
    shared_signatures = {
        signature: sorted(set(product_ids))
        for signature, product_ids in products_by_signature.items()
        if len(set(product_ids)) > 1
    }
    for product_ids in shared_signatures.values():
        for other in product_ids[1:]:
            dsu.union(product_ids[0], other)

    components: dict[str, list[str]] = defaultdict(list)
    for product_id in product_by_id:
        components[dsu.find(product_id)].append(product_id)

    candidates: list[dict[str, Any]] = []
    for members in sorted((sorted(items) for items in components.values() if len(items) > 1), key=lambda items: items[0]):
        rows = [product_by_id[item] for item in members]
        catalogs = sorted({row["catalog_id"] for row in rows})
        source_datasets = sorted({row["source_dataset"] for row in rows})
        component_signatures = sorted(
            signature
            for signature, product_ids in shared_signatures.items()
            if len(set(product_ids).intersection(members)) > 1
        )
        only_svoe = set(catalogs) <= {"svoe_vino_archive", "svoe_vino_current"}
        exact_svoe_links = {
            row.get("source_linked_product_id")
            for row in rows
            if row["source_dataset"] == "04_svoe_vino_web_enrichment"
            and row.get("exact_current_svoe_slug")
        }
        archive_ids = {
            row["source_product_id"]
            for row in rows
            if row["source_dataset"] == "01_svoe_vino_catalog"
        }
        if only_svoe and len(rows) == 2 and exact_svoe_links and exact_svoe_links <= archive_ids:
            continue
        anchor = component_signatures[0] if component_signatures else "|".join(members)
        candidate_id = stable_id("family_candidate", anchor)
        for row in rows:
            row["provisional_family_candidate_id"] = candidate_id
        member_records = [
            {
                "master_product_id": row["master_product_id"],
                "source_dataset": row["source_dataset"],
                "catalog_id": row["catalog_id"],
                "external_product_id": row["external_product_id"],
                "title": row["title"],
                "producer": row["producer"],
                "brand": row["brand"],
                "vintage": row["vintage"],
                "reported_vintages": row["reported_vintages"],
                "volume_l": row["volume_l"],
                "source_bottle_variant_id": row["source_bottle_variant_id"],
                "source_label_design_id": row["source_label_design_id"],
                "exact_current_svoe_slug": row["exact_current_svoe_slug"],
            }
            for row in rows
        ]
        candidate = {
            "manifest_version": MANIFEST_VERSION,
            "dataset_version": DATASET_VERSION,
            "provisional_family_candidate_id": candidate_id,
            "relation": "same_family_uncertain",
            "status": "needs_verification",
            "candidate_basis": "exact_normalized_producer_or_brand_plus_family_title",
            "match_signatures": component_signatures,
            "source_datasets": source_datasets,
            "catalogs": catalogs,
            "member_count": len(members),
            "members": member_records,
            "variant_and_design_policy": "vintage_volume_and_label_design_remain_separate_until_review",
        }
        candidates.append(candidate)
        builder.add_review(
            key=f"family|{candidate_id}",
            required_action="review_same_family_uncertain_without_merging_variants_or_label_designs",
            master_product_ids=members,
            evidence={"match_signatures": component_signatures, "catalogs": catalogs},
            candidates=member_records,
            priority="high" if len(catalogs) > 1 else "normal",
        )
    return sorted(candidates, key=lambda row: row["provisional_family_candidate_id"])


def integrity_checks(
    builder: MasterBuilder,
    family_candidates: list[dict[str, Any]],
    output: Path,
) -> dict[str, bool]:
    product_ids = [row["master_product_id"] for row in builder.products]
    membership_ids = [row["master_catalog_membership_id"] for row in builder.memberships]
    media_ids = list(builder.media)
    association_ids = [row["master_association_id"] for row in builder.associations]
    product_id_set = set(product_ids)
    media_id_set = set(media_ids)
    allowed_svoe_datasets = {"04_svoe_vino_web_enrichment"}
    all_exact_slug_rows = [
        row for collection in (builder.products, builder.memberships, builder.associations)
        for row in collection if row.get("exact_current_svoe_slug")
    ]
    verified_live_slug_pairs = {
        (row["master_product_id"], row["exact_current_svoe_slug"])
        for row in builder.associations
        if row.get("source_dataset") == "04_svoe_vino_web_enrichment"
        and row.get("exact_current_svoe_slug_verified") is True
        and row.get("identity_eligible") is True
    }
    image_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
    copied_images = [path for path in output.rglob("*") if path.is_file() and path.suffix.casefold() in image_suffixes]
    return {
        "unique_master_product_ids": len(product_ids) == len(set(product_ids)),
        "unique_master_membership_ids": len(membership_ids) == len(set(membership_ids)),
        "unique_master_media_ids": len(media_ids) == len(set(media_ids)),
        "unique_master_association_ids": len(association_ids) == len(set(association_ids)),
        "all_memberships_reference_products": all(row["master_product_id"] in product_id_set for row in builder.memberships),
        "all_products_have_catalog_membership": {
            row["master_product_id"] for row in builder.memberships
        } == product_id_set,
        "all_associations_reference_products": all(row["master_product_id"] in product_id_set for row in builder.associations),
        "all_associations_reference_existing_media_or_explicit_null": all(
            row["master_media_id"] is None or row["master_media_id"] in media_id_set for row in builder.associations
        ),
        "all_identity_eligible_associations_have_media": all(
            not row["identity_eligible"] or row["master_media_id"] in media_id_set
            for row in builder.associations
        ),
        "all_media_have_path_hash_and_decode_status": all(
            row.get("relative_path")
            and isinstance(row.get("sha256"), str)
            and len(row["sha256"]) == 64
            and row.get("decode_status") == "ok"
            for row in builder.media.values()
        ),
        "all_media_have_mime_type": all(row.get("media_type") for row in builder.media.values()),
        "all_media_paths_resolve_inside_project_dataset": all(
            referenced_media_path_exists(row.get("relative_path"))
            for row in builder.media.values()
        ),
        "all_products_have_explicit_russian_origin_status": all(
            bool(row.get("russian_origin_status")) for row in builder.products
        ),
        "all_family_members_reference_products": all(
            member["master_product_id"] in product_id_set
            for candidate in family_candidates
            for member in candidate["members"]
        ),
        "family_candidates_are_provisional": all(
            row["relation"] == "same_family_uncertain" and row["status"] == "needs_verification"
            for row in family_candidates
        ),
        "no_cross_source_product_collapse": len(product_ids) == len(builder.product_lookup),
        "exact_current_svoe_slug_only_from_verified_live_associations": all(
            row.get("source_dataset") in allowed_svoe_datasets
            and (row["master_product_id"], row["exact_current_svoe_slug"]) in verified_live_slug_pairs
            for row in all_exact_slug_rows
        ),
        "no_media_copied_into_master_dataset": not copied_images,
    }


def build(output: Path) -> dict[str, Any]:
    builder = MasterBuilder(output)
    ingest_svoe(builder)
    ingest_xwines(builder)
    ingest_off(builder)
    ingest_structured_retailer(
        builder,
        source_dataset="11_mavt_ru_wines",
        catalog_default="mavt",
        associations_filename="product_media_associations.jsonl",
    )
    ingest_structured_retailer(
        builder,
        source_dataset="15_aromatny_mir_ru_wines",
        catalog_default="amwine.ru",
        associations_filename="product_media_associations.jsonl",
    )
    ingest_structured_retailer(
        builder,
        source_dataset="16_alkoteka_ru_wines",
        catalog_default="alkoteka",
        associations_filename="associations.jsonl",
    )

    family_candidates = build_family_candidates(builder)
    builder.products.sort(key=lambda row: row["master_product_id"])
    builder.memberships.sort(key=lambda row: row["master_catalog_membership_id"])
    media_rows = sorted(builder.media.values(), key=lambda row: row["master_media_id"])
    builder.associations.sort(key=lambda row: row["master_association_id"])

    output.mkdir(parents=True, exist_ok=True)
    table_dir = output / "tables"
    review_dir = output / "review"
    decision_files = (
        review_dir / "verified" / "decisions.jsonl",
        review_dir / "rejected" / "decisions.jsonl",
    )
    decision_rows: list[dict[str, Any]] = []
    for decision_file in decision_files:
        if decision_file.exists():
            decision_rows.extend(read_jsonl(decision_file))
        else:
            write_jsonl(decision_file, [])
    resolved_review_ids = {
        str(row["review_item_id"])
        for row in decision_rows
        if row.get("review_item_id")
    }
    review_rows = sorted(
        (
            row
            for row in builder.review.values()
            if row["review_item_id"] not in resolved_review_ids
        ),
        key=lambda row: row["review_item_id"],
    )
    verification_rows = [row for row in review_rows if row["review_state"] == "needs_verification"]
    annotation_rows = [row for row in review_rows if row["review_state"] == "needs_annotation"]
    output_files = {
        "products": table_dir / "products.jsonl",
        "catalog_memberships": table_dir / "catalog_memberships.jsonl",
        "media": table_dir / "media.jsonl",
        "associations": table_dir / "associations.jsonl",
        "family_candidates": table_dir / "family_candidates.jsonl",
        "needs_verification": review_dir / "needs_verification" / "queue.jsonl",
        "needs_annotation": review_dir / "needs_annotation" / "queue.jsonl",
    }
    write_jsonl(output_files["products"], builder.products)
    write_jsonl(output_files["catalog_memberships"], builder.memberships)
    write_jsonl(output_files["media"], media_rows)
    write_jsonl(output_files["associations"], builder.associations)
    write_jsonl(output_files["family_candidates"], family_candidates)
    write_jsonl(output_files["needs_verification"], verification_rows)
    write_jsonl(output_files["needs_annotation"], annotation_rows)

    checks = integrity_checks(builder, family_candidates, output)
    source_counts: dict[str, dict[str, int]] = {}
    for dataset in sorted(builder.sources):
        source_counts[dataset] = {
            "products": sum(row["source_dataset"] == dataset for row in builder.products),
            "catalog_memberships": sum(row["source_dataset"] == dataset for row in builder.memberships),
            "media": sum(row["source_dataset"] == dataset for row in media_rows),
            "associations": sum(row["source_dataset"] == dataset for row in builder.associations),
            "needs_verification": 0,
            "needs_annotation": 0,
        }
        # Review tasks can span multiple datasets, so they are intentionally not
        # attributed to a single source in source_counts.
        source_counts[dataset]["needs_verification"] = sum(
            any(
                product["source_dataset"] == dataset
                for product in builder.products
                if product["master_product_id"] in review["master_product_ids"]
            )
            for review in verification_rows
        )
        source_counts[dataset]["needs_annotation"] = sum(
            any(
                product["source_dataset"] == dataset
                for product in builder.products
                if product["master_product_id"] in review["master_product_ids"]
            )
            for review in annotation_rows
        )

    exact_slugs = {
        row["exact_current_svoe_slug"]
        for row in builder.products
        if row.get("exact_current_svoe_slug")
    }
    summary = {
        "manifest_version": MANIFEST_VERSION,
        "dataset_version": DATASET_VERSION,
        "script_version": SCRIPT_VERSION,
        "purpose": "Russian-wine open-world master index without forced cross-source identity merge",
        "inputs": {
            "sources": {key: builder.sources[key] for key in sorted(builder.sources)},
            "files": [builder.input_files[key] for key in sorted(builder.input_files)],
        },
        "counts": {
            "products": len(builder.products),
            "catalog_memberships": len(builder.memberships),
            "media": len(media_rows),
            "associations": len(builder.associations),
            "identity_eligible_associations": sum(row["identity_eligible"] for row in builder.associations),
            "exact_current_svoe_slugs": len(exact_slugs),
            "provisional_family_candidates": len(family_candidates),
            "cross_catalog_family_candidates": sum(len(row["catalogs"]) > 1 for row in family_candidates),
            "family_candidate_members": sum(row["member_count"] for row in family_candidates),
            "needs_verification": len(verification_rows),
            "needs_annotation": len(annotation_rows),
            "review_decisions_preserved": len(decision_rows),
        },
        "catalog_counts": dict(sorted(Counter(row["catalog_id"] for row in builder.products).items())),
        "origin_status_counts": dict(sorted(Counter(row["russian_origin_status"] for row in builder.products).items())),
        "review_action_counts": dict(sorted(Counter(row["required_action"] for row in review_rows).items())),
        "review_state_counts": dict(sorted(Counter(row["review_state"] for row in review_rows).items())),
        "source_counts": source_counts,
        "integrity_checks": checks,
        "all_integrity_checks_pass": all(checks.values()),
        "policy": {
            "cross_source_merge": "forbidden_without_human_verified_decision",
            "family_candidates": "same_family_uncertain_only",
            "vintage_volume_label_design": "preserved_separately",
            "exact_current_svoe_slug": "only_verified_2026-09-15_live_product_media_associations",
            "media_storage": "references_only_no_image_copy",
            "split_assignment": "not_performed",
        },
        "output_files": {
            name: {
                "relative_path": path.relative_to(PROJECT_ROOT).as_posix(),
                "rows": jsonl_count(path),
                "sha256": sha256_file(path),
            }
            for name, path in sorted(output_files.items())
        },
    }
    write_json(table_dir / "SUMMARY.json", summary)
    write_json(
        review_dir / "STATUS.json",
        {
            "dataset_version": DATASET_VERSION,
            "needs_verification": len(verification_rows),
            "needs_annotation": len(annotation_rows),
            "decisions_preserved": len(decision_rows),
            "resolved_review_ids": len(resolved_review_ids),
            "verified_decisions_file_preserved": True,
            "rejected_decisions_file_preserved": True,
        },
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    summary = build(output.resolve())
    print(json.dumps(summary["counts"], ensure_ascii=False, sort_keys=True))
    print(json.dumps(summary["integrity_checks"], ensure_ascii=False, sort_keys=True))
    return 0 if summary["all_integrity_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
