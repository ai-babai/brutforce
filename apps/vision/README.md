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

## Automatic A2 release

`a2_server.py` wraps the same SHA-pinned F8 without changing its source. One
CPU model serves baseline on loopback 8126 and A2 on 8127, with one shared
nonblocking inference lock. Both health and inference report their actual
model/profile; A2 appends `-a2-auto-v1`. The Docker bridge above still starts
the baseline F8; this new entrypoint is the staged Sigma release path.

A2 first runs service. Only `standalone_label_no_bottle` with `owlv2_label*`
source and finite numeric score >= 0.15 triggers retrieval on the same whole
input. Nonempty retrieval Top1 replaces service; empty/error retains service.
No gold IDs, supplied crops, new OCR or refusal thresholds participate.
The internal response adds `a2` eligibility/reroute/error booleans for acceptance;
Go ignores diagnostics. Private image bytes and labels are not logged.

See [release/rollback procedure](../../deploy/PIPELINE.md#p0--automatic-a2).
