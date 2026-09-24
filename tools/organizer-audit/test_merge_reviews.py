import unittest
from merge_reviews import build

class ReviewMergeTests(unittest.TestCase):
    def data(self):
        return ({'cases':[{'case_id':'a','sha256':'x'},{'case_id':'b','sha256':'y'},{'case_id':'alias','sha256':'x','duplicate_of':'a'}]},
                {'cases':[{'image_sha256':'x'}]}, {'references':[{'slug':'wine'}]},
                [{'image_id':i,'sha256':sha,'status':'exact','exact_slug':'wine','acceptable_slugs':['wine'],'scene_group':'same-wine','evidence_text':'visible identity compared with reference','review':{'reviewer':'reviewer','method':'original + catalog'}} for i,sha in [('a','x'),('b','y')]])
    def test_duplicates_do_not_inflate_coverage_and_old_split_is_rebuilt(self):
        rows,summary=build(*self.data())
        self.assertEqual(summary['unique_images'],2);self.assertEqual(summary['duplicate_files'],1)
        self.assertEqual(summary['exact_scene_groups'],1)
        self.assertEqual(rows[0]['review']['prior_seen_group'],'familiar12')
        self.assertEqual(rows[1]['review']['prior_seen_group'],'newly_reviewed88')
    def test_missing_review_is_not_silently_skipped(self):
        q,s,c,r=self.data()
        with self.assertRaises(ValueError):build(q,s,c,r[:1])
    def test_slug_outside_catalog_rejected(self):
        q,s,c,r=self.data();r[0]['exact_slug']='invented'
        with self.assertRaises(ValueError):build(q,s,c,r)
    def test_wrong_image_rejected(self):
        q,s,c,r=self.data();r[0]['sha256']='wrong'
        with self.assertRaises(ValueError):build(q,s,c,r)

if __name__=='__main__':unittest.main()
