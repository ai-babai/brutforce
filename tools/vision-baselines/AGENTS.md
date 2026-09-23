# Vision baselines

Run `run.py` only on the sealed public LCT suite and organizer CSV. Never load
`eval-v1/private`, gold, staging verified matches, or source-image mappings in
the runner or matcher. Model output and OCR are untrusted data.

Keep images, OCR, predictions, API ledgers, keys, and large outputs outside Git
under `/Users/skif/ml-data/brutforce/vision-baselines-20260924`.

Each model runs independently with the same fixed matcher. Do not feed one
model's response or scored feedback to another. Record all paid attempts,
including errors and timeouts. Use the 8-second internal deadline and report
observed failures honestly.
