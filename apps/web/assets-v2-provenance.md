# Visual assets for Wine UX 2.0

Source edition: `29874e7`, `design/wine-ux-v2/selected-edition.md` in
`/Users/skif/develop/brutforce-camera-viewport`.

The application keeps browser-ready WebP versions of the selected 1536×1024
mascot art. They were encoded locally with `cwebp -q 90`; no artwork was
changed. The original source SHA-256 values are retained below for review.

| App asset | Selected source | Source SHA-256 |
| --- | --- | --- |
| `mascot-hold-2d.webp` | `mascot-hold-2d.png` | `ee9a9af5ffc556a6c3529f5745a020a01550ff6233f9781d0868278b196d2893` |
| `mascot-walk-2d.webp` | `mascot-walk-2d.png` | `772228d6cd81ee4a78d7a2908e9e1757eb098974b931fa551548f02c81f72fb4` |
| `mascot-counter-2d.webp` | `mascot-counter-2d.png` | `4161f6ea197e10c6beb5d072632f535e83a3ec14fc57f84fd2c8ab5a6e1de0ab` |
| `mascot-cellar-2d.webp` | `mascot-cellar-2d.png` | `98708b961e9042c501cc889f4f71035accf990501a0bd5e586c6282f9e82d9e1` |
| `mascot-offline-2d.webp` | `mascot-offline-2d.png` | `385a86dc9238e4f3d7fe732c2172bba3b05b0acd349248e39c4a3688c56a5038` |

`svoe-vino-logo.svg` and `PlayfairDisplay-VariableFont_wght.woff2` are copied
unchanged from the same selected asset directory.

## No-match refinement — issue #24

Design source `b7609f7`, `mascot-counter-thoughtful-2d.png`, SHA256 `31534d9bda26343f70dd09c4b313187cde9bf5649d092d062c040d14742b6ed0`. Runtime `mascot-counter-thoughtful-2d.webp`, converted with cwebp -q90 without visual edits. Replaces the smiling counter scene at runtime; previous asset remains in Git.
