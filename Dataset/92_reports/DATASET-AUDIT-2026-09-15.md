# Аудит датасетов — 2026-09-15

## Короткий вывод

Текущий каталог вин «Своего Вина» обработан полностью по зафиксированному `wines-sitemap.xml`: 2041 из 2041 страниц получены и распарсены, ошибок загрузки/парсинга — 0. У всех текущих карточек есть явная связь product→image; 2033 связей проходят автоматический SKU-gate, 8 оставлены на ручную проверку.

Все найденные файлы учтены и имеют явный статус. Это **не означает**, что все они уже размечены для supervised-обучения: Telegram-сцены и слабые внешние соответствия намеренно не включены в обучение.

Из новых retail web-sources полностью собраны и проаудированы МАВТ, «Ароматный
Мир» и Алкотека. Для K&B, Winelab, SimpleWine и LUDING сохранены разрешённые
policy/access probes; сбор остановлен после ответов 403/401 без обхода защиты.
Для продолжения нужен официальный export или разрешение владельца.

На этапе проверки шести внешних открытых наборов подтверждённое пополнение
составило **11 изображений** (4 новых товара текущего «Своего Вина» + 7
российских WineID из X-Wines). Последующий сбор российских retail-каталогов дал
ещё **3 247 точных source product→media связей**: 760 МАВТ, 1 760 «Ароматный Мир»
и 727 Алкотека. Из них 3 181 связь сейчас проходит identity-gate; остальные
остаются в очередях из-за placeholder/shared/duplicate media. Ещё 11 Open Food
Facts front-изображений подготовлены как barcode-linked кандидаты, но до проверки
происхождения не допускаются в Russian-SKU supervised split.

## Матрица источников

| Источник | Что проверено | Российское SKU-обогащение | Готовность |
|---|---:|---:|---|
| Своё Вино, архив | 15770 изображений; 5487 exact-label; 1 decode error | Базовый каталог 2103 товаров | Не замораживать split до дедупликации/shared review |
| Своё Вино, текущий сайт | 2041 карточек; 4 новых изображения | 4 новых товара относительно архива | 2033 связей проходят gate |
| Telegram РВК | 507 изображений, 49 PDF; таблицы очищены | 0 verified SKU; 39 слабых кандидатов | Требуется ручная разметка 207 сцен |
| Retail Alcohol Detection | 1884 изображений, 21441 валидных bottle/product boxes | Нет exact Russian wine SKU | Готов как detector/domain data после split-dedup |
| Wine Images 126K | 125 787 metadata-записей профильтрованы | 0 российских кандидатов | Не добавляется |
| X-Wines Slim 1K | 1 007 exact WineID image-label пар | 7 российских WineID | Готовы внутри X-Wines; cross-source merge запрещён |
| WineSensed | 24/24 shards, 1014630 строк проверено | 0 кандидатов | Отфильтрован; хранить отдельно из-за NC-ND |
| RF100 Wine Labels | 4643 изображений, 25034 валидных element boxes | Нет SKU/country labels | Готов для label-element detector после near-dup review |
| Open Food Facts | 11 front images | 10 brand + 3 probable | Exact barcode label есть; происхождение требует review |
| МАВТ | 4 780 sitemap-карточек проверено; 763 российских SKU | 760 exact primary images | 2 origin review + 3 missing-image annotation |
| Ароматный Мир | 845 российских SKU; 1 760 gallery images | 1 760 exact source associations | 24 карточки без media + 1 shared-image group в review |
| Алкотека | 727 российских SKU/images, Краснодар | 727 exact source associations | 663 identity-eligible; 58 grouped review tasks |
| Retail access-blocked | K&B 403, Winelab 401, SimpleWine/LUDING 403 | product data не собирались | Нужен официальный export/permission |
| Russian wine master | 6 499 source products; 9 156 media refs | 11 005 associations | 10 719 identity-eligible; 552 verify + 3 annotate |

## Контроль разметки

- Svoe: exact-label имеют только media со статусом `gold_exact_asset_key`; 61 shared-asset изображения исключены; 10 222 site assets явно помечены out-of-scope.
- Retail: все 21441 бокса валидны; 139 координат были только подрезаны на epsilon из-за округления YOLO.
- RF100: все 25034 бокса валидны; один кадр является явным negative без боксов.
- Telegram: 207 реальных сцен, из них 39 имеют лишь event/caption candidates, verified SKU и bbox пока 0.
- X-Wines: каждая из 1 007 картинок имеет точный внешний WineID; семь российских записей прошли визуальный crosswalk review.
- МАВТ/AMWine/Алкотека: чистым product images bbox не нужен; supervision
  задаётся точной source product→media связью. Missing/placeholder/shared assets
  не считаются молча готовыми и направлены в source/master review queues.

Визуальная spot-check QA выполнена на 12 Retail detection-кадрах и на 12 разных
RF100-изображениях, покрывающих все категории, реально присутствующие в bbox.
Систематического сдвига координат не найдено; RF100 остаётся только auxiliary
набором из-за семантической неоднородности upstream-разметки. Подробности:
`BBOX-VISUAL-QA.md`.

Cross-source audit охватывает 27073
media-записей; найдено 0
exact SHA-групп и 24
same-dHash кандидатов. Они не должны пересекать split до review; детали —
`CROSS-SOURCE-DUPLICATES-SUMMARY.json` и
`CROSS-SOURCE-DUPLICATES-REVIEW.md`.

## Почему split пока не заморожен

До создания `train/val/test` нужно завершить очереди ручной проверки, построить общий exact/near-duplicate graph и группировать один SKU/винтаж/событие в один split. Иначе одинаковая этикетка или соседние кадры Telegram попадут одновременно в train и test.

Машиночитаемый результат: `DATASET-AUDIT-2026-09-15.json`. Очереди: глобальные
`review_queue_*.jsonl` в этой папке и materialized views в
`Dataset/<NN_source>/review/`.
