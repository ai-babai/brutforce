import fcntl
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


class StateStore:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "state.json"
        self.lock_path = self.root / "state.lock"
        self.cancel_root = self.root / "cancel-requests"

    @contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self.load()
            yield state
            self.save(state)

    def load(self):
        if not self.path.exists():
            return {"version": 1, "paused": False, "active": None, "tasks": {}, "outbox": [], "cancellations": {}}
        with self.path.open() as src:
            value = json.load(src)
        if value.get("version") != 1:
            raise RuntimeError("unsupported state version")
        value.setdefault("paused", False)
        value.setdefault("active", None)
        value.setdefault("tasks", {})
        value.setdefault("outbox", [])
        value.setdefault("cancellations", {})
        value.setdefault("retry_authorizations", {})
        return value

    def save(self, state):
        fd, name = tempfile.mkstemp(prefix=".state-", suffix=".json", dir=self.root)
        try:
            with os.fdopen(fd, "w") as dst:
                json.dump(state, dst, ensure_ascii=False, sort_keys=True, indent=2)
                dst.write("\n")
                dst.flush()
                os.fsync(dst.fileno())
            os.chmod(name, 0o600)
            os.replace(name, self.path)
            dirfd = os.open(self.root, os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def request_cancel(self, issue, requested_by, reason):
        """Bind a cancellation request to the currently active run without taking the dispatcher lock."""
        if requested_by != 199560169:
            raise ValueError("cancellation is restricted to Maks Telegram ID")
        if not reason.strip():
            raise ValueError("cancellation reason is required")
        state = self.load()
        active = state.get("active")
        if not active or active.get("number") != int(issue) or not active.get("run_id"):
            raise ValueError("issue has no active Sigma run to cancel")
        request = {"issue": int(issue), "run_id": active["run_id"], "requested_by": requested_by,
                   "reason": reason.strip(), "requested_at": time.time()}
        self.cancel_root.mkdir(parents=True, exist_ok=True)
        path = self.cancel_root / (active["run_id"] + ".json")
        if path.exists():
            existing = json.loads(path.read_text())
            if existing.get("issue") == int(issue) and existing.get("run_id") == active["run_id"]:
                return existing
            raise RuntimeError("conflicting cancellation request")
        fd, name = tempfile.mkstemp(prefix=".cancel-", suffix=".json", dir=self.cancel_root)
        try:
            with os.fdopen(fd, "w") as dst:
                json.dump(request, dst, ensure_ascii=False, sort_keys=True, indent=2)
                dst.write("\n"); dst.flush(); os.fsync(dst.fileno())
            os.chmod(name, 0o600); os.replace(name, path)
        finally:
            if os.path.exists(name): os.unlink(name)
        return request

    def cancel_request(self, run_id):
        path = self.cancel_root / (str(run_id) + ".json")
        return json.loads(path.read_text()) if path.exists() else None

    def cancel_requests(self):
        if not self.cancel_root.is_dir():
            return []
        values = []
        for path in self.cancel_root.glob("*.json"):
            try:
                value = json.loads(path.read_text())
                if isinstance(value, dict): values.append(value)
            except (OSError, json.JSONDecodeError):
                continue
        return values

    def consume_cancel(self, run_id):
        path = self.cancel_root / (str(run_id) + ".json")
        try:
            path.unlink()
        except FileNotFoundError:
            pass
