import unittest
from score_reviewed import score

class ScoringTests(unittest.TestCase):
    def label(self,id='x',status='exact'):
        return {'image_id':id,'sha256':id*64,'status':status,'exact_slug':'wine' if status=='exact' else None,'review':{'prior_seen_group':'newly_reviewed88'}}
    def prediction(self,**kw):
        return dict({'case_id':'x','image_sha256':'x'*64,'status':'ok','prediction':{'slug':'wine'},'ranked':[{'slug':'wine'}],'total_latency_ms':11000},**kw)
    def test_missing_predictions_are_failures_not_dropped(self):
        result,_=score([self.label(),self.label('y')],[self.prediction()])
        self.assertEqual(result['all']['exact_denominator'],2);self.assertEqual(result['all']['top1'],1)
        self.assertEqual(result['all']['exact_response_under_10s'],0)
    def test_ambiguous_not_forced_into_accuracy(self):
        result,_=score([self.label(status='ambiguous')],[self.prediction()])
        self.assertEqual(result['all']['exact_denominator'],0);self.assertEqual(result['all']['images'],1)
    def test_hash_mismatch_fails(self):
        with self.assertRaises(ValueError):score([self.label()],[self.prediction(image_sha256='bad')])
    def test_error_cannot_get_credit_from_stale_ranking(self):
        result,_=score([self.label()],[self.prediction(status='error')])
        self.assertEqual(result['all']['top1'],0)
    def test_rank_and_returned_response_separate(self):
        result,_=score([self.label()],[self.prediction(prediction={'action':'no_match'})])
        self.assertEqual(result['all']['top1'],1);self.assertEqual(result['all']['exact_response'],0)
    def test_composition_cached_time_not_live(self):
        row={'case_id':'x','query_sha256':'x'*64,'status':'ok','predictions':{'all':{'slug':'wine'}},'variants_top20':{'all':[{'slug':'wine'}]},'variant_cached_stage_sum_ms':{'all':15}}
        result,_=score([self.label()],[row],'all')
        self.assertEqual(result['all']['top1'],1);self.assertIsNone(result['all']['exact_response_under_10s'])

if __name__=='__main__':unittest.main()
