#!/usr/bin/env python3
"""Independent visual QA for the wine-image pilot.

Reads the parent-owned manifest without changing it.  Results are append-only
and re-entrant: a completed output SHA is never sent to the judge twice.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


CORPUS_ROOT = Path("/Users/skif/ml-data/brutforce/vision-pilot-20260924")
KEY_PATH = Path("/Users/skif/skif-os/v001/secrets/agent-ops/values/brutforce/lct-openrouter-api-key")
MODEL = "deepseek/deepseek-v4.1-flash"
API_URL = "https://openrouter.ai/api/v1/chat/completions"
QA_VERSION = "deepseek-v4.1-flash-independent-qa-v2"
MAX_TOTAL_USD = 0.50
RESERVED_PER_CALL_USD = 0.005
MAX_WORKERS = 2  # Kept as a contract limit; calls stay sequential for ledger safety.

SCHEMA = {
    "identity_correct": "yes|no|uncertain",
    "label_changed": False,
    "exact_differences": ["short concrete visual difference"],
    "observed_conditions": {"field": "value or uncertain"},
    "scenario_fulfilled": "yes|partial|no",
    "realistic": "yes|partial|no",
    "suggested_qc": "accepted|rejected|pending",
    "reason": "one concise sentence",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_data_url(path: Path) -> str:
    """JPEG-encode an RGB copy constrained to 1024px; source files stay intact."""
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        rgb.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        from io import BytesIO
        buffer = BytesIO()
        rgb.save(buffer, "JPEG", quality=90, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def validate_file_record(root: Path, record: dict[str, Any], role: str) -> Path:
    """Ensure the exact manifest bytes, not a later substitution, reach the API."""
    relative_path = record.get("path")
    expected_hash = record.get("sha256")
    if not isinstance(relative_path, str) or not relative_path:
        raise RuntimeError(f"{role} has no manifest path")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise RuntimeError(f"{role} has no valid manifest SHA-256")
    path = root / relative_path
    if not path.is_file():
        raise RuntimeError(f"{role} file is missing: {relative_path}")
    actual_hash = sha256(path)
    if actual_hash != expected_hash:
        raise RuntimeError(f"{role} SHA-256 mismatch: {relative_path}")
    return path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSONL at {path}:{number}") from exc
    return rows


def completed_keys(qc_path: Path) -> set[tuple[str, str]]:
    return {
        (row.get("output_image_id", ""), row.get("output_sha256", ""))
        for row in load_jsonl(qc_path)
        if row.get("qa_version") == QA_VERSION and row.get("status") == "completed"
    }


def ledger_accounting(ledger_path: Path) -> tuple[float, dict[str, int]]:
    """Return conservative cost and outcome counts without double-counting attempts.

    A started request is reserved until a terminal row proves its actual cost or
    a known pre-inference rejection. Legacy validation failures occurred after
    an HTTP response but before response usage was persisted, so they remain
    conservatively reserved.
    """
    attempts: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(load_jsonl(ledger_path)):
        if row.get("model") != MODEL:
            continue
        attempt_id = row.get("attempt_id") or f"legacy-{index}"
        attempts.setdefault(attempt_id, {}).update(row)
    total = 0.0
    counts = {"completed_actual": 0, "completed_reserved": 0, "failed_actual": 0, "known_unbilled": 0, "unknown_reserved": 0}
    for row in attempts.values():
        status = row.get("status")
        reserve = float(row.get("reserved_cost_usd") or RESERVED_PER_CALL_USD)
        charged = row.get("charged_cost_usd")
        if row.get("billing_outcome") == "known_unbilled" or (status == "failed" and str(row.get("error", "")).startswith("OpenRouter HTTP 400")):
            counts["known_unbilled"] += 1
        elif isinstance(charged, (int, float)):
            total += float(charged)
            if status == "completed":
                counts["completed_actual"] += 1
            else:
                counts["failed_actual"] += 1
        elif status == "completed":
            total += reserve
            counts["completed_reserved"] += 1
        else:
            total += reserve
            counts["unknown_reserved"] += 1
    return total, counts


def spent_or_reserved(ledger_path: Path) -> float:
    return ledger_accounting(ledger_path)[0]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def acquire_runner_lock(root: Path):
    """Acquire a process-lifetime non-blocking lock for a spending run."""
    lock_path = root / "qa-runner.lock"
    lock_file = lock_path.open("a+")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_file.close()
        raise RuntimeError(f"Another QA runner holds {lock_path}") from exc
    return lock_file


def read_manifest(root: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    rows = load_jsonl(root / "manifest.jsonl")
    by_id = {row["image_id"]: row for row in rows if row.get("image_id")}
    outputs = [row for row in rows if row.get("role") == "output"]
    return by_id, outputs


def contact_sheets(root: Path) -> int:
    """Render output review sheets in stable groups of ten with identity insets."""
    by_id, outputs = read_manifest(root)
    output_dir = root / "contact-sheets"
    output_dir.mkdir(parents=True, exist_ok=True)
    cell_width, cell_height, inset_size, gap, header = 480, 390, 116, 16, 36
    columns = 2
    written = 0
    for start in range(0, len(outputs), 10):
        batch = outputs[start : start + 10]
        rows = (len(batch) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * cell_width + (columns + 1) * gap, header + rows * cell_height + (rows + 1) * gap), "#171717")
        draw = ImageDraw.Draw(sheet)
        draw.text((gap, 10), f"Wine pilot outputs {start + 1}-{start + len(batch)}; identity inset at upper left", fill="white")
        for index, output in enumerate(batch):
            col, row = index % columns, index // columns
            x, y = gap + col * (cell_width + gap), header + gap + row * (cell_height + gap)
            output_path = root / output["path"]
            identity = by_id.get(output.get("identity_reference_id"))
            if not output_path.is_file() or not identity or not (root / identity["path"]).is_file():
                draw.text((x, y), f"Missing source for {output.get('image_id', 'unknown')}", fill="#ff8888")
                continue
            with Image.open(output_path) as image:
                candidate = image.convert("RGB")
                candidate.thumbnail((cell_width, cell_height - 28), Image.Resampling.LANCZOS)
                cx = x + (cell_width - candidate.width) // 2
                sheet.paste(candidate, (cx, y))
            with Image.open(root / identity["path"]) as image:
                inset = image.convert("RGB")
                inset.thumbnail((inset_size, inset_size), Image.Resampling.LANCZOS)
                sheet.paste(inset, (x + 6, y + 6))
            label = f"{index + start + 1:02d} {output.get('model', 'unknown')}"
            draw.rectangle((x, y + cell_height - 27, x + cell_width, y + cell_height), fill="#000000")
            draw.text((x + 5, y + cell_height - 22), label[:76], fill="white")
        path = output_dir / f"outputs-{start + 1:03d}-{start + len(batch):03d}.jpg"
        sheet.save(path, "JPEG", quality=88, optimize=True)
        written += 1
    return written


def judge_prompt(output: dict[str, Any], identity: dict[str, Any], scene: dict[str, Any] | None) -> str:
    requested = output.get("requested_conditions") or {}
    catalog = (identity.get("source") or {}).get("catalog_text") or {}
    scene_observed = (scene or {}).get("observed_conditions") or {}
    # Providers and model names are deliberately omitted so this remains blind.
    return f"""You are an independent visual evaluator for a wine image-editing pilot. You receive images in this exact order: (1) authoritative identity reference, (2) generated candidate, and optionally (3) a setting-only scene reference. Do not assume the candidate is good. Do not use any model/provider speculation.

