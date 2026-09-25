# Target-only Qwen3-VL reader

Separate, no-training N2 ablation after the negative LightGlue experiment.
Inference sees only B's selected label-context crop and a fixed transcription
prompt. It never sees candidate names, catalog slugs, or expected answers.

Official model: [Qwen/Qwen3-VL-2B-Instruct](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct)
at revision `89644892e4d85e24eaac8bacfd4f463576704203`, Apache-2.0.
Image longest edge is 768 pixels, output is greedy with at most 128 new tokens.
Prompt and preprocessing are constants in `read.py`. Crops come from the same
gold-blind B selected target/label-context coordinates as the other N2 runs.

Run one ten-case engineering sample before the full 316 rows (288 with crops).
The sample IDs are fixed quantiles of sorted crop IDs from the frozen and
organizer manifests; no labels are used. Save every text result and timing
before scoring. Query crops are lossless PNG, resized only in model input.
The first sample prompt sometimes echoed the instruction or wrote a phrase
instead of an empty string. The final prompt uses the literal `<EMPTY>` token
and a 128-token cap; this adjustment used only the unscored engineering sample.

```sh
python tools/night-reader/read.py --inputs INPUTS_SLIM_JSONL \
  --crop-root CROP_DIR --sample-ids SAMPLE_IDS_JSON --out SAMPLE_RAW_JSONL
python tools/night-reader/read.py --inputs INPUTS_SLIM_JSONL \
  --crop-root CROP_DIR --out FULL_RAW_JSONL
```

`rank.py` compares Qwen text with existing PaddleOCR using the same catalog
wide character-gram lexical index, then separately recomputes B whole+label+
reader-OCR rank fusion. Reader text can add a candidate outside B Top20. A
missing target retains B's action. Scores and private labels stay on the
trusted host after the raw text file is complete. Reader-only latency is
measured; no complete live HTTP SLA is implied.
