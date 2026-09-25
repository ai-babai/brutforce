"""Gold-blind fresh HTTP coverage, parity, and latency summary."""
import argparse
import json
from pathlib import Path


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return round(values[lower] + (values[upper] - values[lower]) * (position - lower), 3)


def timing(rows, field):
    values = [r[field] for r in rows]
    return {"count": len(values), "p50": percentile(values, .5),
            "p95": percentile(values, .95), "p99": percentile(values, .99),
            "max": round(max(values), 3) if values else None,
            "over_10000": sum(value > 10000 for value in values)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--stage", type=Path, required=True)
    p.add_argument("--offline-scores", type=Path)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    rows = [json.loads(line) for line in a.raw.read_text().splitlines() if line]
    stage = {r["case_id"]: r for r in map(json.loads, a.stage.open())}
    if len(rows) != len(stage) or len(rows) != 316:
        raise ValueError("need complete full suite")
    offline = ({r["case_id"]: r for r in map(json.loads, a.offline_scores.open())}
               if a.offline_scores else {})
    order_mismatch = []
    set_mismatch = []
    top1_action_mismatch = []
    qwen_score_mismatch = []
    for row in rows:
        original = stage[row["case_id"]]["baseline_row"]["result"]
        fresh = row["result"].get("b_result", {})
        before = original.get("ranked_slugs") or []
        after = fresh.get("ranked_slugs") or []
        if before != after:
            order_mismatch.append(row["case_id"])
        if set(before) != set(after):
            set_mismatch.append(row["case_id"])
        if (before[:1] != after[:1] or
                original.get("slug", original.get("action")) !=
                fresh.get("slug", fresh.get("action"))):
            top1_action_mismatch.append(row["case_id"])
        if offline and row["http_status"] == 200:
            reference = offline[row["case_id"]]
            observed = row["result"]
            if dict(zip(reference["candidates"], reference["scores"])) != dict(
                    zip(observed["candidates"], observed["scores"])):
                qwen_score_mismatch.append(row["case_id"])
    groups = {}
    for group in ("eval-service", "eval-retrieval", "organizer"):
        selected = [r for r in rows if ((r["dataset"] == "eval" and
                      group == "eval-" + r["track"]) or
                      (r["dataset"] == "organizer" and group == "organizer"))]
        ok = [r for r in selected if r["http_status"] == 200]
        groups[group] = {
            "requests": len(selected), "http_200": len(ok),
            "client_total_ms": timing(ok, "elapsed_ms"),
            "B_ms": timing([r["result"] for r in ok], "b_ms"),
            "Qwen_ms": timing([r["result"] for r in ok], "rerank_ms"),
        }
    summary = {"rows": len(rows), "unique_query_sha256": len({r["query_sha256"] for r in rows}),
               "http_200": sum(r["http_status"] == 200 for r in rows),
               "B_exact_order_mismatch_ids": order_mismatch,
               "B_candidate_set_mismatch_ids": set_mismatch,
               "B_top1_or_action_mismatch_ids": top1_action_mismatch,
               "Qwen_score_by_slug_mismatch_ids": qwen_score_mismatch,
               "groups": groups}
    a.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"rows": len(rows), "http_200": summary["http_200"],
                      "B_exact_order_mismatches": len(order_mismatch),
                      "B_candidate_set_mismatches": len(set_mismatch),
                      "B_top1_or_action_mismatches": len(top1_action_mismatch),
                      "Qwen_score_by_slug_mismatches": len(qwen_score_mismatch)}))


if __name__ == "__main__":
    main()
