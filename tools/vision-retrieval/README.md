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
- V2 supplies that separately named context crop. On frozen v1 cases, all-three fusion improved from 50/141 to 64/141 passed service checks and from 25/62 to 32/62 retrieval Top-1; retrieval Top-5 improved from 44/62 to 53/62. Service checks include the required action on negative cases. This is an observed result on the same suite, not an independent holdout. Full results and corrected submission IDs are in the out-of-Git experiment artifact root.
- A nearest-neighbor visual score is not calibrated evidence for a valid catalog wine. A blank bottle or false wine detection may still receive a slug. Label-only fallback fires only when no bottle box was detected. Inspect negative and partial-bottle baskets instead of inferring robust abstention from aggregate Top-1.
- Missing OCR or short text contributes no candidates. A target with no usable branch evidence can return `insufficient_information`; a scene with no target can return `no_match`. Retrieval submissions with no ranked candidate use an error status because the frozen API requires a nonempty ranking.
- The 103 organizer files include three byte-identical copies from `eval.zip`; they represent 100 unique images. Only ten organizer originals have locally reviewed labels, and those ten overlap the frozen suite. They are not independent organizer gold. No accuracy estimate over the other 90 originals is claimed.
- The frozen public suite has 213 cases, including synthetic transformations. Its basket scores describe that suite; they do not measure broad field performance. No model is selected or tuned using those answers.

The experiment's spend is GPU rental rather than per-image model API charges; record the pod SKU, hourly rate, index build, cold load, warm per-image p50/p95/max, and total running duration with each benchmark. The initial RTX 4090 pod was quoted at $0.74/hour and the comparison RTX 4000 Ada at $0.28/hour; these are session prices, not a universal cost guarantee.

## Pretrained detector and encoder comparison (2026-09-25)

`detector_variants.py` changes only localization, leaving the v2 catalog, SigLIP2-base-patch16-224, PaddleOCR, and fixed weighted RRF unchanged. YOLOE-26s uses separately prompted bottle and label heads, with prompts encoded once at startup. YOLO26n uses its COCO `bottle` class for bottle localization and retains OWLv2 for labels. `yolo26n-geometric` removes the OWLv2 label pass and takes a fixed 6–94% width, 30–92% height label band within the selected bottle; this is a **query preprocessing** ablation, not a detector-only comparison. RT-DETR-r18 likewise uses its COCO bottle class and retains OWLv2 labels. Generic COCO bottles still pass through the original fixed SigLIP wine classifier and central-wine selection rule. `yoloe26s-strict` is an *unrun development hypothesis* about the original YOLOE prompt override and is not an evaluated result.

The frozen comparison uses all 213 public cases (141 graded service and 62 retrieval) and the 103 organizer files (100 unique SHA-256 images). `detector_run.py --phase detect` saves candidate boxes and selection reasons. `--phase full-http` saves complete loopback HTTP responses including all seven retrieval branches, prediction, OCR, and timings. `detector_export_eval.py` converts actual `all` predictions to service/retrieval submissions. Its other six branches are quality calculations from the rankings returned by the same full request; their copied all-branch latency is deliberately conservative and **not** measured branch-specific latency. `detector_contact.py` draws comparable original/box/target/label contact sheets. The output root is `/Users/skif/ml-data/brutforce/vision-retrieval-20260925/detectors/`, outside Git. The inference process receives public queries and catalog only; private evaluation answers stay outside the pod.

Model identities and licensing must be assessed separately from the comparison scores:

