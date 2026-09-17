import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import adapters
import adapter_worker


class AdapterTest(unittest.TestCase):
    def test_review_parses_final_json_after_warning_and_keeps_findings(self):
        payload = {"verdict": "blocked", "summary": "Needs human GitHub check",
                   "findings": [{"criterion": "file", "status": "passed"}],
                   "human_verification": ["Check draft PR"]}
        result = adapter_worker.parse_review("warning: optional scanner unavailable\n" + json.dumps(payload))
        self.assertEqual("blocked", result["verdict"])
        self.assertIn("passed", result["findings"][0])
        with self.assertRaises(ValueError):
            adapter_worker.parse_review(json.dumps(payload) + "\nStill working, no final verdict")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root_patch = patch.object(adapters, "RUN_ROOT", Path(self.temporary.name))
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temporary.cleanup()

    def test_opencode_start_is_idempotent_and_status_uses_exact_session(self):
        calls = []

        def fake_http(method, path, *, directory, body=None):
            calls.append((method, path, directory, body))
            if method == "POST" and path == "/session":
                return {"id": "ses_sigma"}
            if path == "/session/status":
                return {"ses_other": {"type": "busy"}, "ses_sigma": {"type": "idle"}}
            if path in ("/permission", "/question"):
                return []
            if path == "/session/ses_sigma/message":
                return [{"info": {"role": "assistant"}, "parts": [{"type": "text", "text": "done"}]}]
            return None

        with patch.object(adapters, "_http", side_effect=fake_http):
            run = adapters.start_executor("opencode", "/srv/lct/work/team-1-attempt", "item ID: PVTI_x", "run-1")
            repeated = adapters.start_executor("opencode", "/srv/lct/work/team-1-attempt", "ignored", "run-1")
            result = adapters.executor_status(run)

        self.assertEqual(run, repeated)
        self.assertEqual(2, sum(1 for call in calls if call[0] == "POST"))
        self.assertEqual("succeeded", result["state"])
        self.assertEqual("ses_sigma", result["artifact"]["session_id"])

    def test_pending_permission_blocks_only_matching_session(self):
        run = {"adapter": "opencode", "external_id": "ses_sigma", "run_id": "run-2",
               "workdir": "/srv/lct/work/team-2-attempt",
               "result_path": str(Path(self.temporary.name) / "run-2" / "result.json")}

        def fake_http(method, path, *, directory, body=None):
            if path == "/session/status":
                return {"ses_sigma": {"type": "idle"}}
            if path == "/permission":
                return [{"sessionID": "ses_other"}, {"sessionID": "ses_sigma"}]
            if method == "POST" and path == "/session/ses_sigma/abort":
                return True
            if path == "/session/status":
                return {}
            raise AssertionError(path)

        with patch.object(adapters, "_http", side_effect=fake_http):
            result = adapters.executor_status(run)
        self.assertEqual("blocked", result["state"])

    def test_opencode_timeout_is_terminal_without_api_poll(self):
        run_dir = Path(self.temporary.name) / "run-timeout"
        run_dir.mkdir()
        (run_dir / "adapter.json").write_text(json.dumps({
            "adapter": "opencode", "external_id": "ses_sigma", "run_id": "run-timeout",
            "workdir": "/srv/lct/work/team-3-attempt", "result_path": str(run_dir / "result.json"),
            "created_at": int(time.time()) - 1600,
        }))
        run = json.loads((run_dir / "adapter.json").read_text())
        calls = []
        def abort_http(method, path, *, directory, body=None):
            calls.append((method, path))
            if method == "POST" and path.endswith("/abort"):
                return True
            if path == "/session/status":
                return {"ses_sigma": {"type": "idle"}}
            raise AssertionError(path)
        with patch.object(adapters, "_http", side_effect=abort_http):
            result = adapters.executor_status(run)
        self.assertEqual("blocked", result["state"])
        self.assertEqual([("POST", "/session/ses_sigma/abort"), ("GET", "/session/status")], calls)

    def test_reviewer_launch_is_hermes_and_requires_dedicated_config(self):
        hermes_home = Path(self.temporary.name) / "hermes"
        hermes_home.mkdir()
        (hermes_home / "config.yaml").write_text("model: {provider: clirelay, default: gpt-5.6-terra}\n")
        with patch.object(adapters, "HERMES_HOME", str(hermes_home)), \
                patch.object(adapters.subprocess, "Popen") as popen, \
                patch.object(adapters, "_process_identity", return_value={"pid": 4321, "start_time": 7, "process_group": 4321}):
            popen.return_value.pid = 4321
            run = adapters.start_reviewer("/srv/lct/work/team-4-attempt", "review", "review-2")
        manifest = json.loads((Path(self.temporary.name) / "review-2" / "adapter.json").read_text())
        self.assertEqual("hermes-reviewer", run["adapter"])
        self.assertEqual("hermes", manifest["worker_kind"])
        self.assertEqual(150, manifest["timeout_seconds"])

    def test_process_result_promotes_structured_review_fields(self):
        run_dir = Path(self.temporary.name) / "review-1"
        run_dir.mkdir()
        result_path = run_dir / "result.json"
        result_path.write_text(json.dumps({
            "state": "succeeded",
            "output": {"verdict": "fail", "summary": "one finding", "findings": ["bug"],
                       "human_verification": ["confirm expected behavior"]},
        }))
        result = adapters.reviewer_status({
            "adapter": "codex-reviewer", "external_id": "process:review-1", "run_id": "review-1",
            "workdir": "/tmp/work", "result_path": str(result_path),
        })
        self.assertEqual("fail", result["verdict"])
        self.assertEqual(["bug"], result["findings"])

    def test_rejects_unsafe_run_id_and_unapproved_model(self):
        with self.assertRaises(adapters.AdapterError):
            adapters._safe_run_id("../escape")
        with patch.dict("os.environ", {"SIGMA_TEAM_MODEL": "gpt-unapproved"}):
            with self.assertRaises(adapters.AdapterError):
                adapters._model()

    def test_hermes_review_schema_is_strict(self):
        self.assertTrue(adapter_worker._valid_review({
            "verdict": "pass", "summary": "ok", "findings": [], "human_verification": ["open UI"],
        }))
        self.assertFalse(adapter_worker._valid_review({
            "verdict": "pass", "summary": "ok", "findings": [], "human_checks": [],
        }))

    def test_worker_timeout_terminates_entire_process_group(self):
        process = unittest.mock.Mock(pid=8765)
        process.communicate.side_effect = subprocess.TimeoutExpired(["worker"], 1)
        process.wait.side_effect = [subprocess.TimeoutExpired(["worker"], 5), 0]
        with patch.object(adapter_worker.subprocess, "Popen", return_value=process), \
                patch.object(adapter_worker.os, "killpg") as killpg:
            with self.assertRaises(subprocess.TimeoutExpired):
                adapter_worker._run_command(
                    ["worker"], input_data=None, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, env={}, timeout=1,
                )
        self.assertEqual(
            [unittest.mock.call(8765, adapter_worker.signal.SIGTERM),
             unittest.mock.call(8765, adapter_worker.signal.SIGKILL)],
            killpg.call_args_list,
        )

    def _cancel_run(self, adapter="opencode"):
        run_dir = Path(self.temporary.name) / "cancel-run"
        run_dir.mkdir()
        run = {
            "adapter": adapter, "external_id": "ses_parent" if adapter == "opencode" else "process:cancel-run",
            "run_id": "cancel-run", "workdir": "/tmp/work", "result_path": str(run_dir / "result.json"),
        }
        manifest = dict(run)
        if adapter != "opencode":
            manifest["worker_pid"] = 1234
            manifest["worker_identity"] = {"pid": 1234, "start_time": 9, "process_group": 1234}
        (run_dir / "adapter.json").write_text(json.dumps(manifest))
        return run, run_dir

    def test_cancel_opencode_interrupts_exact_parent_and_busy_child_then_waits_all_idle(self):
        run, run_dir = self._cancel_run()
        calls = []
        active = {"ses_parent": "busy", "ses_child": "busy"}

        def fake_http(method, path, *, directory, body=None, query_params=None):
            calls.append((method, path))
            if path == "/api/session":
                return {"data": [
                    {"id": "ses_parent"}, {"id": "ses_child", "parentID": "ses_parent"},
                    {"id": "ses_unrelated"},
                ], "cursor": {}}
            if method == "POST" and path.endswith("/interrupt"):
                active[path.split("/")[-2]] = "idle"
                return None
            if method == "POST" and path.endswith("/wait"):
                self.assertEqual("idle", active[path.split("/")[-2]])
                return None
            if path == "/session/status":
                return {session_id: {"type": state} for session_id, state in active.items()}
            raise AssertionError(path)

        with patch.object(adapters, "_http", side_effect=fake_http):
            result = adapters.cancel(run)
            repeated = adapters.cancel(run)
        self.assertEqual("cancelled", result["state"])
        self.assertEqual(result, repeated)
        self.assertEqual(["ses_parent", "ses_child"], result["sessions"])
        self.assertTrue(result["confirmed"])
        self.assertNotIn(("POST", "/api/session/ses_unrelated/interrupt"), calls)
        self.assertEqual(1, calls.count(("POST", "/api/session/ses_child/interrupt")))
        self.assertTrue((run_dir / "result.json").exists())

    def test_cancel_process_signals_only_recorded_process_group_and_persists_result(self):
        run, run_dir = self._cancel_run("codex-executor")
        identity = {"pid": 1234, "start_time": 9, "process_group": 1234}
        with patch.object(adapters, "_process_identity", return_value=identity), \
                patch.object(adapters, "_process_stopped", return_value=True), \
                patch.object(adapters.os, "killpg") as killpg:
            result = adapters.cancel(run)
        self.assertEqual("cancelled", result["state"])
        killpg.assert_called_once_with(1234, 15)
        self.assertEqual("cancelled", json.loads((run_dir / "result.json").read_text())["state"])

    def test_cancel_process_refuses_reused_pid_without_signalling(self):
        run, run_dir = self._cancel_run("codex-executor")
        mismatch = {"pid": 1234, "start_time": 10, "process_group": 1234}
        with patch.object(adapters, "_process_identity", return_value=mismatch), \
                patch.object(adapters.os, "killpg") as killpg:
            with self.assertRaises(adapters.AdapterError):
                adapters.cancel(run)
        killpg.assert_not_called()
        manifest = json.loads((run_dir / "adapter.json").read_text())
        self.assertEqual("refused_pid_mismatch", manifest["cancellation"]["state"])


if __name__ == "__main__":
    unittest.main()
