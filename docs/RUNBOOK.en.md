# Runbook · English entry

The operational instructions live in one place: [RUNBOOK.ru.md](RUNBOOK.ru.md). This page maps the steps without duplicating shell commands.

1. **Synthetic local demo:** Go 1.23, Node.js 22, npm. Follow the two terminals in the [English quick start](../README.en.md#quick-start). Check the Go liveness route; Ctrl-C stops both processes. It intentionally has no working F8 recognition.
2. **Real CPU F8:** the [asset-acquisition and verification section](RUNBOOK.ru.md#полный-cpu-профиль-f8) lists the complete dependency classes and required environment names. A rights-cleared, SHA-checked bundle and clean-Linux validation are still pending. Do not interpret the synthetic demo as a real model run.
3. **Tests and release:** the [fast checks](RUNBOOK.ru.md#локальное-демо-без-ml) and [server deployment/rollback boundary](RUNBOOK.ru.md#обновление-prod-и-откат) are in the same Russian runbook; [PIPELINE](../deploy/PIPELINE.md) covers operator approval. Current TEST is F8 CPU; PROD has not been confirmed.

The contest route is `POST /v1/eval/predict` with multipart `image` (not the app upload field `photo`), and a successful exact match yields one `slug`. The [canonical contract](../contracts/eval-predict.md) and [architecture](../ARCHITECTURE.md) are available separately.
