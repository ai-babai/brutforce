"""Trusted evaluator: aggregate frozen service checks by expected behavior."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gold', type=Path, required=True)
    parser.add_argument('--profile', action='append', required=True, help='NAME=SCORE_JSON')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    gold = json.loads(args.gold.read_text())
    actions = {case['case_id']: case.get('service', {}).get('expected_action')
               for case in gold['cases']}
    output = {'suite_hash': gold['suite_hash'], 'gold_sha256': hashlib.sha256(args.gold.read_bytes()).hexdigest(),
              'profiles': {}}
    for name, filename in (profile.split('=', 1) for profile in args.profile):
        score = json.loads(Path(filename).read_text())
        assert score['track'] == 'service' and score['submitted'] == 151
        assert score['graded'] == 141
        groups = {}
        for action in ('match', 'no_match', 'insufficient_information'):
            cases = [case for case in score['cases']
                     if case['graded'] and actions[case['case_id']] == action]
            groups[action] = {'correct': sum(case['correct'] for case in cases),
                              'total': len(cases),
                              'errors': sum(case['status'] != 'ok' for case in cases)}
        assert sum(group['total'] for group in groups.values()) == 141
        output['profiles'][name] = groups
    args.out.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output['profiles']))


if __name__ == '__main__':
    main()
