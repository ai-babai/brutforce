# F8 CPU recognition service

This is the Python code used by the local full Docker profile. The pinned F8
overlay and its F0 parent modules are kept byte-for-byte from the verified
CPU runtime snapshot so the overlay's parent SHA checks still hold. `overlay/spec/lexicon.json`
is the fixed OCR policy read by the overlay. The existing historical F0 source
layout is retained to make the verified imports and provenance inspectable.

`deploy/Dockerfile.vision` copies this directory to `/app/vision` and
`scripts/docker-vision-bridge.py` runs `overlay/night_server.py` there. The
service accepts `--catalog /assets/catalog/catalog-bundle.json` and
`--index-dir /assets/index`; `/assets` contains *data*, not Python code.
The outer bridge exposes the internal loopback service to Go on `vision:8127`.

Inputs: validated multipart image bytes from the Go API, read-only weights,
processor, reference vectors, organizer catalog and OCR language data under
`/assets`. Output: ranked organizer slugs or an explicit no-match/error response
per [vision-serving.md](../../contracts/vision-serving.md). Imported display
cards, display WebP media and the text recommendation JSON belong to other
services and are not training or lookup inputs for this module.

For offline visual-index rebuilding use `scripts/build-visual-index.py` with
`--code-root apps/vision` and independently obtained original organizer
reference photos and SO400M PyTorch weights. The ready-made index works
without the original reference photos. See [the transfer guide](../../docs/ASSET-TRANSFER.ru.md).
