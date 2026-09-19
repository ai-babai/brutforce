# API boundary

This directory is the standalone demo HTTP server. Its contract is defined in
[README.md](README.md); keep implementation and fast behavior specs aligned
with it.

- Use only synthetic `DEMO` wine data. Private uploads are allowed only through
  the documented `UPLOAD_DIR` store. The embedded read-only catalog and its
  `GET /api/catalog` route follow
  [`contracts/demo-catalog.md`](../../contracts/demo-catalog.md); do not add
  real catalog exports, upload GET/list routes, secrets, or request-body
  logging.
- The server is a prototype boundary only. Upload receipt persistence exists,
  and the embedded synthetic catalog is readable, but recognition, OCR, real
  catalog lookup, authentication, and analytics remain deliberate stubs.
- Keep dependencies in the Go standard library unless a later approved task
  changes this boundary.
- `go test -count=1 ./...` is the required fast verification command.

- Preserve [Security Specs](../../docs/product/security-spec.md). Never call DecodeAll or process stored originals without resource bounds. A successful upload is not a malware-clean verdict.
