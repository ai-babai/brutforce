#!/usr/bin/env python3
"""Build a numbered contact sheet for rendered Telegram PDF first pages."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tmp/pdfs/rvk/first_pages"
OUTPUT = ROOT / "tmp/pdfs/rvk/first-pages-contact-sheet.png"


def main() -> int:
    paths = sorted(SOURCE.glob("*.png"))
    columns = 5
    cell_w, cell_h, label_h = 300, 390, 28
    rows = (len(paths) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * cell_w, rows * (cell_h + label_h)), "white")
    draw = ImageDraw.Draw(canvas)
    for index, path in enumerate(paths):
        with Image.open(path) as image:
            page = ImageOps.contain(image.convert("RGB"), (cell_w - 10, cell_h - 10))
        x = (index % columns) * cell_w + (cell_w - page.width) // 2
        y = (index // columns) * (cell_h + label_h) + 5
        canvas.paste(page, (x, y))
        draw.text(((index % columns) * cell_w + 8, y + cell_h), path.stem, fill="black")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUTPUT, optimize=True)
    print(f"PASS: {len(paths)} pages -> {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
