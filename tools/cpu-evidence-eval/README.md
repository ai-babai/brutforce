# ML-083: trusted paired scorer

Run `score.py` **only on the trusted Mac**, after both raw HTTP runs have been
sealed. It takes `--frozen-manifest`, `--organizer-manifest`, `--frozen-gold`,
`--organizer-labels`, `--organizer-overlay`, `--baseline-frozen`,
`--baseline-organizer`, `--candidate-frozen`, `--candidate-organizer`,
`--timing-control historical|paired|contaminated`, and `--out` (a new file outside Git).
All arguments are required. The output is a mode-0600 private JSON containing
each changed output and its reviewed outcome; stdout contains aggregates only.
Never send labels, the output JSON, or the scorer to an inference node.

Source data are the SHA-sealed public manifests and HTTP rows under
`/Users/skif/ml-data/brutforce/night-20260925/cpu/`. Existing public manifest
hashes: frozen `cee45789da9e10deb6426a17338583eba2ce1688ef76a6df32f4f0e9aef22f20`,
organizer `396a66f0ac4d70c88598259aab76ce39087462777d571246b9774a53dccf4b3d`.
The trusted frozen gold is in `cpu/.scorer/gold-v2.json`; corrected organizer
labels and the one-OOD overlay are in `vision-retrieval-20260925/annotation/sealed-v1.jsonl`
and `vision-retrieval-20260925/absence-audit/parent-accepted-overlay-v1.json`.
Keep all images, raw results, gold, and detailed flips outside Git/web-root.

For the timing gate, supply fresh ORT6 rows and the candidate rows from
the same Sigma host, review CPU/memory quotas and contention in the runtime
receipt, and match request order and 10 s deadline; set `--timing-control paired`
only after that review. The scorer cannot verify resource comparability from
HTTP rows alone. The historical ORT6 rows are appropriate
for a SHA/quality self-check, but `--timing-control historical` never proves the
time gate. Set `--timing-control contaminated` when a runner was paused or
competed with app-smoke: preserve all original rows and measure quality, but
`gate_proven` remains false even if raw p95 is below the numeric threshold.
The scorer checks all 213 frozen and 103 organizer request IDs and
input SHA values, HTTP status/deadlines, 141 graded service + 62 retrieval, 54
reviewed exact unique images, negative actions and one reviewed OOD. Three
duplicate organizer requests count once at unique-image level. The organizer
labels are reused development diagnostics, not an independent holdout.
