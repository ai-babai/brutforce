# API boundary

This directory is the standalone demo HTTP server. Its contract is defined in
[README.md](README.md); keep implementation and fast behavior specs aligned
with it.

- INFRA-047 authorizes the validated real display-catalog importer for Maks and TEST after mandatory gates.
  PROD still requires separate approval; follow `../../deploy/PIPELINE.md`. Full exports stay outside Git;
  see `../../contracts/catalog-display.md`.
- Default fixtures remain synthetic `DEMO` wine data. Private uploads are allowed only through
  the documented `UPLOAD_DIR` store. The synthetic PostgreSQL catalog (embedded only when DATABASE_URL is unset) and its
  `GET /v2/catalog` route follow
  [`contracts/demo-catalog.md`](../../contracts/demo-catalog.md); do not commit
  real catalog exports, upload GET/list routes, secrets, or request-body
  logging.
- The server is a prototype boundary with imported display catalogs. When
  `VISION_SERVICE_URL` is configured, the shared ranked vision response feeds
  contest prediction and real photo search; see `../../contracts/vision-serving.md`.
  Authentication and analytics remain outside this boundary.
- Keep dependencies in the Go standard library except the approved
  `golang.org/x/image/webp` decoder used by the contest and private upload boundaries and the
  authorized PostgreSQL catalog dependencies `github.com/jackc/pgx/v5` and
  `github.com/pressly/goose/v3`. It lets
  `POST /v1/eval/predict` identify actual WebP/BMP/TIFF bytes regardless of filename;
  the private upload allowlist is JPEG/PNG/GIF/WebP/BMP/TIFF, checked by decoded bytes.
- `go test -count=1 ./...` is the required fast verification command.

- Preserve [Security Specs](../../docs/product/security-spec.md). Never call DecodeAll or process stored originals without resource bounds. A
  successful upload is not a malware-clean verdict.
