import unittest
import numpy as np
from reference_gate import apply_gate

class GateTests(unittest.TestCase):
    def data(self):
        return ({'references':[{'slug':'bad','sha256':'a'},{'slug':'good','sha256':'b'}]},
                ['bad','good'], {'full':np.ones((2,3)),'label':np.ones((2,3))},
                {'excluded':[{'slug':'bad','sha256':'a','reason':'wrong product','evidence':'review42'}]})
    def test_only_named_image_disabled_old_index_unchanged(self):
        c,s,a,d=self.data();out,log=apply_gate(c,s,a,d)
        self.assertTrue(np.isnan(out['full'][0]).all());self.assertTrue(np.isfinite(out['full'][1]).all())
        self.assertTrue(np.isfinite(a['full']).all());self.assertEqual(len(log),1)
    def test_new_reference_requires_new_review(self):
        c,s,a,d=self.data();c['references'][0]['sha256']='new'
        with self.assertRaises(ValueError):apply_gate(c,s,a,d)
    def test_index_reordering_rejected(self):
        c,s,a,d=self.data()
        with self.assertRaises(ValueError):apply_gate(c,s[::-1],a,d)
    def test_unsupported_exclusion_rejected(self):
        c,s,a,d=self.data();d['excluded'][0]['evidence']=''
        with self.assertRaises(ValueError):apply_gate(c,s,a,d)

if __name__=='__main__':unittest.main()
