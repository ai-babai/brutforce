import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location('attribute_score', Path(__file__).with_name('score.py'))
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


class ScoreTests(unittest.TestCase):
    def test_service_action_mismatch_not_fixed_by_slug(self):
        expected = {'expected_action': 'match', 'expected_slug': 'right'}
        self.assertFalse(score.score_service('no_match', 'right', expected))
        self.assertTrue(score.score_service('match', 'right', expected))

    def test_candidate_top20_unchanged_when_only_order_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            input_path, output_path = Path(folder) / 'input.jsonl', Path(folder) / 'output.jsonl'
            source = {'case_id': 'c1', 'track': 'service', 'status': 'ok',
                      'query_sha256': 'image-sha',
                      'prediction': {'action': 'match', 'slug': 'wrong'}}
            result = {'case_id': 'c1', 'track': 'service', 'before': ['wrong', 'right'],
                      'after': ['right', 'wrong'], 'changed': True,
                      'before_prediction_slug': 'wrong', 'after_prediction_slug': 'right',
                      'attributes': {}, 'groups': []}
            input_path.write_text(json.dumps(source) + '\n')
            output_path.write_text(json.dumps(result) + '\n')
            frozen = {'c1': {'verified': True, 'service': {
                'expected_action': 'match', 'expected_slug': 'right'}}}
            metrics, cases = score.score_run('frozen-synthetic', input_path, output_path, frozen, {},
                                             {'c1': 'image-sha'}, {}, 'suite-hash')
            self.assertEqual(metrics['delta_top1'], 1)
            self.assertEqual(metrics['delta_top5'], 0)
            self.assertEqual(metrics['delta_top20'], 0)
            self.assertEqual(metrics['candidate_rank_improved'], 1)
            self.assertEqual(metrics['candidate_rank_worsened'], 0)
            self.assertEqual(cases[0]['old_rank'], 2)

    def test_error_status_is_wrong_even_with_stale_correct_slug(self):
        with tempfile.TemporaryDirectory() as folder:
            input_path, output_path = Path(folder) / 'input.jsonl', Path(folder) / 'output.jsonl'
            source = {'case_id': 'c1', 'track': 'service', 'status': 'error',
                      'query_sha256': 'image-sha',
                      'prediction': {'action': 'match', 'slug': 'right'}}
            result = {'case_id': 'c1', 'track': 'service', 'before': ['right'],
                      'after': ['right'], 'changed': False,
                      'before_prediction_slug': 'right', 'after_prediction_slug': 'right'}
            input_path.write_text(json.dumps(source) + '\n')
            output_path.write_text(json.dumps(result) + '\n')
            frozen = {'c1': {'verified': True, 'service': {
                'expected_action': 'match', 'expected_slug': 'right'}}}
            metrics, _ = score.score_run('frozen-synthetic', input_path, output_path, frozen, {},
                                         {'c1': 'image-sha'}, {}, 'suite-hash')
            self.assertEqual(metrics['baseline_top1'], 0)
            self.assertEqual(metrics['baseline_top20'], 0)

    def test_input_identity_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            input_path, output_path = Path(folder) / 'input.jsonl', Path(folder) / 'output.jsonl'
            input_path.write_text(json.dumps({'case_id': 'c1', 'track': 'service',
                'status': 'ok', 'query_sha256': 'wrong', 'prediction': {'slug': 'right'}}) + '\n')
            output_path.write_text(json.dumps({'case_id': 'c1', 'track': 'service',
                'before': ['right'], 'after': ['right'], 'changed': False}) + '\n')
            frozen = {'c1': {'verified': True, 'service': {
                'expected_action': 'match', 'expected_slug': 'right'}}}
            with self.assertRaisesRegex(ValueError, 'query image SHA'):
                score.score_run('frozen-synthetic', input_path, output_path, frozen, {},
                                {'c1': 'image-sha'}, {}, 'suite-hash')

    def test_organizer_exact_image_sha_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            input_path, output_path = Path(folder) / 'input.jsonl', Path(folder) / 'output.jsonl'
            input_path.write_text(json.dumps({'case_id': 'o1', 'track': 'service',
                'status': 'ok', 'image_sha256': 'wrong',
                'prediction': {'slug': 'right'}}) + '\n')
            output_path.write_text(json.dumps({'case_id': 'o1', 'track': 'service',
                'before': ['right'], 'after': ['right'], 'changed': False}) + '\n')
            organizer = {'o1': {'status': 'exact', 'exact_slug': 'right'}}
            with self.assertRaisesRegex(ValueError, 'query image SHA'):
                score.score_run('organizer-synthetic', input_path, output_path, {}, organizer,
                                {}, {'o1': 'image-sha'}, 'suite-hash')


if __name__ == '__main__':
    unittest.main()
