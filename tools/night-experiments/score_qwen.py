"""Trusted-host scoring after complete blind Qwen inference. Never ship to GPU."""
import argparse, subprocess, sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--labels',type=Path,required=True);p.add_argument('--overlay',type=Path,required=True);a=p.parse_args()
    code=Path(__file__).resolve().parents[1]/'night-cpu';out=a.root/'qwen/exported'
    for mode in ('top20','top5','fusion','confident'):
        for track in ('service','retrieval'):
            subprocess.run([sys.executable,str(code/'score_frozen.py'),'--gold',str(a.root/'cpu/.scorer/gold-v2.json'),'--manifest',str(a.root/'cpu/public-v2.json'),'--submission',str(out/(mode+'-'+track+'.json')),'--out',str(out/(mode+'-'+track+'-score.json'))],check=True)
        subprocess.run([sys.executable,str(code/'score_organizer.py'),'--manifest',str(a.root/'cpu/organizer-public.json'),'--predictions',str(out/(mode+'-organizer.jsonl')),'--labels',str(a.labels),'--overlay',str(a.overlay),'--profile','qwen-'+mode,'--out',str(out/(mode+'-organizer-score.json'))],check=True)

if __name__=='__main__':main()