Compare the candidate with the identity reference for the SAME wine. Check label visual design, printed producer, printed wine name, printed year/vintage only where text is visually legible, bottle geometry, color, foil/capsule, and major label layout. If text or an angle cannot be read, say uncertain; never invent it. The scene reference supplies setting, lighting, and framing only: do not require its bottles or text to match.

Requested conditions: {json.dumps(requested, ensure_ascii=False)}
Scene observations: {json.dumps(scene_observed, ensure_ascii=False)}
Catalog text is context only, not proof of unreadable label text: {json.dumps({k: catalog.get(k) for k in ('winery', 'wine_name')}, ensure_ascii=False)}

Assess geometry, lighting, glare, crop, and occlusion against requested conditions. If requested label visibility is partial but the candidate label is fully visible, scenario_fulfilled must be partial or no and suggested_qc must be pending or rejected, never accepted. If identity changes materially, suggested_qc must be rejected. Use pending whenever visual evidence cannot support a firm decision.

Return JSON only, matching this schema exactly (no Markdown). `label_changed` must be the JSON boolean literal true or false, never a quoted word:
{json.dumps(SCHEMA, ensure_ascii=False)}"""


class KnownUnbilledError(RuntimeError):
    """An API rejection before inference; it consumes no retained reserve."""


def call_openrouter(key: str, prompt: str, identity_path: Path, output_path: Path, scene_path: Path | None) -> tuple[str, dict[str, Any], float]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": image_data_url(identity_path)}},
        {"type": "image_url", "image_url": {"url": image_data_url(output_path)}},
    ]
    if scene_path:
        content.append({"type": "image_url", "image_url": {"url": image_data_url(scene_path)}})
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 600,
        "reasoning": {"enabled": False},
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(detail).get("error", {}).get("message", "request rejected")
        except json.JSONDecodeError:
            message = "request rejected"
        error = f"OpenRouter HTTP {exc.code}: {message}"
        if 400 <= exc.code < 500:
            raise KnownUnbilledError(error) from exc
        raise RuntimeError(error) from exc
    latency_ms = (time.perf_counter() - started) * 1000
    choices = raw.get("choices") or []
    text = (choices[0].get("message") or {}).get("content") if choices else None
    if not isinstance(text, str):
        raise RuntimeError("OpenRouter returned no judge content")
    return text, raw, latency_ms


def validate_judgement(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("Judge result is not a JSON object")
    required = set(SCHEMA)
    if set(value) != required:
        raise RuntimeError(f"Judge JSON keys differ from contract: {sorted(set(value) ^ required)}")
    if value["identity_correct"] not in {"yes", "no", "uncertain"}:
        raise RuntimeError("Invalid identity_correct")
    if not isinstance(value["label_changed"], bool):
        raise RuntimeError("label_changed must be boolean")
    if value["scenario_fulfilled"] not in {"yes", "partial", "no"}:
        raise RuntimeError("Invalid scenario_fulfilled")
    if value["realistic"] not in {"yes", "partial", "no"}:
        raise RuntimeError("Invalid realistic")
    if value["suggested_qc"] not in {"accepted", "rejected", "pending"}:
        raise RuntimeError("Invalid suggested_qc")
    if not isinstance(value["exact_differences"], list) or not isinstance(value["observed_conditions"], dict) or not isinstance(value["reason"], str):
        raise RuntimeError("Invalid judge JSON value types")
    return value


def actual_cost(raw: dict[str, Any]) -> float | None:
    usage = raw.get("usage") or {}
    for key in ("cost", "total_cost"):
        value = usage.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=CORPUS_ROOT)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--contact-sheets-only", action="store_true")
    args = parser.parse_args()
    root = args.root
    if args.contact_sheets_only:
        print(json.dumps({"contact_sheets_written": contact_sheets(root)}, ensure_ascii=False))
        return
    lock_file = None if args.dry_run else acquire_runner_lock(root)
    qc_path, ledger_path, raw_dir = root / "qc-deepseek.jsonl", root / "qa-ledger.jsonl", root / "qa-raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    completed = completed_keys(qc_path)
    spent, accounting = ledger_accounting(ledger_path)
    by_id, outputs = read_manifest(root)
    key = "" if args.dry_run else KEY_PATH.read_text(encoding="utf-8").strip()
    if not args.dry_run and not key:
        raise RuntimeError("OpenRouter API key file is empty")

    candidates = []
    invalid_sources = []
    for output in outputs:
        try:
            output_path = validate_file_record(root, output, "output")
            output_hash = output["sha256"]
            identity = by_id.get(output.get("identity_reference_id"))
            if not identity:
                raise RuntimeError("output has no identity reference")
            identity_path = validate_file_record(root, identity, "identity reference")
            scene = by_id.get(output.get("scene_reference_id"))
            scene_path = validate_file_record(root, scene, "scene reference") if scene else None
        except RuntimeError as exc:
            invalid_sources.append({"image_id": output.get("image_id"), "reason": str(exc)})
            continue
        if (output["image_id"], output_hash) in completed:
            continue
        candidates.append((output, output_hash, identity, scene, output_path, identity_path, scene_path))
    if args.limit is not None:
        candidates = candidates[:args.limit]

    summary = {"available_outputs": len(outputs), "eligible": len(candidates), "already_completed": len(completed), "invalid_sources": invalid_sources, "ledger_total_usd": spent, "ledger_accounting": accounting, "max_total_usd": MAX_TOTAL_USD, "dry_run": args.dry_run}
    for output, output_hash, identity, scene, output_path, identity_path, scene_path in candidates:
        if spent + RESERVED_PER_CALL_USD > MAX_TOTAL_USD:
            summary["budget_stop"] = True
            break
        if args.dry_run:
            print(json.dumps({**summary, "would_judge": output["image_id"]}, ensure_ascii=False))
            continue
        prompt = judge_prompt(output, identity, scene)
        started_at = time.time()
        attempt_id = str(uuid.uuid4())
        ledger_base = {"qa_version": QA_VERSION, "attempt_id": attempt_id, "output_image_id": output["image_id"], "output_sha256": output_hash, "model": MODEL, "reserved_cost_usd": RESERVED_PER_CALL_USD, "started_at_unix": started_at}
        append_jsonl(ledger_path, {**ledger_base, "status": "started", "billing_outcome": "unknown"})
        raw = None
        raw_path = None
        cost = None
        try:
            judgement_text, raw, latency_ms = call_openrouter(key, prompt, identity_path, output_path, scene_path)
            raw_path = raw_dir / f"{output['image_id']}--{QA_VERSION}--{attempt_id}.json"
            raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
            cost = actual_cost(raw)
            judgement = json.loads(judgement_text)
            judgement = validate_judgement(judgement)
            result = {"qa_version": QA_VERSION, "status": "completed", "output_image_id": output["image_id"], "output_sha256": output_hash, "identity_reference_id": identity["image_id"], "scene_reference_id": scene["image_id"] if scene else None, "model": MODEL, "latency_ms": round(latency_ms, 1), "cost_usd": cost, "raw_response_path": str(raw_path.relative_to(root)), "judgement": judgement}
            append_jsonl(qc_path, result)
            append_jsonl(ledger_path, {**ledger_base, "status": "completed", "charged_cost_usd": cost, "latency_ms": round(latency_ms, 1), "raw_response_path": str(raw_path.relative_to(root))})
            spent += cost if cost is not None else RESERVED_PER_CALL_USD
            summary["completed"] = summary.get("completed", 0) + 1
        except KnownUnbilledError as exc:
            append_jsonl(ledger_path, {**ledger_base, "status": "failed", "billing_outcome": "known_unbilled", "charged_cost_usd": 0.0, "error": str(exc)[:1000]})
            summary["failed"] = summary.get("failed", 0) + 1
        except Exception as exc:
            details = {**ledger_base, "status": "failed", "billing_outcome": "unknown", "charged_cost_usd": cost, "error": str(exc)[:1000]}
            if raw_path:
                details["raw_response_path"] = str(raw_path.relative_to(root))
            append_jsonl(ledger_path, details)
            spent += cost if cost is not None else RESERVED_PER_CALL_USD
            summary["failed"] = summary.get("failed", 0) + 1
    if lock_file:
        lock_file.close()
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
