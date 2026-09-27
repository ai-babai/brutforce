# BE-089 · Прозрачные бутылки: аудит и локальный этап

Состояние на 27.09.2026; [поручение #89](https://github.com/ai-babai/brutforce/issues/89).
Это измерения неизменённого каталога и локальная проба, не выпуск всех 2038 карточек.

## Точный источник и контуры

- `lct_maks` (demo) и `lct_shared` (TEST) — **две** PostgreSQL БД: в обеих
  `catalog_state.version=svoe-20260922-v2`, 2038 `catalog_items`, 2035 различных
  значений `image`, 3 aliases. `catalog_versions.package_sha256` в обеих:
  `badee4d2772083de0861927850d4008ae01c22df058df21facd2fbd559cac927`.
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
Это подготовка alpha, а не оценка модельной маски. Browser QA по новому
полному выпуску ещё не выполнялась.

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
Нет подтверждения лицензии для этого применения; веса **не скачаны**,
revision/weight SHA отсутствуют и не должны выдумываться. Для 102 RGB, одного псевдо-alpha и пяти
непривязанных найти совместимую локальную модель/исходник и проверить маски
на стекле, пробке, контуре и надписях на двух фонах до публикации.

Выпуск: новая версия manifest, полный DQ001–008/DQ011, отдельный snapshot и
атомарный импорт в **каждую** целевую БД по
[PIPELINE](../../deploy/PIPELINE.md), DB/HTTP gates и browser QA.
PROD только по утверждённому точному кандидату. Частичную 24-ID версию
в демо/TEST/PROD не устанавливать.
