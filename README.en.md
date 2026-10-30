# BrutForce — Russian wine-label scanner

[Live application](https://app.dzap.pw/) · [Русский README](README.md)

BrutForce was built by Maxim Popkov and Roman Karandashov for the RSHB wine-label
recognition challenge at Digital Transformation Leaders 2026.
It returns an organizer catalog slug or an existing display-catalog card.

## Current production

Verified on 2026-10-31: **Boost V16 C16**, using the fine-tuned SigLIP2 SO400M
`batch32-4744-pass2` checkpoint, RT-DETR, frozen visual galleries and bounded
OCR evidence verification. It runs on CPU with Torch 2 / ONNX Runtime 6 threads.
Initialization and inference share the main model thread; admission is bounded.

The production Python source is committed byte-for-byte in
[`apps/vision/c16`](apps/vision/c16/README.md) and [`apps/vision/boost`](apps/vision/boost/).
The production Go upload-timeout fix and scanner-indicator CSS are included.
The rebuilt frontend JavaScript matched the live file byte-for-byte.

[`deploy/production.json`](deploy/production.json) pins 97 source files,
43 external assets, the checkpoint, runtime versions and observed production
bindings. The detailed [production guide](docs/PRODUCTION.ru.md) is authoritative.
The old public release.json and release-controller receipts are stale.

## Verify and run

```sh
git clone https://github.com/ai-babai/brutforce.git
cd brutforce
python3 scripts/production-vision.py
```

This checks source files only: no model downloads and no service startup.
For actual recognition obtain the exact external C16 data set from its owner;
all relative paths and hashes are in `production.json`. Keep it outside Git.
The old publicly linked F8 data set does not reproduce C16.

With Linux, Python 3.12 and the pinned
[`production-requirements.txt`](deploy/assets/production-requirements.txt):

```sh
python3.12 scripts/production-vision.py --data-root /absolute/c16-data
python3.12 scripts/production-vision.py --data-root /absolute/c16-data \
  --runtime /absolute/new-private-runtime --serve
```

The unchanged C16 entrypoint listens on loopback port 8137. Only machine-specific
bindings are relocated. Sigma activation receipts are not copied to a new host.
Full application use additionally requires the display catalog, media, PostgreSQL,
private upload storage and locally provisioned credentials.

For the synthetic UI demo without recognition:

```sh
docker compose -f deploy/compose.demo.yaml up --build -d --wait
```

The old Docker/Mac bootstrap and full Compose profile are **legacy F8**, not
current production. Clean-host C16 inference parity has not been tested here.

## API

```sh
curl --fail-with-body --max-time 10 \
  -F 'image=@/path/to/photo.jpg' https://app.dzap.pw/v1/eval/predict
```

A successful match returns `{"slug":"catalog-slug"}`. An explicit abstention
has an `action` without a slug; technical errors use non-200 status codes.
In-app search instead uploads `photo` to `/v1/photos` and passes its `photoId`
to `/v1/search`. Catalog search uses `/v2/catalog?q=...`.
See [vision](contracts/vision-serving.md) and [upload](contracts/photo-upload.md) contracts.

Organizer recognition and display catalogs have different coverage. A missing
display card remains unavailable rather than being replaced with another wine.
Recommendations use a separate pinned index.

Weights, catalog data, private evaluations, uploads and secrets are not in Git.
Public repository access does not grant redistribution rights to third-party
models or catalog photographs. A separate code reuse license is not established.
No production service was changed during this synchronization, and no new model
quality or clean-host reproduction claim is made.
