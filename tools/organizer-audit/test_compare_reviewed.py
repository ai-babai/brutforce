import unittest
from compare_reviewed import adapt_completed_offline


class OfflineAdapterTests(unittest.TestCase):
    def row(self):
        return {'version':'legacy-offline-v1','variants_top20':{'all':[]},'predictions':{'all':{}}}

    def test_opt_in_completed_row_and_explicit_failure(self):
        row=self.row()
        out=adapt_completed_offline([row,{**row,'status':'error'},{**row,'error':'failed'}],'legacy-offline-v1')
        self.assertEqual([r['status'] for r in out],['ok','error','error'])
        self.assertNotIn('status',row)

    def test_rejects_other_version_live_or_partial_record(self):
        for row in [self.row(),{**self.row(),'result':{}},{**self.row(),'predictions':{}}]:
            version='wrong' if row==self.row() else 'legacy-offline-v1'
            with self.assertRaises(ValueError):adapt_completed_offline([row],version)


if __name__=='__main__':unittest.main()
