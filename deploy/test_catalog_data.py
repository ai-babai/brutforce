import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("catalog_data", Path(__file__).with_name("catalog_data.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CatalogMaterializationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source, self.target = self.root / "source", self.root / "catalog"
        (self.source / "public/images").mkdir(parents=True)
        (self.source / "internal").mkdir()
        image = base64.b64decode("UklGRiIAAABXRUJQVlA4IBYAAAAwAQCdASoBAAEADsD+JaQAA3AAAAAA")
        digest = hashlib.sha256(image).hexdigest()
        (self.source / "public/images/tiny.webp").write_bytes(image)
        meta = {"path": "images/tiny.webp", "sha256": digest, "bytes": len(image),
                "width": 1, "height": 1, "mime_type": "image/webp"}
        variants = [dict(meta, role=r) for r in module.ROLES]
        self.row = {"slug": "test-wine", "title": "Test", "image": dict(meta, variants=variants)}
        self.write_rows([self.row])
        self.write("public/catalog.json", {"schema_version": "svoe-display-catalog-2.0.0"})
        self.write("public/aliases.json", {"aliases": []})
        self.write("internal/accepted-text-suppressions.json", {"entries": []})
        self.write("validation-manifest.json", {"fixture": True})

    def write(self, path, data):
        (self.source / path).write_text(json.dumps(data))

    def write_rows(self, rows):
        (self.source / "public/wines.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_small_image_in_all_directories_and_repeat_is_immutable(self):
        first = module.materialize(self.source, self.target, "test-v2")
        second = module.materialize(self.source, self.target, "test-v2")
        self.assertEqual(first, second)
        for role in ("400", "800", "original"):
            files = list((self.target / "media" / role).glob("*.webp"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_bytes(), (self.source / "public/images/tiny.webp").read_bytes())

    def test_existing_version_cannot_change(self):
        module.materialize(self.source, self.target, "test-v2")
        self.row["title"] = "Changed"
        self.write_rows([self.row])
        with self.assertRaisesRegex(ValueError, "version already exists"):
            module.materialize(self.source, self.target, "test-v2")

    def test_materializer_preserves_text_and_unknown_values(self):
        self.row.update({"description": "Source text", "year": None, "volume_l": None,
                         "source_url": "https://example.test/wine"})
        self.write_rows([self.row])
        module.materialize(self.source, self.target, "test-v2")
        accepted = json.loads((self.target / "releases/test-v2/wines.jsonl").read_text())
        for field in ("title", "description", "year", "volume_l", "source_url"):
            self.assertEqual(accepted[field], self.row[field])

    def test_missing_policy_does_not_install_media(self):
        (self.source / "internal/accepted-text-suppressions.json").unlink()
        with self.assertRaises(ValueError):
            module.materialize(self.source, self.target, "test-v2")
        self.assertFalse((self.target / "media").exists())

    def test_symlinked_media_directory_rejected(self):
        self.target.mkdir()
        external = self.root / "external"
        external.mkdir()
        (self.target / "media").symlink_to(external)
        with self.assertRaises(ValueError):
            module.materialize(self.source, self.target, "test-v2")
        self.assertEqual(list(external.iterdir()), [])

    def test_same_hash_inconsistent_metadata_rejected(self):
        other = json.loads(json.dumps(self.row))
        other["slug"] = "another"
        other["image"]["variants"][0]["width"] = 2
        self.write_rows([self.row, other])
        with self.assertRaisesRegex(ValueError, "inconsistent declarations"):
            module.materialize(self.source, self.target, "test-v2")


if __name__ == "__main__":
    unittest.main()
