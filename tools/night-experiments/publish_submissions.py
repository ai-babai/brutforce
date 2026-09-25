"""Run on Sigma: publish an explicit manifest of already-reviewed submissions.

Reads the existing participant token without printing or exporting it.
"""
import argparse,json,shlex,urllib.request
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
    token=None
    for line in Path('/srv/lct/eval-access/participant.env').read_text().splitlines():
        line=line.removeprefix('export ')
        if line.startswith('LCT_EVAL_PARTICIPANT_TOKEN='):token=shlex.split(line.split('=',1)[1])[0]
    if not token:raise ValueError('Participant token missing')
    outputs=[]
    paths=json.loads(a.manifest.read_text())
    prepared=[(Path(path).read_bytes(),json.loads(Path(path).read_bytes())) for path in paths]
    assert len(paths)==len(set(paths))==len({s['submission_id'] for raw,s in prepared}), 'Duplicate submission ID or path'
    for raw,sub in prepared:
        assert sub['suite_version']=='v2' and sub['track'] in ('service','retrieval')
        assert len(sub['results'])=={'service':151,'retrieval':62}[sub['track']]
    for raw,sub in prepared:
        request=urllib.request.Request('http://127.0.0.1:8124/api/submissions',data=raw,headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        with urllib.request.urlopen(request,timeout=30) as response:result=json.load(response)
        outputs.append({'submission_id':sub['submission_id'],'response':result})
        a.receipt.write_text(json.dumps(outputs,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'submission_id':sub['submission_id'],'run_id':result.get('run_id'),'overall':result.get('overall')}),flush=True)

if __name__=='__main__':main()
