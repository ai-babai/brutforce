# LCT evaluation service

Start with README.md and the hosted `/guide.html`.
Data/reference policy: source `../../docs/agent-guide/DATA-RULES.md`; Sigma `/srv/lct/guide/docs/agent-guide/DATA-RULES.md`.
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

## Generated-image pilot and baselines

For per-slug pilot images use `/data/` and `../../tools/vision-pilot/README.md`.
Read `../../tools/vision-baselines/README.md` before reproducing baseline runs.
Pilot data lives in `/srv/lct/data/vision`, separate from frozen evaluation data.
Requested conditions are not observed labels; keep AI origin, QC and lineage visible.
Runtime copies: `/srv/lct/data/vision/README.md` and `/srv/lct/data/vision-baselines/20260924/README.md`.

Organizer requirements: `../../docs/project/REQUIREMENTS.md`, hosted `/requirements.html`.
Public mirror `web/gallery/requirements-data.json` must match `docs/project/requirements.json`.

New runs use `-suite-version v2`; keep v1 for historical replay. UI selects v2 by default.
Never compare or combine runs across suite_version/suite_hash without an explicit rescore.
For an untrusted inference host, use `run -no-submit -output FILE`: no gold or scoring token there.
Submit the resulting predictions from the trusted host with `scripts/suite_io.py score`.
