"""Convert only the sealed public basket manifest to the visual runner shape."""
import argparse,json,hashlib
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--suite-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 a=p.parse_args()
 suite=json.loads((a.suite_root/'baskets/v1.json').read_text())
 cases=[]
 for c in suite['cases']:
  if len(c['tracks'])!=1:raise ValueError('expected one track per case')
  cases.append({'case_id':c['case_id'],'track':c['tracks'][0],
                'path':c['image_path'],'sha256':c['image_sha256']})
 payload={'version':suite['version'],'suite_hash':suite['suite_hash'],
          'source_public_manifest_sha256':hashlib.sha256((a.suite_root/'baskets/v1.json').read_bytes()).hexdigest(),
          'cases':cases}
 a.out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'cases':len(cases),'suite_hash':suite['suite_hash']}))
if __name__=='__main__':main()
