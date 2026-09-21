#!/usr/bin/env python3
"""Create deterministic maskable Icon 24 renditions from the approved source.

Only the connected burgundy background is replaced while padding the image.  The
cream disc and all disconnected illustration pixels, including burgundy bottle
details, remain source pixels.  ``--check`` verifies that checked-in outputs
are byte-for-byte reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "apps/web/public/assets/icon-24.png"
GEOMETRY = ROOT / "apps/web/public/assets/icon24-meta/geometry.json"
OUTPUTS = {
    192: ROOT / "apps/web/public/assets/icon-24-maskable-v2-192.png",
    512: ROOT / "apps/web/public/assets/icon-24-maskable-v2-512.png",
}
BURGUNDY = (124, 28, 52)


def edge_feather(size: int) -> Image.Image:
    """Fade only the source's outer burgundy border; artwork remains untouched."""
    alpha = Image.new("L", (size, size))
    pixels = alpha.load()
    center = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            distance = max(abs(x - center), abs(y - center)) / size
            if distance <= 0.47:
                pixels[x, y] = 255
            else:
                pixels[x, y] = round(255 * max(0, (0.5 - distance) / 0.03))
    return alpha


def render(size: int, geometry: dict[str, object]) -> bytes:
    source = Image.open(SOURCE).convert("RGB")
    source_size = round(size * float(geometry["scale"]))
    art = source.resize((source_size, source_size), Image.Resampling.LANCZOS)
    alpha = edge_feather(source_size)
    canvas = Image.new("RGB", (size, size), BURGUNDY)
    offset_x = (size - source_size) // 2 + round(size * float(geometry["offsetX"]))
    offset_y = (size - source_size) // 2 + round(size * float(geometry["offsetY"]))
    canvas.paste(art, (offset_x, offset_y), alpha)
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if checked-in files differ from generated output")
    args = parser.parse_args()
    if Image.open(SOURCE).size != (1254, 1254):
        raise ValueError(f"expected a 1254x1254 source icon: {SOURCE}")
    geometry = json.loads(GEOMETRY.read_text())
    if geometry.get("sourceSize") != 1254:
        raise ValueError(f"expected sourceSize 1254: {GEOMETRY}")
    for size, path in OUTPUTS.items():
        generated = render(size, geometry)
        if args.check:
            if not path.is_file() or path.read_bytes() != generated:
                print(f"out of date: {path.relative_to(ROOT)}", file=sys.stderr)
                return 1
        else:
            path.write_bytes(generated)
            print(f"wrote {path.relative_to(ROOT)} sha256={hashlib.sha256(generated).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