- YOLOE: official `yoloe-26s-seg.pt`; YOLO26n: official `yolo26n.pt`. Ultralytics code and checkpoints follow [AGPL-3.0 or Enterprise terms](https://www.ultralytics.com/license). YOLOE text prompting also downloads Apple's `mobileclip2_b.ts` model; the [MobileCLIP model license](https://github.com/apple/ml-mobileclip/blob/main/LICENSE_MODELS) is research-only/noncommercial, separately from its MIT code. These weights are experiment inputs, not approved commercial deployment assets.
- RT-DETR control: [`PekingU/rtdetr_r18vd`](https://huggingface.co/PekingU/rtdetr_r18vd) at revision `ac77a11ff0170a41b771c03264987f8ce2b0d753`, Apache-2.0 checkpoint and [Apache-2.0 source](https://github.com/lyuwenyu/RT-DETR/blob/main/LICENSE).
- Larger encoder control: [`google/siglip2-so400m-patch16-384`](https://huggingface.co/google/siglip2-so400m-patch16-384) at revision `dd658faac399427308559e2c3ac1e99cbe43845d`, Apache-2.0. It is **patch16-384**, not patch14. `so400m_ablation.py` rebuilds both visual reference matrices and encodes the original v2 query target/label crops; OWLv2 selections, OCR, and RRF remain fixed. Its quality and embedding-stage timing are offline diagnostics, not measured live end-to-end serving.

The original v2 visual index had 2080 finite source images among 2103 text slugs, but availability was not a semantic audit: 17 previously quarantined references and two newly confirmed wrong visual references remained in it. The separately versioned `index-reference-gated-v1` masks these 19 rows, leaving 2061 finite visual references and all 2103 text entries. The original index remains a fixed control for detector comparisons; gated results are named separately and never silently substituted. `gray_label_ablation.py` is a separate L→RGB grayscale label-embedding control with the same base encoder and original v2 target/OCR inputs. Its `verified_refs` output field means file SHA and availability, **not** confirmed wine identity. Color+gray RRF showed no consistent gain on this frozen suite, so it is not a serving default.

The public suite measures actions as well as retrieval. In particular, `insufficient_information` occurs only after a target is selected and **all** ranking branches are empty; with thousands of finite references a false bottle usually acquires a candidate, while a bottle rejected by the wine selector becomes `no_match`. A blank or obscured label therefore needs an explicit evidence-sufficiency design, assessed on independent data. Detector candidate coverage is not bounding-box recall or localization accuracy without reviewed boxes. The separate 100-image organizer review is the real-photo diagnostic; its gold labels must not affect candidate thresholds, prompts, or weights.

On the original v2 index, the frozen 141 graded service / 62 retrieval all-branch results were: OWLv2 64/141 and 32/62 Top-1; YOLOE-26s 76/141 and 34/62; YOLO26n+OWLv2 69/141 and 32/62; YOLO26n+geometric-label 59/141 and 35/62; RT-DETR-r18+OWLv2 77/141 and 32/62. These are *historical frozen-suite* numbers: the later catalog audit found at least one incorrect expected SKU in that suite, so the versioned erratum and corrected real-photo diagnostic must accompany any interpretation. The cleaned 19-reference gate v1 left the OWLv2 and YOLOE all-branch aggregate scores unchanged; its purpose is reference provenance. The later 20-reference gate v2 excludes another confirmed wrong visual reference and is the shared control for the encoder comparison. Keep all index versions explicit.

The same RTX 4090 pod's AMD EPYC 75F3 host ran 24 distinct organizer images on CPU with `OMP_NUM_THREADS=4` and two OCR threads. Warm full-request p95 among queries that actually executed OCR and embedding was 22.80 s for OWLv2 (23 requests), 3.45 s for YOLOE (22), 9.52 s for YOLO26n+OWLv2 (22), 2.61 s for YOLO26n+geometric label (19), and 13.19 s for RT-DETR+OWLv2 (21). These are end-to-end loopback HTTP measurements, including selection, retrieval and OCR; first request and cold model/index load are separate in each `cpu24/*.json`. The geometric branch trades the OWLv2 label pass for an unlearned fixed label band and has lower quality on the frozen service track. These 24 images do not establish a worst-case deadline guarantee.

On the paired 20-reference-gated index, newly encoded Base224 and SO400M/384 OWLv2 crops yielded historical frozen all-branch scores of 63 versus 90 service checks out of 141, and 29 versus 50 retrieval Top-1 out of 62. Both arms use the same original image bytes, target/context boxes, OCR ranking and fusion. The difference from the older Base224 result was traced at the final prediction level to four formerly selected catalog slugs that the versioned gate excludes; OCR ranks were identical. Deeper visual-rank differences outside the exclusions were adjacent, nearly tied swaps. On the sealed 54-image real-photo review available at this stage, all-branch Top-1 was 30 for Base224 and 34 for SO400M; this is not a result for all 100 organizer originals. The new encoder's `whole` branch itself was stronger than its fixed three-branch fusion on several reviewed cases, so fusion weights are not re-tuned to this review.

`encoder_detector_composition.py` makes one further *offline* paired control: it reads saved RT-DETR HTTP selections, label-context boxes and OCR ranks, then re-encodes those same original crops with Base224 and SO400M on the same gated index. It does not invoke detection or OCR again. Its `eval.jsonl` and `organizer.jsonl` contain quality predictions and embedding-stage timings only. Do not infer live request latency from those rows or promote a combination without serving and license review.

`detector_encoder_server.py` then verifies the RT-DETR+SO400M composition through actual loopback HTTP. It retains Base224 solely for the wine/nonwine gate and uses SO400M solely for whole/label retrieval. On 24 fixed organizer originals, all predictions matched the offline composition; among 21 warm requests that ran OCR and embeddings, p95 was 4.79 s (max 5.44 s). The full 103 organizer files and 213 frozen cases returned HTTP 200, with live all-branch predictions equal to the offline composition on 103/103 organizer files. The historical frozen all-branch score was 102/141 service and 50/62 retrieval Top-1, equal to the separately named offline composition; apply the versioned gold erratum before using these totals in a final report.

The separately versioned `whole_encoder_server.py` (maintained by the organizer audit team) serves the RT-DETR+SO400M **whole** branch directly and skips routine label detection, label embedding and OCR. Its `all` field is explicitly an alias of `whole`, not the three-branch fusion. On the same CPU host with four OpenMP threads, 24/24 requests succeeded; 23 warm requests had p50/p95/max 3.94/4.44/4.51 s. The 24 live predictions and image hashes matched the saved offline whole branch exactly. Its 22.27 s cold load and 4.67 s first request are separate. This small sample supports a fast CPU candidate, not a worst-case guarantee or a substitute for the full 100-image review.
