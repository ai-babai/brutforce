# Wine image pilot · 2026-09-24

Start here for generation, corpus structure and continuation. For frozen test baskets
and submission use `../../apps/eval/AGENTS.md`; for recognition use
`../vision-baselines/README.md`. This guide applies to every agent, including Roman's.

## Where to look

- Gallery: https://cv.ops.dzap.pw/data/ (same participant access as the evaluation stand).
- Results matrix: https://cv.ops.dzap.pw/ ; hosted onboarding: `/guide.html`.
- Pilot on Sigma: `/srv/lct/data/vision`; local working copy:
  `/Users/skif/ml-data/brutforce/vision-pilot-20260924`.
- Baseline raw predictions, costs and submissions: `/srv/lct/data/vision-baselines/20260924`.
- Frozen suite: `/srv/lct/data/eval`. **Never add pilot outputs to v1 or modify its gold.**
- Code: private BrutForce repo, `tools/vision-pilot`, `tools/vision-baselines`, `apps/eval`.

The gallery lists wines first, loads thumbnails after selecting a wine and originals
only when opening a card. Filters select model, origin, scenario, QC and role.
A card shows identity reference, scene reference, result, requested conditions,
observed conditions and QC. Scene refs can have no target slug; this is intentional.

## Files and meaning

`manifest.jsonl` has one immutable image identity per row. `path` and
`thumbnail_path` are relative to this directory. `sha256` verifies image bytes.
`slug` comes from the catalog association, not a guess made by the generator.
`parent_ids`, `identity_reference_id` and `scene_reference_id` preserve lineage.
`origin` distinguishes real images, AI edits and deterministic augmentations.
`jobs.jsonl` holds exact prompts and requested conditions. The two stages are:
20 paired jobs across three models, then 40 different jobs with the chosen model.
These 40 must not be used as an equal-size head-to-head comparison.

`requested_conditions` are intentions; `observed_conditions` are the judge's
observations and can be uncertain. Exact physical camera angles are not asserted.
A Pillow rotation is a known image-plane transformation, not a measured 3D pose.

QC `accepted` means a two-agent pilot visual screen passed; it does **not** certify
all fine print, licensing or suitability for automatic model training. `pending`
means unconfirmed conditions/identity/physical plausibility; `rejected` means a
known identity or physical-scene failure. `accepted-pilot.jsonl` excludes pending
and rejected results. Augmentations inherit parent defects and remain separately
marked. All images remain `split: pilot`; no model was trained in this experiment.

Independent checks: `qc-deepseek.jsonl` (latest v2 per image hash),
`visual-audit-coordinator.jsonl`, `visual-audit-sol.jsonl`,
`visual-audit-extension-sol.jsonl`. `summary.json` records counts and generator cost.
Raw API usage and redacted prompts live in `runs/`; no token or base64 input is logged.
`qa-ledger.jsonl` accounts for the separate judge calls.

## Read/use the corpus

For trusted SSH agents, read JSONL directly and verify the hash before use.
Do not redistribute secrets alongside data. For remote agents, use the authenticated
API (get the token from the operator or existing server participant file):

```sh
BASE=https://cv.ops.dzap.pw
curl -H "Authorization: Bearer $LCT_EVAL_PARTICIPANT_TOKEN" "$BASE/api/data/slugs"
curl -H "Authorization: Bearer $LCT_EVAL_PARTICIPANT_TOKEN" \
  "$BASE/api/data/images?slug=zb-vajn-roze-suhoe-rozovoe"
# An image record supplies authenticated detail, thumbnail and original URLs.
```

The evaluation API/archives are separate: frozen test images are returned without
answers. Run your solution, submit **its actual predictions** via
`POST /api/submissions`, and inspect `/api/runs/<submission_id>`. The hosted guide
contains Bash and PowerShell examples. Private gold must never enter the recognizer.

## Reproduce or continue (requires an explicit new budget)

Use Python 3.9+ with Pillow. Scripts currently contain documented local defaults;
set their paths for a new machine. API key location is a secret reference in
`generate.py`/`qa.py`; never copy its value into source. Generation is two-reference
editing through OpenRouter: Qwen Image 3, Gemini 3.1 Flash Image, FLUX.2 Pro.
Model/provider snapshots are stored with the experiment; future prices may differ.

```sh
# Read-only task/cost preview. Do not accidentally generate all 3 models for extension jobs.
python generate.py --root "$CORPUS" --models qwen --dry-run
# Only after the operator authorizes another paid batch:
python generate.py --root "$CORPUS" --models qwen --job-ids '<explicit IDs>' --workers 2 --budget 10
# Failed calls remain reserved; --retry-errors is deliberate, not automatic.
python qa.py --help
python augment.py --root "$CORPUS"
python finalize.py --root "$CORPUS" --expected-outputs 100 --eval-provenance "$PRIVATE_PROVENANCE"
```

Do not rerun source preparation on a live corpus: refs were visually corrected and
some sideways scene refs were rotated before this run. Preserve the saved manifest,
job prompts and originals for exact reproduction. New experiments get a separate root.
The generator takes an exclusive run lock, reserves concurrent cost before sending,
skips hash-verified completed images, and writes the manifest atomically. Failed or
interrupted calls retain conservative cost reserves; report those separately from
confirmed `usage.cost`. An HTTP timeout does not prove the provider did not bill.

`finalize.py` validates files, hashes, links and training-scene leakage, merges QA,
and refuses to finalize while the generator runs. It is not an automated judge:
visual audit files must describe actual inspected images, never invented approvals.

## Publish safely

Sync referenced image files first; replace server `manifest.jsonl` atomically last.
Do not use destructive `--delete` against data roots. The Go service reloads the
manifest by modification time. Gallery code/static deploy follows `apps/eval/README.md`.
Leave frozen suite hashes and append-only run history intact. Keep previous runtime
release for rollback; rollback code only, never delete the new corpus or submissions.
