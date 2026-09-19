# API boundary

This directory is the standalone demo HTTP server. Its contract is defined in
[README.md](README.md); keep implementation and fast behavior specs aligned
with it.

- Use only synthetic `DEMO` wine data. Do not add catalog exports, user photos,
  secrets, or request-body logging.
- The server is a prototype boundary only. Recognition, OCR, catalog lookup,
  persistence, authentication, and analytics are deliberately stubs.
- Keep dependencies in the Go standard library unless a later approved task
  changes this boundary.
- `go test -count=1 ./...` is the required fast verification command.
