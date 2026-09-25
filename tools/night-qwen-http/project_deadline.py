"""Conservative retrospective 10s scoring projection from uncapped HTTP times."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    rows = [json.loads(line) for line in a.raw.read_text().splitlines() if line]
    if len(rows) != len({row["case_id"] for row in rows}) or len(rows) != 316:
        raise ValueError("need complete uncapped capture")
    projected = []
    for row in rows:
        copy = dict(row)
        late = row["elapsed_ms"] > 10000
        copy["deadline_projection"] = "late_as_error" if late else "on_time"
        if late:
            copy["http_status"] = 0
            copy["result"] = {"error": "projected_client_deadline_10000ms"}
        projected.append(copy)
    a.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                             for row in projected))
    print(json.dumps({"rows": len(projected),
                      "projected_late": sum(r["deadline_projection"] == "late_as_error"
                                            for r in projected)}))


if __name__ == "__main__":
    main()
