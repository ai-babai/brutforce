"""Focused safety tests for the native release controller."""
import hashlib
import importlib.util
import io
import json
import pathlib
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

SOURCE = pathlib.Path(__file__).with_name("release.py")
SPEC = importlib.util.spec_from_file_location("release_under_test", SOURCE)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
SHA = "a" * 40
MANIFEST_SHA = "b" * 64
VALIDATOR_SHA = "c" * 64


class ReleaseSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        release.ROOT = base / "releases"
        release.CONFIG = base / "config.json"
        # The controller runs with Ubuntu's Python 3.12. Keep these focused
        # tests runnable on older local Python versions too.
        release.digest = lambda path: hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
        self.extractall = release.tarfile.TarFile.extractall
        if sys.version_info < (3, 12):
            def extractall_compat(archive, path=None, members=None, *, numeric_owner=False, filter=None):
                return self.extractall(archive, path, members, numeric_owner=numeric_owner)
            release.tarfile.TarFile.extractall = extractall_compat
        for name in ("packages", "records", "public"):
            (release.ROOT / name).mkdir(parents=True, exist_ok=True)
        self.test_path = base / "test"
        self.prod_path = base / "prod"
        self.test_path.mkdir()
        self.prod_path.mkdir()
        release.CONFIG.write_text(json.dumps({"environments": {
            "test": {"path": str(self.test_path), "url": "http://unused", "migrationEnv": "unused"},
            "prod": {"path": str(self.prod_path), "url": "http://unused", "migrationEnv": "unused"},
        }}))

    def tearDown(self):
        release.tarfile.TarFile.extractall = self.extractall
        self.tmp.cleanup()

    def archive(self, files):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as archive:
            for name, data in files.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        return stream.getvalue()

    def install_bytes(self, data, checksum=None):
        original = sys.stdin
        sys.stdin = type("Input", (), {"buffer": io.BytesIO(data)})()
        try:
            release.install(SHA, checksum or hashlib.sha256(data).hexdigest(), "123")
        finally:
            sys.stdin = original

    def valid_files(self, checks):
        files = {
            "brutforce-api": b"api", "reference-engine": b"engine",
            "roman-conformance": b"conformance", "catalog-migrate": b"migrate", "catalog-import": b"import",
            "REVISION": (SHA + "\n").encode(), "web/index.html": b"<html>",
            "web/release.json": json.dumps({"revision": SHA}).encode(),
            "migrations/00001_demo_catalog.sql": b"select 1;",
            "evidence/checks.json": json.dumps(checks).encode(),
        }
        manifest = {"schemaVersion": 1, "revision": SHA, "mode": "reference",
                    "catalogVersion": "demo-v1", "modelVersion": "reference-demo-v1",
                    "synthetic": True, "files": []}
        for name, data in files.items():
            manifest["files"].append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
        files["manifest.json"] = json.dumps(manifest).encode()
        return files

    def installed_target(self, target):
        target.mkdir(parents=True, exist_ok=True)
        manifest = {"files": []}
        (target / "manifest.json").write_text(json.dumps(manifest))
        return manifest

    def test_rejects_unsafe_archive_member(self):
        data = self.archive({"../outside": b"unsafe"})
        with self.assertRaisesRegex(RuntimeError, "Unsafe archive member"):
            self.install_bytes(data)

    def test_rejects_checksum_mismatch_before_unpacking(self):
        data = self.archive({"manifest.json": b"{}"})
        with self.assertRaisesRegex(RuntimeError, "Archive checksum mismatch"):
            self.install_bytes(data, "0" * 64)

    def test_rejects_missing_ci_gate(self):
        data = self.archive(self.valid_files({"status": "failed", "revision": SHA}))
        with self.assertRaisesRegex(RuntimeError, "Required CI checks did not pass"):
            self.install_bytes(data)

    def test_rejects_demo_only_package_from_test_prod_controller(self):
        data = self.archive(self.valid_files({"status": "passed", "revision": SHA,
                                              "bddCoverageStatus": "partial", "targetScope": "maks-demo-only"}))
        with self.assertRaisesRegex(RuntimeError, "Partial BDD coverage"):
            self.install_bytes(data)

    def test_production_requires_explicit_approval_after_other_gates(self):
        target = release.ROOT / "packages" / SHA
        manifest = self.installed_target(target)
        release.write(release.record(SHA), {"revision": SHA, "gates": {
            "ci": {"status": "passed"}, "test": {"status": "passed"},
            "browser": {"status": "passed"},
        }, "manifest": manifest, "history": []})
        with self.assertRaisesRegex(RuntimeError, "Explicit approval"):
            release.switch("prod", SHA)

    def test_rollback_refuses_different_schema(self):
        previous_sha = "b" * 40
        previous = release.ROOT / "packages" / previous_sha
        target = release.ROOT / "packages" / SHA
        (previous / "migrations").mkdir(parents=True)
        (target / "migrations").mkdir(parents=True)
        (previous / "migrations" / "00001.sql").write_text("old")
        (target / "migrations" / "00001.sql").write_text("new")
        (self.test_path / "current").symlink_to(previous)
        manifest = {"files": []}
        (target / "manifest.json").write_text(json.dumps(manifest))
        release.write(release.record(SHA), {"revision": SHA, "gates": {}, "manifest": manifest, "history": []})
        with self.assertRaisesRegex(RuntimeError, "Schema differs"):
            release.switch("test", SHA, "rollback")

    def test_cli_rejects_missing_or_invalid_arguments(self):
        with self.assertRaisesRegex(RuntimeError, "Invalid command or argument count"):
            release.main([])
        with self.assertRaisesRegex(RuntimeError, "Invalid command or argument count"):
            release.main(["install", SHA])

    def test_data_report_requires_every_preflight_case_to_pass(self):
        report = {
            "schemaVersion": 1, "kind": "catalog-data-quality", "status": "passed",
            "catalogVersion": "catalog-v2", "manifestSHA256": MANIFEST_SHA,
            "validatorVersion": VALIDATOR_SHA, "startedAt": "2026-09-22T00:00:00Z",
            "completedAt": "2026-09-22T00:01:00Z", "durationMs": 60000,
            "cases": [{"id": f"DQ{i:03d}", "status": "passed"} for i in range(1, 9)]
                     + [{"id": "DQ011", "status": "skipped"}],
        }
        with self.assertRaisesRegex(RuntimeError, "did not pass"):
            release.validate_data_report(report)

    def test_candidate_changes_when_only_data_changes(self):
        first = release.candidate_id(SHA, MANIFEST_SHA, "reference", "reference-demo-v1")
        second = release.candidate_id(SHA, "d" * 64, "reference", "reference-demo-v1")
        self.assertNotEqual(first, second)

    def test_real_candidate_approval_is_bound_to_candidate_and_manifest(self):
        candidate = release.candidate_id(SHA, MANIFEST_SHA, "reference", "reference-demo-v1")
        release.write(release.record(candidate), {
            "candidateId": candidate, "revision": SHA, "catalogManifestSHA256": MANIFEST_SHA,
            "gates": {name: {"status": "passed"} for name in ("ci", "data", "test", "browser", "placement")},
            "manifest": {"files": []}, "history": []
        })
        release.main(["approve", candidate, "maks", "telegram:chat:message"])
        approved = release.load(candidate)["approval"]
        self.assertEqual(approved["candidateId"], candidate)
        self.assertEqual(approved["catalogManifestSHA256"], MANIFEST_SHA)

    def test_exact_external_removed_ids_approval_is_accepted(self):
        candidate = release.candidate_id(SHA, MANIFEST_SHA, "reference", "reference-demo-v1")
        path = pathlib.Path(self.tmp.name) / "approvals" / f"{candidate}.json"
        path.parent.mkdir()
        path.write_text(json.dumps({
            "candidateId": candidate, "manifestSHA256": MANIFEST_SHA,
            "ids": ["demo-a", "demo-b"], "reason": "approved demo replacement",
            "approvalRef": "task:BE-045"
        }))
        record = {"catalogManifestSHA256": MANIFEST_SHA}
        self.assertEqual(release.validate_removal_approval(path, candidate, record), path)

    def test_removed_ids_approval_for_another_candidate_is_rejected(self):
        candidate = release.candidate_id(SHA, MANIFEST_SHA, "reference", "reference-demo-v1")
        path = pathlib.Path(self.tmp.name) / "approval.json"
        path.write_text(json.dumps({
            "candidateId": "f" * 64, "manifestSHA256": MANIFEST_SHA,
            "ids": ["demo-a"], "reason": "wrong candidate", "approvalRef": "task:BE-045"
        }))
        with self.assertRaisesRegex(RuntimeError, "another candidate"):
            release.validate_removal_approval(path, candidate, {"catalogManifestSHA256": MANIFEST_SHA})

    def test_failed_post_import_smoke_restores_db_before_old_app(self):
        candidate = release.candidate_id(SHA, MANIFEST_SHA, "reference", "reference-demo-v1")
        target = release.ROOT / "packages" / SHA
        previous = release.ROOT / "packages" / ("b" * 40)
        for folder in (target, previous):
            (folder / "migrations").mkdir(parents=True)
            (folder / "migrations" / "00001.sql").write_text("same schema")
        importer = target / "catalog-import"; importer.write_bytes(b"validator")
        validator = hashlib.sha256(b"validator").hexdigest()
        manifest = {"files": []}; (target / "manifest.json").write_text(json.dumps(manifest))
        (self.test_path / "current").symlink_to(previous)
        catalog_env = self.test_path / "catalog.env"; catalog_env.write_text("CATALOG_VERSION=demo-v1\n")
        config = json.loads(release.CONFIG.read_text())
        backup_root = pathlib.Path(self.tmp.name) / "backups"
        config["catalogBackupRoot"] = str(backup_root)
        config["environments"]["test"]["catalogEnv"] = str(catalog_env)
        migration_env = pathlib.Path(self.tmp.name) / "migration.env"; migration_env.write_text("MIGRATION_DATABASE_URL=postgresql://unused\n")
        config["environments"]["test"]["migrationEnv"] = str(migration_env)
        release.CONFIG.write_text(json.dumps(config))
        report = {"schemaVersion":1,"kind":"catalog-data-quality","status":"passed","catalogVersion":"real-v1",
                  "manifestSHA256":MANIFEST_SHA,"validatorVersion":validator,"startedAt":"2026-09-22T00:00:00Z",
                  "completedAt":"2026-09-22T00:01:00Z","durationMs":60000,
                  "cases":[{"id":f"DQ{i:03d}","status":"passed"} for i in range(1,9)]+[{"id":"DQ011","status":"passed"}]}
        approval = backup_root / "test" / "approvals" / f"{candidate}.json"; approval.parent.mkdir(parents=True)
        approval.write_text(json.dumps({"candidateId":candidate,"manifestSHA256":MANIFEST_SHA,"ids":["demo"],
                                        "reason":"approved initial replacement","approvalRef":"task:BE-045"}))
        release.write(release.record(candidate), {"candidateId":candidate,"revision":SHA,"catalogVersion":"real-v1",
            "catalogManifestSHA256":MANIFEST_SHA,"validatorVersion":validator,"mode":"reference","modelVersion":"reference-demo-v1",
            "manifest":manifest,"dataReport":report,"catalogPackage":"/catalog","catalogMediaRoot":"/media",
            "gates":{"ci":{"status":"passed"},"data":{"status":"passed"},"test":{"status":"pending"},"browser":{"status":"pending"},"placement":{"status":"pending"}},"history":[]})
        calls=[]
        def command(*args,**kwargs):
            calls.append(args)
            if "--export-snapshot" in args:
                pathlib.Path(args[args.index("--export-snapshot")+1]).write_text(json.dumps({"version":"demo-v1","manifestSHA256":"e"*64,"wines":[{"id":"demo"}]}))
            if "--report-out" in args:
                pathlib.Path(args[args.index("--report-out")+1]).write_text(json.dumps(report))
        with mock.patch.object(release,"command",side_effect=command), \
             mock.patch.object(release,"validate_catalog_bytes",return_value=(pathlib.Path('/catalog'),pathlib.Path('/media'))), \
             mock.patch.object(release,"smoke",side_effect=RuntimeError("smoke failed")):
            with self.assertRaisesRegex(RuntimeError,"smoke failed"):
                release.switch("test",candidate)
        restore_index=next(i for i,x in enumerate(calls) if "--restore" in x)
        compare_call=next(x for x in calls if "--compare-ids" in x)
        self.assertEqual(compare_call[compare_call.index("--allow-removed")+1],str(approval))
        import_call=next(x for x in calls if "--snapshot-out" in x)
        self.assertIn("--accepted-report",import_call)
        self.assertEqual(import_call[import_call.index("--validator-version")+1],validator)
        restart_indexes=[i for i,x in enumerate(calls) if x[-1]=="restart-test"]
        self.assertLess(restore_index,restart_indexes[-1])
        self.assertEqual((self.test_path / "current").resolve(),previous.resolve())
        self.assertEqual(catalog_env.read_text(),"CATALOG_VERSION=demo-v1\n")
        self.assertEqual(release.load(candidate)["gates"]["test"]["status"],"failed")

    def test_preflight_block_is_recorded_as_failed_attempt(self):
        release.write(release.record(SHA), {"revision":SHA,"candidateId":SHA,"gates":{"test":{"status":"pending"}},"history":[]})
        with mock.patch.object(release,"switch",side_effect=RuntimeError("installed bytes changed")):
            with self.assertRaisesRegex(RuntimeError,"installed bytes changed"):
                release.safe_switch("test",SHA)
        saved=release.load(SHA)
        self.assertEqual(saved["gates"]["test"]["status"],"failed")
        self.assertEqual(saved["history"][-1]["action"],"deploy-failed")


if __name__ == "__main__":
    unittest.main()
