"""Small offline checks for abstention and available-branch fusion."""
import unittest,hashlib,tempfile
from pathlib import Path
import numpy as np
from ranking import Lexical, top
from fuse import rank_fuse,ocr_top,assert_target_hash
from vision_queries import cache_key

CATALOG=[{'slug':'w-a','title':'Рислинг','producer':'Фанагория'},
         {'slug':'w-b','title':'Мерло','producer':'Шато Пино'}]
class RankingTest(unittest.TestCase):
    def test_empty_or_short_ocr_does_not_invent_catalog_candidate(self):
        lexical=Lexical(CATALOG)
        for text in ('','a','12'):
            self.assertEqual([],ocr_top(lexical,text,['w-a','w-b']))
    def test_missing_branches_and_valid_ocr(self):
        self.assertEqual([],rank_fuse({'whole':[],'label':[],'ocr':[]}))
        self.assertEqual('w-b',rank_fuse({'whole':[],'ocr':[{'slug':'w-b','score':.9}]})[0]['slug'])
        scores=Lexical(CATALOG).scores('Шато Пино Мерло')
        self.assertEqual('w-b',top(scores,['w-a','w-b'])[0]['slug'])
    def test_identical_bytes_across_tracks_need_distinct_target_selection(self):
        self.assertNotEqual(cache_key('same-sha','service'),cache_key('same-sha','retrieval'))
    def test_stale_ocr_crop_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'target.jpg';path.write_bytes(b'first')
            visual={'case_id':'x','target_path':str(path)}
            old={'target_sha256':hashlib.sha256(b'first').hexdigest()}
            assert_target_hash(visual,old)
            path.write_bytes(b'second')
            with self.assertRaisesRegex(ValueError,'OCR target hash'):
                assert_target_hash(visual,old)
if __name__=='__main__':unittest.main()
