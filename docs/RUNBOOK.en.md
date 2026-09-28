# Runbook · English entry

The operational instructions live in one place: [RUNBOOK.ru.md](RUNBOOK.ru.md). This page maps the steps without duplicating shell commands.

1. **Synthetic local demo:** Go 1.23, Node.js 22, npm. Follow the two terminals in the [English quick start](../README.en.md#quick-start). Check the Go liveness route; Ctrl-C stops both processes. It intentionally has no working F8 recognition.
2. **Real CPU F8 with Docker:** the [asset-acquisition and step-by-step Compose section](RUNBOOK.ru.md#полный-cpu-профиль-f8) covers the 50-file SHA manifest, private bundle/catalog/media/recommendations, `deploy/.env.local`, two password files, and `sh scripts/docker-local.sh preflight|up|smoke|stop|down`. Repro built both linux/amd64 images on OrbStack in a separate patch branch; `main` still has the TS blocker. External asset delivery and clean-Linux/OCR parity remain unverified. The synthetic demo does not run the model.
3. **Tests and release:** the [fast checks](RUNBOOK.ru.md#локальное-демо-без-ml) and [server deployment/rollback boundary](RUNBOOK.ru.md#обновление-prod-и-откат) are in the same Russian runbook; [PIPELINE](../deploy/PIPELINE.md) covers operator approval. TEST and [PROD](https://app.dzap.pw) run the approved F8 CPU candidate `b0428147…`; public HTTP smoke passed on 28 September 2026.

The contest route is `POST /v1/eval/predict` with multipart `image` (not the app upload field `photo`), and a successful exact match yields one `slug`. The [canonical contract](../contracts/eval-predict.md) and [architecture](../ARCHITECTURE.md) are available separately.
