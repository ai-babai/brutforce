# CPU vision service

This folder owns the pinned F8 CPU Python serving code. Read [README.md](README.md)
and [vision-serving.md](../../contracts/vision-serving.md) before changing its behavior.

- Keep `overlay/` and `parent/` source SHA checks aligned with code changes.
- Only model data, reference index and catalog metadata are mounted at `/assets`;
  the serving source and OCR lexicon are copied into the image from this repo.
- Do not commit model weights, reference photos, private evaluations or uploads.
- Verify the import SHA boundary and the Compose image before claiming runtime parity.
