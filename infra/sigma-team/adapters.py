#!/usr/bin/env python3
"""Asynchronous executor and reviewer adapters for Sigma's team dispatcher."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class AdapterError(RuntimeError):
    pass


RUN_ROOT = Path(os.environ.get("SIGMA_TEAM_RUN_ROOT", "/srv/agents/sigma/team/runs"))
OPENCODE_URL = os.environ.get("SIGMA_OPENCODE_URL", "http://127.0.0.1:4096").rstrip("/")
OPENCODE_WEB_URL = os.environ.get("SIGMA_OPENCODE_WEB_URL", "https://code.dzap.pw").rstrip("/")
OPENCODE_AGENT = os.environ.get("SIGMA_OPENCODE_AGENT", "sigma-worker")
OPENCODE_PROVIDER = os.environ.get("SIGMA_OPENCODE_PROVIDER", "clirelay")
CODEX_BIN = os.environ.get("SIGMA_CODEX_BIN", "/opt/codex/0.154.0/bin/codex")
CODEX_HOME = os.environ.get("SIGMA_CODEX_HOME", "/home/sigma-ops/.codex-sigma-worker")
HERMES_BIN = os.environ.get("SIGMA_HERMES_BIN", "/opt/sigma-hermes/venv/bin/hermes")
HERMES_HOME = os.environ.get("SIGMA_REVIEWER_HERMES_HOME", "/home/sigma-ops/.hermes-reviewer")
BWRAP_BIN = os.environ.get("SIGMA_BWRAP_BIN", "/usr/bin/bwrap")
GH_CONFIG_DIR = os.environ.get("SIGMA_GH_CONFIG_DIR", "/etc/sigma-team/github")
ALLOWED_MODELS = {"gpt-5.6-terra", "gpt-5.6-sol"}
PROJECT_ID = "PVT_kwHOCw80aM4Bjtu9"
STATUS_FIELD_ID = "PVTSSF_lAHOCw80aM4Bjtu9zhihCOk"
SIGMA_VERIFICATION_OPTION_ID = "b250bbfa"


def _safe_run_id(run_id: str) -> str:
    if not run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in run_id):
        raise AdapterError("run_id contains unsupported characters")
    return run_id


def _run_dir(run_id: str) -> Path:
    return RUN_ROOT / _safe_run_id(run_id)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def _http(method: str, path: str, *, directory: str, body: dict | None = None,
          query_params: dict[str, str] | None = None) -> Any:
    query = urlencode({"directory": directory, **(query_params or {})})
    data = None if body is None else json.dumps(body).encode()
    request = Request(f"{OPENCODE_URL}{path}?{query}", data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    username = os.environ.get("OPENCODE_SERVER_USERNAME")
    password = os.environ.get("OPENCODE_SERVER_PASSWORD")
    if not username or not password:
        raise AdapterError("OpenCode API credentials are unavailable")
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    request.add_header("Authorization", f"Basic {token}")
    try:
        with urlopen(request, timeout=15) as response:
            content = response.read()
            return json.loads(content) if content else None
    except HTTPError as error:
        detail = error.read(1000).decode("utf-8", "replace")
        raise AdapterError(f"OpenCode {method} {path} returned HTTP {error.code}: {detail}") from error
    except (URLError, TimeoutError) as error:
        raise AdapterError(f"OpenCode {method} {path} is unavailable: {error}") from error


def _model() -> str:
    model = os.environ.get("SIGMA_TEAM_MODEL", "gpt-5.6-terra")
    if model not in ALLOWED_MODELS:
        raise AdapterError(f"unsupported team model: {model}")
    return model


def _executor_prompt(prompt: str) -> str:
    return f"""You are the executor for one Sigma team assignment.
Use only the worktree named in this assignment. Before any GitHub write, run
`/opt/sigma-hermes/bin/sigma-gh api user --jq .login` and require the exact result
`aika-ai-agent`. Configure Git author only in this worktree and use the scoped
sigma-gh credential helper; never use another user's credentials or global Git config.
Keep the already checked-out task branch. Do not create or switch to another branch.

