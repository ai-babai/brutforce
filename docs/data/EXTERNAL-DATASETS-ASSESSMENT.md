# Оценка дополнительных датасетов

Дата проверки публичных карточек: 2026-09-15. Цель проекта — некоммерческое
обучение/исследование. Оценка ниже определяет техническую роль, но не является
юридическим заключением.

## Вывод

Ни один внешний набор не заменяет основной контур «эталон каталога → реальное
query-фото → точный slug». Лучший порядок вложения усилий:

1. нормализовать архив «Своё Вино» и Telegram РВК;
2. вручную снять контролируемый holdout и hard cases;
3. пилотировать Retail Alcohol Detection для retail-domain features;
4. metadata-first отфильтровать Open Food Facts;
5. использовать RF100 как OCR/detection auxiliary task;
6. проверять Wine Images/X-Wines только малой выборкой;
7. WineSensed оставить низкоприоритетным research-only pilot.

## Сравнение

| Источник | Близость к задаче | Сильная сторона | Главный пробел/риск | Решение |
|---|---:|---|---|---|
| Retail Alcohol Detection | высокая для сцены, низкая для slug | российские реальные полки, clutter/occlusion | неизвестны публичные точные schema/count | pilot первым из внешних |
| Open Food Facts | средняя/высокая после фильтра | открытые product metadata + фото | неоднородное качество, BY-SA/ODbL | фильтровать metadata, не скачивать весь bucket |
| RF100 Wine Labels | средняя как auxiliary | 4 643 image, 12 областей этикетки | не exact-SKU и не российский каталог | OCR/crop baseline |
| Wine Images 126K | средняя как pretrain | 107 821 clean product images с text links | Russian coverage и underlying photo rights неизвестны | sample/streaming audit |
| X-Wines | низкая/средняя | 100 646 wines и 21M ratings | editions/licenses и image coverage различаются | metadata pilot после выбора edition |
| WineSensed | низкая/средняя | 1M multimodal records | 35.8 GB, CC BY-NC-ND, sparse card | только малый research pilot |

## 05 — Retail Alcohol Detection Dataset

[Карточка Kaggle](https://www.kaggle.com/datasets/axlifreeway/retail-alcohol-detection-dataset)
указывает российские розничные фото алкоголя и MIT. Проверенный API-card размер
— 965 326 532 байта, обновление — 2025-09-03. Это наиболее полезный внешний
набор для domain adaptation, product/bottle detection и hard negatives. Он не
даёт соответствия конкретным slug. До полной загрузки проверить annotation
format, точное число изображений, состав wine class, дубли и лицензионные файлы.

## 06 — Wine Images Dataset 126K

[Карточка Hugging Face](https://huggingface.co/datasets/cipher982/wine-images-126k)
заявляет 107 821 image records, связанные стабильными ID с текстовым набором, и
CC BY 4.0. Текущий file listing показывает около 12.5 GB, тогда как текст
карточки упоминает около 5.8 GB — размер нужно подтвердить при intake. Набор
годится для общего bottle/image-text pretraining. Сначала проверить Russian
coverage и права на retailer-originated фотографии, отдельно от лицензии
компиляции.

## 07 — X-Wines

[Основной репозиторий](https://github.com/rogerioxavier/X-Wines) заявляет
100 646 вин, 21 013 536 рейтингов и 62 страны; основной корпус прежде всего
табличный. Репозиторий показывает CC0-1.0 и просит цитирование. У
[Kaggle slim edition](https://www.kaggle.com/datasets/rogerioxavier/x-wines-slim-version)
иная лицензионная маркировка базы/содержимого, а в репозитории отдельно есть
архив label images для test subset. Поэтому нельзя смешивать editions под одним
правовым статусом. Сначала выбрать конкретный релиз и проверить фактическое
image/Russian coverage.

## 08 — WineSensed

[Карточка Hugging Face](https://huggingface.co/datasets/christopher/winesensed)
показывает 1 018 017 multimodal records, около 35.8 GB и лицензию
CC BY-NC-ND 4.0. Некоммерческий режим соответствует `NC`, но `ND` остаётся:
публикация преобразованного subset/разметки или передача производных требует
отдельной проверки. До решения допустим только локальный streaming pilot без
распространения.

## 09 — RF100 Wine Labels

[Roboflow Universe](https://universe.roboflow.com/roboflow-100/wine-labels)
указывает 4 643 object-detection images, CC BY 4.0 и 12 классов элементов
этикетки: maker, appellation/region, country, logo, vintage, alcohol, sweetness,
type и другие. Это хороший auxiliary набор для поиска области этикетки и OCR,
но он не решает exact wine recognition.

## 10 — Open Food Facts Images

[Официальный AWS registry](https://registry.opendata.aws/openfoodfacts-images/)
даёт открытый S3 image corpus с ежемесячными обновлениями и CC BY-SA для
изображений. Структурированная база Open Food Facts отдельно распространяется
под ODbL. Эффективная стратегия: сначала отфильтровать metadata по wine,
стране/рынку и производителям, затем загрузить только связанные изображения.
Полный bucket для этой задачи избыточен.

## Gate перед загрузкой любого внешнего источника

- точная edition/version и карточка лицензии сохранены;
- оценены размер, format/schema, image count и Russian coverage;
- сформулирована конкретная роль в pipeline и критерий полезности pilot;
- raw path зарезервирован, источник включён в registry;
- явно разделены training, derivative и redistribution rights;
- источник не смешивается с `test`, `holdout` и caseholder evaluation.
