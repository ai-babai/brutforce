import subprocess
import tempfile
import unittest
import fcntl
import json
import datetime as dt
import sys
from pathlib import Path
from unittest.mock import patch

import adapters
from engine import Engine
from state_store import StateStore


def item(number=7, status="Backlog", comments=None):
    return {"id": "ISSUE", "item_id": "ITEM", "number": number, "title": "Task", "body": "Do it",
            "url": "https://example/7", "state": "OPEN",
            "fields": {"Исполнитель": "Команда Sigma", "Status": status},
            "comments": {"nodes": comments or []}}


class Board:
    def __init__(self, value):
        self.value, self.statuses, self.comments = value, [], []
        self.fail_comment = False
        self.fail_status = False

    def list_items(self): return [self.value]
    def set_status(self, unused, status):
        if self.fail_status: raise RuntimeError("status API unavailable")
        self.statuses.append(status); self.value["fields"]["Status"] = status
    def comment(self, unused, body):
        if self.fail_comment: raise RuntimeError("comment API unavailable")
        self.comments.append(body)
    def review_evidence(self, commit):
        return {"oid": commit, "pull_requests": [{"number": 9, "isDraft": True, "baseRefName": "main"}]}


class Adapter:
    def __init__(self, executor=None, reviewer=None):
        self.starts = 0
        self.executor = executor or [{"state": "running"}]
        self.reviewer = reviewer or [{"state": "succeeded", "summary": "pass", "verdict": "pass"}]
        self.executor_workdir = self.reviewer_prompt = self.executor_prompt = None
        self.cancelled = []

    def start_executor(self, mode, workdir, prompt, run_id):
        self.starts += 1
        self.executor_workdir = workdir
        self.executor_prompt = prompt
        return {"external_id": "exec", "run_id": run_id}

    def executor_status(self, run): return self.executor.pop(0)
    def start_reviewer(self, workdir, prompt, run_id):
        self.reviewer_prompt = prompt
        return {"external_id": "review", "run_id": run_id}
    def reviewer_status(self, run): return self.reviewer.pop(0)
    def cancel(self, run):
        self.cancelled.append(run)
        return {"state": "cancelled", "confirmed": True, "reason": "fake stopped"}


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name) / "source"
        self.source.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.source, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=self.source, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.source, check=True)
        (self.source / "README").write_text("fixture\n")
        subprocess.run(["git", "add", "README"], cwd=self.source, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=self.source, check=True)
        self.store = StateStore(self.tmp.name)
        self.board = Board(item())
        self.adapter = Adapter()
        self.engine = Engine(self.board, self.store, {"work_root": str(Path(self.tmp.name) / "work"),
                                                      "repo_source": str(self.source)}, self.adapter)

    def tearDown(self): self.tmp.cleanup()

    def test_reservation_prevents_duplicate_start(self):
        self.assertEqual(self.engine.poll(), "RESERVED")
        self.assertEqual(self.adapter.starts, 0)
        self.assertEqual(self.engine.poll(), "EXECUTING")
        self.assertEqual(self.engine.poll(), "EXECUTING")
        self.assertEqual(self.adapter.starts, 1)
        self.assertIn("OpenCode session_id=exec", self.board.comments[0])
        self.assertIn("OpenCode UI=https://code.dzap.pw", self.board.comments[0])

    def test_start_comment_failure_keeps_running_worker_and_slot(self):
        self.engine.poll()
        self.board.fail_comment = True
        self.assertEqual(self.engine.poll(), "EXECUTING")
        self.assertEqual(self.engine.poll(), "DELIVERY_RETRY")
        with self.store.locked() as state:
            self.assertEqual(state["active"]["phase"], "executing")
            self.assertEqual(state["active"]["executor_run"]["external_id"], "exec")
        self.assertNotIn("Pending", self.board.statuses)

    def test_pause_blocks_claim_and_review_launch(self):
        with self.store.locked() as state: state["paused"] = True
        self.assertEqual(self.engine.poll(), "PAUSED")
        self.assertEqual(self.adapter.starts, 0)
        with self.store.locked() as state:
            state["paused"] = False
        self.engine.poll(); self.engine.poll()
        self.adapter.executor = [{"state": "succeeded", "summary": "ok"}]
        self.board.value["fields"]["Status"] = "Sigma verification"
        self.assertEqual(self.engine.poll(), "REVIEW_WAIT")
        with self.store.locked() as state: state["paused"] = True
        self.assertEqual(self.engine.poll(), "PAUSED_REVIEW_WAIT")

    def test_pause_blocks_already_reserved_launch(self):
        self.assertEqual(self.engine.poll(), "RESERVED")
        with self.store.locked() as state: state["paused"] = True
        self.assertEqual(self.engine.poll(), "PAUSED_RESERVED")
        self.assertEqual(self.adapter.starts, 0)

    def test_withdrawn_assignment_cancels_without_launch_or_board_write(self):
        self.assertEqual(self.engine.poll(), "RESERVED")
        self.board.value["fields"]["Исполнитель"] = "Макс"
        self.assertEqual(self.engine.poll(), "CANCELLED_NO_LAUNCH")
        self.assertEqual(self.adapter.starts, 0)
        self.assertEqual(self.board.statuses, [])
        self.board.value["fields"]["Исполнитель"] = "Команда Sigma"
        self.assertEqual(self.engine.poll(), "IDLE")

    def test_status_poll_error_keeps_global_active(self):
        self.engine.poll(); self.engine.poll()
        def unavailable(unused): raise RuntimeError("temporary API failure")
        self.adapter.executor_status = unavailable
        self.assertEqual(self.engine.poll(), "EXECUTOR_OBSERVE_ERROR")
        with self.store.locked() as state:
            self.assertEqual(state["active"]["phase"], "executing")

    def test_workdir_is_clone_with_branch_identity_and_remote(self):
        self.engine.poll(); self.engine.poll()
        workdir = self.adapter.executor_workdir
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=workdir, text=True).strip()
        self.assertRegex(branch, r"^sigma/7-[0-9a-f]{8}$")
        self.assertEqual(subprocess.check_output(["git", "config", "user.name"], cwd=workdir, text=True).strip(), "aika-ai-agent")
        self.assertEqual(subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=workdir, text=True).strip(),
                         "https://github.com/ai-babai/brutforce.git")
        helpers = subprocess.check_output(["git", "config", "--local", "--get-all", "credential.helper"],
                                          cwd=workdir, text=True).splitlines()
        self.assertEqual(helpers, ["", "!/opt/sigma-hermes/bin/sigma-gh auth git-credential"])

    def test_only_allowlisted_human_retry_is_accepted(self):
        with self.store.locked() as state:
            state["tasks"]["7"] = {"phase": "pending", "finished_at": "2026-01-01T00:00:00+00:00"}
        self.board.value["comments"]["nodes"] = [
            {"body": "/sigma retry", "createdAt": "2026-02-01T00:00:00+00:00", "author": {"login": "aika-ai-agent"}},
        ]
        self.assertEqual(self.engine.poll(), "IDLE")
        self.board.value["comments"]["nodes"].append(
            {"body": "/sigma retry please", "createdAt": "2026-02-02T00:00:00+00:00", "author": {"login": "MisterMolox"}})
        self.assertEqual(self.engine.poll(), "RESERVED")

    def test_telegram_retry_authorization_is_consumed_once(self):
        with self.store.locked() as state:
            state["tasks"]["7"] = {"phase": "pending", "finished_at": "2026-01-01T00:00:00+00:00"}
            Engine.authorize_retry(state, 7, 199560169, "Макс явно попросил повтор")
        self.assertEqual(self.engine.poll(), "RESERVED")
        with self.store.locked() as state:
            authorization = state["retry_authorizations"]["7"]
            self.assertIsNotNone(authorization["consumed_at"])
            state["active"] = None
        self.assertEqual(self.engine.poll(), "IDLE")

    def test_telegram_retry_rejects_unknown_sender(self):
        with self.store.locked() as state:
            with self.assertRaises(ValueError):
                Engine.authorize_retry(state, 7, 123, "retry")

    def test_ambiguous_crash_becomes_pending_without_restart(self):
        with self.store.locked() as state:
            state["active"] = {"number": 7, "phase": "launching", "run_id": "r", "url": "u"}
        self.assertEqual(self.engine.poll(), "PENDING")
        self.assertEqual(self.adapter.starts, 0)
        self.assertEqual(self.board.statuses[-1], "Pending")

    def test_failed_review_still_goes_to_human_verification(self):
        self.adapter.executor = [{"state": "succeeded", "summary": "built"}]
        self.adapter.reviewer = [{"state": "succeeded", "summary": "tests fail", "verdict": "fail",
                                  "findings": ["regression"], "human_verification": ["inspect logs"]}]
        self.engine.poll(); self.engine.poll()
        self.board.value["fields"]["Status"] = "Sigma verification"
        self.assertEqual(self.engine.poll(), "REVIEW_WAIT")
        self.assertEqual(self.engine.poll(), "REVIEWING")
        with self.store.locked() as state: commit = state["active"]["result_commit"]
        self.assertIn("Исходная карточка", self.adapter.reviewer_prompt)
        self.assertIn("Do it", self.adapter.reviewer_prompt)
        self.assertIn(commit, self.adapter.reviewer_prompt)
        self.assertIn('"isDraft": true', self.adapter.reviewer_prompt)
        self.assertIn("observed_at", self.adapter.reviewer_prompt)
        self.assertEqual(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.adapter.executor_workdir,
                                                text=True).strip(), commit)
        self.assertEqual(self.engine.poll(), "HUMAN_VERIFICATION")
        self.assertEqual(self.board.statuses[-1], "human_verification")
        self.assertIn("run_id=", self.board.comments[-1])
        self.assertIn("OpenCode session_id=exec", self.board.comments[-1])
        self.assertIn("Summary: tests fail", self.board.comments[-1])
        self.assertIn("- regression", self.board.comments[-1])
        self.assertIn("- inspect logs", self.board.comments[-1])
        with self.store.locked() as state: self.assertIsNone(state["active"])

    def test_github_evidence_error_is_disclosed_but_review_starts(self):
        self.adapter.executor = [{"state": "succeeded", "summary": "built"}]
        self.engine.poll(); self.engine.poll()
        self.board.value["fields"]["Status"] = "Sigma verification"
        self.engine.poll()
        def unavailable(unused): raise RuntimeError("GitHub unavailable")
        self.board.review_evidence = unavailable
        self.assertEqual(self.engine.poll(), "REVIEWING")
        self.assertIn('"verified": false', self.adapter.reviewer_prompt)
        self.assertIn("GitHub unavailable", self.adapter.reviewer_prompt)

    def test_reviewer_runtime_error_becomes_pending(self):
        self.adapter.executor = [{"state": "succeeded", "summary": "built"}]
        self.adapter.reviewer = [{"state": "blocked", "summary": "review session unavailable"}]
        self.engine.poll(); self.engine.poll()
        self.board.value["fields"]["Status"] = "Sigma verification"
        self.engine.poll(); self.engine.poll()
        self.assertEqual(self.engine.poll(), "PENDING")
        self.assertEqual(self.board.statuses[-1], "Pending")

    def test_retry_resumes_clean_prior_branch_and_includes_authorization_context(self):
        self.engine.poll(); self.engine.poll()
        with self.store.locked() as state:
            old = dict(state["active"])
            old.update({"phase": "pending", "finished_at": "2026-01-01T00:00:00+00:00"})
            state["tasks"]["7"] = old
            state["active"] = None
            Engine.authorize_retry(state, 7, 199560169, "continue the prior attempt")
        self.board.value["fields"]["Status"] = "Backlog"
        self.board.value["comments"]["nodes"] = [{"body": "/sigma retry", "createdAt": "2026-02-01T00:00:00+00:00", "author": {"login": "ai-babai"}}]
        self.assertEqual(self.engine.poll(), "RESERVED")
        self.assertEqual(self.engine.poll(), "EXECUTING")
        self.assertEqual(self.adapter.executor_workdir, old["workdir"])
        self.assertIn(old["branch"], self.adapter.executor_prompt)
        self.assertIn("continue the prior attempt", self.adapter.executor_prompt)
        self.assertIn("Latest issue comments", self.adapter.executor_prompt)

    def test_dirty_retry_is_pending_without_second_worker(self):
        self.engine.poll(); self.engine.poll()
        with self.store.locked() as state:
            old = dict(state["active"]); old.update({"phase": "pending", "finished_at": "2026-01-01T00:00:00+00:00"})
            state["tasks"]["7"] = old; state["active"] = None
        (Path(old["workdir"]) / "dirty").write_text("x")
        self.board.value["fields"]["Status"] = "Backlog"
        self.board.value["comments"]["nodes"] = [{"body": "/sigma retry", "createdAt": "2026-02-01T00:00:00+00:00", "author": {"login": "ai-babai"}}]
        self.assertEqual(self.engine.poll(), "RESERVED")
        self.assertEqual(self.engine.poll(), "PENDING")
        self.assertEqual(self.adapter.starts, 1)
        self.assertIn("dirty", self.board.comments[-1])

    def test_cancellation_stops_exact_executor_before_pending(self):
        self.engine.poll(); self.engine.poll()
        request = self.store.request_cancel(7, 199560169, "operator stop")
        self.assertEqual(self.engine.poll(), "PENDING")
        self.assertEqual(self.adapter.cancelled, [{"external_id": "exec", "run_id": self.adapter.cancelled[0]["run_id"]}])
        with self.store.locked() as state:
            request = state["cancellation_audit"][-1]
            self.assertIsNotNone(request["confirmed_at"]); self.assertTrue(request["evidence"])
            self.assertIsNone(state["active"])
        self.assertEqual(self.board.statuses[-1], "Pending")

    def test_engine_accepts_real_adapter_cancellation_contract(self):
        self.engine.poll(); self.engine.poll()
        run_root = Path(self.tmp.name) / "adapter-runs"
        with self.store.locked() as state:
            task = state["active"]
            run_dir = run_root / task["run_id"]; run_dir.mkdir(parents=True)
            run = {"adapter": "opencode", "external_id": "ses_real", "run_id": task["run_id"],
                   "workdir": task["workdir"], "result_path": str(run_dir / "result.json")}
            (run_dir / "adapter.json").write_text(json.dumps(run))
            task["executor_run"] = run
        self.store.request_cancel(7, 199560169, "real adapter contract")
        actual = Engine(self.board, self.store, self.engine.config, adapters)
        with patch.object(adapters, "RUN_ROOT", run_root), \
                patch.object(adapters, "_interrupt_opencode_family", return_value=["ses_real"]):
            self.assertEqual("PENDING", actual.poll())
        with self.store.locked() as state:
            self.assertIsNone(state["active"])

    def test_unconfirmed_cancellation_blocks_progress(self):
        self.engine.poll(); self.engine.poll()
        self.adapter.cancel = lambda run: {"confirmed": False, "reason": "still stopping"}
        self.store.request_cancel(7, 199560169, "stop")
        self.assertEqual(self.engine.poll(), "CANCEL_WAITING")
        with self.store.locked() as state:
            self.assertEqual(state["active"]["phase"], "executing")
            self.assertEqual("waiting", state["cancellation_audit"][-1]["outcome"])

    def test_comment_timeout_marker_prevents_duplicate_delivery(self):
        self.engine.poll(); self.engine.poll()
        calls = []
        def timed_out(unused, body):
            calls.append(body)
            self.board.value["comments"]["nodes"].append({"body": body, "createdAt": "2026-02-01T00:00:00+00:00", "author": {"login": "aika-ai-agent"}})
            raise TimeoutError("response lost")
        self.board.comment = timed_out
        self.assertEqual(self.engine.poll(), "EXECUTING")
        self.assertEqual(len(calls), 1)

    def test_delivery_error_after_review_keeps_completed_slot(self):
        self.adapter.executor = [{"state": "succeeded", "summary": "built"}]
        self.adapter.reviewer = [{"state": "succeeded", "summary": "ok", "verdict": "pass"}]
        self.engine.poll(); self.engine.poll()
        self.board.value["fields"]["Status"] = "Sigma verification"
        self.engine.poll(); self.engine.poll()
        self.board.fail_comment = True
        self.assertEqual(self.engine.poll(), "DELIVERY_RETRY")
        with self.store.locked() as state:
            self.assertEqual(state["active"]["phase"], "human_verification_delivery")
        self.assertEqual(self.adapter.starts, 1)

    def test_initial_status_retry_launches_executor_exactly_once(self):
        self.assertEqual(self.engine.poll(), "RESERVED")
        self.board.fail_status = True
        self.assertEqual(self.engine.poll(), "DELIVERY_RETRY")
        self.assertEqual(self.adapter.starts, 0)
        with self.store.locked() as state:
            state["outbox"][0]["next_at"] = "2000-01-01T00:00:00+00:00"
            self.assertEqual(state["active"]["phase"], "start_status_delivery")
        self.board.fail_status = False
        self.assertEqual(self.engine.poll(), "EXECUTING")
        self.assertEqual(self.adapter.starts, 1)

    def test_terminal_delivery_backoff_survives_restart_and_keeps_slot(self):
        self.adapter.executor = [{"state": "succeeded", "summary": "built"}]
        self.adapter.reviewer = [{"state": "succeeded", "summary": "ok", "verdict": "pass",
                                  "findings": [], "human_verification": []}]
        self.engine.poll(); self.engine.poll(); self.board.value["fields"]["Status"] = "Sigma verification"
        self.engine.poll(); self.engine.poll(); self.board.fail_comment = True
        self.assertEqual(self.engine.poll(), "DELIVERY_RETRY")
        restarted = Engine(self.board, self.store, self.engine.config, self.adapter)
        self.assertEqual(restarted.poll(), "DELIVERY_WAIT")
        with self.store.locked() as state:
            self.assertIsNotNone(state["active"])
            for event in state["outbox"]: event["next_at"] = "2000-01-01T00:00:00+00:00"
        self.board.fail_comment = False
        self.assertEqual(restarted.poll(), "HUMAN_VERIFICATION")

    def test_terminal_intents_are_persisted_atomically_before_delivery(self):
        self.adapter.executor = [{"state": "succeeded", "summary": "built"}]
        self.adapter.reviewer = [{"state": "succeeded", "summary": "ok", "verdict": "pass",
                                  "findings": [], "human_verification": []}]
        self.engine.poll(); self.engine.poll(); self.board.value["fields"]["Status"] = "Sigma verification"
        self.engine.poll(); self.engine.poll(); self.engine.config["notification_command"] = ["notify"]
        self.board.fail_status = True
        self.assertEqual(self.engine.poll(), "DELIVERY_RETRY")
        with self.store.locked() as state:
            self.assertEqual({"status", "comment", "notify"}, {event["kind"] for event in state["outbox"]})

    def test_existing_marker_is_checked_before_comment_post(self):
        marker = "<!-- sigma-team-event:event-1 -->"
        self.board.value["comments"]["nodes"].append({"body": "already posted\n" + marker,
            "createdAt": "2026-01-01T00:00:00+00:00", "author": {"login": "aika-ai-agent"}})
        with self.store.locked() as state:
            state["outbox"] = [{"id": "event-1", "kind": "comment", "issue": 7, "item": {"id": "ISSUE"},
                                "body": "already posted", "attempts": 0, "next_at": "2000-01-01T00:00:00+00:00"}]
        self.assertEqual(self.engine.poll(), "RESERVED")
        self.assertEqual(self.board.comments, [])

    def test_cancel_request_is_run_bound_consumed_and_rejected_without_active(self):
        self.engine.poll(); self.engine.poll()
        first = self.store.request_cancel(7, 199560169, "stop first")
        self.engine.poll()
        self.assertFalse((self.store.cancel_root / (first["run_id"] + ".json")).exists())
        with self.assertRaises(ValueError): self.store.request_cancel(7, 199560169, "future cancel")
        with self.store.locked() as state:
            Engine.authorize_retry(state, 7, 199560169, "retry")
        self.board.value["fields"]["Status"] = "Backlog"
        self.assertEqual(self.engine.poll(), "RESERVED")
        with self.store.locked() as state:
            self.assertNotEqual(first["run_id"], state["active"]["run_id"])

    def test_stale_cancel_race_is_audited_and_consumed(self):
        self.engine.poll(); self.engine.poll()
        request = self.store.request_cancel(7, 199560169, "raced completion")
        with self.store.locked() as state:
            state["tasks"]["7"] = {**state["active"], "phase": "pending", "finished_at": "2026-01-01T00:00:00+00:00"}
            state["active"] = None
        self.assertEqual("IDLE", self.engine.poll())
        with self.store.locked() as state:
            self.assertEqual("stale_run", state["cancellation_audit"][-1]["outcome"])
        self.assertFalse((self.store.cancel_root / (request["run_id"] + ".json")).exists())

    def test_cancel_request_does_not_wait_for_dispatcher_flock(self):
        self.engine.poll(); self.engine.poll()
        self.store.root.mkdir(parents=True, exist_ok=True)
        with self.store.lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            request = self.store.request_cancel(7, 199560169, "quick")
        self.assertEqual(7, request["issue"])

    def test_retry_without_recorded_base_is_explicit_blocker(self):
        with self.store.locked() as state:
            state["tasks"]["7"] = {"phase": "pending", "finished_at": "2026-01-01T00:00:00+00:00"}
            Engine.authorize_retry(state, 7, 199560169, "continue")
        self.assertEqual(self.engine.poll(), "RESERVED")
        self.assertEqual(self.engine.poll(), "PENDING")
        self.assertEqual(self.adapter.starts, 0)
        self.assertIn("no recorded workdir", self.board.comments[-1])

    def test_cancel_supersedes_deferred_running_status(self):
        self.engine.poll(); self.board.fail_status = True
        self.assertEqual(self.engine.poll(), "DELIVERY_RETRY")
        self.store.request_cancel(7, 199560169, "cancel before launch")
        self.board.fail_status = False
        self.assertEqual(self.engine.poll(), "PENDING")
        self.assertEqual(self.board.statuses, ["Pending"])
        self.assertEqual(self.adapter.starts, 0)
        with self.store.locked() as state:
            self.assertFalse(any(event.get("status") == "running" for event in state["outbox"]))

    def test_cancel_during_launching_never_creates_worker_to_cancel(self):
        self.engine.poll()
        with self.store.locked() as state:
            state["active"]["phase"] = "launching"
        self.store.request_cancel(7, 199560169, "stop ambiguous launch")
        self.assertEqual(self.engine.poll(), "CANCEL_WAITING")
        self.assertEqual(self.adapter.starts, 0)

    def test_cli_cancel_returns_while_dispatcher_lock_is_held(self):
        self.engine.poll(); self.engine.poll()
        config = Path(self.tmp.name) / "team.json"
        config.write_text(json.dumps({"state_root": self.tmp.name}))
        command = [sys.executable, str(Path(__file__).with_name("sigma-team")), "--config", str(config),
                   "cancel", "7", "--requested-by", "199560169", "--reason", "quick"]
        with self.store.lock_path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            completed = subprocess.run(command, text=True, capture_output=True, timeout=2)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(7, json.loads(completed.stdout)["issue"])

    def test_cancel_crash_after_finalization_resumes_same_outbox(self):
        self.engine.poll(); self.engine.poll()
        request = self.store.request_cancel(7, 199560169, "stop")
        original = self.engine._flush_outbox
        self.engine._flush_outbox = lambda state, items: (_ for _ in ()).throw(SystemExit("crash"))
        with self.assertRaises(SystemExit): self.engine.poll()
        self.engine._flush_outbox = original
        self.assertTrue((self.store.cancel_root / (request["run_id"] + ".json")).exists())
        with self.store.locked() as state:
            self.assertEqual("pending_delivery", state["active"]["phase"])
            self.assertEqual(3, len(state["outbox"]))
        restarted = Engine(self.board, self.store, self.engine.config, self.adapter)
        self.assertEqual("PENDING", restarted.poll())
        with self.store.locked() as state:
            self.assertEqual([], state["outbox"])
            self.assertIsNone(state["active"])
        self.assertEqual(["running", "Pending"], self.board.statuses)
        self.assertEqual(2, len(self.board.comments))
        self.assertFalse((self.store.cancel_root / (request["run_id"] + ".json")).exists())


if __name__ == "__main__":
    unittest.main()
