"""Conservative post-hoc development gate over already saved geometry evidence.

Chosen after analysis of the first negative frozen result. Never describe its
same-suite score as independent validation.
"""
import argparse
import collections
import json
from pathlib import Path

MIN_INLIERS = 50
MIN_COVERAGE = 0.10
MIN_SCORE_RATIO = 2.0
MAX_BASELINE_RANK = 5


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--reference-meta", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    meta = json.loads(args.reference_meta.read_text())
    ready = [r for r in meta["references"] if r["status"] == "ready"]
    count_by_sha = collections.Counter(r["reference_sha256"] for r in ready)
    ref_by_slug = {r["slug"]: r for r in ready}
    rows = [json.loads(line) for line in args.raw.read_text().splitlines() if line]
    changed = []
    with args.out.open("w") as output:
        for row in rows:
            pool = row["baseline_top20"]
            selected = None
            if pool:
                evidence = {e["slug"]: e for e in row["evidence"]}
                b_score = evidence[pool[0]]["geometry"].get("score", 0.0)
                candidates = []
                for slug in pool[1:MAX_BASELINE_RANK]:
                    ref = ref_by_slug.get(slug)
                    if not ref or count_by_sha[ref["reference_sha256"]] != 1:
                        continue
                    geom = evidence[slug]["geometry"]
                    if (geom.get("inliers", 0) >= MIN_INLIERS
                            and geom.get("coverage", 0.0) >= MIN_COVERAGE
                            and geom.get("score", 0.0) >= MIN_SCORE_RATIO * max(b_score, 1.0)):
                        candidates.append(slug)
                if candidates:
                    selected = max(candidates, key=lambda slug: evidence[slug]["geometry"]["score"])
            if selected:
                row["cascade_top20"] = [selected] + [slug for slug in pool if slug != selected]
                changed.append(row["case_id"])
            else:
                row["cascade_top20"] = pool[:]
            row["cascade_reason"] = "strong_unique_reference_geometry" if selected else "preserve_B"
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(rows), "changed": len(changed), "case_ids": changed}))


if __name__ == "__main__":
    main()
