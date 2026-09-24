"""Render reproducible source/selection/label diagnostics from HTTP traces."""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from detector_run import cases_from_manifest, image_path


def fit(image, size):
    result = Image.new('RGB', size, '#eef0f2')
    image = image.copy()
    image.thumbnail((size[0]-8, size[1]-8), Image.Resampling.LANCZOS)
    result.paste(image, ((size[0]-image.width)//2, (size[1]-image.height)//2))
    return result


def overlay(image, selection):
    result = image.copy()
    draw = ImageDraw.Draw(result)
    width = max(2, round(max(image.size)/400))
    for item in selection['boxes']:
        draw.rectangle(item['box'], outline='#36c9df', width=width)
    if selection['selected_box'] is not None:
        draw.rectangle(selection['selected_box'], outline='#ff4242', width=width*2)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--image-root', type=Path, required=True)
    parser.add_argument('--results-root', type=Path, required=True)
    parser.add_argument('--set-name', choices=('eval', 'organizer'), required=True)
    parser.add_argument('--case-id', action='append', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    _, cases = cases_from_manifest(args.manifest)
    by_case = {x['case_id']: x for x in cases}
    variants = ('yoloe26s', 'yolo26n', 'yolo26n-geometric')
    result_rows = {}
    for variant in variants:
        path = args.results_root/variant/('full-'+args.set_name+'.jsonl')
        result_rows[variant] = {x['case_id']: x for x in
                                (json.loads(line) for line in path.read_text().splitlines())}
    tile = (180, 180)
    pad = 12
    label_h = 24
    count = len(args.case_id)
    sheet = Image.new('RGB', (10*(tile[0]+pad)+pad, (count+1)*(tile[1]+label_h+pad)+pad), '#ffffff')
    draw = ImageDraw.Draw(sheet)
    headings = ['source']
    for variant in variants:
        headings += [variant+' boxes', variant+' target', variant+' label']
    for col, name in enumerate(headings):
        draw.text((pad+col*(tile[0]+pad), pad), name, fill='#202020')
    for row_idx, cid in enumerate(args.case_id, 1):
        case = by_case[cid]
        source = ImageOps.exif_transpose(Image.open(image_path(args.image_root, case))).convert('RGB')
        y = pad+row_idx*(tile[1]+label_h+pad)
        cells = [source]
        for variant in variants:
            result = result_rows[variant][cid]['result']
            selection = result['selection']
            cells.append(overlay(source, selection))
            box = selection['selected_box']
            if box is None:
                blank = Image.new('RGB', tile, '#dadde0')
                cells.extend([blank, blank])
            else:
                target = source.crop(box)
                label_box = result['label_context_box']
                label = target.crop(label_box) if label_box is not None else target
                cells.extend([target, label])
        for col, cell in enumerate(cells):
            x = pad+col*(tile[0]+pad)
            sheet.paste(fit(cell, tile), (x, y))
            caption = cid if col == 0 else ''
            if col in (1, 4, 7):
                variant = variants[(col-1)//3]
                result = result_rows[variant][cid]['result']
                caption = result['selection']['selection_reason'][:27]
            draw.text((x, y+tile[1]+2), caption, fill='#202020')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.out, 'PNG')
    print(json.dumps({'file': str(args.out), 'cases': args.case_id,
                      'variants': variants, 'size': list(sheet.size)}))


if __name__ == '__main__':
    main()
