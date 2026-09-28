#!/usr/bin/env python3
"""Warm CPU endpoint and Russian/English OCR availability (not quality parity)."""
import json
import subprocess
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8127/healthz", timeout=2) as response:
    health = json.load(response)
assert health["status"] == "ready"
assert health["model_version"] == "rtdetr-so400m-whole-only-v1-f8-text-confirmed-v1-onnx640"
assert health["index_version"] == "so400m384-owlv2-v2-crops-reference-gated-20260925"
ocr = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, timeout=2, check=True)
assert {"eng", "rus"} <= set(ocr.stdout.splitlines())
