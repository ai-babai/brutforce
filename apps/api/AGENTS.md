# API boundary

This directory is the standalone demo HTTP server. Its contract is defined in
[README.md](README.md); keep implementation and fast behavior specs aligned
with it.

- BE-045 authorizes a validated real display-catalog adapter/importer and tests, not live import/deployment.
  Full exports stay outside Git; see `../../contracts/catalog-display.md`.
- Default fixtures remain synthetic `DEMO` wine data. Private uploads are allowed only through
  the documented `UPLOAD_DIR` store. The synthetic PostgreSQL catalog (embedded only when DATABASE_URL is unset) and its
  `GET /v2/catalog` route follow
  [`contracts/demo-catalog.md`](../../contracts/demo-catalog.md); do not commit
  real catalog exports, upload GET/list routes, secrets, or request-body
  logging.
- The server is a prototype boundary only. Upload receipt persistence exists,
  and imported display catalogs are readable. Recognition, OCR, authentication,
  and analytics remain deliberate stubs.
- Keep dependencies in the Go standard library except the approved
  `golang.org/x/image/webp` decoder used only by the contest adapter and the
  authorized PostgreSQL catalog dependencies `github.com/jackc/pgx/v5` and
  `github.com/pressly/goose/v3`. It lets
  `POST /v1/eval/predict` identify actual WebP bytes regardless of filename;
  the demo upload allowlist remains JPEG/PNG/GIF.
- `go test -count=1 ./...` is the required fast verification command.

- Preserve [Security Specs](../../docs/product/security-spec.md). Never call DecodeAll or process stored originals without resource bounds. A
  successful upload is not a malware-clean verdict.
