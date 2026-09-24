"""Contract tests for the separate frozen-report diagnostic scorer."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).with_name('correct_frozen_report.py')
spec = importlib.util.spec_from_file_location('correct_frozen_report', MODULE)
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def sample_report(track, prediction):
    case = {'case_id': 'case-000137', 'status': 'ok', 'origin_kind': 'real',
            'reference_derived': False, 'basket_ids': ['b1'], 'graded': True,
            'correct': False, 'rank': 0, 'prediction': prediction}
    report = {'run_id': 'run1', 'scoring_version': '1',
              'submission': {'track': track, 'suite_hash': 'suite1',
                             'solution': {'name': 'test'}},
              'cases': [case], 'by_origin': {'real': {}},
              'by_reference': {'independent': {}}, 'by_basket': {'b1': {}}}
    report.update(scorer.recompute(report))
    return report


def correction(track):
    old = {'expected_slug': 'wrong'}
    new = {'expected_slug': 'right'}
    if track == 'service':
        old['expected_action'] = new['expected_action'] = 'match'
    return {'track': track, 'old_gold': old, 'new_gold': new}


class ScoreContractTests(unittest.TestCase):
    def test_branch_discovery_only_accepts_scorer_reports(self):
        with tempfile.TemporaryDirectory() as root:
            reports = Path(root) / 'model' / 'reports'
            reports.mkdir(parents=True)
            (reports / 'report-all-service.json').write_text(json.dumps({'scoring_version': '1', 'cases': [], 'submission': {}}))
            (reports / 'report-label-service.json').write_text(json.dumps({'scoring_version': '1', 'cases': [], 'submission': {}}))
            (reports / 'notes.json').write_text('{}')
            (reports.parent / 'all-service.json').write_text('{}')
            self.assertEqual(len(scorer.discover_reports([Path(root)], False)), 1)
            self.assertEqual(len(scorer.discover_reports([Path(root)], True)), 2)

    def test_service_corrected_without_mutating_historical_report(self):
        report = sample_report('service', {'action': 'match', 'slug': 'right'})
        original = copy.deepcopy(report)
        corrected, info = scorer.correct_report(report, {'case-000137': correction('service')},
                                                'suite1', 'source-sha', 'erratum-sha')
        self.assertEqual(report, original)
        self.assertEqual(corrected['overall']['correct_top1'], 1)
        self.assertEqual(corrected['cases'][0]['rank'], 1)
        self.assertEqual(info['public']['delta']['correct_top1'], 1)
        self.assertEqual(info['private']['changes'][0]['old_rank'], 0)

    def test_service_action_mismatch_cannot_become_correct(self):
        report = sample_report('service', {'action': 'no_match', 'slug': 'right'})
        corrected, info = scorer.correct_report(report, {'case-000137': correction('service')},
                                                'suite1', 'source-sha', 'erratum-sha')
        self.assertEqual(corrected['cases'][0]['rank'], 0)
        self.assertEqual(info['public']['delta']['correct_top1'], 0)

    def test_retrieval_rank_and_mrr_follow_new_expected_slug(self):
        report = sample_report('retrieval', {'ranked_slugs': ['a', 'right', 'b']})
        corrected, info = scorer.correct_report(report, {'case-000137': correction('retrieval')},
                                                'suite1', 'source-sha', 'erratum-sha')
        self.assertEqual(corrected['cases'][0]['rank'], 2)
        self.assertEqual(corrected['overall']['correct_top1'], 0)
        self.assertEqual(corrected['overall']['correct_top5'], 1)
        self.assertEqual(corrected['overall']['mrr'], 0.5)
        self.assertEqual(info['public']['delta']['mrr'], 0.5)

    def test_report_suite_and_old_score_must_match(self):
        report = sample_report('service', {'action': 'match', 'slug': 'right'})
        with self.assertRaisesRegex(ValueError, 'suite hash'):
            scorer.correct_report(report, {'case-000137': correction('service')},
                                  'other-suite', 'source-sha', 'erratum-sha')
        report['cases'][0]['rank'] = 1
        with self.assertRaisesRegex(ValueError, 'historical'):
            scorer.correct_report(report, {'case-000137': correction('service')},
                                  'suite1', 'source-sha', 'erratum-sha')

    def test_incomplete_full_report_is_rejected(self):
        report = sample_report('service', {'action': 'match', 'slug': 'right'})
        corrections = {'case-000137': correction('service'),
                       'case-000138': correction('service')}
        with self.assertRaisesRegex(ValueError, 'missing one or more'):
            scorer.correct_report(report, corrections, 'suite1', 'source-sha', 'erratum-sha')

    def test_erratum_rejects_modified_gold_and_image_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            suite_path, gold_path, provenance_path = [root / name for name in
                ('suite.json', 'gold.json', 'provenance.json')]
            image = root / 'image.webp'
            image.write_bytes(b'image')
            case = {'case_id': 'case-000137', 'tracks': ['service'],
                    'image_path': 'image.webp', 'image_sha256': scorer.digest(image),
                    'scene_group_id': 'scene'}
            suite = {'version': '1', 'suite_hash': 'hash', 'cases': [case]}
            gold = {'suite_hash': 'hash', 'cases': [{'case_id': 'case-000137', 'verified': True,
                     'service': {'expected_action': 'match', 'expected_slug': 'wrong'}}]}
            provenance = {'cases': [{'case_id': 'case-000137', 'scene_group_id': 'scene',
                           'parent_case_id': None, 'transformation': None}]}
            for path, data in ((suite_path, suite), (gold_path, gold),
                               (provenance_path, provenance)):
                path.write_text(json.dumps(data))
            item = {'case_id': 'case-000137', 'track': 'service',
                    'image_sha256': scorer.digest(image), 'old_gold': copy.deepcopy(gold['cases'][0]['service']),
                    'new_gold': {'expected_action': 'match', 'expected_slug': 'right'},
                    'scene_group_id': 'scene', 'lineage': {'parent_case_id': None,
                    'transformation': None}}
            erratum = {'schema_version': 1, 'source_suite_version': '1',
                       'source_suite_hash': 'hash', 'source_suite_file_sha256': scorer.digest(suite_path),
                       'source_gold_file_sha256': scorer.digest(gold_path),
                       'source_provenance_file_sha256': scorer.digest(provenance_path),
                       'corrections': [item]}
            validate = lambda: scorer.validate_erratum(suite, gold, provenance, erratum,
                suite_path, gold_path, provenance_path, root)
            self.assertEqual(len(validate()), 1)
            gold['cases'][0]['service']['expected_slug'] = 'changed'
            with self.assertRaisesRegex(ValueError, 'old gold'):
                validate()
            gold['cases'][0]['service']['expected_slug'] = 'wrong'
            image.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'image bytes'):
                validate()


if __name__ == '__main__':
    unittest.main()
