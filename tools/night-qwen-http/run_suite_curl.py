"""Fresh HTTP suite with curl's absolute 10s transaction deadline."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path


def drain(url: str) -> None:
    # The Qwen HTTP server handles one request at a time; this health reply
    # arrives only after any abandoned timed-out prediction has finished.
    probe = subprocess.run(
        ["curl", "--silent", "--show-error", "--max-time", "180",
         url + "/healthz"], capture_output=True, text=True, timeout=185)
    if probe.returncode != 0 or json.loads(probe.stdout).get("status") != "ready":
        raise RuntimeError("Qwen server did not drain after timeout")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--queries", type=Path, required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    manifest = [json.loads(line) for line in a.inputs.read_text().splitlines() if line]
    if len(manifest) != 316 or len({r["case_id"] for r in manifest}) != 316:
        raise ValueError("need 316 unique input rows")
    existing = ([json.loads(line) for line in a.out.read_text().splitlines() if line]
                if a.out.exists() else [])
    done = {r["case_id"] for r in existing}
    if len(done) != len(existing):
        raise ValueError("duplicate existing output")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    response_path = a.out.parent / "curl-response-strict.tmp"
    with a.out.open("a") as output:
        for index, row in enumerate(manifest, 1):
            if row["case_id"] in done:
                continue
            path = a.queries / row["query_path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != row["query_sha256"]:
                raise ValueError("query SHA mismatch " + row["case_id"])
            argv = ["curl", "--silent", "--show-error", "--http1.1",
                    "--connect-timeout", "5", "--max-time", "10",
                    "--header", "Content-Type: application/octet-stream",
                    "--header", "Expect:",
                    "--data-binary", "@" + str(path),
                    "--output", str(response_path),
                    "--write-out", "%{http_code} %{time_total}",
                    a.url + "/v1/eval/predict?track=" + row["track"]]
            started = time.perf_counter()
            try:
                run = subprocess.run(argv, capture_output=True, text=True, timeout=12)
                wall_ms = round((time.perf_counter() - started) * 1000, 3)
                fields = run.stdout.strip().split()
                curl_http = int(fields[0]) if fields and fields[0].isdigit() else 0
                curl_ms = round(float(fields[1]) * 1000, 3) if len(fields) >= 2 else None
                if run.returncode == 0 and curl_http == 200 and wall_ms <= 10000:
                    status = 200
                    result = json.loads(response_path.read_text())
                    deadline_status = "on_time"
                elif run.returncode == 28 or wall_ms > 10000:
                    status = 0
                    result = {"error": "client_deadline_10000ms"}
                    deadline_status = "timeout"
                else:
                    status = curl_http
                    result = {"error": "curl_exit_" + str(run.returncode) + ": " +
                              run.stderr.strip()[:250]}
                    deadline_status = "http_error" if curl_http else "transport_error"
            except subprocess.TimeoutExpired:
                wall_ms = round((time.perf_counter() - started) * 1000, 3)
                curl_ms = None
                status = 0
                result = {"error": "curl_process_timeout_12s"}
                deadline_status = "timeout"
            item = {"case_id": row["case_id"], "track": row["track"],
                    "dataset": row["dataset"], "query_sha256": row["query_sha256"],
                    "http_status": status, "deadline_status": deadline_status,
                    "elapsed_ms": wall_ms, "curl_time_total_ms": curl_ms,
                    "result": result}
            output.write(json.dumps(item, ensure_ascii=False) + "\n")
            output.flush()
            if deadline_status == "timeout":
                drain(a.url)
            if index % 10 == 0 or status != 200:
                print(json.dumps({"processed": index, "total": len(manifest),
                                  "case_id": row["case_id"], "http_status": status,
                                  "deadline_status": deadline_status,
                                  "elapsed_ms": wall_ms, "curl_time_total_ms": curl_ms}),
                      flush=True)
    print(json.dumps({"complete": True, "rows": len(manifest)}), flush=True)


if __name__ == "__main__":
    main()
