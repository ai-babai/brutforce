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

SOURCE = pathlib.Path(__file__).with_name("release.py")
SPEC = importlib.util.spec_from_file_location("release_under_test", SOURCE)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
SHA = "a" * 40


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
            "roman-conformance": b"conformance", "catalog-migrate": b"migrate",
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


if __name__ == "__main__":
    unittest.main()