Finish the requested implementation, run proportionate checks, commit and push the
task branch. Only after those steps succeed, update the exact ProjectV2 item ID in
the assignment to Status option `Sigma verification` using:
project `{PROJECT_ID}`, status field `{STATUS_FIELD_ID}`, option
`{SIGMA_VERIFICATION_OPTION_ID}`. Use `/opt/sigma-hermes/bin/sigma-gh`; do not alter
any other project item. If the assignment does not contain an exact ProjectV2 item
ID, report blocked and do not guess. Do not move the item to Human verification.
Preferred submission command: `/opt/sigma-hermes/bin/sigma-task set ISSUE_NUMBER
--status 'Sigma verification'`, using the issue number supplied below. It uses the
dedicated account and the current project's item. Do not use `gh project item-edit`
or broad helper queries that require unrelated read:org/read:discussion scopes.
Those extra scopes are not needed; the exact GraphQL mutation or sigma-task works.
Return the required JSON result as your final output.

ASSIGNMENT
{prompt}"""


def _existing_manifest(run_id: str) -> dict[str, Any] | None:
    path = _run_dir(run_id) / "adapter.json"
    return json.loads(path.read_text()) if path.exists() else None


def _public_run(manifest: dict[str, Any]) -> dict[str, Any]:
    return {key: manifest[key] for key in ("external_id", "run_id", "workdir", "result_path", "adapter")}


def _process_identity(pid: int) -> dict[str, int] | None:
    """Return Linux process identity fields which change when a PID is reused."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat[stat.rfind(")") + 2:].split()
        return {"pid": pid, "start_time": int(fields[19]), "process_group": int(fields[2])}
    except (FileNotFoundError, IndexError, ValueError, PermissionError):
        return None


