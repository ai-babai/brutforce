"""Create one immutable 768px JPEG view for both CPU and GPU readers."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, nargs='+', required=True)
    parser.add_argument('--crop-roots', type=Path, nargs='+', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if len(args.inputs) != len(args.crop_roots) or args.out.exists():
        raise ValueError('inputs/roots mismatch or output already exists')
    args.out.mkdir()
    (args.out / 'crops').mkdir()
    output = []
    for path, root in zip(args.inputs, args.crop_roots):
        for line in path.read_text().splitlines():
            if not line:
                continue
            row = json.loads(line)
            item = row.copy()
            item['origin_target_png_sha256'] = row['crop_sha256']
            item['reader_view_transform'] = 'RGB LANCZOS longest_edge<=768 JPEG quality=90 subsampling=0'
            if row['crop']:
                source = root / row['crop']
                if sha(source) != row['crop_sha256']:
                    raise ValueError('source target crop SHA mismatch: ' + row['case_id'])
                with Image.open(source) as original:
                    image = original.convert('RGB')
                scale = min(1, 768 / max(image.size))
                if scale < 1:
                    image = image.resize(tuple(max(1, round(n * scale)) for n in image.size), Image.Resampling.LANCZOS)
                item['crop'] = 'crops/' + row['case_id'] + '.jpg'
                image.save(args.out / item['crop'], format='JPEG', quality=90, subsampling=0)
                item['crop_sha256'] = sha(args.out / item['crop'])
                item['reader_view_size'] = list(image.size)
            output.append(item)
    if len(output) != len({r['case_id'] for r in output}):
        raise ValueError('duplicate case ID')
    target = args.out / 'inputs.jsonl'
    target.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in output))
    receipt = {'rows': len(output), 'crops': sum(bool(r['crop']) for r in output),
               'reader_view_input_sha256': sha(target), 'source_sha256': sha(Path(__file__)),
               'origin_inputs_sha256': [sha(path) for path in args.inputs],
               'total_reader_view_bytes': sum((args.out / r['crop']).stat().st_size for r in output if r['crop'])}
    (args.out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
