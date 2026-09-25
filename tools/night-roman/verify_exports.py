"""Independent check of six full-basket Roman submissions against paired rows."""
import argparse
import hashlib
import json
from pathlib import Path


def read_rows(path):
    return [json.loads(line) for line in path.open(encoding='utf-8')]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    a = p.parse_args()
    pairs = read_rows(a.root/'paired-predictions.jsonl')
    if len(pairs) != len({r['case_id'] for r in pairs}) or len(pairs) != 316:
        raise ValueError('Paired rows incomplete or duplicated')
    by_id = {r['case_id']: r for r in pairs}
    ids = []
    files = {}
    for mode in ('base5','roman5','roman20'):
        for track, expected_count in (('service',151),('retrieval',62)):
            path = a.root/f'{mode}-{track}.json'
            document = json.loads(path.read_text())
            ids.append(document['submission_id'])
            outputs = document['results']
            if len(outputs) != expected_count or len({r['case_id'] for r in outputs}) != expected_count:
                raise ValueError('Submission rows incomplete or duplicated '+path.name)
            for result in outputs:
                pair = by_id[result['case_id']]
                if pair['basket'] != 'frozen' or pair['track'] != track:
                    raise ValueError('Wrong case/track '+result['case_id'])
                if result['latency_ms'] != round(pair[mode]['judge_elapsed_ms']):
                    raise ValueError('Latency mismatch '+result['case_id'])
                rank = pair[mode]['ranked_slugs']
                prediction = result['prediction']
                if track == 'retrieval' and prediction.get('ranked_slugs') != rank:
                    raise ValueError('Retrieval rank mismatch '+result['case_id'])
                if track == 'service':
                    if rank and prediction.get('slug') != rank[0]:
                        raise ValueError('Service slug mismatch '+result['case_id'])
                    if not rank and prediction.get('action') != (pair['b_action'] or 'no_match'):
                        raise ValueError('Service no-candidate mismatch '+result['case_id'])
            weights = document['solution']['weights_version']
            if ('without LoRA' in weights) != (mode == 'base5'):
                raise ValueError('Weights metadata mismatch '+mode)
            files[path.name] = sha(path)
        org_path = a.root/f'{mode}-organizer.jsonl'
        org = read_rows(org_path)
        if len(org) != len({r['case_id'] for r in org}) or len(org) != 103:
            raise ValueError('Organizer rows incomplete '+mode)
        if {r['case_id'] for r in org} != {r['case_id'] for r in pairs if r['basket']=='organizer'}:
            raise ValueError('Organizer case set mismatch '+mode)
        files[org_path.name] = sha(org_path)
    if len(ids) != len(set(ids)) or len(ids) != 6:
        raise ValueError('Submission IDs not unique')
    report = dict(valid=True,paired_rows=316,submission_ids=ids,sha256=files)
    (a.root/'export-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(valid=True,paired_rows=316,unique_submission_ids=len(ids))))


if __name__ == '__main__':
    main()
