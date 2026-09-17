#!/usr/bin/env python3
"""Capture the public Alkoteca catalogue subset for Russian wines.

The crawler uses the site's public web API exactly as the catalogue UI does.
It keeps one honest User-Agent, serializes every request through one rate gate,
checks the captured robots policy before requesting a path, and immediately
stops on HTTP 403/429 or an anti-bot challenge marker. Raw response bytes are
kept under ``Dataset/00_raw``; normalized manifests omit store addresses,
phones, cookies, tokens and other fields irrelevant to wine identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from common import image_probe, sha256_file, stable_id, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
SOURCE_BASE = "https://alkoteka.com"
ASSET_BASE = "https://web.alkoteka.com"
USER_AGENT = "VinoDatasetResearch/1.0 (+noncommercial research; contact: local operator)"
CITY_UUID = "4a70f9e0-46ae-11e7-83ff-00155d026416"
CITY_SLUG = "krasnodar"
CITY_NAME = "Краснодар"
ROOT_CATEGORIES = ("vino", "shampanskoe-i-igristoe")
COUNTRY_FILTER = "rossiya"
BLOCK_MARKERS = (
    b"checking your browser",
    b"access denied",
    b"cloudflare ray id",
    b"qrator",
)
SAFE_RESPONSE_HEADERS = {
    "content-type",
    "content-length",
    "etag",
    "last-modified",
    "cache-control",
}


class StopCrawl(RuntimeError):
    """A hard access-control stop: never retry or work around it."""


class FetchFailure(RuntimeError):
    """A normal fetch failure that can be recorded without evasion."""


class RateGate:
    def __init__(self, interval: float) -> None:
        self.interval = max(0.0, interval)
        self.last_request = 0.0

    def wait(self) -> None:
        delay = self.interval - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.monotonic()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.part")
    temporary.write_bytes(payload)
    temporary.replace(path)


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    result = re.sub(r"\s+", " ", str(value)).strip()
    return result or None


def json_from_bytes(payload: bytes, url: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise FetchFailure(f"invalid JSON from {url}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(value, dict):
        raise FetchFailure(f"unexpected JSON root from {url}: {type(value).__name__}")
    if value.get("success") is not True:
        raise FetchFailure(f"API error from {url}: {clean_text(value.get('error')) or 'unknown error'}")
    return value


def response_record(
    *,
    request_url: str,
    final_url: str,
    target: Path,
    payload: bytes,
    status: int,
    headers: Any,
    cached: bool,
    capture_root: Path,
) -> dict[str, Any]:
    safe_headers = {}
    if headers:
        for key in SAFE_RESPONSE_HEADERS:
            value = headers.get(key)
            if value:
                safe_headers[key] = value
    return {
        "request_url": request_url,
        "final_url": final_url,
        "relative_path": target.relative_to(ROOT).as_posix(),
        "capture_relative_path": target.relative_to(capture_root).as_posix(),
        "status_code": status,
        "fetch_status": "cached" if cached else "downloaded",
        "captured_at_utc": None if cached else utc_now(),
        "sha256": sha256_bytes(payload),
        "bytes": len(payload),
        "response_headers": safe_headers,
    }


class Client:
    def __init__(
        self,
        *,
        capture_root: Path,
        interval: float,
        retries: int,
        timeout: float,
    ) -> None:
        self.capture_root = capture_root
        self.gate = RateGate(interval)
        self.retries = max(0, retries)
        self.timeout = timeout
        self.records: list[dict[str, Any]] = []
        self.policy: urllib.robotparser.RobotFileParser | None = None
        self.disallow_prefixes: list[str] = []
        self.hard_stop: dict[str, Any] | None = None

    def set_policy(self, payload: bytes) -> None:
        text = payload.decode("utf-8", errors="replace")
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(f"{SOURCE_BASE}/robots.txt")
        parser.parse(text.splitlines())
        self.policy = parser
        # urllib.robotparser does not consistently implement the trailing '*'
        # syntax used by this site. Keep explicit path prefixes as a second,
        # conservative enforcement layer.
        self.disallow_prefixes = []
        applies_to_all = False
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            key, separator, value = line.partition(":")
            if not separator:
                continue
            key = key.strip().casefold()
            value = value.strip()
            if key == "user-agent":
                applies_to_all = value == "*"
            elif key == "disallow" and applies_to_all and value:
                self.disallow_prefixes.append(value.rstrip("*"))

    def ensure_allowed(self, url: str) -> None:
        if urllib.parse.urlsplit(url).path == "/robots.txt":
            return
        if self.policy is None:
            raise StopCrawl("robots policy must be captured and parsed before other requests")
        path = urllib.parse.urlsplit(url).path
        if any(path.startswith(prefix) for prefix in self.disallow_prefixes):
            raise StopCrawl(f"robots policy disallows {url}")
        if not self.policy.can_fetch(USER_AGENT, url):
            raise StopCrawl(f"robots policy disallows {url}")

    def fetch(self, url: str, target: Path, *, accept: str, use_cache: bool = True) -> bytes:
        self.ensure_allowed(url)
        if use_cache and target.is_file() and target.stat().st_size > 0:
            payload = target.read_bytes()
            self.records.append(response_record(
                request_url=url,
                final_url=url,
                target=target,
                payload=payload,
                status=200,
                headers=None,
                cached=True,
                capture_root=self.capture_root,
            ))
            return payload

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": accept,
            })
            try:
                self.gate.wait()
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    status = int(getattr(response, "status", 200))
                    final_url = response.geturl()
                    payload = response.read()
                    headers = response.headers
                if status in {403, 429}:
                    raise StopCrawl(f"HTTP {status} at {url}")
                if status < 200 or status >= 300:
                    raise FetchFailure(f"HTTP {status} at {url}")
                prefix = payload[:200_000].lower()
                if any(marker in prefix for marker in BLOCK_MARKERS):
                    raise StopCrawl(f"anti-bot/challenge marker at {url}")
                atomic_write_bytes(target, payload)
                self.records.append(response_record(
                    request_url=url,
                    final_url=final_url,
                    target=target,
                    payload=payload,
                    status=status,
                    headers=headers,
                    cached=False,
                    capture_root=self.capture_root,
                ))
                return payload
            except urllib.error.HTTPError as exc:
                if exc.code in {403, 429}:
                    self.hard_stop = {"url": url, "status_code": exc.code, "at_utc": utc_now()}
                    raise StopCrawl(f"HTTP {exc.code} at {url}") from exc
                last_error = exc
                if 400 <= exc.code < 500:
                    break
            except StopCrawl:
                self.hard_stop = {"url": url, "reason": "access_control_or_challenge", "at_utc": utc_now()}
                raise
            except Exception as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(min(2 ** attempt, 8))
        raise FetchFailure(f"fetch failed at {url}: {type(last_error).__name__}: {last_error}")


def build_api_url(path: str, params: list[tuple[str, Any]]) -> str:
    query = urllib.parse.urlencode(params, doseq=True)
    return f"{SOURCE_BASE}{path}?{query}"


def capture_static(client: Client) -> dict[str, Any]:
    robots_path = client.capture_root / "robots.txt"
    robots_url = f"{SOURCE_BASE}/robots.txt"
    if robots_path.is_file() and robots_path.stat().st_size:
        robots = robots_path.read_bytes()
        client.records.append(response_record(
            request_url=robots_url,
            final_url=robots_url,
            target=robots_path,
            payload=robots,
            status=200,
            headers=None,
            cached=True,
            capture_root=client.capture_root,
        ))
    else:
        # robots.txt is the only request allowed before a policy exists.
        request = urllib.request.Request(robots_url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/plain",
        })
        client.gate.wait()
        try:
            with urllib.request.urlopen(request, timeout=client.timeout) as response:
                status = int(getattr(response, "status", 200))
                payload = response.read()
                final_url = response.geturl()
                headers = response.headers
        except urllib.error.HTTPError as exc:
            if exc.code in {403, 429}:
                raise StopCrawl(f"HTTP {exc.code} while retrieving robots.txt") from exc
            raise
        if status != 200:
            raise StopCrawl(f"robots.txt returned HTTP {status}")
        atomic_write_bytes(robots_path, payload)
        robots = payload
        client.records.append(response_record(
            request_url=robots_url,
            final_url=final_url,
            target=robots_path,
            payload=payload,
            status=status,
            headers=headers,
            cached=False,
            capture_root=client.capture_root,
        ))
    client.set_policy(robots)

    if not {"/nova/", "/account/"}.issubset(set(client.disallow_prefixes)):
        raise StopCrawl("robots policy no longer disallows the expected private route families; review required")

    catalog = client.fetch(
        f"{SOURCE_BASE}/catalog/",
        client.capture_root / "entry" / "catalog.html",
        accept="text/html,application/xhtml+xml",
    )
    sitemap = client.fetch(
        f"{SOURCE_BASE}/sitemap.xml",
        client.capture_root / "sitemap.xml",
        accept="application/xml,text/xml",
    )
    sitemap_root = ET.fromstring(sitemap)
    sitemap_urls = [
        element.text.strip()
        for element in sitemap_root.iter()
        if element.tag.endswith("loc") and element.text
    ]
    product_sitemaps = [url for url in sitemap_urls if "sitemap-product-" in url]
    for url in product_sitemaps:
        filename = Path(urllib.parse.urlsplit(url).path).name
        client.fetch(
            url,
            client.capture_root / "sitemaps" / filename,
            accept="application/xml,text/xml",
        )
    return {
        "robots_sha256": sha256_bytes(robots),
        "catalog_entry_sha256": sha256_bytes(catalog),
        "sitemap_sha256": sha256_bytes(sitemap),
        "declared_product_sitemaps": product_sitemaps,
    }


def fetch_catalog_lists(
    client: Client,
    *,
    city_uuid: str,
    per_page: int,
    max_products: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_vendor_code: dict[str, dict[str, Any]] = {}
    roots_summary: dict[str, Any] = {}
    for root_slug in ROOT_CATEGORIES:
        page = 1
        seen_for_root = 0
        declared_total = None
        while True:
            params = [
                ("city_uuid", city_uuid),
                ("root_category_slug", root_slug),
                ("options[strana][]", COUNTRY_FILTER),
                ("per_page", per_page),
                ("page", page),
            ]
            url = build_api_url("/web-api/v1/product", params)
            target = client.capture_root / "api" / "lists" / root_slug / f"page-{page:04d}.json"
            response = json_from_bytes(client.fetch(url, target, accept="application/json"), url)
            meta = response.get("meta") or {}
            results = response.get("results") or []
            if declared_total is None:
                declared_total = int(meta.get("total") or 0)
            for row in results:
                vendor_code = str(row.get("vendor_code") or "").strip()
                if not vendor_code:
                    continue
                stored = by_vendor_code.setdefault(vendor_code, dict(row))
                stored.setdefault("discovered_root_categories", [])
                if root_slug not in stored["discovered_root_categories"]:
                    stored["discovered_root_categories"].append(root_slug)
                seen_for_root += 1
                if max_products and len(by_vendor_code) >= max_products:
                    break
            print(
                f"list {root_slug}: page={page}, rows={len(results)}, "
                f"declared_total={declared_total}, unique={len(by_vendor_code)}",
                flush=True,
            )
            if max_products and len(by_vendor_code) >= max_products:
                break
            if not meta.get("has_more_pages") or not results:
                break
            page += 1
        roots_summary[root_slug] = {
            "declared_total": declared_total,
            "rows_seen": seen_for_root,
            "pages_captured": page,
        }
        if max_products and len(by_vendor_code) >= max_products:
            break
    products = sorted(by_vendor_code.values(), key=lambda row: int(row.get("vendor_code") or 0))
    return products, roots_summary


def fetch_details(
    client: Client,
    listings: list[dict[str, Any]],
    *,
    city_uuid: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    details = []
    errors = []
    for index, listing in enumerate(listings, 1):
        slug = str(listing.get("slug") or "").strip()
        vendor_code = str(listing.get("vendor_code") or "").strip()
        url = build_api_url(
            f"/web-api/v1/product/{urllib.parse.quote(slug, safe='-_')}",
            [("city_uuid", city_uuid)],
        )
        target = client.capture_root / "api" / "products" / f"{vendor_code}.json"
        try:
            response = json_from_bytes(client.fetch(url, target, accept="application/json"), url)
            detail = response.get("results")
            if not isinstance(detail, dict):
                raise FetchFailure("product results is not an object")
            detail["_listing"] = listing
            details.append(detail)
        except StopCrawl:
            raise
        except Exception as exc:
            errors.append({
                "vendor_code": vendor_code,
                "slug": slug,
                "url": url,
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })
        if index % 25 == 0 or index == len(listings):
            print(f"details {index}/{len(listings)}: ok={len(details)}, errors={len(errors)}", flush=True)
    return details, errors


def attribute_map(detail: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for block in detail.get("description_blocks") or []:
        code = clean_text(block.get("code"))
        if not code:
            continue
        item: dict[str, Any] = {
            "title": clean_text(block.get("title")),
            "type": clean_text(block.get("type")),
            "unit": clean_text(block.get("unit")),
        }
        if isinstance(block.get("values"), list):
            item["values"] = [
                {"slug": clean_text(value.get("slug")), "name": clean_text(value.get("name"))}
                for value in block["values"]
                if isinstance(value, dict)
            ]
        for key in ("min", "max"):
            if block.get(key) is not None:
                item[key] = block[key]
        result[code] = item
    return result


def attribute_names(attributes: dict[str, dict[str, Any]], code: str) -> list[str]:
    return [
        value["name"]
        for value in attributes.get(code, {}).get("values", [])
        if value.get("name")
    ]


def attribute_scalar(attributes: dict[str, dict[str, Any]], code: str) -> Any:
    item = attributes.get(code) or {}
    minimum = item.get("min")
    maximum = item.get("max")
    if minimum is None and maximum is None:
        return None
    if minimum == maximum:
        return minimum
    return {"min": minimum, "max": maximum}


def image_extension(url: str) -> str:
    suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}:
        return suffix
    guessed = mimetypes.guess_extension(mimetypes.guess_type(url)[0] or "")
    return guessed or ".img"


def normalize_and_download(
    client: Client,
    details: list[dict[str, Any]],
    *,
    source_id: str,
    snapshot_id: str,
    city_uuid: str,
    city_slug: str,
    city_name: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    products = []
    media = []
    associations = []
    memberships = []
    review = []
    asset_urls = []
    for index, detail in enumerate(details, 1):
        listing = detail.pop("_listing")
        vendor_code = str(detail.get("vendor_code") or listing.get("vendor_code") or "").strip()
        slug = str(listing.get("slug") or "").strip()
        product_id = stable_id("product_alkoteka", vendor_code)
        attributes = attribute_map(detail)
        description_country = attribute_names(attributes, "strana")
        detail_country_code = clean_text(detail.get("country_code"))
        detail_country_name = clean_text(detail.get("country_name"))
        russian_exact = (
            detail_country_code == "RU"
            and detail_country_name == "Россия"
            and "Россия" in description_country
        )
        volume = attribute_scalar(attributes, "obem")
        vintage = attribute_scalar(attributes, "god-urozaya")
        variant_key = json.dumps(
            {"vendor_code": vendor_code, "volume": volume, "vintage": vintage},
            ensure_ascii=False,
            sort_keys=True,
        )
        wine_family_id = stable_id("family_alkoteka_pending", vendor_code)
        bottle_variant_id = stable_id("variant_alkoteka", variant_key)
        canonical_url = str(listing.get("product_url") or f"{SOURCE_BASE}/product/{detail.get('category', {}).get('slug')}/{slug}")
        image_url = clean_text(detail.get("image_url")) or clean_text(listing.get("image_url"))
        listing_image_url = clean_text(listing.get("image_url"))
        discovered_image_urls = []
        for role, candidate_url in (
            ("primary_original", clean_text(detail.get("image_url"))),
            ("listing_resize_derivative", listing_image_url),
        ):
            if candidate_url and candidate_url not in {row["url"] for row in discovered_image_urls}:
                discovered_image_urls.append({"url": candidate_url, "role": role})
        media_id = None
        label_design_id = None
        image_ok = False
        if image_url:
            media_id = stable_id("media_alkoteka", f"{vendor_code}:{image_url}")
            extension = image_extension(image_url)
            image_path = client.capture_root / "images" / f"{vendor_code}{extension}"
            try:
                client.fetch(image_url, image_path, accept="image/avif,image/webp,image/png,image/jpeg,image/*")
                probe = image_probe(image_path, calculate_dhash=True)
                digest = sha256_file(image_path)
                label_design_id = stable_id("label_design_alkoteka", digest)
                image_ok = probe["decode_status"] == "ok"
                media.append({
                    "manifest_version": "1.0.0",
                    "source_id": source_id,
                    "source_capture_id": snapshot_id,
                    "media_id": media_id,
                    "wine_family_id": wine_family_id,
                    "product_id": product_id,
                    "bottle_variant_id": bottle_variant_id,
                    "label_design_id": label_design_id,
                    "vintage": vintage,
                    "slug": None,
                    "identity_group_id": bottle_variant_id,
                    "near_duplicate_group_id": None,
                    "association_grade": "gold" if russian_exact else "bronze",
                    "role": "russian_open_world_reference",
                    "relative_path": image_path.relative_to(ROOT).as_posix(),
                    "source_url": image_url,
                    "asset_role": "primary_original" if image_url == clean_text(detail.get("image_url")) else "listing_resize_fallback",
                    "sha256": digest,
                    "bytes": image_path.stat().st_size,
                    "media_type": mimetypes.guess_type(image_path.name)[0],
                    "rights_status": "internal_noncommercial_research_pending_terms_review",
                    "quality_status": "verified_decode" if image_ok else "decode_error",
                    "image_represents_product": image_ok,
                    "parent_media_id": None,
                    **probe,
                })
            except StopCrawl:
                raise
            except Exception as exc:
                review.append({
                    "review_item_id": stable_id("review_alkoteka", f"image:{vendor_code}"),
                    "source_dataset": "16_alkoteka_ru_wines",
                    "review_state": "needs_verification",
                    "product_id": product_id,
                    "media_id": media_id,
                    "required_action": "verify_or_recapture_missing_product_image",
                    "evidence": {"source_url": image_url, "error": f"{type(exc).__name__}: {exc}"[:500]},
                    "candidates": [],
                })

        for candidate in discovered_image_urls:
            candidate_url = candidate["url"]
            candidate_media_id = media_id if candidate_url == image_url else None
            asset_urls.append({
                "asset_url_id": stable_id("asset_url_alkoteka", f"{vendor_code}:{candidate_url}"),
                "product_id": product_id,
                "external_product_id": vendor_code,
                "url": candidate_url,
                "role": candidate["role"],
                "original_asset": candidate["role"] == "primary_original",
                "downloaded": candidate_media_id is not None and image_ok,
                "media_id": candidate_media_id,
                "skip_reason": None if candidate_media_id else "resize_derivative_not_downloaded_original_retained",
            })

        product_row = {
            "source_id": source_id,
            "source_capture_id": snapshot_id,
            "catalog_id": "alkoteka",
            "product_id": product_id,
            "external_product_id": vendor_code,
            "source_uuid": clean_text(detail.get("uuid")),
            "source_slug": slug,
            "canonical_url": canonical_url,
            "name": clean_text(detail.get("name")),
            "alternate_name": clean_text(detail.get("subname")),
            "category_name": clean_text((detail.get("category") or {}).get("name")),
            "category_slug": clean_text((detail.get("category") or {}).get("slug")),
            "discovered_root_categories": listing.get("discovered_root_categories") or [],
            "wine_family_id": wine_family_id,
            "family_identity_status": "source_product_provisional_pending_cross_source_review",
            "bottle_variant_id": bottle_variant_id,
            "label_design_id": label_design_id,
            "vintage": vintage,
            "volume_l": volume,
            "alcohol_percent": attribute_scalar(attributes, "krepost"),
            "brand": attribute_names(attributes, "brend"),
            "producer": attribute_names(attributes, "proizvoditel"),
            "country_code": detail_country_code,
            "country_name": detail_country_name,
            "region": attribute_names(attributes, "region"),
            "color": attribute_names(attributes, "cvet"),
            "sugar": attribute_names(attributes, "soderzanie-saxara"),
            "grapes": attribute_names(attributes, "sortovoi-sostav"),
            "production_method": attribute_names(attributes, "metod-proizvodstva"),
            "wine_type": attribute_names(attributes, "vid"),
            "attributes": attributes,
            "description_blocks": [
                {"title": clean_text(block.get("title")), "content_html": clean_text(block.get("content"))}
                for block in detail.get("text_blocks") or []
                if isinstance(block, dict)
            ],
            "primary_image_url": image_url,
            "discovered_image_urls": discovered_image_urls,
            "image_api_shape": "one detail image_url plus one listing resize derivative; no gallery field exposed",
            "primary_media_id": media_id,
            "usable_primary_media_id": media_id if image_ok else None,
            "primary_media_status": "downloaded_unreviewed" if image_ok else "missing_or_decode_error",
            "country_evidence": {
                "api_country_code": detail_country_code,
                "api_country_name": detail_country_name,
                "description_block_values": description_country,
                "catalog_filter": "options[strana][]=rossiya",
            },
            "russian_origin_status": "gold_source_explicit" if russian_exact else "needs_verification",
            "price_snapshot": {
                "price": detail.get("price"),
                "previous_price": detail.get("prev_price"),
                "price_mode": clean_text(detail.get("price_mode")),
                "available": detail.get("available"),
                "quantity_total": detail.get("quantity_total"),
            },
            "catalog_context": {
                "city_uuid": city_uuid,
                "city_slug": city_slug,
                "city_name": city_name,
            },
            "svoe_vino_slug": None,
            "svoe_crosswalk_status": "not_attempted_no_forced_match",
            "rights_status": "internal_noncommercial_research_pending_terms_review",
        }
        products.append(product_row)
        memberships.append({
            "catalog_membership_id": stable_id("membership_alkoteka", f"{snapshot_id}:{vendor_code}"),
            "catalog_id": "alkoteka",
            "snapshot_id": snapshot_id,
            "external_product_id": vendor_code,
            "product_id": product_id,
            "bottle_variant_id": bottle_variant_id,
            "source_url": canonical_url,
            "city_context": city_slug,
            "membership_status": "listed",
            "country_filter": COUNTRY_FILTER,
        })
        if media_id:
            associations.append({
                "association_id": stable_id("assoc_alkoteka", f"{vendor_code}:{media_id}"),
                "product_id": product_id,
                "external_product_id": vendor_code,
                "media_id": media_id,
                "association_grade": "gold" if russian_exact and image_ok else "bronze",
                "association_evidence": "same Alkoteca product API record",
                "source_sku_exact": True,
                "image_represents_product": image_ok,
                "russian_origin_source_explicit": russian_exact,
                "image_decode_ok": image_ok,
                "eligible_for_source_sku_supervision_by_identity": russian_exact and image_ok,
                "eligible_for_training_under_rights": False,
                "training_rights_gate": "pending_terms_and_asset_rights_review",
                "svoe_vino_slug": None,
            })
        if not russian_exact:
            review.append({
                "review_item_id": stable_id("review_alkoteka", f"origin:{vendor_code}"),
                "source_dataset": "16_alkoteka_ru_wines",
                "review_state": "needs_verification",
                "product_id": product_id,
                "media_id": media_id,
                "required_action": "verify_russian_origin_from_product_card",
                "evidence": product_row["country_evidence"],
                "candidates": [],
            })
        if not image_url:
            review.append({
                "review_item_id": stable_id("review_alkoteka", f"missing-image:{vendor_code}"),
                "source_dataset": "16_alkoteka_ru_wines",
                "review_state": "needs_verification",
                "product_id": product_id,
                "media_id": None,
                "required_action": "verify_missing_product_image",
                "evidence": {"canonical_url": canonical_url},
                "candidates": [],
            })
        if index % 25 == 0 or index == len(details):
            print(
                f"images {index}/{len(details)}: media={len(media)}, "
                f"decode_ok={sum(row['decode_status'] == 'ok' for row in media)}, review={len(review)}",
                flush=True,
            )
    return products, media, associations, memberships, review, asset_urls


def apply_image_identity_gates(
    products: list[dict[str, Any]],
    media: list[dict[str, Any]],
    associations: list[dict[str, Any]],
    review: list[dict[str, Any]],
) -> dict[str, Any]:
    """Exclude placeholders and route cross-SKU exact images to review."""
    product_by_id = {row["product_id"]: row for row in products}
    association_by_media = {row["media_id"]: row for row in associations}
    media_by_sha: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in media:
        media_by_sha[row["sha256"]].append(row)

    placeholder_media = []
    shared_groups = []
    for digest, group in sorted(media_by_sha.items()):
        duplicate_group_id = stable_id("exactdup_alkoteka", digest) if len(group) > 1 else None
        is_placeholder_group = all("product_no_image" in str(row.get("source_url") or "") for row in group)
        if is_placeholder_group:
            for media_row in group:
                media_row["exact_duplicate_group_id"] = duplicate_group_id
                media_row["quality_status"] = "placeholder_not_product"
                media_row["role"] = "excluded_placeholder"
                media_row["image_represents_product"] = False
                assoc = association_by_media[media_row["media_id"]]
                assoc["association_grade"] = "rejected"
                assoc["image_represents_product"] = False
                assoc["eligible_for_source_sku_supervision_by_identity"] = False
                assoc["identity_gate"] = "source_placeholder_not_product_image"
                product = product_by_id[media_row["product_id"]]
                product["usable_primary_media_id"] = None
                product["primary_media_status"] = "placeholder_not_product"
                review.append({
                    "review_item_id": stable_id("review_alkoteka", f"placeholder:{product['external_product_id']}"),
                    "source_dataset": "16_alkoteka_ru_wines",
                    "review_state": "needs_verification",
                    "product_id": product["product_id"],
                    "media_id": media_row["media_id"],
                    "required_action": "find_or_capture_real_product_image; current source asset is a placeholder",
                    "evidence": {
                        "external_product_id": product["external_product_id"],
                        "source_url": media_row["source_url"],
                        "sha256": digest,
                    },
                    "candidates": [],
                })
                placeholder_media.append(media_row["media_id"])
            continue
        if len(group) <= 1:
            group[0]["exact_duplicate_group_id"] = None
            product_by_id[group[0]["product_id"]]["primary_media_status"] = "decoded_unique_exact_asset"
            continue
        media_ids = []
        products_in_group = []
        for media_row in group:
            media_row["exact_duplicate_group_id"] = duplicate_group_id
            media_row["quality_status"] = "decoded_shared_exact_image_needs_identity_review"
            assoc = association_by_media[media_row["media_id"]]
            assoc["eligible_for_source_sku_supervision_by_identity"] = False
            assoc["identity_gate"] = "same_exact_image_used_by_multiple_source_skus"
            product = product_by_id[media_row["product_id"]]
            product["primary_media_status"] = "shared_exact_image_needs_identity_review"
            media_ids.append(media_row["media_id"])
            products_in_group.append({
                "product_id": product["product_id"],
                "external_product_id": product["external_product_id"],
                "name": product["name"],
                "bottle_variant_id": product["bottle_variant_id"],
            })
        review.append({
            "review_item_id": stable_id("review_alkoteka", f"exactdup:{digest}"),
            "source_dataset": "16_alkoteka_ru_wines",
            "review_state": "needs_verification",
            "group_id": duplicate_group_id,
            "required_action": "verify whether the shared exact source image represents every SKU and assign variant/design relation",
            "evidence": {"sha256": digest, "media_ids": media_ids},
            "candidates": products_in_group,
        })
        shared_groups.append({
            "group_id": duplicate_group_id,
            "sha256": digest,
            "media_ids": media_ids,
            "products": products_in_group,
        })
    return {
        "placeholder_media": placeholder_media,
        "shared_non_placeholder_groups": shared_groups,
    }


def scan_detail_image_schema(details: list[dict[str, Any]], asset_urls: list[dict[str, Any]]) -> dict[str, Any]:
    field_occurrences: Counter[str] = Counter()
    urls_by_path: dict[str, set[str]] = defaultdict(set)

    def walk(value: Any, path: str = "results") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                key_folded = str(key).casefold()
                if any(token in key_folded for token in ("image", "photo", "gallery")):
                    field_occurrences[child_path] += 1
                    if isinstance(child, str) and child.startswith(("http://", "https://")):
                        urls_by_path[child_path].add(child)
                walk(child, child_path)
        elif isinstance(value, list):
            for child in value:
                walk(child, f"{path}[]")

    for detail in details:
        walk(detail)
    observed_urls = set().union(*urls_by_path.values()) if urls_by_path else set()
    accounted_urls = {row["url"] for row in asset_urls}
    gallery_like_paths = sorted(
        path for path in field_occurrences
        if path != "results.image_url"
    )
    return {
        "detail_records_scanned": len(details),
        "image_like_field_occurrences": dict(sorted(field_occurrences.items())),
        "distinct_urls_by_path": {path: len(urls) for path, urls in sorted(urls_by_path.items())},
        "observed_detail_image_urls": len(observed_urls),
        "all_observed_detail_image_urls_accounted": observed_urls.issubset(accounted_urls),
        "gallery_or_additional_image_paths": gallery_like_paths,
        "api_exposes_only_single_primary_image_url": gallery_like_paths == [] and set(field_occurrences) == {"results.image_url"},
    }


def audit(
    *,
    listings: list[dict[str, Any]],
    details: list[dict[str, Any]],
    detail_errors: list[dict[str, Any]],
    products: list[dict[str, Any]],
    media: list[dict[str, Any]],
    associations: list[dict[str, Any]],
    asset_urls: list[dict[str, Any]],
    image_gates: dict[str, Any],
    roots_summary: dict[str, Any],
    static: dict[str, Any],
    client: Client,
    source_id: str,
    snapshot_id: str,
) -> dict[str, Any]:
    product_ids = {row["product_id"] for row in products}
    media_ids = {row["media_id"] for row in media}
    association_by_media = {row["media_id"]: row for row in associations}
    vendor_codes = [row["external_product_id"] for row in products]
    media_by_sha: dict[str, list[str]] = defaultdict(list)
    for row in media:
        media_by_sha[row["sha256"]].append(row["media_id"])
    duplicate_groups = [group for group in media_by_sha.values() if len(group) > 1]
    image_schema = scan_detail_image_schema(details, asset_urls)
    checks = {
        "all_listed_products_have_details": len(details) == len(listings) and not detail_errors,
        "unique_source_sku": len(vendor_codes) == len(set(vendor_codes)),
        "all_products_source_explicit_russia": all(row["russian_origin_status"] == "gold_source_explicit" for row in products),
        "all_products_have_decoded_media": len(media) == len(products) and all(row["decode_status"] == "ok" for row in media),
        "all_associations_referential": all(
            row["product_id"] in product_ids and row["media_id"] in media_ids
            for row in associations
        ),
        "all_source_sku_associations_exact": len(associations) == len(products) and all(row["source_sku_exact"] for row in associations),
        "all_identity_unsafe_images_gated": all(
            (row.get("quality_status") not in {"placeholder_not_product", "decoded_shared_exact_image_needs_identity_review"})
            or not association_by_media[row["media_id"]]["eligible_for_source_sku_supervision_by_identity"]
            for row in media
        ),
        "all_detail_image_urls_accounted": image_schema["all_observed_detail_image_urls_accounted"],
        "all_original_detail_images_downloaded": all(
            row["downloaded"] for row in asset_urls if row["role"] == "primary_original"
        ),
        "no_403_or_429": client.hard_stop is None,
        "training_rights_remain_gated": all(not row["eligible_for_training_under_rights"] for row in associations),
        "no_forced_svoe_crosswalk": all(row["svoe_vino_slug"] is None for row in products),
    }
    return {
        "manifest_version": "1.0.0",
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "capture_completed_at_utc": utc_now(),
        "catalog_context": {"city_uuid": CITY_UUID, "city_slug": CITY_SLUG, "city_name": CITY_NAME},
        "scope": {
            "root_categories": list(ROOT_CATEGORIES),
            "country_filter": COUNTRY_FILTER,
            "coverage_claim": "products returned by the two public category API filters in the fixed city context",
            "does_not_claim": "all historic, delisted, or every-city-only Alkoteca products",
        },
        "static_capture": static,
        "roots": roots_summary,
        "counts": {
            "unique_listed_products": len(listings),
            "product_details": len(details),
            "detail_errors": len(detail_errors),
            "normalized_products": len(products),
            "explicit_russian_products": sum(row["russian_origin_status"] == "gold_source_explicit" for row in products),
            "media": len(media),
            "decoded_media": sum(row["decode_status"] == "ok" for row in media),
            "decode_errors": sum(row["decode_status"] != "ok" for row in media),
            "exact_product_media_associations": len(associations),
            "identity_eligible_product_media_associations": sum(
                row["eligible_for_source_sku_supervision_by_identity"] for row in associations
            ),
            "placeholder_media_excluded": len(image_gates["placeholder_media"]),
            "shared_non_placeholder_exact_image_groups_for_review": len(image_gates["shared_non_placeholder_groups"]),
            "shared_non_placeholder_media_for_review": sum(
                len(row["media_ids"]) for row in image_gates["shared_non_placeholder_groups"]
            ),
            "discovered_unique_image_urls": len({row["url"] for row in asset_urls}),
            "primary_original_image_urls": sum(row["role"] == "primary_original" for row in asset_urls),
            "listing_resize_derivative_urls": sum(row["role"] == "listing_resize_derivative" for row in asset_urls),
            "additional_gallery_image_urls": 0,
            "exact_duplicate_image_groups": len(duplicate_groups),
            "network_objects_accounted": len(client.records),
            "fetch_statuses": dict(Counter(row["fetch_status"] for row in client.records)),
        },
        "exact_duplicate_media_groups": duplicate_groups,
        "detail_image_schema_audit": image_schema,
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "rights": {
            "purpose": "noncommercial_research",
            "training_use": "pending_terms_and_asset_rights_review",
            "attribution": "source_url_capture_time_and_city_context_required",
            "derivatives": "legal_review",
            "redistribution": "not_confirmed",
        },
        "hard_stop": client.hard_stop,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-date", default=str(date.today()))
    parser.add_argument("--city-uuid", default=CITY_UUID)
    parser.add_argument("--city-slug", default=CITY_SLUG)
    parser.add_argument("--city-name", default=CITY_NAME)
    parser.add_argument("--interval", type=float, default=0.4, help="minimum seconds between every network request")
    parser.add_argument("--retries", type=int, default=2, help="retries for transient errors; never used for 403/429")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--max-products", type=int, default=None, help="bounded pilot/debug run")
    args = parser.parse_args()

    capture_root = ROOT / "Dataset/00_raw/16_alkoteka_ru_wines" / args.capture_date
    tables = ROOT / "Dataset/16_alkoteka_ru_wines/tables"
    review_root = ROOT / "Dataset/16_alkoteka_ru_wines/review"
    source_id = f"alkoteka-russian-wine-web-{args.capture_date}-{args.city_slug}"
    snapshot_id = stable_id("capture_alkoteka", f"{args.capture_date}:{args.city_uuid}")
    capture_root.mkdir(parents=True, exist_ok=True)
    write_json(capture_root / "CAPTURE-CONTEXT.json", {
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "capture_date": args.capture_date,
        "source_url": f"{SOURCE_BASE}/catalog/",
        "api_base": f"{SOURCE_BASE}/web-api/v1",
        "asset_origin": ASSET_BASE,
        "user_agent": USER_AGENT,
        "request_interval_seconds": args.interval,
        "retries_transient_only": args.retries,
        "hard_stop_status_codes": [403, 429],
        "city_context": {"uuid": args.city_uuid, "slug": args.city_slug, "name": args.city_name},
        "root_categories": list(ROOT_CATEGORIES),
        "country_filter": COUNTRY_FILTER,
    })
    client = Client(
        capture_root=capture_root,
        interval=args.interval,
        retries=args.retries,
        timeout=args.timeout,
    )
    try:
        static = capture_static(client)
        listings, roots_summary = fetch_catalog_lists(
            client,
            city_uuid=args.city_uuid,
            per_page=args.per_page,
            max_products=args.max_products,
        )
        details, detail_errors = fetch_details(client, listings, city_uuid=args.city_uuid)
        products, media, associations, memberships, review, asset_urls = normalize_and_download(
            client,
            details,
            source_id=source_id,
            snapshot_id=snapshot_id,
            city_uuid=args.city_uuid,
            city_slug=args.city_slug,
            city_name=args.city_name,
        )
        image_gates = apply_image_identity_gates(products, media, associations, review)
        for rows in (associations, memberships, review, asset_urls, detail_errors):
            for row in rows:
                row.setdefault("source_id", source_id)
                row.setdefault("source_capture_id", snapshot_id)
        summary = audit(
            listings=listings,
            details=details,
            detail_errors=detail_errors,
            products=products,
            media=media,
            associations=associations,
            asset_urls=asset_urls,
            image_gates=image_gates,
            roots_summary=roots_summary,
            static=static,
            client=client,
            source_id=source_id,
            snapshot_id=snapshot_id,
        )
    except StopCrawl as exc:
        write_jsonl(capture_root / "RESPONSE-MANIFEST.jsonl", (
            {"source_id": source_id, "source_capture_id": snapshot_id, **row}
            for row in client.records
        ))
        write_json(capture_root / "HARD-STOP.json", {
            "stopped_at_utc": utc_now(),
            "reason": str(exc),
            "detail": client.hard_stop,
            "policy": "no retry, header rotation, cookie rotation, proxying, or access-control bypass",
        })
        print(f"HARD STOP: {exc}", file=sys.stderr, flush=True)
        return 3

    tables.mkdir(parents=True, exist_ok=True)
    write_jsonl(capture_root / "RESPONSE-MANIFEST.jsonl", (
        {"source_id": source_id, "source_capture_id": snapshot_id, **row}
        for row in client.records
    ))
    write_jsonl(tables / "products.jsonl", products)
    write_jsonl(tables / "media.jsonl", media)
    write_jsonl(tables / "associations.jsonl", associations)
    write_jsonl(tables / "catalog_memberships.jsonl", memberships)
    write_jsonl(tables / "asset_urls.jsonl", asset_urls)
    write_jsonl(tables / "detail_errors.jsonl", detail_errors)
    write_json(tables / "SUMMARY.json", summary)
    write_jsonl(review_root / "needs_verification/queue.jsonl", review)
    write_jsonl(review_root / "needs_annotation/queue.jsonl", [])
    (review_root / "verified").mkdir(parents=True, exist_ok=True)
    (review_root / "rejected").mkdir(parents=True, exist_ok=True)
    for decision_path in (review_root / "verified/decisions.jsonl", review_root / "rejected/decisions.jsonl"):
        if not decision_path.exists():
            decision_path.touch()
    write_json(review_root / "STATUS.json", {
        "contract_version": "1.0.0",
        "source_dataset": "16_alkoteka_ru_wines",
        "generated_queues": {
            "needs_verification": len(review),
            "needs_annotation": 0,
        },
        "human_decision_logs": {
            "verified": "verified/decisions.jsonl",
            "rejected": "rejected/decisions.jsonl",
        },
        "media_copy_policy": "reference_by_media_id_and_relative_path_only",
    })
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0 if summary["all_checks_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
