# Документация BrutForce / Vino

## Проект и продукт

- [Матрица требований и приёмки](product/ACCEPTANCE-MATRIX.md).
- [Контракт данных](data/DATA-CONTRACT.md),
  [реестр источников](data/SOURCE-REGISTRY.md) и
  [runbook сбора](data/COLLECTION-RUNBOOK.md).
- [Протокол оценки](evaluation/EVALUATION-PROTOCOL.md).
- [Архитектурные решения](adr/README.md).
- [Вспомогательные OCR/LLM/text-сервисы](infrastructure/AI-SERVICES.md) и их
  отличие от обязательного visual retrieval.
- [Результаты независимых проверок](testing/README.md).

## Команда и инфраструктура

- [Вход нового участника](agent-guide/AGENTS.md),
  [сервер](agent-guide/SERVER.md) и [доска](agent-guide/BOARD.md).
- [Проверка onboarding-пакета](reviews/2026-09-16-onboarding/README.md).
- [Разбор передачи Vino](transfer/HANDOFF-2026-09-17.md).

Документ [architecture-options.md](architecture-options.md) фиксирует варианты,
которые обсуждались до принятия Vino основой репозитория. Он не заменяет
актуальные границы из корневого `ARCHITECTURE.md` и принятые ADR.
