# BE-089 · Прозрачные бутылки: аудит и demo-выпуск

Состояние на 27.09.2026; [поручение #89](https://github.com/ai-babai/brutforce/issues/89).
Ниже — исходный аудит, локальная подготовка и выпуск версии
`svoe-20260927-alpha-2035-v1` только на demo Макса.

## Точный источник и контуры до выпуска

- `lct_maks` (demo) и `lct_shared` (TEST) — **две** PostgreSQL БД: в обеих
  было `catalog_state.version=svoe-20260922-v2`, 2038 `catalog_items`, 2035 различных
  значений `image`, 3 aliases. `catalog_versions.package_sha256` в обеих:
  `badee4d2772083de0861927850d4008ae01c22df058df21facd2fbd559cac927`.
  После выпуска demo перешёл на `svoe-20260927-alpha-2035-v1`, а TEST
  сохранил `svoe-20260922-v2`.
- `lct_prod`: `catalog_items`/`catalog_state` отсутствуют; подготовленная PROD-БД
  не равна запущенному приложению. Общий immutable media root:
  `/srv/lct/data/catalog/media/{400,800,original}/<sha256>.webp`.
  Release `svoe-20260922-v2`, схема `catalog-release-1`: 2038 строк,
  6105 файлов (по 2035 на роль), 391,73 МиБ. Все 6105 декодированных WebP —
  **без alpha-канала**. Прошлый display-builder сводил alpha на белый RGB-фон;
  это явно записано в `/srv/lct/data/roman/vino/catalog-display-20260922/PREPARATION.ru.md`.
- Исходники: `/srv/lct/data/roman/vino/2026-09-17/Dataset/01_svoe_vino_catalog/`
  и 26 решений в `catalog-display-20260922/internal/photo-decisions.json`.
  Контрольные SHA256: raw-source-wines.jsonl
  `a2a6dc93c94e584b31fbc28bb4e8de340adfd197fddfb816c6c8c338674982b7`,
  исходный media.jsonl
  `c06afc3eb0634aabbd6654a12c7b755c8346a4282ed865161a0f44fc7fd31441`,
  photo-decisions.json
  `7c962b626f8793d08f9a847334108efa9e1264527ae6e75c2f5ac30f9515b055`.

| Канонические ID | Число | Метод |
|---|---:|---|
| Готовые raw-оригиналы с настоящим alpha | 1905 | 2007 по source_media_id: 1906 RGBA, но один имеет alpha только 222…255; 101 RGB |
| Прозрачные оригиналы из решений 26 спорных фото | 25 | Декодирование сохранённых файлов; один из 26 RGB |
| Непрозрачные raw/decision | 102 | 101 + 1, требуется отдельное удаление фона и QA |
| Alpha-канал есть, фона с настоящей прозрачностью нет | 1 | `chateau-de-talu-yuzhnaya-vertikal-kaberne-fran-krasnoe-suhoe-142`: min=222, corner=222, ни одного пикселя alpha<16 |
| Пока нет сопоставленного upstream-файла | 5 | 5 сторонних/обогащённых source_media_id вне проверенного архива |
| Итого | 2038 | Потенциальный reuse-alpha: 1930/2038 (94,70 %), 1927 уникальных upstream SHA; **не** факт готовности выпуска |

Все 2038 карточек имеют уникальные `source_url`; для 25 решений записаны
`source_photo_url` (24 различных URL). Два URL совпадают; три display image
повторяются между карточками. По раннему `associations.jsonl` у одного продукта
может быть несколько media — подмена по одному slug/имени файла без проверки
`source_media_id` и утверждённого решения запрещена. Исходные URL сервиса
`api.vino-svoe.ru/v1/img/...` не скачивались: публичный `robots.txt` сайта
запрещает `/api/*`, а проверенных локальных копий достаточно для пробы.
Среди 103 opaque/псевдо-alpha карточек только у указанной псевдо-alpha записи
в `associations.jsonl` есть три дополнительных RGBA media; их точная
принадлежность и качество для показа **не** подтверждены и они не подменялись.

«Имеет A» ≠ «прозрачен»: проверяются фактические значения alpha, доля прозрачных
и видимых пикселей, прозрачный угол, хеш исходника и соответствие ID.

## Минимальная подготовка в действующей схеме

`deploy/catalog_alpha_sources.py` только читает архив и release; на выходе
кандидаты локальных прозрачных originals по точному ID/source_media_id и уже
принятым photo-decisions. Его JSONL — частный рабочий файл вне Git; сначала
проверить соответствие изображения и карточки. Непрозрачные/неизвестные
исключаются, никакого сетевого запроса. `deploy/catalog_alpha.py` принимает
проверенный JSONL `{id,path,sha256,source_ref}`, base manifest SHA и новую
версию. По умолчанию dry-run; `--write` сохраняет **только новую** версию
`releases/<version>` и новые content-addressed media с 400/800/original,
фактическими width/height/bytes/SHA; upstream WebP original при допустимом
размере сохраняется byte-for-byte, без белой подложки. Старые ключи и версия
остаются неизменны. Отобранные ID получают новые `image` и `image.variants`,
остальные сохраняют прежние пути. `PREPARATION.md` новой версии хранит
источник SHA/референс, прежний и новый мастер; пути исходников/сырьё не
публикуются в release. Никакого нового API: `Candidate.image` и
`imageVariants[thumbnail|card|original]` попадают через существующий импорт
в `/media/catalog/<400|800|original>/<sha>.webp`, фактическая ширина — в API.

Нужны Pillow 12.x и Python 3.11+. Не запускать `--write` с live root до
согласования версии, ресурса и полного data gate. Для локального теста root
содержит копию **метаданных** базового release и нужные старые media; исходники
и результаты расположены вне Git в `/Users/skif/ml-data/brutforce/background-removal/`.
Пример: `python3 deploy/catalog_alpha.py --root ROOT --base-version
svoe-20260922-v2 --base-manifest-sha256 BASE_SHA --version NEW_VERSION
--source-root PRIVATE_SOURCE_ROOT --selection PRIVATE_SELECTION.jsonl`
(добавить `--write` только для выделенного staging). Затем отдельный
`catalog-import --package ROOT/releases/NEW_VERSION --media-root ROOT/media
--version NEW_VERSION --dry-run --previous-snapshot SNAPSHOT --report-out REPORT
--validator-version VALIDATOR` — проверка без БД.

## Проверенная партия и граница ресурсов

Локально 24/24 прозрачных оригинала (22 архивных, 2 из решений), 0 отказов после
разрешённой нормализации исходника 4486×6726 до max-side 1600. Пробная версия
`be089-local-pilot24-v2`: manifest SHA256
`655346792da2f8b5ba65b9b4c4cf49cc5db821da0424dc153907436bd4996d6c`.
Это manifest **24-строчного scratch-пакета**, НЕ полноценный кандидат 2038.
Selection SHA256 `7f4ca04656ba2dc1fe6278cd18c03b456b60c4bc4d150407db89f430d735ba91`.
В `PREPARATION.md` этой пробы закреплены SHA генератора
`11b84d41263e299aafed9b3c4af100c991166861e426ca3aa3e9a1ceb72015ac`,
Python 3.13.2, Pillow 12.1.0 и libwebp 1.6.0; весов/модели нет.
72 новых media — 1 451 824 Б; исходники — 1 349 146 Б;
staging ~7,1 МиБ + исходники ~1,3 МиБ. Все 72 bytes/hash/dimensions/alpha
проверены повторно. Локальный `catalog-import --dry-run` с 24-ID baseline:
DQ001–008, DQ011 **passed**, без доступа к БД. Report SHA256
`ecc2c7169cc79c477451631f50dc5f1fccb7459b8ff91599c039f10f03cc8010`.
Светлый `#fbf6ec` и тёмный `#182336` композиты шести разных геометрий
сохранены вне Git в `temp/pilot24/qa-{00,04,08,12,16,23}-{light,dark}.png`.
Независимый vision review координатора смог прочитать только пару `qa-00`:
бутылка/этикетка целы, белого прямоугольника/ореола не обнаружено. Остальные
пять пар технически не прочитались — визуальная приёмка **не пройдена**.
Это подготовка alpha, а не оценка модельной маски. Позднейший browser QA
полного выпуска указан отдельно ниже.

Измерено на Mac: 10 кодирований 1000px WebP за 21,61 с; полный dry-run
24 разных размеров — 63,21 с (2,63 с/ID, один worker). Получение 24 исходников
и 72 старых вариантов по SSH заняло 39,9 с отдельно. Экстраполяция кодирования
на 1930 ID — ~85 мин CPU wall без I/O/QA,
консервативный предел 2–4 ч, ~0,3–1 ГиБ новых файлов. Это **оценка**, не
согласованный лимит массовой работы. Пробная партия разрешена до 30 мин,
300 МиБ staging; использовано меньше. Для следующей партии сначала согласовать
лимит. Не запускать полный downloader/inference автоматически.

BRIA `RMBG-1.4` и `RMBG-2.0`: карточки моделей
[1.4](https://huggingface.co/briaai/RMBG-1.4) и
[2.0](https://huggingface.co/briaai/RMBG-2.0) проверены 27.09.2026:
gated, разрешены для non-commercial use; коммерческое требует соглашения.
Нет подтверждения лицензии для этого применения; веса BRIA **не скачаны**.

## Массовый локальный staging, 27.09.2026

После отдельного разрешения подготовлены 1930 архивных alpha и ещё 4
совпавших по SHA originals из сохранённых raw snapshots (без сетевых запросов
к сайту). Их selection SHA256:
`38298cdd6805641f00ce99b52cd9dcf3180feac17500c051a0ddcbdbcadd1fdb`;
исходники суммарно 132 246 938 Б. Один worker, 20 возобновляемых партий
по 100 (последняя 34), ~95 мин. Итоговый immutable release
`svoe-20260927-alpha-1934-v1`, manifest SHA256
`0bea34db3526afcdd0c3c8545c774acc6938b6706b3c7ac9f66ba18367849af6`:
2038 строк, 1934 обновлённых карточки, 5793 уникальных новых файла
(130 591 180 Б), 6105 прежних media не заменены. Локальный
`catalog-import --dry-run` с полным 2038-ID baseline прошёл
DQ001–008 и DQ011; report SHA256
`01bb0f3fbcfb1ae94505bbc69fba3cfb6afc8cb0ba722b115431184dbad6e110`.

Для оставшихся источников использована официальная
[BiRefNet](https://huggingface.co/ZhengPeng7/BiRefNet) по
[MIT-лицензии автора](https://github.com/ZhengPeng7/BiRefNet/blob/ebcc0bc8ec7fe919cec829f2dea656b3078acddc/LICENSE)
(проверено 27.09.2026): HF revision
`e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4`, GitHub license commit
`ebcc0bc8ec7fe919cec829f2dea656b3078acddc`. Локальный файл
`model.safetensors` — 444 473 596 Б, SHA256
`9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154`.
Веса, Python/MPS environment, dataset и результаты находятся только в
`/Users/skif/ml-data/brutforce/background-removal/{weights,cache,datasets,temp}`.
Проба пяти разных фото (включая 3992×5976 и псевдо-alpha) при размере
модели 1024×1024 занимала 0,93–4,26 с на фото: peak RSS 2,24 GiB,
MPS driver allocated 5,43 GiB; даже консервативная сумма <12 GiB.

После просмотра композитов на светлом/тёмном фоне обработаны 102
локальных исходника: 101 маска прошла проверку SHA, прозрачных углов и
контуров на шести обзорных листах; исходник
`soyuz-vino-soyuz-vino-shardone-suhoe-beloe-11` обрезан в нижних углах
(alpha маски там 232/251), исключён. Ещё две карточки не подменялись:
`agrolayn-mountain-eagle-traminer-traminer-beloe-suhoe-12` — нет точной
идентичности найденному альтернативному файлу;
`vibes-vermentino-viognier-barrel-fermented-2022` — сохранённый source-page
photo подписан как Silvaner, совпадение с SKU не доказано. В `source_ref`
каждой модельной маски сохранены ревизия BiRefNet, SHA весов и SHA входа;
маска явно обозначена как inference, а не upstream alpha.

Отдельный immutable release поверх 1934 originals:
`svoe-20260927-alpha-2035-v1`, manifest SHA256
`d88c4454a46802490ee2f69e32d2fb28fd8816d23a6d4d554356697632f845ef`.
Из 2038 canonical изменены ровно 2035 (1934 originals + 101 model masks),
три перечисленные карточки сохраняют старые media. По сравнению с базой
добавлены 6096 media (146 115 418 Б), из них model overlay 303 файла
(15 524 238 Б). Дедупликация обошлась без перезаписи прежних ключей.
Локальный полный `catalog-import --dry-run` с baseline прошёл
DQ001–008 и DQ011; report SHA256
`fa3569510c49f7e1ebe4b4a53750bed221a23946a026504d8a0e65c22ebb2152`.
Общий локальный staging ~806 МиБ (включая base media и промежуточные
immutable releases), dataset ~163 МиБ. Это техническая проверка целостности
и выборочный visual review до установки на demo.

В установленном неизменяемом `PREPARATION.md` последовательная история:
20 alpha-блоков для 1934 upstream originals и 5 inferred-блоков для 101
маски. Фраза «Reviewed upstream originals» относится к первым 20 блокам;
последующие блоки прямо называют модельные изображения inferred и указывают
в `source_ref` ревизию модели, SHA весов и входа. Исторический пакет под
указанным manifest SHA не редактировался; генератор исправлен для новых
выпусков, в том числе для смешанного selection.

## Установка и проверка demo, 27.09.2026

- После сверки manifest и новых media на сервере установлены 6096 новых файлов
  с правами доступа только на них; прежние 6105 файлов общего media root
  не менялись. Финальный серверный dry-run DQ001–008/DQ011 — `passed`:
  `/srv/lct/backups/catalog/maks/be089-alpha-2035-20260927-final-dq.json`,
  SHA256 `c84136aefb41852e866790c603afd97004ff707ed58655f0c500d5e45c163dc2`.
- Перед атомарным импортом в `lct_maks` сохранены PostgreSQL dump
  `/srv/lct/backups/catalog/maks/be089-alpha-2035-20260927-before.dump`
  (SHA256 `ac2f262dafaae1404a59cfb8a9aadc7ca3feecef465e710beeef0c14e73bccef0`)
  и JSON snapshot `.../be089-alpha-2035-20260927-before.json`
  (SHA256 `e23027777dd59c088a365eb27c4958768a260526604481cee7619979204987c3`).
  После импорта DQ009 — `passed`:
  `/srv/lct/maks/catalog-be089-staging/demo-post-import-dq.json`,
  SHA256 `4226f7e0ffabbdf16a8336396a4bcb8ce1d7d95d8511884e4db5a6b18deae88d`.
- Demo-only приложение выпущено из успешного CI main run `36346389887`, Git
  `b4db2c6aad092a845f91084bac5519c2f3b8e105`, архив SHA256
  `b0ad564aa7a9366ca3b7c79114661b731415cecc21856b945a34c93df5c08321`.
  Публичные `/release.json`, `/v1/health`, `/v2/catalog` отвечают; режим
  модели `reference`, качество распознавания не проверялось. TEST/PROD
  не переключались, TEST-БД осталась на прежней версии.
- Публичный HTTP/media gate (DQ010-проверки вручную): у трёх обновлённых
  карточек и всех трёх исключений сверены API-мастер и все 3 media-роли —
  200, WebP, заявленный размер, SHA256, immutable cache. Пути
  `/media/catalog/internal/...`, `/media/catalog/manifest.json` и
  `/media/catalog/PREPARATION.md` возвращают 404. Произвольный URL
  `/data/catalog/releases/.../manifest.json` возвращает SPA HTML (200),
  **не** байты manifest: этот маршрут не является доступом к данным выпуска.
- Выборочный browser QA на публичном demo: поиск «Массандра Кагор Гурзуф»
  и «Массандра Портвейн белый Алушта» показывает новые изображения; у кагора
  карточка загрузила новый original. Поиск «Брют Розовое Золотая Балка»
  открыл карточку с модельной маской. Три исключения — Mountain Eagle
  Traminer, Vibes Vermentino-Viognier 2022, Союз-Вино Шардоне Сухое —
  находятся поиском и открывают карточки с прежними media. Изображения в
  этих карточках декодируются браузером. Это выборка, не визуальная приёмка
  каждой из 2035 бутылок. Блок рекомендаций возвращал 503 на проверенных
  карточках — отдельное наблюдение, не успех media или поиска по фото.

Дальнейшее продвижение в TEST/PROD требует отдельного точного кандидата,
собственных data/DB/HTTP gates и разрешения по [PIPELINE](../../deploy/PIPELINE.md).
