#!/usr/bin/env python3
"""Robots-aware snapshot of Russian wines published by amwine.ru.

The crawler deliberately uses one descriptive user agent, one request at a
time, a host-level delay and a hard stop on HTTP 403/429.  It never calls
private APIs and never changes headers, cookies or IP identity to evade access
controls.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import html
import http.client
import json
import math
import mimetypes
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

from PIL import Image


SOURCE_ID = "aromatny-mir-russian-wine-web"
CAPTURE_DATE = "2026-09-15"
CAPTURE_ID = "amwine_20260915_001"
BASE_URL = "https://amwine.ru"
CDN_URL = "https://cdn.amwine.ru"
USER_AGENT = (
    "VinoResearchBot/1.0 (noncommercial dataset audit; "
    "single-client polite crawl)"
)
ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "Dataset" / "00_raw" / "15_aromatny_mir_ru_wines" / CAPTURE_DATE
OUT_ROOT = ROOT / "Dataset" / "15_aromatny_mir_ru_wines"
RUN_ROOT = ROOT / "runs" / "2026-09-15-amwine-collection"

ROBOTS_URLS = {
    "amwine.ru": f"{BASE_URL}/robots.txt",
    "cdn.amwine.ru": f"{CDN_URL}/robots.txt",
}
SITEMAP_URLS = {
    "sitemap.xml": f"{BASE_URL}/sitemap.xml",
    "sitemap-iblock-2.xml": f"{BASE_URL}/sitemap-iblock-2.xml",
    "sitemap-vino-part-1.xml": f"{BASE_URL}/sitemap-vino-part-1.xml",
    "sitemap-vino-part-2.xml": f"{BASE_URL}/sitemap-vino-part-2.xml",
    "sitemap_igristoe_vino_i_shampanskoe.xml": (
        f"{BASE_URL}/sitemap_igristoe_vino_i_shampanskoe.xml"
    ),
}
CATEGORY_ROUTES = {
    "still_wine": f"{BASE_URL}/catalog/vino/filter/country-is-rossiya/",
    "sparkling_wine": (
        f"{BASE_URL}/catalog/igristoe_vino_i_shampanskoe/"
        "igristoe_vino/filter/country-is-rossiya/"
    ),
    "nonalcoholic_sparkling_wine": (
        f"{BASE_URL}/catalog/igristoe_vino_i_shampanskoe/"
        "bezalkogolnoe_igristoe_vino/filter/country-is-rossiya/"
    ),
}
ALLOWED_HOSTS = {"amwine.ru", "cdn.amwine.ru"}
IMAGE_MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}
IMAGE_MIME_BY_SUFFIX = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
PRODUCT_PATH_PREFIXES = (
    "/catalog/vino/",
    "/catalog/igristoe_vino_i_shampanskoe/",
)
FILTER_MARKER = "/filter/"


class AccessBlocked(RuntimeError):
    """Raised immediately for a 403/429 response."""


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_id(prefix: str, value: str, length: int = 20) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:length]}"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json_dumps(row) + "\n")


def relative_to_root(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def canonical_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    path = re.sub(r"/{2,}", "/", parsed.path)
    if not path.endswith("/"):
        path += "/"
    return urllib.parse.urlunsplit(("https", parsed.netloc.lower(), path, "", ""))


@dataclass(frozen=True)
class RobotRule:
    allow: bool
    pattern: str

    @property
    def specificity(self) -> int:
        return len(self.pattern.replace("*", "").replace("$", ""))

    def matches(self, path_with_query: str) -> bool:
        expression = re.escape(self.pattern).replace(r"\*", ".*")
        if expression.endswith(r"\$"):
            expression = expression[:-2] + "$"
        else:
            expression += ".*"
        return bool(re.match("^" + expression, path_with_query))


def generic_robot_rules(data: bytes) -> list[RobotRule]:
    """Read only the `User-agent: *` groups relevant to our honest custom UA."""
    rules: list[RobotRule] = []
    applies = False
    saw_directive = False
    for raw_line in data.decode("utf-8", errors="replace").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if saw_directive:
                applies = False
                saw_directive = False
            if value == "*":
                applies = True
            continue
        if key in {"allow", "disallow"}:
            saw_directive = True
            if applies and value:
                rules.append(RobotRule(key == "allow", value))
    return rules


def robots_allows(url: str, rules_by_host: dict[str, list[RobotRule] | None]) -> bool:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in ALLOWED_HOSTS:
        return False
    rules = rules_by_host.get(parsed.netloc.lower())
    if rules is None:
        return True
    candidate = parsed.path + (("?" + parsed.query) if parsed.query else "")
    matches = [rule for rule in rules if rule.matches(candidate)]
    if not matches:
        return True
    maximum = max(rule.specificity for rule in matches)
    return any(rule.allow for rule in matches if rule.specificity == maximum)


class PoliteFetcher:
    def __init__(self, delay_seconds: float, timeout_seconds: int, retries: int) -> None:
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.last_request: dict[str, float] = {}
        self.events: list[dict[str, Any]] = []
        self.connections: dict[tuple[int, str], http.client.HTTPSConnection] = {}
        self.rate_lock = threading.Lock()
        self.events_lock = threading.Lock()
        self.blocked = threading.Event()

    def _wait(self, host: str) -> None:
        with self.rate_lock:
            elapsed = time.monotonic() - self.last_request.get(host, 0.0)
            if elapsed < self.delay_seconds:
                time.sleep(self.delay_seconds - elapsed)
            self.last_request[host] = time.monotonic()

    def _record(self, event: dict[str, Any]) -> None:
        with self.events_lock:
            self.events.append(event)

    def get(
        self,
        url: str,
        *,
        accept_404: bool = False,
        follow_redirects: bool = True,
    ) -> tuple[bytes | None, dict[str, Any]]:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc.lower() not in ALLOWED_HOSTS:
            raise ValueError(f"URL outside allowed hosts: {url}")
        host = parsed.netloc.lower()
        current_url = url
        redirects = 0
        for attempt in range(self.retries + 1):
            if self.blocked.is_set():
                raise AccessBlocked("hard stop already triggered by another in-flight request")
            parsed = urllib.parse.urlsplit(current_url)
            host = parsed.netloc.lower()
            self._wait(host)
            headers = {
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*;q=0.8,*/*;q=0.5",
                    "Connection": "keep-alive",
                }
            started = time.monotonic()
            captured_at = now_utc()
            try:
                connection_key = (threading.get_ident(), host)
                connection = self.connections.get(connection_key)
                if connection is None:
                    connection = http.client.HTTPSConnection(host, timeout=self.timeout_seconds)
                    self.connections[connection_key] = connection
                target = parsed.path or "/"
                if parsed.query:
                    target += "?" + parsed.query
                connection.request("GET", target, headers=headers)
                response = connection.getresponse()
                data = response.read()
                status = int(response.status)
                event = {
                    "url": current_url,
                    "status": status,
                    "bytes": len(data),
                    "content_type": response.getheader("Content-Type"),
                    "captured_at": captured_at,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "attempt": attempt + 1,
                }
                self._record(event)
                if status in {301, 302, 303, 307, 308}:
                    location = response.getheader("Location")
                    redirected = urllib.parse.urljoin(current_url, location or "")
                    event["redirect_url"] = redirected or None
                    if not follow_redirects:
                        event["error"] = "redirect_not_followed_for_immutable_resource"
                        return None, event
                    if not location or redirects >= 4:
                        event["error"] = "redirect_without_safe_destination"
                        return None, event
                    redirected_parsed = urllib.parse.urlsplit(redirected)
                    if (
                        redirected_parsed.scheme != "https"
                        or (redirected_parsed.hostname or "").lower() not in ALLOWED_HOSTS
                        or redirected_parsed.port not in {None, 443}
                    ):
                        event["error"] = "redirect_outside_allowed_hosts"
                        return None, event
                    current_url = redirected
                    redirects += 1
                    continue
                if status in {403, 429}:
                    self.blocked.set()
                    raise AccessBlocked(f"hard stop: HTTP {status} for {current_url}")
                if status == 200:
                    if current_url != url:
                        event["requested_url"] = url
                        event["redirects"] = redirects
                    return data, event
                if status == 404 and accept_404:
                    return None, event
                event["error"] = f"HTTP {status} {response.reason}"
                if status < 500 or attempt >= self.retries:
                    return None, event
            except (TimeoutError, ConnectionError, OSError, http.client.HTTPException) as exc:
                connection_key = (threading.get_ident(), host)
                connection = self.connections.pop(connection_key, None)
                if connection is not None:
                    connection.close()
                event = {
                    "url": current_url,
                    "status": None,
                    "bytes": 0,
                    "content_type": None,
                    "captured_at": captured_at,
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "attempt": attempt + 1,
                    "error": str(exc),
                }
                self._record(event)
                if attempt >= self.retries:
                    return None, event
            time.sleep(min(8.0, 2.0 ** attempt))
        return None, self.events[-1]


def raw_file_record(path: Path, url: str, event: dict[str, Any]) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "source_id": SOURCE_ID,
        "source_capture_id": CAPTURE_ID,
        "relative_path": relative_to_root(path),
        "source_url": url,
        "captured_at": event.get("captured_at"),
        "http_status": event.get("status"),
        "content_type": event.get("content_type") or mimetypes.guess_type(path.name)[0] or IMAGE_MIME_BY_SUFFIX.get(path.suffix.lower()),
        "bytes": len(data),
        "sha256": sha256_bytes(data),
    }


def fetch_raw(
    fetcher: PoliteFetcher,
    url: str,
    path: Path,
    *,
    accept_404: bool = False,
    follow_redirects: bool = True,
) -> tuple[bytes | None, dict[str, Any], bool]:
    """Fetch once or return immutable bytes already captured at the target."""
    if path.exists():
        data = path.read_bytes()
        return data, {
            "url": url,
            "status": 200,
            "bytes": len(data),
            "content_type": mimetypes.guess_type(path.name)[0],
            "captured_at": None,
            "elapsed_ms": 0,
            "attempt": 0,
            "cache": "immutable_raw",
        }, True
    data, event = fetcher.get(
        url, accept_404=accept_404, follow_redirects=follow_redirects
    )
    if data is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return data, event, False


def sitemap_locs(data: bytes) -> list[str]:
    root = ET.fromstring(data)
    result = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] == "loc" and node.text:
            result.append(node.text.strip())
    return result


def extract_script_json(document: str, script_id: str) -> Any | None:
    pattern = re.compile(
        rf"<script[^>]*\bid=[\"']{re.escape(script_id)}[\"'][^>]*>(.*?)</script>",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(document)
    if not match:
        return None
    try:
        return json.loads(html.unescape(match.group(1).strip()))
    except json.JSONDecodeError:
        return None


def extract_jsonld_products(document: str) -> list[dict[str, Any]]:
    scripts = re.findall(
        r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        document,
        flags=re.IGNORECASE | re.DOTALL,
    )
    products: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            kind = value.get("@type")
            if kind == "Product" or (isinstance(kind, list) and "Product" in kind):
                products.append(value)
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    for script in scripts:
        try:
            visit(json.loads(html.unescape(script.strip())))
        except json.JSONDecodeError:
            continue
    return products


def listing_products(document: str) -> tuple[int, list[str]]:
    initial = extract_script_json(document, "catalog-listing-initial-data") or {}
    total = int(initial.get("listing", {}).get("productsTotalCount", 0) or 0)
    structured = extract_script_json(document, "listing-structured-data") or {}
    urls: list[str] = []
    for node in structured.get("@graph", []):
        if node.get("@type") != "ItemList":
            continue
        for entry in node.get("itemListElement", []):
            if not isinstance(entry, dict):
                continue
            item = entry.get("item") or {}
            if isinstance(item, str):
                value = item
            elif isinstance(item, dict):
                value = item.get("url") or item.get("@id")
            else:
                value = None
            if value:
                urls.append(canonical_url(urllib.parse.urljoin(BASE_URL, value.split("#", 1)[0])))
    return total, sorted(set(urls))


def product_page_fields(document: str, url: str) -> dict[str, Any]:
    candidates = extract_jsonld_products(document)
    direct = [item for item in candidates if item.get("sku") and item.get("image")]
    product = direct[-1] if direct else (candidates[-1] if candidates else {})
    hero_match = re.search(
        r'<div\s+class="[^"]*product-hero[^" ]*[^" ]*\s+js-catalog-item"(?P<a>[^>]*)>',
        document,
        flags=re.IGNORECASE,
    )
    if not hero_match:
        hero_match = re.search(
            r'<div\s+class="[^"]*product-hero[^"]*"(?P<a>[^>]*)>',
            document,
            flags=re.IGNORECASE,
        )
    attrs = {}
    if hero_match:
        attrs = {
            key.lower(): html.unescape(value)
            for key, _, value in re.findall(
                r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", hero_match.group("a"), re.DOTALL
            )
        }
    stats: dict[str, str] = {}
    for block in re.findall(
        r'<li\s+class="[^"]*stats-list__item[^"]*"[^>]*>(.*?)</li>',
        document,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        title_match = re.search(
            r'class="[^"]*stats-list__item-title[^"]*"[^>]*>(.*?)</',
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
        value_match = re.search(
            r'class="[^"]*stats-list__item-value[^"]*"[^>]*>(.*?)</',
            block,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if title_match and value_match:
            stats[clean_text(title_match.group(1))] = clean_text(value_match.group(1))
    title_match = re.search(r"<title>(.*?)</title>", document, re.IGNORECASE | re.DOTALL)
    description_match = re.search(
        r'<meta\s+name="description"\s+content="(.*?)"\s*/?>',
        document,
        re.IGNORECASE | re.DOTALL,
    )
    images = product.get("image") or []
    if isinstance(images, str):
        images = [images]
    image_urls = []
    for value in images:
        if not isinstance(value, str) or not value.strip():
            continue
        absolute = urllib.parse.urljoin(BASE_URL, str(value))
        if urllib.parse.urlsplit(absolute).netloc.lower() in ALLOWED_HOSTS:
            image_urls.append(absolute)
    offers = product.get("offers") or {}
    rating = product.get("aggregateRating") or {}
    country = stats.get("Страна")
    meta_description = html.unescape(description_match.group(1)) if description_match else None
    return {
        "source_url": url,
        "canonical_url": canonical_url(offers.get("url") or url),
        "external_product_id": str(product.get("sku") or attrs.get("data-article") or "") or None,
        "source_internal_id": attrs.get("data-id"),
        "name": clean_text(str(product.get("name") or attrs.get("data-name") or "")) or None,
        "category": attrs.get("data-category"),
        "country": country,
        "country_evidence": "product_stat_exact" if country == "Россия" else None,
        "stats": stats,
        "description": clean_text(str(product.get("description") or "")) or None,
        "meta_description": meta_description,
        "price": offers.get("price") or attrs.get("data-price"),
        "price_currency": offers.get("priceCurrency"),
        "availability": offers.get("availability"),
        "rating_value": rating.get("ratingValue"),
        "rating_count": rating.get("ratingCount") or rating.get("reviewCount"),
        "image_urls": list(dict.fromkeys(image_urls)),
        "jsonld_present": bool(product),
        "page_title": clean_text(title_match.group(1)) if title_match else None,
    }


def image_extension(url: str, content_type: str | None) -> str:
    suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}:
        return suffix
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip())
    return guessed or ".bin"


def source_asset_key(url: str) -> str:
    """Collapse explicit resize-cache variants onto the published asset path."""
    path = urllib.parse.urlsplit(url).path
    match = re.match(
        r"^/upload/resize_cache/iblock/([^/]+)/[^/]+/(.+)$", path, flags=re.IGNORECASE
    )
    if match:
        return f"/upload/iblock/{match.group(1)}/{match.group(2)}"
    return path


def infer_cached_source_url(path: Path) -> str | None:
    """Recover public URL for cached HTML not visited in the current resume."""
    if path.name.endswith(".status.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return str(value.get("url")) if value.get("url") else None
        except (OSError, json.JSONDecodeError):
            return None
    if path.suffix.lower() != ".html":
        return None
    try:
        prefix = path.read_bytes()[:250_000].decode("utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(
        r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)["\']',
        prefix,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    url = html.unescape(match.group(1))
    page_match = re.search(r"-page-(\d+)\.html$", path.name)
    if page_match and int(page_match.group(1)) > 1:
        url += ("&" if "?" in url else "?") + "page=" + str(int(page_match.group(1)))
    return url


def decode_image(data: bytes) -> dict[str, Any]:
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            return {
                "decode_ok": True,
                "width": int(image.width),
                "height": int(image.height),
                "format": image.format,
                "mode": image.mode,
            }
    except Exception as exc:  # Pillow exposes multiple format-specific exceptions.
        return {
            "decode_ok": False,
            "width": None,
            "height": None,
            "format": None,
            "mode": None,
            "decode_error": f"{type(exc).__name__}: {exc}",
        }


def ensure_layout() -> None:
    for path in (
        RAW_ROOT / "policy",
        RAW_ROOT / "sitemaps",
        RAW_ROOT / "listing_pages",
        RAW_ROOT / "product_pages",
        RAW_ROOT / "images",
        OUT_ROOT / "tables",
        OUT_ROOT / "media",
        OUT_ROOT / "review" / "needs_verification",
        OUT_ROOT / "review" / "needs_annotation",
        OUT_ROOT / "review" / "verified",
        OUT_ROOT / "review" / "rejected",
        RUN_ROOT,
    ):
        path.mkdir(parents=True, exist_ok=True)


def run(args: argparse.Namespace) -> dict[str, Any]:
    ensure_layout()
    fetcher = PoliteFetcher(args.delay, args.timeout, args.retries)
    rules_by_host: dict[str, list[RobotRule] | None] = {}
    raw_records: dict[str, dict[str, Any]] = {}
    stopped_reason: str | None = None

    try:
        # Phase 1a: policy snapshot must precede any catalog capture.
        for host, url in ROBOTS_URLS.items():
            filename = "robots.txt" if host == "amwine.ru" else "cdn-robots.txt"
            path = RAW_ROOT / "policy" / filename
            data, event, _ = fetch_raw(fetcher, url, path, accept_404=True)
            write_json(RAW_ROOT / "policy" / f"{filename}.status.json", event)
            if data is None:
                rules_by_host[host] = None
            else:
                rules_by_host[host] = generic_robot_rules(data)
                raw_records[relative_to_root(path)] = raw_file_record(path, url, event)

        for name, url in SITEMAP_URLS.items():
            if not robots_allows(url, rules_by_host):
                raise RuntimeError(f"robots disallows declared sitemap: {url}")
            path = RAW_ROOT / "sitemaps" / name
            data, event, _ = fetch_raw(fetcher, url, path)
            if data is None:
                raise RuntimeError(f"could not capture required sitemap: {url}")
            raw_records[relative_to_root(path)] = raw_file_record(path, url, event)

        product_sitemap_path = RAW_ROOT / "sitemaps" / "sitemap-iblock-2.xml"
        all_sitemap_urls = sorted(set(sitemap_locs(product_sitemap_path.read_bytes())))
        sitemap_products = {
            canonical_url(url)
            for url in all_sitemap_urls
            if urllib.parse.urlsplit(url).netloc.lower() == "amwine.ru"
            and urllib.parse.urlsplit(url).path.startswith(PRODUCT_PATH_PREFIXES)
            and FILTER_MARKER not in urllib.parse.urlsplit(url).path
            and robots_allows(canonical_url(url), rules_by_host)
        }

        # Phase 1b: country pages enumerate Russian product URLs.  Each URL must
        # also exist in the official product sitemap before it can be crawled.
        discovered: dict[str, set[str]] = defaultdict(set)
        listing_stats: list[dict[str, Any]] = []
        for category, route in CATEGORY_ROUTES.items():
            if not robots_allows(route, rules_by_host):
                raise RuntimeError(f"robots disallows category discovery route: {route}")
            first_path = RAW_ROOT / "listing_pages" / f"{category}-page-001.html"
            data, event, _ = fetch_raw(fetcher, route, first_path)
            if data is None:
                raise RuntimeError(f"could not capture category page: {route}")
            raw_records[relative_to_root(first_path)] = raw_file_record(first_path, route, event)
            total, urls = listing_products(data.decode("utf-8", errors="replace"))
            for url in urls:
                discovered[url].add(category)
            pages = max(1, math.ceil(total / max(1, len(urls))))
            listing_stats.append({
                "category": category,
                "route": route,
                "reported_products": total,
                "items_first_page": len(urls),
                "pages": pages,
            })
            for page in range(2, pages + 1):
                page_url = f"{route}?page={page}"
                if not robots_allows(page_url, rules_by_host):
                    raise RuntimeError(f"robots disallows pagination URL: {page_url}")
                page_path = RAW_ROOT / "listing_pages" / f"{category}-page-{page:03d}.html"
                page_data, page_event, _ = fetch_raw(fetcher, page_url, page_path)
                if page_data is None:
                    continue
                raw_records[relative_to_root(page_path)] = raw_file_record(
                    page_path, page_url, page_event
                )
                _, page_urls = listing_products(page_data.decode("utf-8", errors="replace"))
                for url in page_urls:
                    discovered[url].add(category)

        # The live result order can shift while pages are being fetched.  Use
        # official, robots-allowed Russia+brand facets as a second enumeration
        # path so products displaced between adjacent pages are still found.
        facet_locs: set[str] = set()
        for sitemap_name in (
            "sitemap-vino-part-1.xml",
            "sitemap-vino-part-2.xml",
            "sitemap_igristoe_vino_i_shampanskoe.xml",
        ):
            facet_locs.update(
                sitemap_locs((RAW_ROOT / "sitemaps" / sitemap_name).read_bytes())
            )
        brand_facet_routes = sorted(
            canonical_url(url)
            for url in facet_locs
            if "country-is-rossiya" in urllib.parse.urlsplit(url).path
            and re.search(r"/brand-is-[^/]+/$", urllib.parse.urlsplit(url).path)
            and urllib.parse.urlsplit(url).path.startswith(PRODUCT_PATH_PREFIXES)
            and robots_allows(url, rules_by_host)
        )
        brand_facet_stats: list[dict[str, Any]] = []
        if not args.skip_brand_facets:
            for route in brand_facet_routes:
                facet_id = stable_id("facet", route, 16)
                first_path = (
                    RAW_ROOT / "listing_pages" / "brand_facets" / f"{facet_id}-page-001.html"
                )
                data, event, _ = fetch_raw(fetcher, route, first_path)
                if data is None:
                    brand_facet_stats.append(
                        {"route": route, "reported_products": None, "pages": 0, "status": "fetch_error"}
                    )
                    continue
                raw_records[relative_to_root(first_path)] = raw_file_record(first_path, route, event)
                total, urls = listing_products(data.decode("utf-8", errors="replace"))
                for url in urls:
                    discovered[url].add("russia_brand_facet")
                pages = max(1, math.ceil(total / max(1, len(urls))))
                brand_facet_stats.append(
                    {"route": route, "reported_products": total, "pages": pages, "status": "captured"}
                )
                for page in range(2, pages + 1):
                    page_url = f"{route}?page={page}"
                    if not robots_allows(page_url, rules_by_host):
                        raise RuntimeError(f"robots disallows brand pagination URL: {page_url}")
                    page_path = (
                        RAW_ROOT
                        / "listing_pages"
                        / "brand_facets"
                        / f"{facet_id}-page-{page:03d}.html"
                    )
                    page_data, page_event, _ = fetch_raw(fetcher, page_url, page_path)
                    if page_data is None:
                        continue
                    raw_records[relative_to_root(page_path)] = raw_file_record(
                        page_path, page_url, page_event
                    )
                    _, page_urls = listing_products(page_data.decode("utf-8", errors="replace"))
                    for url in page_urls:
                        discovered[url].add("russia_brand_facet")

        allowed_product_rows = []
        for url, categories in sorted(discovered.items()):
            allowed_product_rows.append({
                "source_id": SOURCE_ID,
                "source_capture_id": CAPTURE_ID,
                "source_url": url,
                "categories": sorted(categories),
                "in_official_product_sitemap": url in sitemap_products,
                "robots_allowed": robots_allows(url, rules_by_host),
                "selected_for_product_crawl": (
                    url in sitemap_products and robots_allows(url, rules_by_host)
                ),
            })
        write_jsonl(OUT_ROOT / "tables" / "allowed_product_urls.jsonl", allowed_product_rows)
        selected_urls = [
            row["source_url"] for row in allowed_product_rows if row["selected_for_product_crawl"]
        ]
        if args.max_products is not None:
            selected_urls = selected_urls[: args.max_products]
        write_json(
            OUT_ROOT / "tables" / "DISCOVERY-SUMMARY.json",
            {
                "source_id": SOURCE_ID,
                "source_capture_id": CAPTURE_ID,
                "captured_at": now_utc(),
                "user_agent": USER_AGENT,
                "request_delay_seconds": args.delay,
                "robots_generic_rules": {
                    host: None if rules is None else len(rules)
                    for host, rules in rules_by_host.items()
                },
                "listing_categories": listing_stats,
                "official_russia_brand_facet_routes": len(brand_facet_routes),
                "brand_facets_captured": sum(
                    row["status"] == "captured" for row in brand_facet_stats
                ),
                "brand_facet_pages_captured": sum(row["pages"] for row in brand_facet_stats),
                "official_sitemap_urls": len(all_sitemap_urls),
                "official_product_urls_in_scope": len(sitemap_products),
                "country_route_unique_urls": len(discovered),
                "country_routes_intersect_product_sitemap": sum(
                    row["in_official_product_sitemap"] for row in allowed_product_rows
                ),
                "selected_product_urls": len(selected_urls),
                "discover_only": args.discover_only,
            },
        )
        if args.discover_only:
            return {
                "status": "discovery_complete",
                "selected_product_urls": len(selected_urls),
                "fetch_events": len(fetcher.events),
            }

        # Phase 2: capture and parse the selected product cards.
        products: list[dict[str, Any]] = []
        page_failures: list[dict[str, Any]] = []
        def capture_product(task: tuple[int, str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
            index, url = task
            page_id = stable_id("page", url)
            page_path = RAW_ROOT / "product_pages" / f"{page_id}.html"
            data, event, _ = fetch_raw(
                fetcher,
                url,
                page_path,
                accept_404=True,
                follow_redirects=False,
            )
            if data is None:
                return None, {"source_url": url, "event": event}, None
            raw_record = raw_file_record(page_path, url, event)
            fields = product_page_fields(data.decode("utf-8", errors="replace"), url)
            external_id = fields["external_product_id"]
            product_key = external_id or url
            fields.update({
                "source_id": SOURCE_ID,
                "source_capture_id": CAPTURE_ID,
                "product_id": stable_id("amwine_product", str(product_key)),
                "wine_family_id": None,
                "bottle_variant_id": stable_id("amwine_variant", str(product_key)),
                "label_design_id": None,
                "identity_group_id": stable_id("amwine_identity", str(product_key)),
                "svoe_slug": None,
                "association_grade": "gold" if external_id else "bronze",
                "catalog_role": "russian_open_world_reference",
                "raw_page_path": relative_to_root(page_path),
                "raw_page_sha256": sha256_bytes(data),
                "category_routes": sorted(discovered[url]),
                "country_route_evidence": "country-is-rossiya",
                "quality_status": (
                    "verified_source_association"
                    if external_id and fields["country"] == "Россия"
                    else "needs_verification"
                ),
                "crawl_index": index,
            })
            return fields, None, raw_record

        product_executor = concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)
        product_futures = [
            product_executor.submit(capture_product, task)
            for task in enumerate(selected_urls, 1)
        ]
        try:
            for future in concurrent.futures.as_completed(product_futures):
                product, failure, raw_record = future.result()
                if product is not None:
                    products.append(product)
                    raw_records[raw_record["relative_path"]] = raw_record
                elif failure is not None:
                    page_failures.append(failure)
        except AccessBlocked:
            fetcher.blocked.set()
            for future in product_futures:
                future.cancel()
            product_executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            product_executor.shutdown(wait=True)
        products.sort(key=lambda row: row["crawl_index"])
        page_failures.sort(key=lambda row: row["source_url"])

        # Phase 3: download images explicitly listed by product JSON-LD.
        image_urls: dict[str, list[tuple[dict[str, Any], int]]] = defaultdict(list)
        for product in products:
            candidates = product["image_urls"]
            if args.image_mode == "primary":
                candidates = candidates[:1]
            elif args.image_mode == "none":
                candidates = []
            for ordinal, image_url in enumerate(candidates, 1):
                image_urls[image_url].append((product, ordinal))

        media_rows: list[dict[str, Any]] = []
        media_by_url: dict[str, dict[str, Any]] = {}
        def capture_image(task: tuple[str, list[tuple[dict[str, Any], int]]]) -> tuple[str, dict[str, Any], dict[str, Any] | None]:
            image_url, associations = task
            if not robots_allows(image_url, rules_by_host):
                return image_url, {
                    "media_id": stable_id("amwine_media", image_url),
                    "source_url": image_url,
                    "download_status": "robots_disallowed",
                }, None
            media_id = stable_id("amwine_media", image_url)
            provisional = RAW_ROOT / "images" / media_id
            existing = next((path for path in provisional.parent.glob(media_id + ".*")), None)
            if existing:
                data = existing.read_bytes()
                event = {
                    "url": image_url,
                    "status": 200,
                    "bytes": len(data),
                    "content_type": mimetypes.guess_type(existing.name)[0],
                    "captured_at": None,
                    "cache": "immutable_raw",
                }
                image_path = existing
            else:
                data, event = fetcher.get(image_url, accept_404=True)
                if data is None:
                    return image_url, {
                        "media_id": media_id,
                        "source_url": image_url,
                        "download_status": "http_error",
                        "http_status": event.get("status"),
                    }, None
                image_path = provisional.with_suffix(
                    image_extension(image_url, event.get("content_type"))
                )
                image_path.write_bytes(data)
            decoded = decode_image(data)
            row = {
                "manifest_version": "1.0.0",
                "source_id": SOURCE_ID,
                "source_capture_id": CAPTURE_ID,
                "media_id": media_id,
                "source_url": image_url,
                "relative_path": relative_to_root(image_path),
                "sha256": sha256_bytes(data),
                "bytes": len(data),
                "media_type": (
                    event.get("content_type")
                    or mimetypes.guess_type(image_path.name)[0]
                    or IMAGE_MIME_BY_FORMAT.get(decoded.get("format"))
                ),
                "download_status": "downloaded",
                "rights_status": "internal_noncommercial_research_pending_terms_review",
                "quality_status": "decode_ok" if decoded["decode_ok"] else "decode_error",
                "annotation_status": "bbox_not_required_catalog_reference",
                "product_association_count": len(associations),
                **decoded,
            }
            raw_record = raw_file_record(
                image_path, image_url, event
            )
            return image_url, row, raw_record

        media_executor = concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)
        media_futures = [
            media_executor.submit(capture_image, task)
            for task in sorted(image_urls.items())
        ]
        try:
            for future in concurrent.futures.as_completed(media_futures):
                image_url, row, raw_record = future.result()
                media_by_url[image_url] = row
                media_rows.append(row)
                if raw_record is not None:
                    raw_records[raw_record["relative_path"]] = raw_record
        except AccessBlocked:
            fetcher.blocked.set()
            for future in media_futures:
                future.cancel()
            media_executor.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            media_executor.shutdown(wait=True)
        media_rows.sort(key=lambda row: row["media_id"])
        asset_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in media_rows:
            asset_key = source_asset_key(row["source_url"])
            row["source_asset_key"] = asset_key
            row["derivative_group_id"] = stable_id("amwine_derivative", asset_key)
            row["parent_media_id"] = None
            asset_groups[asset_key].append(row)
        for rows in asset_groups.values():
            original = next(
                (
                    row
                    for row in rows
                    if "/resize_cache/" not in urllib.parse.urlsplit(row["source_url"]).path
                ),
                None,
            )
            if original is not None:
                for row in rows:
                    if row["media_id"] != original["media_id"]:
                        row["parent_media_id"] = original["media_id"]

        associations_rows: list[dict[str, Any]] = []
        membership_rows: list[dict[str, Any]] = []
        review_rows: list[dict[str, Any]] = []
        product_by_id = {product["product_id"]: product for product in products}
        for product in products:
            primary_media_sha = None
            selected_images = product["image_urls"]
            if args.image_mode == "primary":
                selected_images = selected_images[:1]
            elif args.image_mode == "none":
                selected_images = []
            for ordinal, image_url in enumerate(selected_images, 1):
                media = media_by_url.get(image_url, {})
                associations_rows.append({
                    "source_id": SOURCE_ID,
                    "source_capture_id": CAPTURE_ID,
                    "product_id": product["product_id"],
                    "external_product_id": product["external_product_id"],
                    "media_id": media.get("media_id") or stable_id("amwine_media", image_url),
                    "image_ordinal": ordinal,
                    "is_primary": ordinal == 1,
                    "source_url": image_url,
                    "association_grade": "gold",
                    "association_evidence": "product_jsonld_image",
                    "download_status": media.get("download_status", "not_downloaded"),
                    "decode_ok": media.get("decode_ok"),
                })
                if ordinal == 1 and media.get("sha256"):
                    primary_media_sha = media["sha256"]
            if primary_media_sha:
                product["label_design_id"] = stable_id("amwine_label", primary_media_sha)
            membership_rows.append({
                "source_id": SOURCE_ID,
                "source_capture_id": CAPTURE_ID,
                "catalog_id": "amwine.ru",
                "snapshot_date": CAPTURE_DATE,
                "external_product_id": product["external_product_id"],
                "product_id": product["product_id"],
                "bottle_variant_id": product["bottle_variant_id"],
                "label_design_id": product["label_design_id"],
                "source_url": product["canonical_url"],
                "country": product["country"],
                "country_evidence": product["country_evidence"],
                "svoe_slug": None,
            })
            reasons = []
            if not product["external_product_id"]:
                reasons.append("missing_external_product_id")
            if product["country"] != "Россия":
                reasons.append("country_not_confirmed_on_product_page")
            if not selected_images:
                reasons.append("no_selected_product_image")
            elif not any(
                row["product_id"] == product["product_id"]
                and row["is_primary"]
                and row["decode_ok"] is True
                for row in associations_rows
            ):
                reasons.append("primary_image_missing_or_decode_error")
            if reasons:
                review_rows.append({
                    "review_item_id": stable_id("review_amwine", product["product_id"]),
                    "source_dataset": "15_aromatny_mir_ru_wines",
                    "review_state": "needs_verification",
                    "product_id": product["product_id"],
                    "media_id": None,
                    "required_action": ";".join(reasons),
                    "evidence": [product["raw_page_path"], product["source_url"]],
                    "candidates": [],
                })

        content_groups: dict[str, list[str]] = defaultdict(list)
        for row in media_rows:
            if row.get("sha256"):
                content_groups[row["sha256"]].append(row["media_id"])
        duplicate_groups = {
            digest: ids for digest, ids in content_groups.items() if len(ids) > 1
        }
        for digest, duplicate_media_ids in sorted(duplicate_groups.items()):
            duplicate_associations = [
                row for row in associations_rows if row["media_id"] in duplicate_media_ids
            ]
            duplicate_product_ids = sorted(
                {row["product_id"] for row in duplicate_associations}
            )
            if len(duplicate_product_ids) < 2:
                continue
            for product_id in duplicate_product_ids:
                product_by_id[product_id]["quality_status"] = "needs_verification"
            for association in duplicate_associations:
                association["quality_status"] = (
                    "needs_verification_cross_product_exact_duplicate"
                )
            review_rows.append({
                "review_item_id": stable_id("review_amwine_duplicate", digest),
                "source_dataset": "15_aromatny_mir_ru_wines",
                "review_state": "needs_verification",
                "group_id": f"amwine_exact_duplicate_{digest[:20]}",
                "product_id": None,
                "media_id": duplicate_media_ids[0],
                "required_action": "cross_product_exact_duplicate_media",
                "evidence": [
                    media_by_url[row["source_url"]].get("relative_path")
                    for row in duplicate_associations
                ],
                "candidates": [
                    {
                        "product_id": row["product_id"],
                        "external_product_id": row["external_product_id"],
                        "media_id": row["media_id"],
                        "image_ordinal": row["image_ordinal"],
                    }
                    for row in duplicate_associations
                ],
            })
        # Product table does not need to repeat all source image URLs after the
        # explicit association table has been built.
        write_jsonl(OUT_ROOT / "tables" / "products.jsonl", products)
        write_jsonl(OUT_ROOT / "tables" / "media.jsonl", media_rows)
        write_jsonl(OUT_ROOT / "tables" / "product_media_associations.jsonl", associations_rows)
        write_jsonl(OUT_ROOT / "tables" / "catalog_memberships.jsonl", membership_rows)
        write_jsonl(OUT_ROOT / "tables" / "page_failures.jsonl", page_failures)
        write_jsonl(
            OUT_ROOT / "review" / "needs_verification" / "queue.jsonl", review_rows
        )
        annotation_queue = OUT_ROOT / "review" / "needs_annotation" / "queue.jsonl"
        if not annotation_queue.exists():
            write_jsonl(annotation_queue, [])
        for decisions in (
            OUT_ROOT / "review" / "verified" / "decisions.jsonl",
            OUT_ROOT / "review" / "rejected" / "decisions.jsonl",
        ):
            if not decisions.exists():
                write_jsonl(decisions, [])

        # Include every immutable raw artifact, including resumed files.
        for path in sorted(RAW_ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = relative_to_root(path)
            if rel not in raw_records:
                raw_records[rel] = {
                    "source_id": SOURCE_ID,
                    "source_capture_id": CAPTURE_ID,
                    "relative_path": rel,
                    "source_url": infer_cached_source_url(path),
                    "captured_at": None,
                    "http_status": None,
                    "content_type": mimetypes.guess_type(path.name)[0] or IMAGE_MIME_BY_SUFFIX.get(path.suffix.lower()),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_bytes(path.read_bytes()),
                }
        write_jsonl(OUT_ROOT / "tables" / "raw_files.jsonl", raw_records.values())
        write_jsonl(OUT_ROOT / "tables" / "crawl_events.jsonl", fetcher.events)

        product_ids = [product["product_id"] for product in products]
        association_product_ids = {row["product_id"] for row in associations_rows}
        media_ids = {row["media_id"] for row in media_rows}
        orphan_associations = [
            row for row in associations_rows if row["media_id"] not in media_ids
        ]
        country_counts = Counter(product.get("country") for product in products)
        summary = {
            "dataset_version": "1.0.0",
            "source_id": SOURCE_ID,
            "source_capture_id": CAPTURE_ID,
            "capture_date": CAPTURE_DATE,
            "generated_at": now_utc(),
            "status": "complete" if not stopped_reason else "partial_stopped",
            "crawl_policy": {
                "user_agent": USER_AGENT,
                "request_delay_seconds": args.delay,
                "sequential": args.workers == 1,
                "concurrent_workers": args.workers,
                "minimum_request_start_interval_seconds_per_host": args.delay,
                "hard_stop_statuses": [403, 429],
                "robots_aware": True,
                "cookies_used": False,
                "private_api_used": False,
                "image_mode": args.image_mode,
            },
            "counts": {
                "allowed_product_urls": len(allowed_product_rows),
                "selected_product_urls": len(selected_urls),
                "product_pages_parsed": len(products),
                "product_page_failures": len(page_failures),
                "unique_products": len(set(product_ids)),
                "external_product_ids": len({p["external_product_id"] for p in products if p["external_product_id"]}),
                "country_values": dict(sorted((str(k), v) for k, v in country_counts.items())),
                "explicit_russia_product_pages": sum(p["country"] == "Россия" for p in products),
                "product_image_urls_selected": len(image_urls),
                "media_urls_accounted": len(media_rows),
                "images_downloaded": sum(
                    row.get("download_status") == "downloaded" for row in media_rows
                ),
                "images_not_downloaded": sum(
                    row.get("download_status") != "downloaded" for row in media_rows
                ),
                "images_decode_ok": sum(row.get("decode_ok") is True for row in media_rows),
                "images_decode_error": sum(
                    row.get("download_status") == "downloaded"
                    and row.get("decode_ok") is False
                    for row in media_rows
                ),
                "product_media_associations": len(associations_rows),
                "products_with_media_association": len(association_product_ids),
                "orphan_media_associations": len(orphan_associations),
                "exact_duplicate_image_hash_groups": len(duplicate_groups),
                "source_asset_groups": len(asset_groups),
                "multi_representation_asset_groups": sum(
                    len(rows) > 1 for rows in asset_groups.values()
                ),
                "resize_cache_media": sum(
                    "/resize_cache/" in urllib.parse.urlsplit(row["source_url"]).path
                    for row in media_rows
                ),
                "needs_verification": len(review_rows),
                "needs_annotation": 0,
                "raw_files": len(raw_records),
                "fetch_events_this_run": len(fetcher.events),
            },
            "invariants": {
                "all_selected_pages_accounted": len(products) + len(page_failures) == len(selected_urls),
                "all_product_ids_unique": len(product_ids) == len(set(product_ids)),
                "all_parsed_products_have_external_id": all(p["external_product_id"] for p in products),
                "all_parsed_products_explicitly_russian": all(p["country"] == "Россия" for p in products),
                "all_downloaded_images_decode": all(
                    row.get("decode_ok") is True
                    for row in media_rows
                    if row.get("download_status") == "downloaded"
                ),
                "all_media_have_mime_type": all(row.get("media_type") for row in media_rows),
                "all_associations_reference_media": not orphan_associations,
                "no_forced_svoe_slug": all(p["svoe_slug"] is None for p in products),
            },
            "rights": {
                "purpose": "internal_noncommercial_research",
                "training_use": "pending_terms_and_asset_rights_review",
                "attribution": "source_url_and_capture_time_required",
                "derivatives": "legal_review",
                "redistribution": "not_confirmed",
            },
            "limitations": [
                "wine_family_id remains null until cross-source identity review",
                "label_design_id identifies exact primary-image bytes, not a manually reviewed rebrand family",
                "no Svoe Vino slug is inferred from retailer metadata",
                "availability and price reflect the site's default selected Moscow store context",
                "clean catalog images have no object bounding boxes; bbox annotation is not required for exact catalog association",
            ],
        }
        write_json(OUT_ROOT / "tables" / "SUMMARY.json", summary)
        audit = {
            "audit_version": "1.0.0",
            "source_id": SOURCE_ID,
            "source_capture_id": CAPTURE_ID,
            "generated_at": now_utc(),
            "checks": {
                "selected_pages_accounted": summary["invariants"]["all_selected_pages_accounted"],
                "product_ids_unique": summary["invariants"]["all_product_ids_unique"],
                "external_sku_complete": summary["invariants"]["all_parsed_products_have_external_id"],
                "country_explicit_on_every_product": summary["invariants"]["all_parsed_products_explicitly_russian"],
                "all_gallery_urls_accounted": len(media_rows) == len(image_urls),
                "downloaded_files_decode": summary["invariants"]["all_downloaded_images_decode"],
                "media_mime_complete": summary["invariants"]["all_media_have_mime_type"],
                "associations_reference_product": all(
                    row["product_id"] in product_by_id for row in associations_rows
                ),
                "associations_reference_media": summary["invariants"]["all_associations_reference_media"],
                "source_id_consistent": all(
                    row.get("source_id") == SOURCE_ID
                    for rows in (products, media_rows, associations_rows, membership_rows)
                    for row in rows
                ),
                "capture_id_consistent": all(
                    row.get("source_capture_id") == CAPTURE_ID
                    for rows in (products, media_rows, associations_rows, membership_rows)
                    for row in rows
                ),
                "no_null_image_serialized_as_url": all(
                    row["source_url"] != f"{BASE_URL}/None" for row in associations_rows
                ),
                "no_forced_svoe_slug": summary["invariants"]["no_forced_svoe_slug"],
                "raw_manifest_paths_exist": all(
                    (ROOT / row["relative_path"]).is_file() for row in raw_records.values()
                ),
                "raw_manifest_covers_capture": len(raw_records) == sum(
                    path.is_file() for path in RAW_ROOT.rglob("*")
                ),
                "raw_manifest_source_urls_complete": all(
                    row.get("source_url") for row in raw_records.values()
                ),
                "media_asset_lineage_complete": all(
                    row.get("source_asset_key") and row.get("derivative_group_id")
                    for row in media_rows
                ),
            },
            "bbox": {
                "status": "not_applicable_clean_catalog_reference",
                "reason": "source publishes isolated product gallery images, not multi-object scenes",
            },
            "review": {
                "needs_verification": len(review_rows),
                "needs_annotation": 0,
            },
        }
        audit["passed"] = all(audit["checks"].values())
        write_json(OUT_ROOT / "tables" / "AUDIT.json", audit)
        write_json(
            OUT_ROOT / "review" / "STATUS.json",
            {
                "source_dataset": "15_aromatny_mir_ru_wines",
                "needs_verification": len(review_rows),
                "needs_annotation": 0,
                "verified_decisions": 0,
                "rejected_decisions": 0,
                "generated_at": now_utc(),
            },
        )
        return summary
    except AccessBlocked as exc:
        stopped_reason = str(exc)
        write_jsonl(OUT_ROOT / "tables" / "crawl_events.jsonl", fetcher.events)
        partial = {
            "source_id": SOURCE_ID,
            "source_capture_id": CAPTURE_ID,
            "generated_at": now_utc(),
            "status": "partial_stopped",
            "stopped_reason": stopped_reason,
            "fetch_events_this_run": len(fetcher.events),
            "last_event": fetcher.events[-1] if fetcher.events else None,
        }
        write_json(OUT_ROOT / "tables" / "SUMMARY.json", partial)
        return partial
    finally:
        write_jsonl(OUT_ROOT / "tables" / "crawl_events.jsonl", fetcher.events)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--image-mode", choices=("none", "primary", "all"), default="primary")
    parser.add_argument("--max-products", type=int)
    parser.add_argument("--skip-brand-facets", action="store_true")
    parser.add_argument("--delay", type=float, default=0.8)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = run(args)
    return 2 if summary.get("status") == "partial_stopped" else 0


if __name__ == "__main__":
    sys.exit(main())
