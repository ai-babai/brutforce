# Локальный комплект данных BrutForce · 28.09.2026

Комплект доступен в [папке Яндекс Диска](https://disk.yandex.ru/d/dHAXDPcitS-ZJQ).
Скачайте **все 14 файлов** в одну директорию, сохранив имена: пять обычных
архивов из таблицы, шесть частей архива весов, `README.ru.md`,
`02-recognition-weights.tar.sha256` и `SHA256SUMS`. Цельного
`02-recognition-weights.tar` в папке нет. Публичный доступ к файлам не
устанавливает права на распространение моделей, каталога и фотографий.
Архивы создаются вне Git; пароли, пользовательские загрузки, gold и фото
конкурсных запросов в комплект не включены.

## Что находится в комплекте

| Архив | Назначение после распаковки |
|---|---|
| `01-recognition-data.tar.gz` | `f8-bundle/overlay`, `catalog`, `index`, `ocr`: slug организаторов, OCR-данные и **готовый визуальный индекс**; без Python-кода |
| `02-recognition-weights.tar.part-000` … `005` | Шесть частей одного tar-архива: `f8-bundle/onnx` и `models/hub`, ONNX и закреплённые веса детектора/энкодеров |
| `03-display-catalog.tar.gz` | `catalog-package`: 2 038 карточек витрины и release manifest |
| `04-display-media.tar` | `catalog-media`: ровно 12 201 WebP, перечисленных в manifest (три размера) |
| `05-text-recommendations.tar.gz` | `recommendations/index.json`: отдельная таблица 2 038 наборов похожих карточек, **не** визуальный индекс |
| `06-visual-index-inputs.tar.gz` | `visual-build-inputs/`: промежуточный индекс, регионы и решения для пересборки (только данные) |

После распаковки архивов по инструкции ниже получается такая структура:

```text
brutforce/apps/vision/                КОД CPU-СЕРВИСА (из Git, не в архиве)
|-- overlay/night_server.py          HTTP + OCR rescue
|-- overlay/spec/lexicon.json        Фиксированные правила OCR
`-- parent/*.py                      Детектор, эмбеддинг и поиск

~/brutforce-local/                    ДАННЫЕ ДЛЯ ПОЛНОГО РЕЖИМА (вне Git)
|-- f8-bundle/                         Веса, OCR и каталог распознавателя
|   |-- onnx/, models/hub/, ocr/       Веса и данные для инференса/OCR
|   |-- index/index.npz               Готовые векторы фото организаторов
|   `-- catalog/catalog-bundle.json   Эталоны и slug организаторов
|-- catalog-package/                  Карточки и manifest витрины (импорт в БД)
|-- catalog-media/{400,800,original}/ WebP карточек приложения, НЕ фото для индекса
|-- recommendations/index.json        Рекомендации по карточкам, НЕ ML-векторы
|-- visual-build-inputs/              Только промежуточные входы пересборки
`-- secrets/                          Пароли создаются отдельно; их нет в архиве
```

`SHA256SUMS` содержит SHA-256 остальных 13 скачиваемых файлов;
`02-recognition-weights.tar.sha256` — SHA-256 потока цельного архива весов.
Внешний набор содержит
32 зафиксированных файла данных; проверка их отдельных SHA находится в
`deploy/assets/f8-cpu.sha256` **репозитория**. Python-код и OCR-правила находятся
в `apps/vision/` репозитория и собираются в Docker-образ. Эталонных фотографий организаторов для
**пересборки** визуального индекса в комплекте нет; это не мешает использовать
уже готовый `f8-bundle/index/index.npz`.

## Как восстановить на Linux

Нужен отдельный клон **репозитория BrutForce** (код не лежит в
архиве). На Linux-машине с Python 3.11+, GNU `sha256sum` и `tar`,
из каталога со всеми 14 файлами:

```sh
sha256sum -c SHA256SUMS
cat 02-recognition-weights.tar.part-??? | sha256sum -c 02-recognition-weights.tar.sha256
DATA_ROOT="$HOME/brutforce-local"
mkdir -p "$DATA_ROOT"
tar -xf 01-recognition-data.tar.gz -C "$DATA_ROOT"
cat 02-recognition-weights.tar.part-??? | tar -xf - -C "$DATA_ROOT"
for archive in 03-display-catalog.tar.gz 04-display-media.tar \
               05-text-recommendations.tar.gz 06-visual-index-inputs.tar.gz; do
  tar -xf "$archive" -C "$DATA_ROOT"
done
```

Части весов читаются по порядку и распаковываются потоком, без временной
копии цельного tar. Не запускайте распаковку по `*.tar*`: части не являются
отдельными архивами. Если `SHA256SUMS` не проходит, не распаковывайте файлы.

Затем из корня клона репозитория в том же терминале:

```sh
python3 scripts/asset-bundle.py verify "$DATA_ROOT/f8-bundle"
sha256sum "$DATA_ROOT/recommendations/index.json"
sha256sum "$DATA_ROOT/catalog-package/manifest.json"
```

Последние два SHA должны быть соответственно
`f05f16c7790782ec3c1b50047bba4e29f1d906217f63846c217d5516e6ef8e7f`
и `d88c4454a46802490ee2f69e32d2fb28fd8816d23a6d4d554356697632f845ef`.
Проверка `sha256sum -c` обнаруживает битый архив, а `asset-bundle.py verify`
сверяет его содержимое. Медиа также сверяются с `catalog-package/manifest.json`
при сборке архива и импортом каталога при запуске.

Из корня клона выполните:

```sh
sh scripts/docker-local.sh init "$DATA_ROOT"
sh scripts/docker-local.sh up
sh scripts/docker-local.sh smoke
```

`init` создаёт локальные пароли и файл `deploy/.env.local` с путями к
распакованным данным, не перезаписывая уже созданную конфигурацию. Для этого
закреплённого комплекта версии и SHA из `deploy/docker.env.example` менять не
нужно. `up` включает `preflight` с проверкой SHA и Compose-конфигурации.
Откройте <http://127.0.0.1:8097/>.

Полная инструкция по требованиям хоста, проверке известного фото и ручному
режиму — `docs/SELF-HOST.ru.md` в репозитории. Полный Compose с распакованным
комплектом прошёл health/catalog smoke на Mac/OrbStack (linux/amd64). На
отдельном чистом Linux полный прогон по известному фото **ещё не подтверждён**;
preflight доказывает целостность байтов, но не точность или OCR-паритет. Локальный
`stop`/`down` не удаляет volumes и не затрагивает серверы команды.

## Как заново построить индексы

### Рекомендации по текстам и атрибутам витрины

Нужны `catalog-package/wines.jsonl`, `catalog-package/catalog.json` и
`f8-bundle/index/index-info.json`; модель и изображения для этого **не нужны**.
Офлайновый Python-скрипт вычисляет совместимые пары и десятку соседей на
карточку: тип+цвет+сладость, ограничение по крепости, затем сорта, мотивы
описания, регион и производитель. Спорные поля исключаются явно. Выход —
JSON `catalogVersion`, `modelVersion`, `indexVersion`, `neighbors`; последний
токен indexVersion нужен текущей проверке совместимости Go API, не означает
визуальное ранжирование.

```sh
python3 scripts/build-text-recommendations.py \
  --wines "$DATA_ROOT/catalog-package/wines.jsonl" \
  --index-info "$DATA_ROOT/f8-bundle/index/index-info.json" \
  --out "$DATA_ROOT/recommendations/rebuilt.json"
sha256sum "$DATA_ROOT/recommendations/rebuilt.json"
```

На данном снимке 2 038 карточек пересборка даёт **точно** SHA
`f05f16c7790782ec3c1b50047bba4e29f1d906217f63846c217d5516e6ef8e7f`.
Для обновлённого каталога хеш и качество рекомендаций будут другими: сначала
проверьте спорные поля и пары, затем обновляйте закреплённые версии/хеши
в своём выпуске. Это не просто сохранение полей карточек в JSON.

### Визуальный индекс по эталонным изображениям организаторов

Файл `f8-bundle/index/index.npz` содержит массивы `full`, `label` и `slugs`
в порядке 2 103 эталонных позиций: нормализованные векторы целой бутылки и
вырезки этикетки SigLIP2 SO400M/384, 1 152 измерения; 2 060 позиций доступны,
43 помечены как недоступные/исключённые. `index-info.json` хранит версии
энкодера, crop policy и SHA каталога/промежуточных данных. Это **не** JSON
карточек и не картинки интерфейса `catalog-media/`.

Для воспроизведения с нуля нужны: каталог `f8-bundle/catalog/catalog-bundle.json`,
**отдельные оригинальные 2 060 проверенных reference WebP** организаторов в
`IMAGE_DIR/images/<slug>.webp`, промежуточный Base224 v2 индекс, файл
`label-regions.jsonl`, решения об исключении reference и исходный PyTorch
чекпойнт `google/siglip2-so400m-patch16-384` ревизии
`dd658faac399427308559e2c3ac1e99cbe43845d`. Последний **не** входит в
runtime bundle: там ONNX для обслуживания запросов; HF snapshots в архиве
относятся к другим трём моделям. Для генератора нужны Python-библиотеки из
ML-окружения (NumPy, PyTorch, Transformers, Pillow). Перечисленные
промежуточные индекс/регионы/решения включены в `visual-build-inputs/`,
а reference WebP и PyTorch-чекпойнт — **не включены**; готовая пересборка без
них сейчас недоступна. Подменять их картинками витрины нельзя.

Когда появятся разрешённые оригиналы и чекпойнт, разместите изображения
под `IMAGE_DIR/images/` с указанными в каталоге SHA и установите чекпойнт
в локальный HF cache; затем из независимого ML-окружения:

```sh
python3 scripts/build-visual-index.py \
  --code-root apps/vision --bundle "$DATA_ROOT/f8-bundle" \
  --inputs "$DATA_ROOT/visual-build-inputs" \
  --image-dir "$IMAGE_DIR" --out "$DATA_ROOT/visual-index-new" --device cuda
```

Скрипт проверяет SHA входов и каждого доступного reference WebP **до**
загрузки модели и запускает исходный `apps/vision/parent/so400m_ablation.py`
в режиме `--phase index`. Для отдельной проверки входов добавьте
`--check-only`. Новый индекс записывается в другой каталог; не заменяйте
рабочий `f8-bundle/index/` без проверки версии, SHA и качества результатов.
