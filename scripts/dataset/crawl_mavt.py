#!/usr/bin/env python3
"""Collect a robots-aware snapshot of Russian wine product pages from MAVT.

The collector deliberately does not use the site's faceted or pagination URLs:
robots.txt disallows generic query parameters and ``/filter/``.  Discovery is
limited to the public XML sitemap.  Product pages are scanned with one honest
User-Agent and a global request interval; only pages whose product property
explicitly says Russia are retained as raw HTML.  A 403 or 429 stops the run.

Raw response bodies are never rewritten.  Derived manifests are regenerated
from checkpoints, making an interrupted polite scan resumable.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import html as html_lib
import json
import mimetypes
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from lxml import html

from common import image_probe, relative_posix, sha256_file, stable_id, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DATE = "2026-09-15"
SOURCE_ID = f"mavt-ru-wines-{CAPTURE_DATE}"
CAPTURE_ID = "mavt-capture-20260915"
USER_AGENT = "VinoDatasetResearch/1.0"
BASE = "https://mavt.ru"
SEEDS = {
    "robots.txt": f"{BASE}/robots.txt",
    "sitemap.xml": f"{BASE}/sitemap.xml",
    "sitemap-iblock-9.xml": f"{BASE}/sitemap-iblock-9.xml",
    "russian-category.html": f"{BASE}/catalog/wine/vino-rossiya/",
    "agreement.html": f"{BASE}/agreement/",
    "policy.html": f"{BASE}/policy/",
}
BLOCK_STATUS = {403, 429}
BLOCK_MARKERS = (
    b"access denied",
    b"checking your browser",
    b"captcha",
    b"too many requests",
)
PRODUCT_RE = re.compile(r"^https://mavt\.ru/catalog/id/(\d+)/$")


class CrawlStopped(RuntimeError):
    """Raised when the remote site asks this collector to stop."""


class PoliteGate:
    def __init__(self, interval: float) -> None:
        self.interval = interval
        self.lock = threading.Lock()
        self.last_started = 0.0

    def wait(self) -> None:
        with self.lock:
            delay = self.interval - (time.monotonic() - self.last_started)
            if delay > 0:
                time.sleep(delay)
            self.last_started = time.monotonic()


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = html_lib.unescape(str(value)).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_headers(headers: Any) -> dict[str, str]:
    """Keep reproducibility headers without persisting cookies or identifiers."""

    allowed = {
        "content-type",
        "content-length",
        "content-encoding",
        "etag",
        "last-modified",
        "cache-control",
        "expires",
        "vary",
    }
    return {
        str(key).lower(): str(value)
        for key, value in headers.items()
        if str(key).lower() in allowed
    }


def decode_http_body(payload: bytes, headers: dict[str, str]) -> bytes:
    encoding = headers.get("content-encoding", "").lower()
    if encoding == "gzip":
        return gzip.decompress(payload)
    return payload


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.part")
    temp.write_bytes(payload)
    temp.replace(path)


def fetch(
    url: str,
    gate: PoliteGate,
    *,
    accept: str,
    compressed: bool,
    retries: int,
    stop_event: threading.Event,
) -> tuple[int, bytes, dict[str, str], str]:
    if stop_event.is_set():
        raise CrawlStopped("run already stopped")
    error: Exception | None = None
    for attempt in range(retries + 1):
        if stop_event.is_set():
            raise CrawlStopped("run already stopped")
        try:
            gate.wait()
            headers = {
                "User-Agent": USER_AGENT,
                "Accept": accept,
                "Connection": "close",
            }
            if compressed:
                headers["Accept-Encoding"] = "gzip"
            parts = urllib.parse.urlsplit(url)
            request_url = urllib.parse.urlunsplit(
                (
                    parts.scheme,
                    parts.netloc,
                    urllib.parse.quote(urllib.parse.unquote(parts.path), safe="/!$&'()*+,;=:@-._~"),
                    parts.query,
                    "",
                )
            )
            request = urllib.request.Request(request_url, headers=headers)
            with urllib.request.urlopen(request, timeout=45) as response:
                status = int(getattr(response, "status", 200))
                body = response.read()
                result_headers = safe_headers(response.headers)
                final_url = response.geturl()
            if status in BLOCK_STATUS:
                stop_event.set()
                raise CrawlStopped(f"HTTP {status} for {url}")
            decoded_prefix = decode_http_body(body, result_headers)[:100_000].lower()
            if status == 200 and any(marker in decoded_prefix for marker in BLOCK_MARKERS):
                stop_event.set()
                raise CrawlStopped(f"block marker in HTTP 200 response for {url}")
            return status, body, result_headers, final_url
        except urllib.error.HTTPError as exc:
            if exc.code in BLOCK_STATUS:
                stop_event.set()
                raise CrawlStopped(f"HTTP {exc.code} for {url}") from exc
            error = exc
            if exc.code < 500 or attempt >= retries:
                raise
        except CrawlStopped:
            raise
        except Exception as exc:  # network errors are retried but reported
            error = exc
            if attempt >= retries:
                raise
        time.sleep(min(2 ** (attempt + 1), 8))
    assert error is not None
    raise error


def capture_seeds(capture: Path, gate: PoliteGate, stop_event: threading.Event) -> None:
    headers_dir = capture / "headers"
    headers_dir.mkdir(parents=True, exist_ok=True)
    for filename, url in SEEDS.items():
        target = capture / filename
        header_target = headers_dir / f"{filename}.json"
        if target.exists() and header_target.exists():
            continue
        status, body, response_headers, final_url = fetch(
            url,
            gate,
            accept="text/plain,application/xml,text/html;q=0.9,*/*;q=0.1",
            compressed=False,
            retries=2,
            stop_event=stop_event,
        )
        if status != 200:
            raise RuntimeError(f"seed returned HTTP {status}: {url}")
        atomic_bytes(target, body)
        write_json(
            header_target,
            {
                "requested_url": url,
                "final_url": final_url,
                "status": status,
                "captured_at": now_utc(),
                "request_user_agent": USER_AGENT,
                "response_headers": response_headers,
                "body_bytes": len(body),
                "body_sha256": sha256_bytes(body),
            },
        )


def robots_gate(capture: Path, urls: Iterable[str]) -> None:
    robots_path = capture / "robots.txt"
    robots_text = robots_path.read_text(encoding="utf-8", errors="replace")
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(robots_text.splitlines())
    failures = []
    for url in urls:
        parts = urllib.parse.urlsplit(url)
        if parts.query or not PRODUCT_RE.fullmatch(url):
            failures.append({"url": url, "reason": "not a canonical query-free product URL"})
        elif not parser.can_fetch(USER_AGENT, url):
            failures.append({"url": url, "reason": "robots.txt disallows product URL"})
    if failures:
        raise RuntimeError(f"robots gate rejected {len(failures)} product URLs: {failures[:3]}")
    if "Allow: /upload/" not in robots_text:
        raise RuntimeError("robots policy no longer explicitly allows /upload/; review required")


def sitemap_product_urls(path: Path) -> list[str]:
    root = ET.parse(path).getroot()
    locations = [
        (element.text or "").strip()
        for element in root.iter()
        if element.tag.endswith("loc") and element.text
    ]
    wine_root = f"{BASE}/catalog/wine/"
    next_root = f"{BASE}/catalog/strong_alcohol/"
    try:
        start = locations.index(wine_root)
        end = locations.index(next_root)
    except ValueError as exc:
        raise RuntimeError("sitemap category boundaries changed; manual review required") from exc
    urls = [url for url in locations[start + 1 : end] if PRODUCT_RE.fullmatch(url)]
    if len(urls) != len(set(urls)):
        raise RuntimeError("duplicate product URL in wine sitemap segment")
    return urls


def xpath_text(node: Any, expression: str) -> str | None:
    values = node.xpath(expression)
    if not values:
        return None
    value = values[0]
    if hasattr(value, "text_content"):
        value = value.text_content()
    return clean_text(value)


def parse_product(decoded: bytes, url: str) -> dict[str, Any]:
    requested_id = PRODUCT_RE.fullmatch(url).group(1)  # type: ignore[union-attr]
    tree = html.fromstring(decoded)
    roots = tree.xpath('//div[@id="catalog_detail" and @data-id]')
    if not roots:
        return {
            "parse_status": "missing_product_root",
            "external_product_id": requested_id,
            "country": None,
            "is_russian": False,
        }
    root = roots[0]
    rendered_id = clean_text(root.get("data-id"))
    title = xpath_text(tree, '(//div[contains(concat(" ",normalize-space(@class)," ")," content-right ")]//h1)[1]')
    if not title:
        title = xpath_text(root, '(.//meta[@itemprop="name"]/@content)[1]')
    category = xpath_text(root, '(.//meta[@itemprop="category"]/@content)[1]')
    description = xpath_text(root, '(.//meta[@itemprop="description"]/@content)[1]')
    image_assets: list[dict[str, str]] = []
    seen_images: set[str] = set()
    primary_values = {str(value) for value in root.xpath('.//meta[@itemprop="image"]/@content')}
    # Product galleries differ between templates.  The outer Bitrix component
    # also contains a "similar products" carousel, so product assets are
    # restricted to itemprop=image plus nodes inside the product main/gallery
    # presentation area.  Recommendation cards are never associated to the
    # current SKU.
    for element in root.xpath('.//*[@content or @src or @data-src or @href or @data-image]'):
        classes = " ".join(
            str(ancestor.get("class") or "").casefold()
            for ancestor in [element, *element.iterancestors()]
        )
        inside_product_presentation = any(
            marker in classes
            for marker in (
                "catalog-element__main-wrapper",
                "catalog-element__image",
                "catalog-element__photo",
                "catalog-element__gallery",
            )
        )
        excluded_carousel = any(
            marker in classes
            for marker in (
                "catalog-element__similar-products",
                "catalog-element__recommendations",
                "catalog-lenta",
                "catalog-item-v2",
            )
        )
        for attribute in ("content", "src", "data-src", "href", "data-image"):
            value = element.get(attribute)
            if not value or "/upload/" not in value:
                continue
            is_primary_evidence = value in primary_values
            if not is_primary_evidence and (not inside_product_presentation or excluded_carousel):
                continue
            absolute = urllib.parse.urljoin(BASE, value)
            parts = urllib.parse.urlsplit(absolute)
            suffix = Path(urllib.parse.unquote(parts.path)).suffix.lower()
            if (
                parts.scheme != "https"
                or parts.netloc.lower() not in {"mavt.ru", "www.mavt.ru"}
                or not parts.path.startswith("/upload/")
                or suffix not in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
            ):
                continue
            canonical = urllib.parse.urlunsplit((parts.scheme, "mavt.ru", parts.path, "", ""))
            if canonical in seen_images:
                continue
            seen_images.add(canonical)
            image_assets.append(
                {
                    "url": canonical,
                    "role": "primary" if is_primary_evidence or not image_assets else "gallery",
                    "evidence_attribute": attribute,
                }
            )
    image_urls = [asset["url"] for asset in image_assets]
    article = xpath_text(root, '(.//div[contains(concat(" ",normalize-space(@class)," ")," catalog-element__acticle ")])[1]')
    if article:
        article = clean_text(re.sub(r"^Артикул\s*:\s*", "", article, flags=re.I))

    properties: dict[str, str] = {}
    property_conflicts: dict[str, list[str]] = {}
    for item in root.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," display-properties__item ")]'):
        key = xpath_text(item, '(.//div[contains(concat(" ",normalize-space(@class)," ")," display-properties__item__title ")])[1]')
        value = xpath_text(item, '(.//div[contains(concat(" ",normalize-space(@class)," ")," display-properties__item__value ")])[1]')
        if not key or not value:
            continue
        key = re.sub(r"\s*:\s*$", "", key)
        if key in properties and properties[key] != value:
            property_conflicts.setdefault(key, [properties[key]])
            if value not in property_conflicts[key]:
                property_conflicts[key].append(value)
        else:
            properties.setdefault(key, value)
    country = properties.get("Страна")
    status = "ok"
    if rendered_id != requested_id:
        status = "product_id_mismatch"
    elif not title or not country:
        status = "missing_required_fields"
    return {
        "parse_status": status,
        "external_product_id": requested_id,
        "rendered_product_id": rendered_id,
        "external_article": article,
        "title": title,
        "category": category,
        "description": description,
        "country": country,
        "country_evidence": {"property": "Страна", "value": country} if country else None,
        "is_russian": bool(country and country.casefold().startswith("россия")),
        "properties": properties,
        "property_conflicts": property_conflicts,
        "image_assets": image_assets,
        "image_urls": image_urls,
        "primary_image_url": image_urls[0] if image_urls else None,
    }


def load_latest_jsonl(path: Path, key: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            value = row.get(key)
            if value:
                rows[str(value)] = row
    return rows


def scan_one(url: str, capture: Path, gate: PoliteGate, stop_event: threading.Event, retries: int) -> dict[str, Any]:
    product_id = PRODUCT_RE.fullmatch(url).group(1)  # type: ignore[union-attr]
    base = {
        "source_id": SOURCE_ID,
        "source_capture_id": CAPTURE_ID,
        "url": url,
        "external_product_id": product_id,
        "scanned_at": now_utc(),
    }
    try:
        status, body, response_headers, final_url = fetch(
            url,
            gate,
            accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
            compressed=True,
            retries=retries,
            stop_event=stop_event,
        )
        base.update(
            http_status=status,
            final_url=final_url,
            response_headers=response_headers,
            response_body_bytes=len(body),
            response_body_sha256=sha256_bytes(body),
        )
        if status != 200:
            base.update(scan_status="http_error", parse_status="not_parsed", is_russian=False)
            return base
        decoded = decode_http_body(body, response_headers)
        parsed = parse_product(decoded, url)
        base.update(scan_status="ok", decoded_bytes=len(decoded), decoded_sha256=sha256_bytes(decoded), **parsed)
        if parsed["is_russian"]:
            suffix = ".html.gz" if response_headers.get("content-encoding", "").lower() == "gzip" else ".html"
            target = capture / "pages" / f"{product_id}{suffix}"
            atomic_bytes(target, body)
            base["raw_page_path"] = relative_posix(target, ROOT / "Dataset")
        else:
            base["raw_page_path"] = None
        return base
    except CrawlStopped as exc:
        return {**base, "scan_status": "blocked_stop", "error": str(exc), "is_russian": False}
    except urllib.error.HTTPError as exc:
        return {**base, "scan_status": "http_error", "http_status": exc.code, "error": f"HTTPError: {exc}", "is_russian": False}
    except Exception as exc:
        return {**base, "scan_status": "error", "error": f"{type(exc).__name__}: {exc}"[:1000], "is_russian": False}


def scan_products(
    urls: list[str],
    capture: Path,
    gate: PoliteGate,
    stop_event: threading.Event,
    *,
    workers: int,
    retries: int,
) -> dict[str, dict[str, Any]]:
    checkpoint = capture / "scan_checkpoint.jsonl"
    rows = load_latest_jsonl(checkpoint, "url")
    completed = {url for url, row in rows.items() if row.get("scan_status") in {"ok", "http_error"}}
    pending = [url for url in urls if url not in completed]
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint.open("a", encoding="utf-8", newline="\n") as log:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(scan_one, url, capture, gate, stop_event, retries): url
                for url in pending
            }
            processed = 0
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                rows[row["url"]] = row
                log.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                log.flush()
                processed += 1
                if row.get("scan_status") == "blocked_stop":
                    stop_event.set()
                    for other in futures:
                        other.cancel()
                    write_json(
                        capture / "STOP.json",
                        {
                            "stopped_at": now_utc(),
                            "reason": row.get("error"),
                            "url": row.get("url"),
                            "policy": "No retry or bypass after HTTP 403/429/block marker.",
                        },
                    )
                    break
                if processed % 100 == 0 or processed == len(pending):
                    counts = Counter(item.get("scan_status") for item in rows.values())
                    russian = sum(bool(item.get("is_russian")) for item in rows.values())
                    print(f"Scanned {len(completed) + processed}/{len(urls)}: {dict(counts)}, Russian={russian}", flush=True)
    return rows


def allowed_image_url(url: str, robots_text: str) -> bool:
    parts = urllib.parse.urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.netloc.lower() in {"mavt.ru", "www.mavt.ru"}
        and parts.path.startswith("/upload/")
        and not parts.query
        and "Allow: /upload/" in robots_text
    )


def image_suffix(url: str, content_type: str | None) -> str:
    suffix = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"}:
        return suffix
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip())
    return guessed or ".bin"


def download_image_one(url: str, capture: Path, gate: PoliteGate, stop_event: threading.Event, retries: int) -> dict[str, Any]:
    url_id = stable_id("mavt_asset", url, 24)
    base = {"source_id": SOURCE_ID, "image_url": url, "url_asset_id": url_id, "downloaded_at": now_utc()}
    try:
        status, body, response_headers, final_url = fetch(
            url,
            gate,
            accept="image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.1",
            compressed=False,
            retries=retries,
            stop_event=stop_event,
        )
        base.update(http_status=status, final_url=final_url, response_headers=response_headers)
        if status != 200:
            base.update(download_status="http_error")
            return base
        suffix = image_suffix(final_url, response_headers.get("content-type"))
        target = capture / "images" / f"{url_id}{suffix}"
        atomic_bytes(target, body)
        probe = image_probe(target, calculate_dhash=True)
        base.update(
            download_status="ok",
            relative_path=relative_posix(target, ROOT / "Dataset"),
            bytes=len(body),
            sha256=sha256_bytes(body),
            media_type=response_headers.get("content-type", "").split(";", 1)[0] or None,
            **probe,
        )
        return base
    except CrawlStopped as exc:
        return {**base, "download_status": "blocked_stop", "error": str(exc)}
    except urllib.error.HTTPError as exc:
        return {**base, "download_status": "http_error", "http_status": exc.code, "error": f"HTTPError: {exc}"}
    except Exception as exc:
        return {**base, "download_status": "error", "error": f"{type(exc).__name__}: {exc}"[:1000]}


def download_images(
    urls: list[str],
    capture: Path,
    gate: PoliteGate,
    stop_event: threading.Event,
    *,
    workers: int,
    retries: int,
) -> dict[str, dict[str, Any]]:
    checkpoint = capture / "image_checkpoint.jsonl"
    rows = load_latest_jsonl(checkpoint, "image_url")
    completed = {url for url, row in rows.items() if row.get("download_status") in {"ok", "http_error"}}
    pending = [url for url in urls if url not in completed]
    with checkpoint.open("a", encoding="utf-8", newline="\n") as log:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(download_image_one, url, capture, gate, stop_event, retries): url
                for url in pending
            }
            processed = 0
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                rows[row["image_url"]] = row
                log.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                log.flush()
                processed += 1
                if row.get("download_status") == "blocked_stop":
                    stop_event.set()
                    for other in futures:
                        other.cancel()
                    write_json(
                        capture / "STOP.json",
                        {
                            "stopped_at": now_utc(),
                            "reason": row.get("error"),
                            "url": row.get("image_url"),
                            "policy": "No retry or bypass after HTTP 403/429/block marker.",
                        },
                    )
                    break
                if processed % 50 == 0 or processed == len(pending):
                    counts = Counter(item.get("download_status") for item in rows.values())
                    print(f"Images {len(completed) + processed}/{len(urls)}: {dict(counts)}", flush=True)
    return rows


def refresh_retained_pages(capture: Path, rows: dict[str, dict[str, Any]]) -> None:
    """Reparse retained Russian pages so new parser fields need no refetch."""

    for row in rows.values():
        if row.get("scan_status") != "ok" or not row.get("is_russian") or not row.get("raw_page_path"):
            continue
        path = ROOT / "Dataset" / row["raw_page_path"]
        if not path.exists():
            continue
        body = path.read_bytes()
        decoded = decode_http_body(body, row.get("response_headers", {}))
        parsed = parse_product(decoded, row["url"])
        row.update(parsed)


def category_expected_count(path: Path) -> int | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'class="catalog__title-count"[^>]*>\s*([\d\s]+)\s+товар', text, re.I)
    return int(re.sub(r"\s+", "", match.group(1))) if match else None


def build_outputs(
    capture: Path,
    output: Path,
    product_urls: list[str],
    scan_rows_by_url: dict[str, dict[str, Any]],
    image_rows_by_url: dict[str, dict[str, Any]],
    *,
    partial: bool,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    scan_rows = [scan_rows_by_url[url] for url in product_urls if url in scan_rows_by_url]
    write_jsonl(capture / "crawl_manifest.jsonl", scan_rows)
    image_rows = [image_rows_by_url[url] for url in sorted(image_rows_by_url)]
    write_jsonl(capture / "image_manifest.jsonl", image_rows)

    russian_scan = [row for row in scan_rows if row.get("scan_status") == "ok" and row.get("is_russian")]
    russian_scan.sort(key=lambda row: int(row["external_product_id"]))
    discovered_asset_urls = {
        asset["url"]
        for row in russian_scan
        for asset in row.get("image_assets", [])
        if asset.get("url")
    }
    out_of_scope_images = [
        {
            **row,
            "quality_status": "out_of_scope_recommendation_or_non_product_asset",
            "exclusion_reason": "URL was downloaded during the broad gallery pilot but is not inside the SKU product presentation/gallery selector",
        }
        for row in image_rows
        if row.get("image_url") not in discovered_asset_urls
    ]
    write_jsonl(output / "tables/out_of_scope_images.jsonl", out_of_scope_images)
    image_by_url = image_rows_by_url
    products: list[dict[str, Any]] = []
    memberships: list[dict[str, Any]] = []
    associations: list[dict[str, Any]] = []
    media_by_sha: dict[str, dict[str, Any]] = {}
    for row in russian_scan:
        external_id = row["external_product_id"]
        product_id = stable_id("mavt_product", external_id)
        variant_id = stable_id("mavt_variant", external_id)
        image_assets = row.get("image_assets") or (
            [{"url": row["primary_image_url"], "role": "primary", "evidence_attribute": "itemprop"}]
            if row.get("primary_image_url")
            else []
        )
        media_ids: list[str] = []
        primary_media_id = None
        for asset in image_assets:
            image_url = asset.get("url")
            image = image_by_url.get(image_url or "")
            if not image or image.get("download_status") != "ok":
                continue
            media_id = stable_id("media", image["sha256"])
            if media_id not in media_ids:
                media_ids.append(media_id)
            if asset.get("role") == "primary" and primary_media_id is None:
                primary_media_id = media_id
            media = media_by_sha.setdefault(
                image["sha256"],
                {
                    "manifest_version": "1.1.0",
                    "source_id": SOURCE_ID,
                    "source_capture_id": CAPTURE_ID,
                    "media_id": media_id,
                    "product_id": product_id,
                    "bottle_variant_id": variant_id,
                    "wine_family_id": None,
                    "label_design_id": None,
                    "vintage": row.get("properties", {}).get("Год урожая"),
                    "slug": None,
                    "identity_group_id": stable_id("identity", f"mavt:{external_id}"),
                    "near_duplicate_group_id": None,
                    "association_grade": "gold",
                    "role": "russian_open_world_reference",
                    "relative_path": image["relative_path"],
                    "sha256": image["sha256"],
                    "bytes": image["bytes"],
                    "media_type": image.get("media_type"),
                    "width": image.get("width"),
                    "height": image.get("height"),
                    "image_format": image.get("image_format"),
                    "dhash64": image.get("dhash64"),
                    "decode_status": image.get("decode_status"),
                    "rights_status": "legal_review",
                    "quality_status": "verified_source_association" if image.get("decode_status") == "ok" else "decode_error",
                    "parent_media_id": None,
                    "source_image_urls": [],
                    "raw_paths": [],
                    "associated_product_ids": [],
                    "association_roles": [],
                },
            )
            for key, value in (
                ("source_image_urls", image_url),
                ("raw_paths", image.get("relative_path")),
                ("associated_product_ids", product_id),
                ("association_roles", f"{product_id}:{asset.get('role', 'gallery')}"),
            ):
                if value and value not in media[key]:
                    media[key].append(value)
            associations.append(
                {
                    "source_id": SOURCE_ID,
                    "product_id": product_id,
                    "external_product_id": external_id,
                    "external_article": row.get("external_article"),
                    "media_id": media_id,
                    "image_url": image_url,
                    "association_role": asset.get("role", "gallery"),
                    "association_grade": "gold",
                    "evidence": {
                        "product_page_url": row["url"],
                        "product_page_sha256": row.get("response_body_sha256"),
                        "html_attribute": asset.get("evidence_attribute"),
                    },
                }
            )
        if primary_media_id is None and media_ids:
            primary_media_id = media_ids[0]
        products.append(
            {
                "source_id": SOURCE_ID,
                "source_capture_id": CAPTURE_ID,
                "product_id": product_id,
                "wine_family_id": None,
                "bottle_variant_id": variant_id,
                "label_design_id": None,
                "external_product_id": external_id,
                "external_article": row.get("external_article"),
                "title": row.get("title"),
                "category": row.get("category"),
                "country": row.get("country"),
                "country_evidence": {
                    **(row.get("country_evidence") or {}),
                    "product_page_url": row["url"],
                    "product_page_sha256": row.get("response_body_sha256"),
                },
                "vintage": row.get("properties", {}).get("Год урожая"),
                "properties": row.get("properties", {}),
                "page_url": row["url"],
                "raw_page_path": row.get("raw_page_path"),
                "image_assets": image_assets,
                "primary_image_url": row.get("primary_image_url"),
                "media_id": primary_media_id,
                "media_ids": media_ids,
                "association_grade": "gold" if media_ids else None,
                "role": "russian_open_world_reference",
                "slug": None,
                "svoe_exact_match_status": "not_evaluated",
                "rights_status": "legal_review",
                "quality_status": "verified_source_metadata" if row.get("parse_status") == "ok" else "needs_verification",
            }
        )
        memberships.append(
            {
                "source_id": SOURCE_ID,
                "catalog_id": "mavt",
                "snapshot_id": CAPTURE_ID,
                "product_id": product_id,
                "bottle_variant_id": variant_id,
                "external_product_id": external_id,
                "external_article": row.get("external_article"),
                "page_url": row["url"],
                "country": row.get("country"),
                "slug": None,
            }
        )

    media = sorted(media_by_sha.values(), key=lambda row: row["media_id"])
    products.sort(key=lambda row: int(row["external_product_id"]))
    memberships.sort(key=lambda row: int(row["external_product_id"]))
    associations.sort(key=lambda row: (int(row["external_product_id"]), row["association_role"], row["image_url"]))
    write_jsonl(output / "tables/products.jsonl", products)
    write_jsonl(output / "tables/media.jsonl", media)
    write_jsonl(output / "tables/catalog_memberships.jsonl", memberships)
    write_jsonl(output / "tables/product_media_associations.jsonl", associations)

    scan_errors = [row for row in scan_rows if row.get("scan_status") != "ok" or row.get("parse_status") != "ok"]
    image_errors = [row for row in image_rows if row.get("download_status") != "ok" or row.get("decode_status") != "ok"]
    write_jsonl(output / "tables/crawl_errors.jsonl", scan_errors)
    write_jsonl(output / "tables/image_errors.jsonl", image_errors)

    articles: dict[str, list[str]] = defaultdict(list)
    for product in products:
        if product.get("external_article"):
            articles[product["external_article"]].append(product["product_id"])
    duplicate_articles = {key: value for key, value in articles.items() if len(value) > 1}
    shared_media = {
        row["media_id"]: row["associated_product_ids"]
        for row in media
        if len(row["associated_product_ids"]) > 1
    }
    missing_media = [product for product in products if not product.get("media_ids")]
    verification_queue = []
    for article, product_ids in sorted(duplicate_articles.items()):
        verification_queue.append(
            {
                "review_item_id": stable_id("review", f"mavt:duplicate_article:{article}"),
                "source_dataset": "11_mavt_ru_wines",
                "review_state": "needs_verification",
                "group_id": article,
                "required_action": "verify whether repeated external article represents variants or a source conflict",
                "evidence": {"external_article": article, "product_ids": product_ids},
                "candidates": product_ids,
            }
        )
    for media_id, product_ids in sorted(shared_media.items()):
        verification_queue.append(
            {
                "review_item_id": stable_id("review", f"mavt:shared_media:{media_id}"),
                "source_dataset": "11_mavt_ru_wines",
                "review_state": "needs_verification",
                "media_id": media_id,
                "required_action": "verify shared source image across distinct product IDs/variants",
                "evidence": {"media_id": media_id, "product_ids": product_ids},
                "candidates": product_ids,
            }
        )
    for product in products:
        country_value = str(product.get("country") or "")
        if "винос де мадрид" not in country_value.casefold():
            continue
        verification_queue.append(
            {
                "review_item_id": stable_id("review", f"mavt:suspicious_country:{product['product_id']}"),
                "source_dataset": "11_mavt_ru_wines",
                "review_state": "needs_verification",
                "product_id": product["product_id"],
                "required_action": "verify contradictory source country/region evidence before Russian-origin use",
                "evidence": {
                    "country": country_value,
                    "page_url": product.get("page_url"),
                    "external_product_id": product.get("external_product_id"),
                },
                "candidates": [],
            }
        )
    annotation_queue = [
        {
            "review_item_id": stable_id("review", f"mavt:missing_media:{product['product_id']}"),
            "source_dataset": "11_mavt_ru_wines",
            "review_state": "needs_annotation",
            "product_id": product["product_id"],
            "required_action": "obtain and verify a label/bottle reference image",
            "evidence": {"page_url": product["page_url"], "primary_image_url": product.get("primary_image_url")},
            "candidates": [],
        }
        for product in missing_media
    ]
    write_jsonl(output / "review/needs_verification/queue.jsonl", verification_queue)
    write_jsonl(output / "review/needs_annotation/queue.jsonl", annotation_queue)
    for decision_path in (
        output / "review/verified/decisions.jsonl",
        output / "review/rejected/decisions.jsonl",
    ):
        if not decision_path.exists():
            write_jsonl(decision_path, [])
    write_json(
        output / "review/STATUS.json",
        {
            "contract_version": "1.0.0",
            "source_dataset": "11_mavt_ru_wines",
            "generated_queues": {
                "needs_verification": len(verification_queue),
                "needs_annotation": len(annotation_queue),
            },
            "human_decision_logs": {
                "verified": "verified/decisions.jsonl",
                "rejected": "rejected/decisions.jsonl",
            },
            "media_copy_policy": "reference_by_media_id_and_relative_path_only",
        },
    )

    category_count = category_expected_count(capture / "russian-category.html")
    all_urls_scanned = len(scan_rows) == len(product_urls)
    scan_accounted = all(row.get("scan_status") in {"ok", "http_error"} for row in scan_rows)
    accepted_country_valid = all(str(row.get("country", "")).casefold().startswith("россия") for row in russian_scan)
    raw_pages_valid = all(
        row.get("raw_page_path")
        and (ROOT / "Dataset" / row["raw_page_path"]).exists()
        and sha256_file(ROOT / "Dataset" / row["raw_page_path"]) == row.get("response_body_sha256")
        for row in russian_scan
    )
    media_hashes_valid = all(
        all(
            (ROOT / "Dataset" / raw_path).exists()
            and sha256_file(ROOT / "Dataset" / raw_path) == row["sha256"]
            for raw_path in row["raw_paths"]
        )
        for row in media
    )
    all_image_urls_accounted = all(url in image_rows_by_url for url in discovered_asset_urls)
    summary = {
        "manifest_version": "1.1.0",
        "source_id": SOURCE_ID,
        "source_capture_id": CAPTURE_ID,
        "capture_date": CAPTURE_DATE,
        "collection_scope": "query-free wine product URLs from the public MAVT sitemap; accepted only when product property Страна starts with Россия",
        "request_policy": {
            "user_agent": USER_AGENT,
            "cookies_persisted": False,
            "header_or_ip_rotation": False,
            "faceted_or_pagination_urls_requested": False,
            "stop_on_http_status": sorted(BLOCK_STATUS),
        },
        "rights": {
            "declared_dataset_license": None,
            "rights_status": "legal_review",
            "training_use": "internal_noncommercial_research_pending_legal_review",
            "derivatives": "legal_review",
            "redistribution": "not_allowed_without_permission",
            "basis": "Public retailer pages and product images; no dataset/open-content license found in captured pages.",
        },
        "counts": {
            "sitemap_wine_product_urls": len(product_urls),
            "product_urls_scanned": len(scan_rows),
            "scan_http_or_parse_errors": len(scan_errors),
            "russian_category_reported_products": category_count,
            "russian_products_from_sitemap": len(products),
            "russian_products_with_primary_image_url": sum(bool(row.get("primary_image_url")) for row in russian_scan),
            "russian_products_with_decoded_media": sum(bool(row.get("media_id")) for row in products),
            "discovered_product_gallery_image_urls": len(discovered_asset_urls),
            "primary_image_associations": sum(row["association_role"] == "primary" for row in associations),
            "gallery_image_associations": sum(row["association_role"] == "gallery" for row in associations),
            "unique_image_urls": len(image_rows),
            "raw_image_urls_excluded_as_non_product_assets": len(out_of_scope_images),
            "unique_decoded_media_by_sha256": len(media),
            "image_download_or_decode_errors": len(image_errors),
            "exact_duplicate_image_groups": sum(len(row["raw_paths"]) > 1 for row in media),
            "shared_media_product_groups": len(shared_media),
            "duplicate_external_articles": len(duplicate_articles),
            "needs_verification": len(verification_queue),
            "needs_annotation": len(annotation_queue),
        },
        "gates": {
            "full_sitemap_scan_complete": all_urls_scanned and not partial,
            "scan_results_accounted": scan_accounted,
            "accepted_products_have_russian_country_evidence": accepted_country_valid,
            "all_retained_raw_pages_exist_and_match_hash": raw_pages_valid,
            "all_downloaded_media_exist_and_match_hash": media_hashes_valid,
            "all_product_gallery_image_urls_accounted": all_image_urls_accounted,
            "all_downloaded_images_decode": not image_errors,
            "all_products_have_decoded_media": not missing_media,
            "category_count_matches_sitemap_result": category_count == len(products) if category_count is not None else None,
            "ready_for_frozen_split": False,
        },
        "limitations": [
            "The Russian country category uses query-string pagination disallowed by robots.txt; it was not crawled beyond the clean landing page.",
            "The public sitemap can include items unavailable in the selected store/region, so its count may differ from the category UI count.",
            "Retailer country metadata and exact source image association are captured; cross-source wine family, vintage and redesign identity remain unreviewed.",
            "No MAVT product is assigned a Svoe Vino slug without separate exact identity review.",
        ],
    }
    write_json(output / "tables/SUMMARY.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-date", default=CAPTURE_DATE)
    parser.add_argument("--interval", type=float, default=0.5, help="Minimum seconds between all request starts")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--retries", type=int, default=2, help="Retries for network/5xx errors; never used for 403/429")
    parser.add_argument("--max-products", type=int, default=0, help="Pilot limit; zero means full sitemap wine segment")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    if args.capture_date != CAPTURE_DATE:
        raise SystemExit("This version is pinned to capture date 2026-09-15; update source IDs before a new snapshot")
    if args.interval < 0.25:
        raise SystemExit("Refusing an impolite interval below 0.25 seconds")
    workers = max(1, min(args.workers, 4))
    capture = ROOT / f"Dataset/00_raw/11_mavt_ru_wines/{args.capture_date}"
    output = ROOT / "Dataset/11_mavt_ru_wines"
    gate = PoliteGate(args.interval)
    stop_event = threading.Event()
    capture_seeds(capture, gate, stop_event)
    product_urls = sitemap_product_urls(capture / "sitemap-iblock-9.xml")
    robots_gate(capture, product_urls)
    selected_urls = product_urls[: args.max_products] if args.max_products else product_urls
    partial = len(selected_urls) < len(product_urls)
    scan_rows = scan_products(
        selected_urls,
        capture,
        gate,
        stop_event,
        workers=workers,
        retries=args.retries,
    )
    if stop_event.is_set():
        print("Collection stopped by anti-bot/rate-limit signal. No bypass attempted.", flush=True)
        return 3
    refresh_retained_pages(capture, scan_rows)
    robots_text = (capture / "robots.txt").read_text(encoding="utf-8", errors="replace")
    russian_rows = [
        row for url, row in scan_rows.items()
        if url in selected_urls and row.get("scan_status") == "ok" and row.get("is_russian")
    ]
    image_urls = sorted(
        {
            asset["url"]
            for row in russian_rows
            for asset in row.get("image_assets", [])
            if asset.get("url")
        }
    )
    disallowed_images = [url for url in image_urls if not allowed_image_url(url, robots_text)]
    if disallowed_images:
        raise SystemExit(f"Image robots gate rejected {len(disallowed_images)} URLs; review required")
    image_rows = download_images(
        image_urls,
        capture,
        gate,
        stop_event,
        workers=workers,
        retries=args.retries,
    )
    if stop_event.is_set():
        print("Image collection stopped by anti-bot/rate-limit signal. No bypass attempted.", flush=True)
        return 3
    summary = build_outputs(
        capture,
        output,
        selected_urls,
        scan_rows,
        image_rows,
        partial=partial,
    )
    print(json.dumps(summary["counts"], ensure_ascii=False, indent=2), flush=True)
    gates = summary["gates"]
    essential = (
        gates["scan_results_accounted"]
        and gates["accepted_products_have_russian_country_evidence"]
        and gates["all_retained_raw_pages_exist_and_match_hash"]
        and gates["all_downloaded_media_exist_and_match_hash"]
        and gates["all_product_gallery_image_urls_accounted"]
    )
    if partial and args.allow_partial:
        return 0 if essential else 2
    return 0 if essential and gates["full_sitemap_scan_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
