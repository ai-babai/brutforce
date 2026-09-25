"""Adapt saved gold-blind rerank rows to the organizer diagnostic scorer."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--variant", choices=("local", "fusion", "cascade"), required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    rows = [json.loads(line) for line in args.raw.read_text().splitlines() if line]
    with args.out.open("w") as output:
        for row in rows:
            ranking = row[args.variant + "_top20"]
            result = {"ranked_slugs": ranking}
            if ranking:
                result["slug"] = ranking[0]
            else:
                result["action"] = row["baseline_action"] or "insufficient_information"
            payload = {"case_id": row["case_id"], "query_sha256": row["query_sha256"],
                       "http_status": 200, "result": result,
                       "elapsed_ms": round((row.get("baseline_elapsed_ms") or 0) +
                                           row["rerank_elapsed_ms"], 3)}
            output.write(json.dumps(payload, ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(rows), "variant": args.variant, "out": str(args.out)}))


if __name__ == "__main__":
    main()
