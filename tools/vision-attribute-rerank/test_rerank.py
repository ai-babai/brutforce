import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location('attribute_rerank', Path(__file__).with_name('rerank.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def meta(slug, sweetness, color='розовое', title='Жемчужная 9 Пино Нуар'):
    return {'producer': 'АРАТТИ', 'producer_key': 'aratti', 'title': title,
            'title_key': module.norm(title), 'color': color, 'sweetness': sweetness,
            'year': None, 'catalog_conflict': False}


def rec(ocr, action='match'):
    return {'case_id': 'example', 'track': 'service', 'status': 'ok',
            'prediction': {'action': action, 'slug': 'dry'},
            'ocr': {'action': 'wine', 'raw_text': ocr},
            'ranked': [{'slug': 'dry'}, {'slug': 'semi'}]}


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {'dry': meta('dry', 'сухое'), 'semi': meta('semi', 'полусухое')}

    def test_semi_dry_is_not_dry_and_reorders_only_siblings(self):
        item = module.rerank(rec('АРАТТИ Жемчужная 9 Пино Нуар розовое полусухое'), self.metadata)
        self.assertEqual(item['attributes']['sweetness'], 'полусухое')
        self.assertEqual(item['after'], ['semi', 'dry'])
        self.assertEqual(item['after_prediction_slug'], 'semi')

    def test_nonwine_substrings_and_ambiguous_year_are_neutral(self):
        attrs = module.parse_ocr('полусухарики сухофрукты 2023 2024')
        self.assertEqual(attrs, {'color': None, 'sweetness': None, 'year': None})
        self.assertFalse(module.rerank(rec('АРАТТИ Жемчужная 9 Пино Нуар сухофрукты'), self.metadata)['changed'])

    def test_no_match_and_nonwine_ocr_unchanged(self):
        self.assertFalse(module.rerank(rec('АРАТТИ Жемчужная 9 Пино Нуар полусухое', 'no_match'), self.metadata)['changed'])
        item = rec('АРАТТИ Жемчужная 9 Пино Нуар полусухое')
        item['ocr']['action'] = 'other_alcohol'
        self.assertFalse(module.rerank(item, self.metadata)['changed'])

    def test_different_producers_or_weak_title_evidence_unchanged(self):
        changed = dict(self.metadata)
        changed['semi'] = dict(changed['semi'], producer_key='other')
        self.assertFalse(module.rerank(rec('АРАТТИ Жемчужная 9 Пино Нуар полусухое'), changed)['changed'])
        self.assertFalse(module.rerank(rec('АРАТТИ полусухое'), self.metadata)['changed'])

    def test_unknown_and_conflicting_metadata_neutral(self):
        changed = dict(self.metadata)
        changed['semi'] = dict(changed['semi'], sweetness=None)
        self.assertTrue(module.rerank(rec('АРАТТИ Жемчужная 9 Пино Нуар полусухое'), changed)['changed'])
        changed['dry'] = dict(changed['dry'], sweetness=None)
        self.assertFalse(module.rerank(rec('АРАТТИ Жемчужная 9 Пино Нуар полусухое'), changed)['changed'])

    def test_catalog_conflict_and_missing_year_remain_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            display = folder / 'display.jsonl'
            display.write_text(json.dumps({'slug': 'a', 'title': 'Aratti 2024', 'producer': 'Aratti',
                 'producer_slug': 'aratti', 'category_and_sweetness': 'Розовое полусухое',
                 'sweetness': 'сухое'}, ensure_ascii=False) + '\n')
            official = folder / 'official.csv'
            with official.open('w', newline='') as file:
                writer = csv.DictWriter(file, fieldnames=['Slug', 'Название вина', 'Категория', 'Винодельня'])
                writer.writeheader()
                writer.writerow({'Slug': 'a', 'Название вина': 'Aratti 2023',
                                 'Категория': 'Красное', 'Винодельня': 'Aratti'})
            entry = module.catalog(display, official)['a']
            self.assertIsNone(entry['color'])
            self.assertIsNone(entry['sweetness'])
            self.assertIsNone(entry['year'])
            self.assertTrue(entry['catalog_conflict'])


if __name__ == '__main__':
    unittest.main()
