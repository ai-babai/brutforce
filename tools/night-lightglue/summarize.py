"""Gold-blind coverage, change, and offline timing summary."""
import argparse
import json
import math
from pathlib import Path


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * q
    low = int(pos)
    high = min(low + 1, len(values) - 1)
    return round(values[low] * (1 - (pos - low)) + values[high] * (pos - low), 3)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    rows = [json.loads(line) for line in args.raw.read_text().splitlines() if line]
    times = [r["rerank_elapsed_ms"] for r in rows]
    unique_sha = {r["query_sha256"] for r in rows}
    candidates = [e for r in rows for e in r["evidence"]]
    changes = {}
    for variant in ("local", "fusion"):
        changed = []
        for r in rows:
            before = r["baseline_top20"][:1]
            after = r[variant + "_top20"][:1]
            if before != after:
                changed.append({"case_id": r["case_id"], "query_sha256": r["query_sha256"],
                                "before": before, "after": after})
        changes[variant] = changed
    summary = {
        "rows": len(rows), "unique_query_images": len(unique_sha),
        "status_counts": {k: sum(r["status"] == k for r in rows)
                          for k in sorted({r["status"] for r in rows})},
        "candidate_pairs": len(candidates),
        "missing_reference_pairs": sum(e["status"] == "missing_reference" for e in candidates),
        "match_error_pairs": sum(e["status"] == "match_error" for e in candidates),
        "valid_geometry_pairs": sum(e["geometry"]["valid"] for e in candidates),
        "queries_with_valid_geometry": sum(any(e["geometry"]["valid"] for e in r["evidence"])
                                               for r in rows),
        "rerank_elapsed_ms": {"p50": percentile(times, .5), "p95": percentile(times, .95),
                              "p99": percentile(times, .99), "max": max(times) if times else None,
                              "over_3000": sum(t > 3000 for t in times),
                              "over_10000": sum(t > 10000 for t in times)},
        "top1_changes": changes,
    }
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"rows": len(rows), "candidate_pairs": len(candidates),
                      "valid_geometry_pairs": summary["valid_geometry_pairs"],
                      "changed_local": len(changes["local"]),
                      "changed_fusion": len(changes["fusion"])}))


if __name__ == "__main__":
    main()
