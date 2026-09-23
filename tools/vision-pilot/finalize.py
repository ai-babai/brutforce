#!/usr/bin/env python3
"""Validate the pilot and merge independent QA. No network calls or frozen-suite writes."""
import argparse, collections, fcntl, hashlib, json, os, re
from pathlib import Path
from generate import rows,safe_root

def validate(root, data, forbidden, expected=None):
    index={r['image_id']:r for r in data}
    if len(index)!=len(data): raise ValueError('duplicate image_id')
    for r in data:
        for field in ('path','thumbnail_path'):
            value=r.get(field)
            if value is None and field=='thumbnail_path' and r.get('role') in ('identity_reference','scene_reference'): continue
            if not isinstance(value,str) or not value: raise ValueError('missing '+field+' '+r['image_id'])
            p=(root/value).resolve()
            if not p.is_relative_to(root.resolve()) or not p.is_file(): raise ValueError('missing/unsafe '+field)
        if hashlib.sha256((root/r['path']).read_bytes()).hexdigest()!=r['sha256']: raise ValueError('hash mismatch '+r['image_id'])
        if r.get('origin') not in ('real','augmentation','ai_edited','ai_generated'): raise ValueError('unknown origin')
        for parent in r.get('parent_ids',[]):
            if parent not in index: raise ValueError('missing parent '+parent)
        if r.get('role')=='output':
            for field,role in (('identity_reference_id','identity_reference'),('scene_reference_id','scene_reference')):
                ref=r.get(field)
                if ref not in index or index[ref].get('role')!=role or ref not in r.get('parent_ids',[]):
                    raise ValueError('missing/wrong output reference '+field+' '+r['image_id'])
        if r.get('role')=='augmentation':
            parents=r.get('parent_ids',[])
            if len(parents)!=1 or index[parents[0]].get('role')!='output':
                raise ValueError('augmentation needs one output parent '+r['image_id'])
        if r.get('split') in ('train','train_candidate'):
            queue=[r];seen=set()
            while queue:
                x=queue.pop()
                if x['image_id'] in seen: continue
                seen.add(x['image_id'])
                # Identity/catalog refs may be shared. Evaluation scene pixels may not.
                if x.get('role')!='identity_reference':
                    hashes=(x['sha256'],(x.get('source') or {}).get('source_sha256'))
                    if any(h in forbidden for h in hashes if h):raise ValueError('evaluation scene leakage')
                queue.extend(index[p] for p in x.get('parent_ids',[]))
    count=sum(r.get('role')=='output' for r in data)
    if expected is not None and count!=expected: raise ValueError(f'expected {expected} outputs, found {count}')
    return index

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--eval-provenance',type=Path,required=True);ap.add_argument('--expected-outputs',type=int,default=100)
    a=ap.parse_args();root=safe_root(a.root);manifest=root/'manifest.jsonl'
    # Refuse to finalize while generation is mutating the corpus.
    with (root/'runs/generation-run.lock').open('a') as runlock:
        fcntl.flock(runlock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data=rows(manifest);forbidden=set(re.findall(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])',a.eval_provenance.read_text()))
        index=validate(root,data,forbidden,a.expected_outputs)
        qa={q['output_image_id']:q for q in rows(root/'qc-deepseek.jsonl') if q.get('status')=='completed' and q.get('qa_version','').endswith('v2')}
        manual={}
        for name in ('visual-audit-coordinator.jsonl','visual-audit-sol.jsonl','visual-audit-extension-sol.jsonl'):
            for r in rows(root/name): manual[r['image_id']]=r
        summary={'outputs':0,'augmentations':0,'references':0,'by_model':{},'generation_cost_usd':0,'qa_coverage':0,'visual_review_coverage':0}
        for r in data:
            if r['role']!='output':
                summary['augmentations' if r['role']=='augmentation' else 'references']+=1;continue
            summary['outputs']+=1;q=qa.get(r['image_id']);v=manual.get(r['image_id']);reason=[];status='pending'
            if q and q['output_sha256']!=r['sha256']: raise ValueError('stale QA')
            j=q.get('judgement',{}) if q else {}
            if q:summary['qa_coverage']+=1
            if v:summary['visual_review_coverage']+=1
            if j.get('identity_correct')=='no' or (v and v.get('identity')=='no'):
                status='rejected';reason.append('Identity changed or target absent')
            elif j.get('realistic')=='no' or (v and v.get('realistic')=='no'):
                status='rejected';reason.append('Unrealistic physical scene')
            elif (q and v and j.get('suggested_qc')=='accepted'
                  and j.get('identity_correct')=='yes' and j.get('realistic')=='yes'
                  and j.get('scenario_fulfilled')=='yes' and not j.get('label_changed')
                  and v.get('identity')=='yes' and v.get('realistic')=='yes'
                  and v.get('scenario_fulfilled')=='yes'):
                status='accepted';reason.append('Passed two-agent pilot visual screen; not exhaustive fine-text verification')
            else:reason.append('Conditions, physical plausibility or identity require review; do not auto-export to training')
            if v and v.get('concern'):reason.append(v['concern'])
            if j.get('reason'):reason.append(j['reason'])
            r['observed_conditions']=j.get('observed_conditions',{})
            r['qc']={'status':status,'reason':' | '.join(reason),'ai_judgement':j,'visual_review':v or {},'fine_text_verified':False,'scope':'pilot screening; no training approval implied'}
            stats=summary['by_model'].setdefault(r['model'],{'outputs':0,'cost_usd':0,'qc':{},'stage1':{'outputs':0,'qc':{}}})
            stats['outputs']+=1;stats['cost_usd']+=r.get('cost_usd',0);summary['generation_cost_usd']+=r.get('cost_usd',0)
            stats['qc'][status]=stats['qc'].get(status,0)+1
            if int(r['image_id'].split('-')[1])<=20:
                stats['stage1']['outputs']+=1;stats['stage1']['qc'][status]=stats['stage1']['qc'].get(status,0)+1
        for r in data:
            if r['role']=='augmentation':
                parent=index[r['parent_ids'][0]]
                r['qc']={'status':'pending' if parent['qc']['status']!='rejected' else 'rejected','reason':'Deterministic transform verified by parameters/hash; inherits parent QC '+parent['qc']['status']+'. No independent training acceptance.'}
        if summary['qa_coverage']!=summary['outputs'] or summary['visual_review_coverage']!=summary['outputs']: raise ValueError('QA incomplete')
        with manifest.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            temp=manifest.with_suffix('.next');temp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data));os.replace(temp,manifest)
        (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        (root/'accepted-pilot.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data if r['role']=='output' and r['qc']['status']=='accepted'))
        print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
