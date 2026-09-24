# Public, downloadable wine vision baseline

This experiment composes pretrained, self-hosted models. It does **not** train or fine-tune on organizer or frozen evaluation labels. The catalog index is computed from public organizer reference images; the query runner reads public images and metadata only. Scoring happens outside the pipeline.

## Components

| Stage | Implementation | Role |
| --- | --- | --- |
| Bottle and label localization | [OWLv2 base patch16 ensemble](https://huggingface.co/google/owlv2-base-patch16-ensemble), pinned in `model.py` | Open-vocabulary detection. Wine target selection considers candidate bottle boxes and scene center. Label detector can fall back to a declared geometric crop. |
| Whole bottle and label visual search | [SigLIP2 base patch16 224](https://huggingface.co/google/siglip2-base-patch16-224), pinned in `model.py` | **One shared encoder**, run on separate whole-bottle and label crops. Exact cosine search of the 2,103 catalog slots; 2,080 have verified reference images and 23 remain missing. |
| Text | [PaddleOCR PP-OCRv5 mobile](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html) detection with East Slavic mobile recognition | OCR of the selected target, followed by catalog-wide lexical character-gram search. OCR contributes its own candidates, not merely a rerank of visual hits. |
| Fusion | `ranking.py`, `fuse.py` | Fixed rank fusion weights whole 0.25, label 0.35, OCR 0.40, renormalized over present branches. Seven preset ablations: each branch, each pair, and all three. No fitted fusion. |

The selected target is the central wine candidate among detections, including partial bottles. Retrieval-track images are already cropped and skip scene localization. The detector can return a label-only region when **no** bottle is detected; it does not recover every central non-wine or label-only scene. This is an observed limitation, not a verified capability.

## Reproduction

Install `requirements.txt` into an isolated GPU environment, plus `requirements-ocr.txt` for PaddleOCR. The recorded runs used Python in `/workspace/lct-v2/venv` on an RTX 4090 and `HF_HOME=/workspace/lct-v2/hf`. Model revisions are constants in `model.py`. Input manifests have only public paths, SHA-256 values, and tracks; keep gold and private mappings outside the runner.

```sh
cd tools/vision-retrieval
python index.py --catalog "$CATALOG_JSON" --image-dir "$CATALOG_IMAGES" --out "$INDEX_DIR" --device cuda
python vision_queries.py --queries "$PUBLIC_QUERIES_JSON" --query-dir "$QUERY_IMAGES" --index-dir "$INDEX_DIR" --out "$RUN_DIR" --device cuda
OMP_NUM_THREADS=1 python ocr.py --visual "$RUN_DIR/visual.jsonl" --out "$RUN_DIR/ocr.jsonl" --device cpu --threads 2
python fuse.py --catalog "$CATALOG_JSON" --visual "$RUN_DIR/visual.jsonl" --ocr "$RUN_DIR/ocr.jsonl" --out "$RUN_DIR/fused.jsonl"
python summarize.py --fused "$RUN_DIR/fused.jsonl" --out "$RUN_DIR/summary.json"
python export_eval.py --suite "$PUBLIC_SUITE/baskets/v1.json" --fused "$RUN_DIR/fused.jsonl" --variant all --track service --submission-id vision-v1-all-service --out "$RUN_DIR/submissions/all-service.json"
```

To convert the frozen public basket into a query manifest, run `python eval_public_manifest.py --suite-root "$PUBLIC_SUITE" --out "$PUBLIC_QUERIES_JSON"`. For the recorded organizer run, `$CATALOG_JSON` was `/workspace/lct-v2/data/catalog/catalog-bundle.json`, `$CATALOG_IMAGES` its containing directory, and `$RUN_DIR` was `/workspace/lct-v2/results/organizer-v1`. The frozen run used `/workspace/lct-v2/results/eval-v1`. Generated indexes, crops, predictions, submission files, and reports live outside Git under `/Users/skif/ml-data/brutforce/vision-retrieval-20260924` after export. The public frozen suite itself is immutable and is never an output directory.

`vision_queries.py` caches only when `(image SHA-256, track, preprocessing version)` agrees; equal image bytes in different tracks are processed separately. OCR resume and fusion verify the selected target crop SHA before reuse. Index reuse checks catalog, slug order, and encoder revision. Missing catalog reference embeddings stay unavailable rather than being filled with another wine.

### Label context v2

The frozen v1 OWLv2 label box often covered only a line of text. `label_context_v2.py` is a one-change ablation: union that box with a fixed central/lower region (6–94% of target width, 30–92% of target height), then encode the resulting crop with the **same** SigLIP2 weights. It reuses v1 bottle selection, OWLv2 boxes, whole-catalog features, target images, OCR, lexical search and fusion. It rebuilds only catalog label vectors and query label vectors. It does not learn the crop from answers.

```sh
python label_context_v2.py --phase index --catalog "$CATALOG_JSON" \
  --image-dir "$CATALOG_IMAGES" --v1-index "$INDEX_V1" \
  --out "$INDEX_V2" --device cuda
python label_context_v2.py --phase queries --queries "$PUBLIC_QUERIES_JSON" \
  --query-dir "$QUERY_IMAGES" --v1-index "$INDEX_V1" --index-dir "$INDEX_V2" \
  --v1-visual "$RUN_V1/visual.jsonl" --out "$RUN_V2" --device cuda
python fuse.py --catalog "$CATALOG_JSON" --visual "$RUN_V2/visual.jsonl" \
  --ocr "$RUN_V1/ocr.jsonl" --out "$RUN_V2/fused.jsonl"
python export_eval.py --suite "$PUBLIC_SUITE/baskets/v1.json" --fused "$RUN_V2/fused.jsonl" \
  --variant all --track service --label-context-v2 --index-dir "$INDEX_V2" \
  --submission-id vision-v2-context-all-service --out "$RUN_V2/submissions/all-service.json"
```

The v2 evaluation uses the same 213 frozen cases and the same v1 OCR rows, with crop SHA checks before fusion. Only the four affected variants (`label`, `whole_label`, `label_ocr`, `all`) need new submissions; v1 `whole`, `ocr`, and `whole_ocr` remain controls. V2 submission `solution.version` and `config_hash` include the context script and v2 index. An initial set of v2 submissions carried v1 metadata in error; corrected runs with `-metadata-r1` IDs supersede those records. The correction manifest preserves both sets of IDs and confirms equal scores.

## Live endpoint and timing

```sh
HF_HOME=/workspace/lct-v2/hf HF_HUB_OFFLINE=1 OMP_NUM_THREADS=1 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
  python server.py --catalog "$CATALOG_JSON" --index-dir "$INDEX_DIR" \
  --host 127.0.0.1 --port 8080 --device cuda --ocr-threads 2
curl -sS http://127.0.0.1:8080/healthz
curl -sS -H 'Content-Type: image/jpeg' --data-binary @sample.jpg \
  'http://127.0.0.1:8080/v1/eval/predict?track=service'
```

To serve v2, replace `$INDEX_DIR` with `$INDEX_V2` and add `--label-context`. The server checks index crop mode at startup. Its default serves v1 when given the v1 index.

The endpoint loads weights and the index once. `/healthz` reports cold load time and actual device. Each prediction reports decoding, localization, embedding, OCR, rank/fusion, and total server time. Loopback HTTP benchmarks include request parsing, decode and inference, but exclude public-network transit. Frozen seven-branch timings are **modeled sums of cached stages**, not seven measured live endpoint implementations; judge branch quality separately from live end-to-end speed. The server and offline OCR both JPEG-92-roundtrip their selected crop before PaddleOCR.

On 24 distinct organizer originals, the RTX 4090 v1 server completed 24/24 HTTP requests; its 23 warm requests had p50/p95/max of 3.19/3.98/4.05 seconds. V2 completed 24/24 with warm p50/p95/max of 3.06/4.02/4.18 seconds. Both were below ten seconds on this sample; neither establishes a hard timeout guarantee for all inputs. V1 and v2 cold model/index load took 6.80 and 6.91 seconds, respectively, outside warm request times. `runtime-versions.json` in the experiment artifact root records Python 3.12.3, PyTorch 2.8.0+cu128, Transformers 4.57.6, NumPy 2.1.2, PaddlePaddle 3.3.0, PaddleOCR 3.7.0 and other measured packages. `serving-v1-final-source/` preserves the byte-identical source of the v1 HTTP benchmark; v2 source snapshots accompany its result directory.

## Limits and interpretation

- An OWLv2 label box can be just a narrow text strip, excluding the producer art or full label. This damaged label retrieval in examined organizer crops. The frozen v1 label index and queries deliberately retain that behavior; any context-crop fix needs a separately named version.
- V2 supplies that separately named context crop. On frozen v1 cases, all-three fusion improved from 50/141 to 64/141 service Top-1 and from 25/62 to 32/62 retrieval Top-1; retrieval Top-5 improved from 44/62 to 53/62. This is an observed result on the same suite, not an independent holdout. Full results and corrected submission IDs are in the out-of-Git experiment artifact root.
- A nearest-neighbor visual score is not calibrated evidence for a valid catalog wine. A blank bottle or false wine detection may still receive a slug. Label-only fallback fires only when no bottle box was detected. Inspect negative and partial-bottle baskets instead of inferring robust abstention from aggregate Top-1.
- Missing OCR or short text contributes no candidates. A target with no usable branch evidence can return `insufficient_information`; a scene with no target can return `no_match`. Retrieval submissions with no ranked candidate use an error status because the frozen API requires a nonempty ranking.
- The 103 organizer files include three byte-identical copies from `eval.zip`; they represent 100 unique images. Only ten organizer originals have locally reviewed labels, and those ten overlap the frozen suite. They are not independent organizer gold. No accuracy estimate over the other 90 originals is claimed.
- The frozen public suite has 213 cases, including synthetic transformations. Its basket scores describe that suite; they do not measure broad field performance. No model is selected or tuned using those answers.

The experiment's spend is GPU rental rather than per-image model API charges; record the pod SKU, hourly rate, index build, cold load, warm per-image p50/p95/max, and total running duration with each benchmark. The initial RTX 4090 pod was quoted at $0.74/hour and the comparison RTX 4000 Ada at $0.28/hour; these are session prices, not a universal cost guarantee.
