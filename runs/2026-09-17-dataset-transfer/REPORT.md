# VINO-008 — архив распарсенного Dataset

Дата: 2026-09-17.

## Handoff VINO-008

- Результат: собран самодостаточный data-only архив нормализованного Dataset с
  изображениями, bbox/labels, таблицами, review queues и referenced media/PDF.
- Артефакт:
  `artifacts/dataset-transfer/2026-09-17/Vino-parsed-dataset-2026-09-17.7z`.
- Размер архива: 3 982 310 819 байт.
- SHA-256:
  `a3bc9d8bd6d8b1524a46354b4c8f1bb7a7d06964c9dd17325a07b8b22809b8d8`.
- Изменённые файлы: `TASKS.md`, `agents-os/memory/WORKING.md`,
  `Dataset/PARSED-DATASET-TRANSFER.md`, package manifest/summary,
  `scripts/build-parsed-dataset-package.ps1` и этот отчёт.
- Не включено: проектный код, Agents OS, исходное PDF-ТЗ, нереференсный raw,
  нереференсный cache, ключи, токены, веса и индексы.
- Не проверено: фактическая распаковка на машине получателя и права публикации;
  пакет предназначен только для внутреннего некоммерческого исследования.
- Следующий шаг: передать архив и sidecar по внутреннему каналу вне Git.

## Состав

- 32 883 payload-файла по manifest, 4 205 228 981 байт.
- 2 package metadata; всего в 7z — 32 885 файлов.
- 36 890 строк reference-таблиц и 37 650 path-значений.
- 4 330 выбранных файлов из `00_raw`, только непосредственные зависимости:
  - Telegram: 556 файлов / 62 063 766 байт;
  - current Svoe: 4 / 69 912;
  - Open Food Facts: 11 / 5 521 308;
  - МАВТ: 1 272 / 27 097 893;
  - «Ароматный Мир»: 1 760 / 149 778 717;
  - Алкотека: 727 / 211 972 440.
- 1 007 X-Wines cache-изображений сохранены, потому что напрямую входят в
  reference closure; других cache-файлов нет.

## Проверки

- `7z t`: `Everything is Ok`.
- SHA-256 архива совпадает с sidecar.
- Manifest: 32 883 уникальных canonical paths; SHA-256 manifest —
  `6b286ed28a45328bfc86b529c6b68dd1d28efba659d0d9889d1f62313c0ea691`.
- Полный повторный расчёт path/bytes/SHA-256: 0 missing, 0 size mismatch,
  0 hash mismatch.
- Listing 7z в UTF-8 точно равен filelist; missing/extra/duplicates — 0.
- Все 37 650 ссылок разрешаются в исходном дереве и package manifest.
- В `00_raw` ровно 4 330 dependencies + `README.md`; лишних raw — 0.
- Project/code/Agents OS/root PDF/secret-like paths и strong secret patterns — 0.
- Независимый QA: PASS, P0=0, P1=0, P2=0.

## Ограничения

Это не frozen training release: `frozen_split_ready=false`, ручные identity и
annotation очереди не закрыты. Права сохраняются по `rights_status` каждого
источника; весь пакет нельзя публиковать как открытый датасет без отдельного
rights review.
