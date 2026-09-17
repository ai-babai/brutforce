import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


class StateStore:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "state.json"
        self.lock_path = self.root / "state.lock"

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