def _process_stopped(pid: int) -> bool:
    """A zombie has stopped executing even while its parent has not reaped it."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat[stat.rfind(")") + 2:].split()[0] == "Z"
    except (FileNotFoundError, IndexError, PermissionError):
        return True


def _write_manifest(manifest: dict[str, Any]) -> None:
    _atomic_json(_run_dir(manifest["run_id"]) / "adapter.json", manifest)


def _terminal_result(run: dict[str, Any]) -> dict[str, Any] | None:
    path = Path(run["result_path"])
    return json.loads(path.read_text()) if path.exists() else None


def _start_opencode(workdir: str, prompt: str, run_id: str) -> dict[str, Any]:
    existing = _existing_manifest(run_id)
    if existing:
        if existing.get("adapter") != "opencode" or existing.get("workdir") != workdir:
            raise AdapterError(f"run_id {run_id} is already bound to another launch")
        return _public_run(existing)
    model = _model()
    session = _http("POST", "/session", directory=workdir, body={
        "title": f"Sigma team {run_id}",
        "agent": OPENCODE_AGENT,
        "model": {"providerID": OPENCODE_PROVIDER, "id": model, "variant": "medium"},
        "metadata": {"sigma_team_run_id": run_id, "owner": "sigma-hermes"},
    })
    session_id = session.get("id") if isinstance(session, dict) else None
    if not session_id:
        raise AdapterError("OpenCode did not return a session id")
    manifest = {
        "adapter": "opencode", "external_id": session_id, "run_id": run_id,
        "workdir": workdir, "result_path": str(_run_dir(run_id) / "result.json"),
        "created_at": int(time.time()), "model": model,
    }
    _atomic_json(_run_dir(run_id) / "adapter.json", manifest)
    try:
        _http("POST", f"/session/{quote(session_id)}/prompt_async", directory=workdir, body={
            "agent": OPENCODE_AGENT,
            "model": {"providerID": OPENCODE_PROVIDER, "modelID": model},
            "variant": "medium",
            "parts": [{"type": "text", "text": _executor_prompt(prompt)}],
        })
    except Exception:
        # Keep the durable session id: a retry must never create a second session.
        raise
    return _public_run(manifest)


def _schema(reviewer: bool) -> dict[str, Any]:
    if not reviewer:
        return {
            "type": "object", "additionalProperties": False,
            "properties": {
                "summary": {"type": "string"},
                "commit": {"type": ["string", "null"]},
                "checks": {"type": "array", "items": {"type": "string"}},
                "human_verification": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "commit", "checks", "human_verification"],
        }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "fail", "blocked"]},
            "summary": {"type": "string"},
            "findings": {"type": "array", "items": {"type": "string"}},
            "human_verification": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["verdict", "summary", "findings", "human_verification"],
    }


def _start_process(workdir: str, prompt: str, run_id: str, *, reviewer: bool) -> dict[str, Any]:
    adapter = "hermes-reviewer" if reviewer else "codex-executor"
    existing = _existing_manifest(run_id)
    if existing:
        if existing.get("adapter") != adapter or existing.get("workdir") != workdir:
            raise AdapterError(f"run_id {run_id} is already bound to another launch")
        return _public_run(existing)
    run_dir = _run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    if reviewer and not (Path(HERMES_HOME) / "config.yaml").is_file():
        raise AdapterError(f"Hermes reviewer config is missing: {HERMES_HOME}/config.yaml")
    _atomic_json(run_dir / "output-schema.json", _schema(reviewer))
    worker_prompt = prompt if reviewer else _executor_prompt(prompt)
    if reviewer:
        worker_prompt = (
            "Review only. Do not edit files, create commits, push, or change external state. "
            "Inspect the requested work and return only the required JSON review object. "
            "Return verdict (pass, fail, or blocked), summary, findings, and human_verification. "
            "findings and human_verification must be arrays of strings. "
            "You have authenticated private GitHub access through /opt/sigma-hermes/bin/sigma-gh "
            "as aika-ai-agent. Use narrow read-only API queries to inspect the repository, commit, "
            "PR and project item. Do not use broad gh project queries requiring unrelated scopes. "
            "Do not change GitHub state or credentials; report your verdict only. "
            "Output one JSON object without Markdown.\n\n" + prompt
        )
    manifest = {
        "adapter": adapter, "external_id": f"process:{run_id}", "run_id": run_id,
        "workdir": workdir, "result_path": str(run_dir / "result.json"),
        "created_at": int(time.time()), "model": _model(), "codex_bin": CODEX_BIN,
        "codex_home": CODEX_HOME, "gh_config_dir": GH_CONFIG_DIR,
        "sandbox": "danger-full-access", "worker_kind": "hermes" if reviewer else "codex",
        "hermes_bin": HERMES_BIN, "hermes_home": HERMES_HOME, "bwrap_bin": BWRAP_BIN,
        "provider": OPENCODE_PROVIDER,
        "timeout_seconds": 150 if reviewer else int(os.environ.get("SIGMA_TEAM_TIMEOUT_SECONDS", "1500")),
        "prompt": worker_prompt,
    }
    _atomic_json(run_dir / "worker-manifest.json", manifest)
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).with_name("adapter_worker.py")), str(run_dir / "worker-manifest.json")],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True,
    )
    manifest["worker_pid"] = process.pid
    identity = _process_identity(process.pid)
    if identity is None:
        # A worker without a reuse-resistant identity cannot be cancelled safely.
        try:
            os.killpg(process.pid, 15)
        except ProcessLookupError:
            pass
        raise AdapterError("could not record detached worker process identity")
    manifest["worker_identity"] = identity
    _write_manifest(manifest)
    return _public_run(manifest)


def start_executor(mode: str, workdir: str, prompt: str, run_id: str) -> dict[str, Any]:
    if mode == "opencode":
        return _start_opencode(workdir, prompt, run_id)
    if mode == "codex":
        return _start_process(workdir, prompt, run_id, reviewer=False)
    raise AdapterError(f"unsupported executor mode: {mode}")


def start_reviewer(workdir: str, prompt: str, run_id: str) -> dict[str, Any]:
    return _start_process(workdir, prompt, run_id, reviewer=True)


def _message_summary(messages: Any) -> tuple[str, bool, bool]:
    if not isinstance(messages, list):
        return "OpenCode returned no messages", False, False
    for message in reversed(messages):
        info = message.get("info", {})
        if info.get("role") != "assistant":
            continue
        error = info.get("error")
        texts = [part.get("text", "") for part in message.get("parts", []) if part.get("type") == "text"]
        summary = "\n".join(texts).strip()[-8000:] or info.get("finish") or "OpenCode session finished"
        return summary, bool(error), True
    return "OpenCode has not produced an assistant response yet", False, False


def _abort_opencode(session_id: str, workdir: str) -> None:
    aborted = _http("POST", f"/session/{quote(session_id)}/abort", directory=workdir)
    if aborted is not True:
        raise AdapterError(f"OpenCode did not confirm abort for {session_id}")
    deadline = time.monotonic() + float(os.environ.get("SIGMA_OPENCODE_ABORT_WAIT_SECONDS", "15"))
    while True:
        statuses = _http("GET", "/session/status", directory=workdir)
        status = statuses.get(session_id) if isinstance(statuses, dict) else None
        if isinstance(status, dict) and status.get("type") == "idle":
            return
        if time.monotonic() >= deadline:
            observed = status.get("type", "missing") if isinstance(status, dict) else "invalid"
            raise AdapterError(f"OpenCode session {session_id} did not confirm idle after abort ({observed})")
        time.sleep(0.1)


def _opencode_family(session_id: str, workdir: str) -> list[str]:
    """Read the documented session graph and return this session plus descendants."""
    sessions: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        response = _http("GET", "/api/session", directory=workdir,
                         query_params={"cursor": cursor} if cursor else None)
        if not isinstance(response, dict) or not isinstance(response.get("data"), list):
            raise AdapterError("OpenCode session list returned an invalid response")
        sessions.extend(item for item in response["data"] if isinstance(item, dict))
        next_cursor = response.get("cursor", {}).get("next") if isinstance(response.get("cursor"), dict) else None
        if not next_cursor or not isinstance(next_cursor, str):
            break
        cursor = next_cursor
    children: dict[str, list[str]] = {}
    known = set()
    for item in sessions:
        child, parent = item.get("id"), item.get("parentID")
        if isinstance(child, str):
            known.add(child)
            if isinstance(parent, str):
                children.setdefault(parent, []).append(child)
    if session_id not in known:
        raise AdapterError(f"OpenCode parent session {session_id} was not returned by the session list")
    family, pending = [], [session_id]
    while pending:
        current = pending.pop()
        family.append(current)
        pending.extend(children.get(current, []))
    return family


def _interrupt_opencode_family(session_id: str, workdir: str) -> list[str]:
    family = _opencode_family(session_id, workdir)
    # The documented endpoint is an exact-session interrupt. Parent first lets
    # its helper sessions settle, then each discovered descendant is interrupted.
    for target in family:
        _http("POST", f"/api/session/{quote(target)}/interrupt", directory=workdir)
    for target in family:
        _http("POST", f"/api/session/{quote(target)}/wait", directory=workdir)
    statuses = _http("GET", "/session/status", directory=workdir)
    active = [target for target in family
              if not isinstance(statuses, dict) or statuses.get(target, {}).get("type") != "idle"]
    if active:
        raise AdapterError("OpenCode sessions did not confirm idle: " + ", ".join(active))
    return family


def _opencode_status(run: dict[str, Any]) -> dict[str, Any]:
    session_id, workdir = run["external_id"], run["workdir"]
    manifest = _existing_manifest(run["run_id"])
    age = int(time.time()) - int((manifest or {}).get("created_at", 0))
    timeout = int(os.environ.get("SIGMA_OPENCODE_TIMEOUT_SECONDS", "1500"))
    if age >= timeout:
        _abort_opencode(session_id, workdir)
        result = {"state": "blocked", "summary": f"OpenCode exceeded the {timeout} second limit"}
        _atomic_json(Path(run["result_path"]), result)
        return result
    statuses = _http("GET", "/session/status", directory=workdir)
    status = statuses.get(session_id, {"type": "idle"}) if isinstance(statuses, dict) else {"type": "idle"}
    if status.get("type") == "retry":
        _abort_opencode(session_id, workdir)
        return {"state": "blocked", "summary": status.get("message", "OpenCode requested an automatic retry")}
    if status.get("type") == "busy":
        return {"state": "running", "summary": status.get("message", "OpenCode is running")}
    for endpoint, label in (("/permission", "permission"), ("/question", "question")):
        pending = _http("GET", endpoint, directory=workdir)
        if isinstance(pending, list) and any(item.get("sessionID") == session_id for item in pending):
            _abort_opencode(session_id, workdir)
            return {"state": "blocked", "summary": f"OpenCode is waiting for a {label}"}
    messages = _http("GET", f"/session/{quote(session_id)}/message", directory=workdir)
    summary, failed, finished = _message_summary(messages)
    if not finished:
        return {"state": "running", "summary": summary}
    result = {"state": "failed" if failed else "succeeded", "summary": summary,
              "artifact": {"type": "opencode_session", "session_id": session_id,
                           "url": OPENCODE_WEB_URL}}
    _atomic_json(Path(run["result_path"]), result)
    return result


def _process_status(run: dict[str, Any]) -> dict[str, Any]:
    result_path = Path(run["result_path"])
    if result_path.exists():
        result = json.loads(result_path.read_text())
        output = result.get("output")
        if isinstance(output, dict):
            result.setdefault("summary", output.get("summary", result["state"]))
            result.setdefault("artifact", output)
            for key in ("verdict", "commit", "checks", "human_verification", "human_checks", "findings"):
                if key in output:
                    result.setdefault(key, output[key])
        else:
            result.setdefault("summary", result["state"])
        return result
    manifest = _existing_manifest(run["run_id"])
    pid = manifest.get("worker_pid") if manifest else None
    if pid:
        try:
            os.kill(int(pid), 0)
            return {"state": "running", "summary": f"Worker process {pid} is running"}
        except ProcessLookupError:
            pass
        except PermissionError:
            return {"state": "running", "summary": f"Worker process {pid} is owned by the service account"}
    return {"state": "failed", "summary": "Worker exited without writing result.json"}


def executor_status(run: dict[str, Any]) -> dict[str, Any]:
    return _opencode_status(run) if run.get("adapter") == "opencode" else _process_status(run)


def reviewer_status(run: dict[str, Any]) -> dict[str, Any]:
    return _process_status(run)


def _manifest_for_cancel(run: dict[str, Any]) -> dict[str, Any]:
    run_id = run.get("run_id")
    if not isinstance(run_id, str):
        raise AdapterError("cancel run has no run_id")
    manifest = _existing_manifest(run_id)
    if not manifest:
        raise AdapterError(f"no adapter manifest for run_id {run_id}")
    for key in ("adapter", "external_id", "workdir", "result_path"):
        if run.get(key) != manifest.get(key):
            raise AdapterError(f"cancel run does not match manifest field {key}")
    return manifest


def _record_cancellation(manifest: dict[str, Any], state: str, summary: str) -> dict[str, Any]:
    result_path = Path(manifest["result_path"])
    result = _terminal_result(manifest)
    if result is None:
        result = {"state": state, "summary": summary, "cancelled_at": int(time.time())}
        _atomic_json(result_path, result)
    manifest["cancellation"] = {"state": state, "summary": summary, "recorded_at": int(time.time())}
    _write_manifest(manifest)
    return result


def _cancel_process(manifest: dict[str, Any]) -> dict[str, Any]:
    existing = _terminal_result(manifest)
    if existing is not None:
        return existing
    expected = manifest.get("worker_identity")
    if not isinstance(expected, dict):
        raise AdapterError("worker manifest has no reuse-resistant process identity")
    try:
        pid = int(expected["pid"])
        expected_start = int(expected["start_time"])
        expected_group = int(expected["process_group"])
    except (KeyError, TypeError, ValueError) as error:
        raise AdapterError("worker manifest has invalid process identity") from error
    actual = _process_identity(pid)
    if actual is not None and actual != {"pid": pid, "start_time": expected_start, "process_group": expected_group}:
        manifest["cancellation"] = {"state": "refused_pid_mismatch", "recorded_at": int(time.time())}
        _write_manifest(manifest)
        raise AdapterError("refusing to signal worker: PID identity no longer matches manifest")
    if actual is None:
        # It may have exited just before cancellation. A durable result is still required.
        return _record_cancellation(manifest, "cancelled", "Worker was already stopped before cancellation")
    os.killpg(expected_group, 15)
    deadline = time.monotonic() + float(os.environ.get("SIGMA_PROCESS_CANCEL_WAIT_SECONDS", "15"))
    while not _process_stopped(pid):
        if time.monotonic() >= deadline:
            raise AdapterError("worker did not stop after targeted cancellation")
        time.sleep(0.1)
    return _record_cancellation(manifest, "cancelled", "Worker cancellation confirmed")


def cancel(run: dict[str, Any]) -> dict[str, Any]:
    """Stop exactly the run named by its manifest and return only after it is terminal."""
    manifest = _manifest_for_cancel(run)
    existing = _terminal_result(manifest)
    if existing is not None:
        if existing.get("confirmed"):
            return existing
        return {**existing, "confirmed": True,
                "reason": "worker was already terminal"}
    if manifest["adapter"] == "opencode":
        family = _interrupt_opencode_family(manifest["external_id"], manifest["workdir"])
        result = _record_cancellation(manifest, "cancelled", "OpenCode cancellation confirmed idle")
        result.setdefault("sessions", family)
        result["confirmed"] = True
        result["reason"] = "OpenCode parent and descendant sessions confirmed idle"
        _atomic_json(Path(manifest["result_path"]), result)
        return result
    result = _cancel_process(manifest)
    return {**result, "confirmed": True, "reason": "worker process group confirmed stopped"}
