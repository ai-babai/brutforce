import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location('adapt_rtso', Path(__file__).with_name('adapt_rtso.py'))
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


def fixtures():
    selection = {'selected_box': [1, 2, 3, 4], 'selection_reason': 'nearest_center_wine'}
    rtso = {'case_id': 'c1', 'track': 'service', 'query_sha256': 'image-sha',
            'selection': selection, 'label_context_box': [2, 3, 4, 5],
            'predictions': {'all': {'slug': 'a'}},
            'variants_top20': {'all': [{'slug': 'a'}, {'slug': 'b'}]}}
    old = {'case_id': 'c1', 'track': 'service', 'query_sha256': 'image-sha',
           'result': {'image_sha256': 'image-sha', 'selection': selection,
                      'label_context_box': [2, 3, 4, 5],
                      'ocr_text': 'РОЗОВОЕ ПОЛУСУХОЕ', 'ocr_error': None}}
    return rtso, old


class AdapterTests(unittest.TestCase):
    def test_preserves_original_predictions_and_adds_same_crop_ocr(self):
        rtso, old = fixtures()
        adapted = adapter.adapt(rtso, old, 'source-sha')
        self.assertEqual(adapted['predictions'], rtso['predictions'])
        self.assertEqual(adapted['variants_top20'], rtso['variants_top20'])
        self.assertEqual(adapted['ocr_text'], 'РОЗОВОЕ ПОЛУСУХОЕ')
        self.assertNotIn('ocr_text', rtso)

    def test_rejects_image_or_crop_mismatch(self):
        rtso, old = fixtures()
        wrong = dict(old, query_sha256='wrong')
        with self.assertRaisesRegex(ValueError, 'image SHA'):
            adapter.adapt(rtso, wrong, 'source-sha')
        wrong = dict(old, result=dict(old['result'], label_context_box=[9, 9, 9, 9]))
        with self.assertRaisesRegex(ValueError, 'label crop'):
            adapter.adapt(rtso, wrong, 'source-sha')


if __name__ == '__main__':
    unittest.main()
