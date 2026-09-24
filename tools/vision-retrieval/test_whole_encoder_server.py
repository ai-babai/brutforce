"""Small contract checks for the whole-only HTTP variant (no model load)."""
import hashlib
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name('whole_encoder_server.py')
SPEC = importlib.util.spec_from_file_location('whole_encoder_server', MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class WholeEncoderServerTest(unittest.TestCase):
    def test_index_provenance_must_match_all_fields(self):
        catalog = b'{"references":[]}'
        valid = {'model': module.MODEL, 'label_crop': module.LABEL_CROP,
                 'catalog_manifest_sha256': hashlib.sha256(catalog).hexdigest()}
        module.validate_index_info(valid, catalog)
        for key, wrong in [('model', 'other-model'),
                           ('label_crop', 'other-crop'),
                           ('catalog_manifest_sha256', '0' * 64)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                module.validate_index_info({**valid, key: wrong}, catalog)

    def test_service_and_retrieval_contract(self):
        ranked = [{'slug': 'wine-a', 'score': .9},
                  {'slug': 'wine-b', 'score': .8}]
        self.assertEqual(module.prediction('service', True, ranked), {'slug': 'wine-a'})
        self.assertEqual(module.prediction('service', False, ranked), {'action': 'no_match'})
        self.assertEqual(module.prediction('service', True, []),
                         {'action': 'insufficient_information'})
        self.assertEqual(module.prediction('retrieval', True, ranked),
                         {'ranked_slugs': ['wine-a', 'wine-b']})
        with self.assertRaises(ValueError):
            module.prediction('unexpected', True, ranked)


if __name__ == '__main__':
    unittest.main()
