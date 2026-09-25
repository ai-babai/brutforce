# Night DISK + LightGlue experiment

Gold-blind rerank of the **unchanged B Top20**. No training or lookup of expected
answers in inference. Full frozen v2 and organizer predictions are scored only
after `run` has written immutable JSONL output on the trusted host.

The official [cvg/LightGlue](https://github.com/cvg/LightGlue) repository is pinned
to `eb42fee2d71449efb0aa5c10549752b5d75384d8`. It supplies pretrained
DISK `depth` features and `disk_lightglue` matcher. The repository documents
Apache-2.0 for both DISK and LightGlue code and weights. Record downloaded
checkpoint hashes before running.

```text
image + B's selected target/label-context box
    -> DISK(depth, 1024 points) query features
B's fixed Top20 -> SHA-checked reference features -> LightGlue(disk)
    -> homography inliers + query coverage -> local geometry rerank
    -> fixed fusion of B rank and geometry rank -> slug
```

All reference paths must match the frozen catalog SHA. Missing references never
get a replacement image. The query crop uses B's `selection.selected_box` and
`label_context_box`, including B's verified retrieval input; no new detector is
run. `run` checks input SHA, outputs one row per input, and preserves B's action
for requests without a candidate pool.

Usage on a CUDA host with PyTorch, Kornia, OpenCV, Pillow, and the pinned
LightGlue checkout installed:

```sh
python tools/night-lightglue/run.py index \
  --catalog STAGE/catalog-bundle.json --reference-root STAGE \
  --availability STAGE/gatev2-availability.json \
  --lightglue-repo LIGHTGLUE_CHECKOUT --cache OUT/reference-features
python tools/night-lightglue/run.py run \
  --baseline B-eval.jsonl --manifest eval-public.json \
  --query-root INPUT-STAGE --catalog STAGE/catalog-bundle.json \
  --cache OUT/reference-features --lightglue-repo LIGHTGLUE_CHECKOUT \
  --out OUT/frozen-raw.jsonl
```

Repeat `run` with organizer manifest/B rows. Preserve all raw files and `meta.json`.
The fixed fused score is 50% normalized B rank plus 50% normalized geometry
rank, with zero geometry contribution when no valid geometric evidence exists.
Pure local rerank places valid geometry ahead of remaining B candidates and
uses B rank to break ties. A candidate needs at least eight RANSAC homography
inliers and 2% query-area coverage. These rules were fixed before inspecting
private answers. Pair timing excludes B's prior retrieval and includes query
DISK extraction and twenty LightGlue matches; full online latency must add a
fresh B HTTP timing from the same hardware, not historical loopback times.

After the first full frozen result showed broad regressions, `cascade.py` was
added as a **same-suite development diagnostic**. It preserves B unless a
candidate already in B ranks 2–5 has at least 50 inliers, 10% query coverage,
twice B's geometry score, and a reference SHA unique across all gate-valid
catalog entries. The absolute thresholds express a conservative requirement
for broad physical correspondence; they were not fitted by case ID. Its score
does not establish independent generalization.
