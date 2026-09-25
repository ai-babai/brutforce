# Full HTTP vision experiment, 25 September 2026

This record compares one reproduced RT-DETR-r18 + SigLIP2 SO400M/384 + OWLv2 + PaddleOCR baseline with three separately frozen, no-training changes. It uses the same 213 frozen v2 images and 103 organizer files (100 distinct image hashes). Inference received public manifests, the catalog and the pinned index; private answers stayed on the trusted scoring host. All eight complete HTTP files were preserved before their answers were scored. Runs are development diagnostics on known data, not an independent holdout.

## Changes and result

| Variant | Change after the unchanged Base224 wine gate | Frozen v2 service (141 graded) | Frozen v2 retrieval Top-1/5/20 (62 graded) | Reviewed real Top-1/5/20 (54 exact) | Gold-blind primary changes, frozen/organizer |
| --- | --- | ---: | ---: | ---: | ---: |
| Baseline | None | 114 | 57/59/62 | 42/49/51 | control |
| A, strict label/OCR rescue | On a rejected detected bottle, require OWLv2 label score ≥0.15, catalog lexical score ≥0.35, and OCR top-3/visual label top-20 slug agreement | 115 | 57/59/62 | 42/49/51 | 1/0 |
| B, generic wine-text soft gate | On a rejected bottle with wine margin ≥−0.03, require OWLv2 label score ≥0.15 and bounded generic wine-type OCR word; explicit beer, cider and spirit words veto | 114 | 57/59/62 | **44/51/53** | 0/2 |
| C, composite-box guard | Suppress a weak detector box only when it contains two separate, confident bottle boxes; keep the original wine gate and ranker | 115 | 57/59/62 | 40/47/50 | 1/8 |

A recovered one frozen service case (`case-000191`) and changed no organizer response. Its fixed lexical threshold rejected organizer-real-055/080: OWLv2 label scores were 0.23564/0.24273, but whole-crop OCR catalog lexical maxima were 0.221369/0.217483, below 0.35. Both remained `no_match`. The A trace records OCR, label, lexical top-3, and selection evidence without using the answer in inference.

B changed only organizer-real-055 and organizer-real-080, both from `no_match` to the same returned catalog wine. Its word-bounded evidence was `ПОЛУСУХОЕ` for 055 and `ВИНОДЕЛЬНЯ` for 080; no explicit non-wine veto was present. Trusted review counted both as exact Top-1 improvements, with no changed frozen prediction. **B was proposed after inspecting these two known failures**. The 44/54 result therefore shows that this generic rule fixes the observed cases and has no regression on these finite controls; it does not measure independent generalization. The one reviewed out-of-catalog negative remained incorrectly matched for every variant (0/1 correct `no_match`). Forty-two catalog-unresolved and three ambiguous unique organizer images are outside the exact denominator.

C changed eight organizer responses and lost exact Top-1 on organizer-real-010 and -017, with no exact Top-1 fixes. Within already-wrong cases, 089 moved from rank 5 to 2, while 052 moved from rank 3 to 9. Its one changed frozen response was `case-000097`, which improved the service aggregate by one. The guard was frozen before inference from known localization traces 032/052/089/094. **Do not combine or promote C** on this evidence; the full negative-control result is worse than baseline. Its five pure helper tests pass, but they verify the rule rather than retrieval quality.

## Request time and scope

All four runs completed 316/316 HTTP 200 responses with matching public image SHA-256 values. The sequential loopback diagnostic client used a **60-second timeout**, so the counts below are measured observations, not an official 10-second deadline guarantee. They exclude public-network transit. Model cold load was separate (baseline 43.34 s; C 10.23 s; B 10.10 s on the warmed pod).

| Variant | Frozen p50/p95/max, seconds | Frozen >10 s | Organizer p50/p95/max, seconds | Organizer >10 s |
| --- | --- | ---: | --- | ---: |
| Baseline | 2.037 / 4.351 / 7.052 | 0 | 2.942 / 5.740 / 6.978 | 0 |
| A | 2.067 / 4.154 / 6.790 | 0 | 2.982 / 5.670 / 7.071 | 0 |
| B | 2.026 / 4.397 / 6.900 | 0 | 3.023 / 5.627 / 7.035 | 0 |
| C | 2.026 / 3.738 / **29.069** | **1** | 2.636 / 3.872 / 6.666 | 0 |

