# Handoff VINO-001

- Результат: девять полученных семейств raw-источников воспроизводимо приняты,
  разобраны и проверены по применимости. Актуальный wine sitemap «Своё Вино»
  обработан 2 041/2 041 без ошибок. Все media имеют явный статус; глобальный
  аудит проходит 19/19 инвариантов. `VINO-001` закрыт, `VINO-002` начат.
- Изменённые файлы: `Dataset/REGISTRY.yaml`, `Dataset/README.md`, README и
  таблицы в `Dataset/01_svoe_vino_catalog`, `02_rvk_telegram`,
  `03_manual_store`, `04_svoe_vino_web_enrichment`,
  `05_retail_alcohol_detection`, `06_wine_images_126k`, `07_x_wines`,
  `08_winesensed`, `09_rf100_wine_labels`, `10_open_food_facts_wine_ru`;
  `Dataset/91_manifests/raw-source-files-v1.0.0.jsonl` и `.sha256`;
  отчёты в `Dataset/92_reports`; скрипты в `scripts/dataset`;
  `scripts/build-raw-source-manifest.ps1`, `scripts/verify-dataset-layout.ps1`,
  `TASKS.md`, `agents-os/memory/WORKING.md`, `agents-os/memory/FACTS.md`.
- Данные/артефакты: точный список 2 910 raw-файлов находится в
  `Dataset/91_manifests/raw-source-files-v1.0.0.jsonl`; SHA-256 манифеста —
  `d704bfc17f2d618bc1996e1daedad6a51d0eca15e08caa5844111e4d2baa6ca6`.
  Основной результат — `Dataset/92_reports/DATASET-AUDIT-2026-09-15.md`;
  ручные очереди сведены в `Dataset/92_reports/REVIEW-QUEUES-SUMMARY.json`.
- Проверки: uv-managed Python 3.13 `-m compileall -q scripts` — exit 0; полный rebuild raw
  manifest — 2 910 записей и совпадающий sidecar; dataset audit — 19/19 PASS;
  bbox reference/geometry audit — 46 475/46 475 PASS; visual overlay sample —
  12 Retail + 12 RF100; project/setup и dataset/layout checks — PASS.
- Не проверено: семантическая корректность каждого из 46 475 bbox вручную;
  точные SKU и bbox для 207 Telegram-сцен; российское происхождение 13
  Open Food Facts candidates; сильные perceptual near-duplicates до frozen split.
- Риски/допущения: WineSensed допустим для текущего некоммерческого исследования,
  но CC BY-NC-ND 4.0 сохраняет ограничения на атрибуцию и производные;
  Telegram и кейсовые изображения нельзя считать разрешёнными к распространению.
  RF100 размечает элементы этикетки, а не целую бутылку или SKU.
- Следующий шаг: `data_curator` размечает 39 Telegram-сцен с caption-context,
  затем `qa_evaluator` закрывает identity queues и group-safe leakage audit для
  перехода к `VINO-003`.
