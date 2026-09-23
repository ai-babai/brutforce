# LCT evaluation stand

Small Go service for frozen diagnostic wine image baskets. It serves an interactive gallery, a run matrix, participant APIs, and an optional review view. No Docker or database. The data directory is separate from this source repository.

## Build and serve

```sh
go test ./...
go build -o lct-eval ./cmd/lct-eval
./lct-eval seal -data /srv/lct/data/eval
LCT_EVAL_PARTICIPANT_TOKEN='...' LCT_EVAL_REVIEW_TOKEN='...' ./lct-eval serve -data /srv/lct/data/eval -web ./web -listen 127.0.0.1:8124
```

Keep the two tokens distinct and inject them through the service environment. Deployment uses `/etc/lct-eval.env` (root:lct 0640) for both service tokens, `/srv/lct/eval-access/participant.env` (lct:lct 0640) for authorized participant agents, and `/srv/lct/eval-access/review.token` (lct:lct 0640) for reviewers. None is in the web root or archive. Caddy routes `cv.ops.dzap.pw` to `127.0.0.1:8124`. The previous `/vision/` URL remains a compatibility alias. The browser uses relative paths. Protect this route at Caddy if team access control exists; the API additionally requires a bearer token. `GET /healthz` is public.

## Data layout

```text
data/
  images/<neutral-id>.jpg
  baskets/v1.json
  private/gold-v1.json
  catalog/slugs.json                 # optional public allowed-candidates snapshot
  runs.jsonl                         # created on first submit
```

Public suite JSON: `version`, `suite_hash`, `gold_hash`, optional `catalog_path`/`catalog_sha256`, `baskets[]`, `cases[]`. A basket has `basket_id`, `track`, `title`, `description`, `priority`, `readiness`, `target_count`. A case has `case_id`, `image_path`, `image_sha256`, `origin_kind` (`real|ai|augmentation`), `reference_derived`, optional `scene_group_id`, `basket_ids[]`, and one-element `tracks[]`. Full scene service and target crop retrieval use distinct case IDs and images. Neutral paths do not reveal the expected answer.

Private gold JSON: `version`, `suite_hash`, `cases[]`. Each gold case has `case_id`, `verified`, optional `ungraded_reason`, and a track object. Service track: `{"expected_action":"match","expected_slug":"..."}` or `{"expected_action":"no_match"}` or `{"expected_action":"insufficient_information"}`. Retrieval track: `{"expected_slug":"..."}`. An unverified case needs `ungraded_reason`; omit its answer. Provenance and reviewer evidence are private. Empty/ungraded baskets remain in the UI and receive no fabricated pass.

To build a suite, first write both JSON files with empty hashes. `seal -data DIR` fills `gold_hash` as SHA-256 of Go JSON encoding of gold with `suite_hash` empty; then fills `suite_hash` as SHA-256 of Go JSON encoding of public suite with `suite_hash` empty and `gold_hash` populated. It validates all image/catalog bytes. Do this only before the first run. Updating either file requires a new suite version.

## API

All `/api` routes require `Authorization: Bearer <participant-or-review-token>`. No token may appear in a URL. Participants can fetch:

- `GET /api/baskets`
- `GET /api/baskets/{version}/download`
- `GET /api/baskets/{version}/catalog` when present
- `GET /api/baskets/{version}/cases/{id}` and `/image`
- `POST /api/submissions`
- `GET /api/runs` and `GET /api/runs/{id}`

The archive contains only the public manifest, images, and optional allowed-candidates catalog. Participant reports show per-case correctness, prediction, score status, and aggregates, but no expected slug/action. This is a trusted regression stand: score feedback can reveal answers over repeated submissions, so the gold split prevents accidental input disclosure rather than guaranteeing a blind challenge. Review token responses add expected values to scored case details. The UI stores a typed token in browser `sessionStorage` only.

Example submission:

```json
{
  "submission_id":"my-service-001",
  "suite_version":"v1",
  "suite_hash":"<suite_hash>",
  "track":"service",
  "basket_ids":["IMG-09"],
  "solution":{"name":"my-model","version":"0.1","commit":null,"config_hash":null,"weights_version":null,"catalog_version":null},
  "submitted_by":"team-agent",
  "results":[{"case_id":"case-000046","status":"ok","prediction":{"slug":"some-slug"},"latency_ms":420}]
}
```

`status` is transport status `ok|error|timeout`; `ok` does not mean correct. Omitted selected cases become `not_run`. Product-only extensions permit an explicit service abstention using `status:"ok", prediction:{"action":"no_match"}` or `"insufficient_information"`. The official organizer contract requires a top-level slug; these actions are separate product checks. Empty slug, `error`, and `timeout` cannot pass as abstention. Retrieval uses `prediction:{"ranked_slugs":["first","second"]}`. Service reports use top-1 only; ranking metrics are not applicable there. Retrieval top-1, top-5, top-20, and MRR use the one verified target slug. Cases in overlapping baskets count once overall. Stats split by real/AI/augmentation and by catalog-reference derivation. Latency is client reported.

## Run a solution

```sh
export LCT_EVAL_PARTICIPANT_TOKEN='...'
./lct-eval run -source api -base https://cv.ops.dzap.pw -track service -endpoint http://127.0.0.1:8080/v1/eval/predict -submission-id run-001 -solution model -solution-version 0.1 -commit abc123 -config-hash cfg-v1 -weights-version w1 -catalog-version c1
./lct-eval run -source archive -archive lct-eval-v1.zip -base https://cv.ops.dzap.pw -track retrieval -endpoint http://127.0.0.1:8080/v1/eval/predict -submission-id run-002 -solution model -solution-version 0.1 -commit abc123 -config-hash cfg-v1 -weights-version w1 -catalog-version c1
```

The runner sends multipart `image` with the original image extension and accepts HTTP 200/201 with object `slug` or the first array item's `slug`, matching the organizer script. It also accepts `ranked_slugs` for retrieval diagnostics. A single `slug` counts as a one-item retrieval ranking. Connection timeout is 5 seconds; overall per image timeout is 10 seconds. It writes an optional submission JSON with `-output PATH`, then posts it. It never inserts model answers itself. Optional `-commit`, `-config-hash`, `-weights-version`, and `-catalog-version` record reproducibility metadata in the submission.

## Verification and recovery

`go test ./...` checks scoring and service behavior. Check `/healthz`, download/archive contents, a known dummy submission, idempotent resend, `GET /api/runs`, and restart persistence before exposing the service. Back up `runs.jsonl` and the entire sealed suite together. The server refuses an invalid suite/hash and corrupt history. Rollback: stop the new systemd unit and remove the Caddy route; keep data files intact.
