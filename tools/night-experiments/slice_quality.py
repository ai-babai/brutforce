"""Aggregate trusted scores by origin and basket, without publishing answers."""
import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    manifest = load(root / 'common/suite-v2/baskets/v2.json')
    cases = {case['case_id']: case for case in manifest['cases']}
    profiles = {
        'B': 'lightglue/private-score-B-{track}.json',
        'CPU-SO640': 'cpu/scores/so-owl640-{track}.json',
        'Qwen20': 'qwen/exported/top20-{track}-score.json',
        'Roman20': 'roman/scores/final/roman20-{track}.json',
        'Qwen-reader-fused': 'reader/private-score-reader_fused-{track}.json',
        'LightGlue-cascade': 'lightglue/private-score-cascade-{track}.json',
        'Homoglyph': 'text-homoglyph/{track}-score.json',
    }
    report = {}
    for name, pattern in profiles.items():
        tracks = {}
        for track in ('service', 'retrieval'):
            score = load(root / pattern.format(track=track))
            assert score['track'] == track
            graded = [r for r in score['cases'] if r['graded']]
            grouped = {}
            for origin in ('real', 'augmentation', 'ai'):
                rows = [r for r in graded if cases[r['case_id']]['origin_kind'] == origin]
                grouped[origin] = {
                    'graded': len(rows),
                    'correct': sum(bool(r['correct']) for r in rows),
                    'scene_groups': len({cases[r['case_id']]['scene_group_id'] for r in rows}),
                }
            assert sum(r['graded'] for r in grouped.values()) == score['graded']
            grouped['baskets'] = []
            for basket in manifest['baskets']:
                if basket['track'] != track:
                    continue
                rows = [r for r in graded if basket['basket_id'] in cases[r['case_id']]['basket_ids']]
                grouped['baskets'].append({
                    'basket_id': basket['basket_id'], 'title': basket['title'],
                    'graded': len(rows), 'correct': sum(bool(r['correct']) for r in rows),
                })
            tracks[track] = grouped
        report[name] = tracks
    out = root / 'common/quality-slices.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    for name, tracks in report.items():
        print(name, {t: {o: [v['correct'], v['graded']] for o,v in d.items() if o != 'baskets'} for t,d in tracks.items()})


if __name__ == '__main__':
    main()
