# Visual assets for Wine UX 2.0

Source edition: `29874e7`, `design/wine-ux-v2/selected-edition.md` in
`/Users/skif/develop/brutforce-camera-viewport`.

The application keeps browser-ready WebP versions of the selected 1536×1024
mascot art. They were encoded locally with `cwebp -q 90`; no artwork was
changed. The original source SHA-256 values are retained below for review.

| App asset | Selected source | Source SHA-256 |
| --- | --- | --- |
| `mascot-hold-2d-alpha.webp` | `mascot-hold-2d-alpha.png` | `f0ea361d856964e5eef82d9f4ed6eb4bd41ec2581b91b60aa441d991af03a239` |
| `mascot-walk-2d-alpha.webp` | `mascot-walk-2d-alpha.png` | `d2cce77ce38a00007ccecc03775ffea90fa0390139183428981b5cd153fc5ade` |
| `mascot-counter-thoughtful-2d-alpha.webp` | `mascot-counter-thoughtful-2d-alpha.png` | `14004b7b307e90150972e7673b500ff712e79a7fa8fe40385ea39ac7f0148b6b` |
| `mascot-cellar-2d-alpha.webp` | `mascot-cellar-2d-alpha.png` | `282d379e3a1374b2ba9b01a23d24a62438e9690ab79221bc0d1b012d88eeaa4a` |
| `mascot-offline-2d-alpha.webp` | `mascot-offline-2d-alpha.png` | `0a49f347ef75704b1de1586671f0661cd8d5b8586ebdc12b4c71a0ba7776c305` |

`svoe-vino-logo.svg` and `PlayfairDisplay-VariableFont_wght.woff2` are copied
unchanged from the same selected asset directory.

## No-match refinement — issue #24

Design source `b7609f7`, `mascot-counter-thoughtful-2d.png`, SHA256 `31534d9bda26343f70dd09c4b313187cde9bf5649d092d062c040d14742b6ed0`. Its alpha successor is the runtime `mascot-counter-thoughtful-2d-alpha.webp`; previous assets remain in Git.

## Transparent home art — issue #24

Source design `4c0c601`, `mascot-hold-2d-alpha.png`, SHA256 `f0ea361d856964e5eef82d9f4ed6eb4bd41ec2581b91b60aa441d991af03a239`. Runtime `mascot-hold-2d-alpha.webp`, encoded with `cwebp -q 90 -alpha_q 100`; webpmux confirms transparency,1536×1024. No creative edits during conversion. Old opaque asset retained.

## Transparent secondary art — issue #24

Source design `4a3615f`. The walk, thoughtful-counter, cellar and offline runtime assets listed above were encoded with `cwebp -q 90 -alpha_q 100`; `webpmux` confirms transparency at 1536×1024 for each. No creative edits during conversion. The prior opaque WebP assets remain in Git.

## App icon 24

Approved source: `7a4c9e3:design/app-icon-study/assets/icon-24.png`, SHA-256
`cb8fb933f6842f7c17133159acc89894e41ed3681ab4c30331fa7614933b33a6`.
`public/assets/icon-24.png` is an unchanged copy. The versioned `any`, Apple,
and favicon PNGs are dimension-only renditions. Maskable renditions center a
56% copy of the source on a burgundy background, leaving the art inside the
conservative 40%-radius safe circle; no artwork was redrawn or cropped.

## App icon 24 maskable v2

`public/assets/icon-24-maskable-v2-192.png` and
`public/assets/icon-24-maskable-v2-512.png` are reproducible derivatives of
the same 1254×1254 approved source. `scripts/generate-app-icons.py` reads the
shared semantic geometry from `public/assets/icon24-meta/geometry.json`: 83%
Pillow LANCZOS scaling, then 1.8% left and 3.1% down. It applies an edge-only
feather over the outer 3% of the source square onto RGB burgundy
`(124, 28, 52)`. The illustration inside the source is preserved; no creative
redraw occurred. The generator requires Pillow; run
`python3 scripts/generate-app-icons.py --check` to verify committed byte
output.
