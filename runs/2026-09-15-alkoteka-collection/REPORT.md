# Handoff VINO-006 — Алкотека

## Результат

Собран разрешённый snapshot российского вина из публичного web API Алкотеки в
фиксированном контексте Краснодара. Сбор выполнен последовательно с одним
User-Agent и паузой 0,4 с; HTTP 403/429 и challenge не возникали. Обход защиты,
ротация заголовков/cookies/IP и авторизация не применялись.

- `source_id`: `alkoteka-russian-wine-web-2026-09-15-krasnodar`;
- `source_capture_id`: `capture_alkoteka_517d4364d655df114754`;
- категории: `vino` — 551, `shampanskoe-i-igristoe` — 176;
- 727 уникальных source SKU, 727 detail responses, 0 ошибок карточек;
- 727 оригинальных файлов изображений, 211 972 440 байт, 727/727 decode OK;
- 727 точных связей product/media из одной API-карточки;
- 663 связи identity-eligible после автоматических quality gates;
- 53 placeholder-файла исключены, пять групп с 11 SKU направлены на ручную
  проверку одинаковых реальных изображений;
- 58 элементов в `needs_verification`, 0 в `needs_annotation`;
- 1 349 уникальных image URL учтены; detail API даёт только один primary
  `image_url`, дополнительных gallery-полей не найдено;
- у всех 727 товаров есть явное доказательство страны: RU / Россия;
- `svoe_vino_slug` не присваивался, crosswalk со «Своё Вино» не выполнялся.

## Файлы

- raw snapshot: `Dataset/00_raw/16_alkoteka_ru_wines/2026-09-15/`;
- нормализованные таблицы и summary: `Dataset/16_alkoteka_ru_wines/tables/`;
- очереди review: `Dataset/16_alkoteka_ru_wines/review/`;
- воспроизводимый сборщик: `scripts/dataset/crawl_alkoteka.py`;
- логи: `runs/2026-09-15-alkoteka-collection/`.

Сырой контур содержит 1 469 файлов общим объёмом 262 224 965 байт. SHA-256
контрольных артефактов:

- `RESPONSE-MANIFEST.jsonl`: `0a305219339f84cbf7efb27f3bbcf40f74a1c6111d16b993083ac85df73e4cca`;
- `SUMMARY.json`: `9e09f72e11dc88d3cf4dfe0d6503c37b82a88201b28a0314c0bcaa9763e08ce0`;
- `products.jsonl`: `7818416d82a8af9c100d196cdc23c73a9708e9f9597b371f3d269d049b88aa88`;
- `media.jsonl`: `d304e46e8c14c7aa7ffe2d818bba62bdc3b6439ac299e035598a225b49e105c7`;
- `associations.jsonl`: `2f155f71044d9388a4d939a048dfd773c080c11767ce90333275c5dd4fec4c75`.

## Проверки

- финальный cached rerun сборщика: exit code 0;
- 12/12 проверок `SUMMARY.json`: pass;
- `source_id` и `source_capture_id` едины во всех 727 products, 727 media,
  727 associations, 727 memberships, 1 401 asset-url rows и 1 467 строках raw
  response manifest;
- все product/media ссылки разрешаются, source SKU уникальны, все оригиналы
  скачаны, все detail image URL учтены;
- визуальная стратифицированная проверка шести пригодных изображений подтвердила
  каталожный характер и читаемые этикетки; отдельная проверка placeholder
  подтвердила корректность его исключения;
- предупреждение Pillow о palette transparency относится к placeholder PNG и
  не является ошибкой декодирования.

## Не проверено и ограничения

- Snapshot не заявляет покрытие удалённых, исторических либо доступных только в
  других городах SKU.
- Условия использования исходных изображений и допустимость производных требуют
  отдельной legal/rights проверки; некоммерческий режим не снимает этот gate.
- Пять групп одинаковых реальных изображений требуют ручного variant/design
  решения; 53 placeholder SKU требуют поиска настоящего фото.
- Cross-source family resolution, сопоставление со «Своё Вино» и разбиение
  train/validation/test не выполнялись.

## Следующий шаг

Владелец общего контура может синхронизировать `REGISTRY.yaml` и общий raw
manifest с указанным versioned `source_id`, затем отдать 58 review items на
ручную проверку. До завершения rights review данные не помечать как разрешённые
для обучения.
