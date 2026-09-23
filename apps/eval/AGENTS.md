# LCT evaluation service

Start with README.md and the hosted `/guide.html`.
`internal/eval/model.go` defines the JSON contract and scoring.
`cmd/lct-eval/main.go` serves the API and static UI; `client.go` runs solutions.

Use immutable suite versions. Seal public manifests, images, catalog slug snapshots,
and private gold with `lct-eval seal -data DIR` before any run.
A later change to the suite or gold needs a new version.
Keep target mappings, answers, evidence, prompts, and source paths out of public data.
Keep `runs.jsonl` append-only, private gold outside the web root, and tokens out of logs.

API and archive runners submit through `POST /api/submissions`.
Service scores full-frame top-1 action/slug; retrieval scores ranked verified crops.
Missing predictions stay in graded denominators; ungraded cases stay visible.
`error`, `timeout`, and `not_run` are not valid abstentions.

The user's turnkey test-stand request authorizes permanent tests in this module.
Run `go test ./...` and the README smoke flow before deployment.
