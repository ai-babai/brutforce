# API documentation assets

`openapi.json` is the OpenAPI 3.1 description served at `/api/openapi.json`.
It describes the four implemented synthetic demo endpoints only.

`demo-search.schema.json` is an embedded runtime copy of canonical
`contracts/demo-search.schema.json`. Edit the contract source, copy it here,
and run `go test -count=1 ./...` from `apps/api`; API-018 prevents a stale copy.
