#!/usr/bin/env bash
# Isolated, bounded converter for the pinned SO400M FP32 ONNX graph.
set -u
cd /workspace/night-cpu-int8 || exit 2
ulimit -v 25165824  # 24 GiB virtual address-space cap, in KiB.
timeout -s TERM -k 10s 600s venv/bin/python input/quantize_onnx.py \
  --source input/vision.onnx --out-dir output > quantize.log 2>&1
code=$?
printf '%s\n' "$code" > quantize.exit
exit "$code"
