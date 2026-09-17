# Dataset Vino

Единый корень данных проекта. Сырые байты сохраняются неизменяемо, каждый
производный набор имеет номер и карточку, а назначение `train`/`val`/`test`
фиксируется только versioned-манифестами.

## Структура

| Путь | Назначение | Текущее состояние |
|---|---|---|
| [`00_raw/`](00_raw/) | исходные байты всех источников | 15 непустых контуров, 9 219 файлов захешированы |
| [`01_svoe_vino_catalog/`](01_svoe_vino_catalog/) | каталог и эталонные фото «Своё Вино» | распарсен и проаудирован |
| [`02_rvk_telegram/`](02_rvk_telegram/) | фото, сообщения и таблицы оценок РВК | распарсен; 207 сцен ждут ручной разметки |
| [`03_manual_store/`](03_manual_store/) | ручная съёмка в магазинах | схема подготовлена |
| [`04_svoe_vino_web_enrichment/`](04_svoe_vino_web_enrichment/) | дополнение с текущего сайта | 2 041/2 041 карточек; 4 новых товара |
| [`05_retail_alcohol_detection/`](05_retail_alcohol_detection/) | российские полки и hard negatives | 1 884 изображения; 21 441 bbox проверен |
| [`06_wine_images_126k/`](06_wine_images_126k/) | чистые bottle/image-text пары | 125 787 metadata строк; RU-кандидатов 0 |
| [`07_x_wines/`](07_x_wines/) | wine metadata/ratings/label assets | 1 007 image-label пар; 7 российских |
| [`08_winesensed/`](08_winesensed/) | multimodal research corpus | 24/24 shards, 1 014 630 строк; RU-кандидатов 0 |
| [`09_rf100_wine_labels/`](09_rf100_wine_labels/) | элементы этикетки для OCR/detection | 4 643 изображения; 25 034 bbox проверено |
| [`10_open_food_facts_wine_ru/`](10_open_food_facts_wine_ru/) | отфильтрованные российские вина OFF | 11 barcode-linked front images; origin review |
| [`11_mavt_ru_wines/`](11_mavt_ru_wines/) | российские вина МАВТ | 763 SKU; 760 точных primary images; 3 без изображения |
| [`12_krasnoe_i_beloe_ru_wines/`](12_krasnoe_i_beloe_ru_wines/) | российские вина «Красное&Белое» | robots/sitemap сохранены; product access остановлен на 403 |
| [`13_winelab_ru_wines/`](13_winelab_ru_wines/) | российские вина ВинЛаб | sitemap сохранён; product access остановлен на 401 |
| [`14_simplewine_ru_wines/`](14_simplewine_ru_wines/) | российские вина SimpleWine | доступ остановлен на 403 при robots probe |
| [`15_aromatny_mir_ru_wines/`](15_aromatny_mir_ru_wines/) | российские вина «Ароматного Мира» | 845 SKU; 1 760 gallery images; 25 review-задач |
| [`16_alkoteka_ru_wines/`](16_alkoteka_ru_wines/) | российские вина Алкотеки | Краснодар: 727 SKU/images; 663 identity-eligible |
| [`17_luding_ru_wines/`](17_luding_ru_wines/) | российские вина LUDING | доступ остановлен на 403 при robots probe |
| [`18_russian_wine_master/`](18_russian_wine_master/) | единый open-world master-index | 6 499 товаров; 9 156 media refs; 11 005 связей |
| [`90_splits/`](90_splits/) | канонические frozen splits | контракт подготовлен |
| [`91_manifests/`](91_manifests/) | хеши, происхождение и безопасные индексы | raw manifest v1 подготовлен |
| [`92_reports/`](92_reports/) | профили и quality/leakage reports | итоговый аудит 34/34 checks |
| [`99_quarantine/`](99_quarantine/) | повреждённые и неоднозначные объекты | подготовлено |

## Источники истины

- [`CONTRACT.md`](CONTRACT.md) — структура записей, идентичность, права и splits.
- [`REVIEW-ANNOTATION-CONTRACT.md`](REVIEW-ANNOTATION-CONTRACT.md) — очереди
  проверки, полной разметки и решения по редизайну/винтажам.
- [`REGISTRY.yaml`](REGISTRY.yaml) — состояние, происхождение и допуск каждого
  источника.
- [`90_splits/`](90_splits/) — единственное каноническое назначение ролей.
- [`91_manifests/`](91_manifests/) — точные байты и их SHA-256.

## Правила

1. `00_raw` не редактируется, не переименовывается и не попадает в Git.
2. Распаковка, OCR, дедупликация и связывание выполняются скриптом в каталог
   конкретного набора, а не рядом с raw.
3. Номер означает стабильный источник/производный контур, а не качество.
4. Физические копии не задают split: роль берётся из `90_splits/<version>`.
5. Один original/derivative, `identity_group_id` и согласованная
   `near_duplicate_group_id` не пересекают query splits.
6. Некоммерческая исследовательская цель закреплена в реестре, но права и
   ограничения проверяются отдельно по каждому источнику.
7. Российское вино без exact `slug` «Своё Вино» сохраняется как open-world
   объект; ложная привязка к ближайшему SKU запрещена.

Проверка Git metadata без приватных файлов:
`pwsh -File scripts/verify-dataset-layout.ps1 -MetadataOnly` из корня проекта.
На машине с полным подключённым Dataset используется команда без
`-MetadataOnly`; `-FullHash` дополнительно пересчитывает хеш каждого файла raw
manifest и поэтому выполняется существенно дольше.
