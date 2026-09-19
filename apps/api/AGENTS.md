# API boundary

This directory is the standalone demo HTTP server. Its contract is defined in
[README.md](README.md); keep implementation and fast behavior specs aligned
with it.

- Use only synthetic `DEMO` wine data. Private uploads are allowed only through
  the documented `UPLOAD_DIR` store; do not add catalog exports, upload GET or
  list routes, secrets, or request-body logging.
- The server is a prototype boundary only. Upload receipt persistence exists,
  but recognition, OCR, catalog lookup, authentication, and analytics remain
  deliberate stubs.
- Keep dependencies in the Go standard library unless a later approved task
  changes this boundary.
- `go test -count=1 ./...` is the required fast verification command.