C's outlier was `case-000111`: OWLv2 label detection took 23.083 s, OCR 5.233 s, total server time 29.065 s. The guard suppressed no box on that request and selected the identical box as baseline, whose label detection took 0.459 s and total HTTP time 6.440 s. This looks like a transient OWLv2 stage stall rather than a box-selection effect, but it is still a real 10-second miss.

After all A/B/C files were saved, a **TEST-only** tunnel connected the Go app to the running GPU B server. The unchanged three-row organizer script against public HTTPS returned three non-null slugs in 3.373, 2.203, and 4.239 s: `pino-nuar-2025`, `beloe-polusladkoe`, and `abrau-dyurso-udelnoe-vedomstvo-imperatorskoe-beloe-bryut`. This is a transport/contract smoke, **not 3/3 accuracy**; q2 selected the wrong target. The original q1 app photo uploaded with HTTP 201 and searched with HTTP 200 in 3.696 s; the response reported B's `model_version`, the Pinot Noir 2025 slug, and five real display IDs. Parent browser checks showed five cards for q1 and an outside-card explanation for q2. Evidence is at `/Users/skif/ml-data/brutforce/integration-20260925-1700/predictions-sigma-public-gpu-b-confirmed.jsonl` and adjacent `gpu-b-q1-*-confirmed.json`. The TEST app was restored to its CPU profile before the GPU tunnel and pod were removed.

## Frozen definitions and reproducibility

- Public v2 suite: manifest SHA-256 `cee45789da9e10deb6426a17338583eba2ce1688ef76a6df32f4f0e9aef22f20`, suite hash `0691d98b19d92647a41fe4fccd92a36ab23255c02ed65c37830d38a15f379daa`. The 213 image bytes and catalog are identical to v1, while v2 corrects the sealed answers.
- Catalog version: `organizer-catalog-20260919`; index version: `so400m384-owlv2-v2-crops-reference-gated-20260925`. Baseline source was the original `de1fabc` checkout. Experiment code is commit `591e8c8` in the isolated branch; A/B/C source SHA-256 are respectively `605903d9b9b6816a429b88cdff7992e7a9ebcc8fa083e23f0db58135563e9b84`, `57ddc0edab6c842b8a2688a457372951aebdddef4a0b4442454cd72644f840d8`, and `18549020a5351835c42d6c5c8c8cc648aa5bf92d52ba212c8c68ad96589dbab7`. C's shared guard SHA-256 is `f8225655cff3710babe95e3b00e19e7fe4aae665ddf587be595d0776eea3451d`.
- Raw JSONL is under `/Users/skif/ml-data/brutforce/integration-20260925-1700/model/` and mirrored on Sigma under `/srv/lct/data/vision-retrieval/20260925-1700/model/`. The two filenames for each prefix are `<prefix>-eval.jsonl` and `<prefix>-organizer.jsonl`.

| Prefix | Frozen raw SHA-256 | Organizer raw SHA-256 |
| --- | --- | --- |
| `baseline` | `9715fa58c94a33dd2e09a5487a6b833a15f0ebe2ecba6682394afddce0651d9e` | `fbb931d7b544adea0192954534556d71b0521a926d9ed98af5f596d21d03bf82` |
| `fallback-A` | `10bd749afcbbe3dbc5da567201e1af88434f1fc1606b979dab0034ac1bd20c29` | `168851c663da6bc1f754f0ce9eb01a9689b42a53f4d6049021b29de10a6513a9` |
| `softgate-B` | `5727583ec98e8f4ebe9a1e872af11bee978cab797fa277813760d239a3ef9ed5` | `4eee696622521088536bcfc6c8ea1b85dd2d8a82dc7f79d70be1602477fa5f64` |
| `composite-C` | `2aa57b6b41bca6be889fda0a5f7522a330bcecf7547ceb6c0aff85ce40dd13df` | `dd399105df1cb16d411ec4c6970fef9d0e607e755644204406503eaf53bc95e5` |

V2 submission IDs use `gpu-baseline-v2-*`, `gpu-fallback-a-v2-*`, `gpu-softgate-b-v2-*`, and `gpu-composite-c-v2-*` with `service` and `retrieval` tracks and suffix `-20260925-1700`. Original HTTP files, gold-blind comparisons, preregistered B/C rules, detailed 055/080 traces, and private reviewer analyses remain outside Git. Private gold and scorer credentials were never on the inference pod. A separate, independent real-photo holdout and repeated bounded full-pipeline latency checks are still needed before B can be considered validated for deployment.
