#!/usr/bin/env python3
"""Detached Codex or Hermes worker used by the Sigma team adapters."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


class CancellationRequested(Exception):
    pass


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def _valid_review(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("verdict") in {"pass", "fail", "blocked"}
        and isinstance(value.get("summary"), str)
        and isinstance(value.get("findings"), list)
        and all(isinstance(item, str) for item in value["findings"])
        and isinstance(value.get("human_verification"), list)
        and all(isinstance(item, str) for item in value["human_verification"])
    )


def parse_review(raw: str) -> dict:
    # Hermes may emit a startup warning even with -Q. Accept only a final,
    # complete review object; never mistake earlier tool output for a verdict.
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            output, end = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if raw[index + end:].strip() not in {"", "```"}:
            continue
        if isinstance(output, dict) and isinstance(output.get("findings"), list):
            output["findings"] = [json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else x
                                  for x in output["findings"]]
        if _valid_review(output):
            return output
    raise ValueError("No complete final review object")


def _run_command(command: list[str], *, input_data: bytes | None, stdout, stderr, env: dict, timeout: int,
                 on_start=None):
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
        stdout=stdout, stderr=stderr, env=env, start_new_session=True,
    )
    if on_start is not None:
        on_start(process)
    try:
        process.communicate(input=input_data, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise
    return process


def main() -> int:
    manifest_path = Path(sys.argv[1])
    manifest = json.loads(manifest_path.read_text())
    run_dir = manifest_path.parent
    result_path = run_dir / "result.json"
    stdout_path = run_dir / "worker.stdout.jsonl"
    stderr_path = run_dir / "worker.stderr.log"
    last_message_path = run_dir / "last-message.json"

    worker_kind = manifest.get("worker_kind", "codex")
    if worker_kind == "hermes":
        query_path = run_dir / "review-query.txt"
        query_path.write_text(manifest["prompt"])
        command = [
            manifest["bwrap_bin"], "--ro-bind", "/", "/",
            "--dev-bind", "/dev", "/dev", "--tmpfs", "/proc", "--tmpfs", "/tmp",
            "--tmpfs", "/home/sigma-ops", "--dir", "/tmp/reviewer-home",
            "--bind", manifest["hermes_home"], "/tmp/reviewer-home",
            "--chdir", manifest["workdir"],
            manifest["hermes_bin"], "chat", "--oneshot", "--query-file", str(query_path),
            "--max-turns", "8", "--run-budget", "120", "--yolo", "-Q",
            "--provider", manifest["provider"], "--model", manifest["model"],
            "--reasoning", "medium", "--toolsets", "terminal,file", "--source", "tool",
        ]
    else:
        command = [manifest["codex_bin"],
        "exec",
        "--json",
        "--color",
        "never",
        "--skip-git-repo-check",
        "--sandbox",
        manifest["sandbox"],
        "--model",
        manifest["model"],
        "-c",
        'model_reasoning_effort="medium"',
        "-c",
        "sandbox_workspace_write.network_access=true",
        "-C",
        manifest["workdir"],
        "--output-schema",
        str(run_dir / "output-schema.json"),
        "--output-last-message",
        str(last_message_path),
        "-",
        ]
    env = os.environ.copy()
    if worker_kind == "hermes":
        env["HERMES_HOME"] = "/tmp/reviewer-home"
        env["HOME"] = "/tmp/reviewer-home"
        for name in (
            "TELEGRAM_BOT_TOKEN", "OPENCODE_SERVER_USERNAME", "OPENCODE_SERVER_PASSWORD",
            "GH_TOKEN", "GITHUB_TOKEN", "GH_CONFIG_DIR", "SIGMA_STT_TOKEN",
        ):
            env.pop(name, None)
        # Owner explicitly requires private repository access for Hermes review.
        # Reuse the Sigma identity; filesystem is read-only, API writes are
        # forbidden by the reviewer role (not by this credential's scopes).
        env["GH_CONFIG_DIR"] = manifest["gh_config_dir"]
    else:
        env["CODEX_HOME"] = manifest["codex_home"]
        env["GH_CONFIG_DIR"] = manifest["gh_config_dir"]
    started = int(time.time())
    child = [None]

    def cancelled(_signum, _frame):
        # The adapter signals only this detached worker's recorded process group.
        # This worker owns the child group and turns that signal into durable state.
        raise CancellationRequested()

    signal.signal(signal.SIGTERM, cancelled)
    signal.signal(signal.SIGINT, cancelled)
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            completed = _run_command(
                command, input_data=None if worker_kind == "hermes" else manifest["prompt"].encode(),
                stdout=stdout, stderr=stderr, env=env, timeout=manifest["timeout_seconds"],
                on_start=lambda process: child.__setitem__(0, process),
            )
        payload = {
            "state": "succeeded" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode,
            "started_at": started,
            "finished_at": int(time.time()),
        }
        if worker_kind == "hermes" and completed.returncode == 0:
            raw = stdout_path.read_text().strip()
            try:
                output = parse_review(raw)
                payload["output"] = output
            except (json.JSONDecodeError, ValueError):
                payload.update({"state": "failed", "summary": "Hermes reviewer did not return valid review JSON"})
        elif last_message_path.exists():
            try:
                payload["output"] = json.loads(last_message_path.read_text())
            except json.JSONDecodeError:
                payload["output"] = {"summary": last_message_path.read_text()[-8000:]}
        if completed.returncode:
            payload["summary"] = f"{worker_kind.title()} exited with status {completed.returncode}"
        _atomic_json(result_path, payload)
        return completed.returncode
    except CancellationRequested:
        process = child[0]
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        _atomic_json(result_path, {
            "state": "cancelled",
            "summary": "Worker cancellation requested by adapter",
            "started_at": started,
            "finished_at": int(time.time()),
        })
        return 0
    except subprocess.TimeoutExpired:
        _atomic_json(result_path, {
            "state": "blocked",
            "summary": f"{worker_kind.title()} exceeded the {manifest['timeout_seconds']} second limit",
            "started_at": started,
            "finished_at": int(time.time()),
        })
        return 124
    except Exception as error:
        _atomic_json(result_path, {
            "state": "failed",
            "summary": f"Worker launch failed: {type(error).__name__}: {error}",
            "started_at": started,
            "finished_at": int(time.time()),
        })
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
