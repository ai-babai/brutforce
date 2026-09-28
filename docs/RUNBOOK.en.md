# Runbook · English entry

For a first run, use the [English README](../README.en.md) and the [self-hosting guide](SELF-HOST.ru.md). The guide covers the synthetic mode with Go/Node.js or one Docker container, the layout and checks for the full data bundle, and Docker plus manual assembly of the real profile. No team server or token is needed for the synthetic mode. The complete model/catalog bundle has no independent public download yet.

The [Russian operator runbook](RUNBOOK.ru.md) is for the team: exact pinned assets, TEST/PROD checks and recovery. [PIPELINE](../deploy/PIPELINE.md) documents candidate registration, approvals and rollback; it is not a prerequisite for a local demo.

The organizer route is `POST /v1/eval/predict` with multipart `image`, distinct from the application upload field `photo`. Successful recognition yields a nonempty `slug`; [API contract](../contracts/eval-predict.md) and [architecture](../ARCHITECTURE.md).
