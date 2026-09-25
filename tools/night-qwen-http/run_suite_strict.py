"""Fresh HTTP capture with a real 10-second client deadline and server drain."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

DEADLINE_S = 10.0


def call(url: str, track: str, body: bytes):
    request = urllib.request.Request(
        url + "/v1/eval/predict?track=" + track,
        data=body, headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def drain(url: str):
    # The benchmark server is single-threaded. Its health reply can arrive only
    # after the timed-out prediction finishes, so the next case starts cleanly.
    with urllib.request.urlopen(url + "/healthz", timeout=180) as response:
        health = json.load(response)
    if health.get("status") != "ready":
        raise ValueError("server failed to drain")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    manifest = [json.loads(line) for line in args.inputs.read_text().splitlines() if line]
    if len(manifest) != 316:
        raise ValueError("expected 316 input rows")
    existing = ([json.loads(line) for line in args.out.read_text().splitlines() if line]
                if args.out.exists() else [])
    done = {row["case_id"] for row in existing}
    if len(done) != len(existing):
        raise ValueError("duplicate existing rows")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=1) as executor, args.out.open("a") as stream:
        for index, row in enumerate(manifest, 1):
            if row["case_id"] in done:
                continue
            body = (args.queries / row["query_path"]).read_bytes()
            if hashlib.sha256(body).hexdigest() != row["query_sha256"]:
                raise ValueError("input SHA mismatch " + row["case_id"])
            started = time.perf_counter()
            future = executor.submit(call, args.url, row["track"], body)
            try:
                status, result = future.result(timeout=DEADLINE_S)
                deadline_status = "on_time" if status == 200 else "http_error"
            except FutureTimeout:
                status = 0
                result = {"error": "client_deadline_10000ms"}
                deadline_status = "timeout"
            except Exception as exc:
                status = 0
                result = {"error": type(exc).__name__ + ": " + str(exc)[:300]}
                deadline_status = "transport_error"
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            if status == 200 and elapsed > 10000:
                status = 0
                deadline_status = "late_response"
                result = {"error": "client_deadline_10000ms"}
            late_stage = None
            if deadline_status == "timeout":
                # Health alone proves the server finished, but does not prove
                # this single-worker client has consumed its late response.
                # Finish that future before queuing another request.
                try:
                    late_status, late_result = future.result(timeout=180)
                    late_stage = {
                        "http_status": late_status,
                        "B_ms": late_result.get("b_ms"),
                        "Qwen_ms": late_result.get("rerank_ms"),
                        "server_wall_ms": late_result.get("server_wall_ms"),
                    }
                except Exception as exc:
                    late_stage = {"error": type(exc).__name__ + ": " + str(exc)[:200]}
                drain(args.url)
            output = {"case_id": row["case_id"], "track": row["track"],
                      "dataset": row["dataset"], "query_sha256": row["query_sha256"],
                      "http_status": status, "deadline_status": deadline_status,
                      "elapsed_ms": elapsed, "result": result,
                      "late_stage_diagnostic": late_stage}
            stream.write(json.dumps(output, ensure_ascii=False) + "\n")
            stream.flush()
            if index % 10 == 0 or status != 200:
                print(json.dumps({"processed": index, "total": len(manifest),
                                  "case_id": row["case_id"], "http_status": status,
                                  "deadline_status": deadline_status,
                                  "elapsed_ms": elapsed}), flush=True)
    print(json.dumps({"complete": True, "rows": len(manifest)}), flush=True)


if __name__ == "__main__":
    main()
