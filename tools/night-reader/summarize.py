"""Gold-blind reader coverage, rank changes, and measured reader timing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ranked", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.ranked.read_text().splitlines() if line]
    if len(rows) != 316 or len({r["case_id"] for r in rows}) != 316:
        raise ValueError("expected 316 unique cases")
    timings = [r["reader_elapsed_ms"] for r in rows if r["reader_status"] == "ok"]
    changed = []
    for row in rows:
        before = row["baseline_top20"][0] if row["baseline_top20"] else None
        after = row["reader_fused_top20"][0]["slug"] if row["reader_fused_top20"] else None
        if before != after:
            changed.append({"case_id": row["case_id"], "dataset": row["dataset"],
                            "before": before, "after": after})
    summary = {
        "rows": len(rows),
        "unique_query_sha256": len({r["query_sha256"] for r in rows}),
        "status": {status: sum(r["reader_status"] == status for r in rows)
                   for status in sorted({r["reader_status"] for r in rows})},
        "reader_nonempty_text": sum(bool(r["reader_text"].strip()) and
                                    r["reader_text"].strip().upper() != "<EMPTY>"
                                    for r in rows),
        "paddle_nonempty_text": sum(bool(r["paddle_text"].strip()) for r in rows),
        "reader_ocr_nonempty_rank": sum(bool(r["reader_ocr_top20"]) for r in rows),
        "reader_ocr_top1_outside_B_top20": sum(
            bool(r["reader_ocr_top20"]) and
            r["reader_ocr_top20"][0]["slug"] not in r["baseline_top20"] for r in rows),
        "fused_top1_changes": changed,
        "reader_only_ms": {
            "count": len(timings), "p50": quantile(timings, .5),
            "p95": quantile(timings, .95), "p99": quantile(timings, .99),
            "max": round(max(timings), 3) if timings else None,
            "over_3000": sum(t > 3000 for t in timings),
            "over_10000": sum(t > 10000 for t in timings),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"rows": len(rows), "changed": len(changed),
                      "reader_nonempty_text": summary["reader_nonempty_text"],
                      "reader_p50_ms": summary["reader_only_ms"]["p50"]}))


if __name__ == "__main__":
    main()
