# Реестр источников данных Vino

Канонический машинно-читаемый реестр: [`../../Dataset/REGISTRY.yaml`](../../Dataset/REGISTRY.yaml).
Здесь остаётся краткий обзор для навигации. Секреты, закрытые ссылки и локальные
абсолютные пути запрещены.

Режим проекта — некоммерческое исследование. Он не заменяет лицензию и не даёт
автоматического права распространять исходники или производные.

| № | Source ID | Роль | Статус | Raw/manifest |
|---:|---|---|---|---|
| — | `caseholder-tz-2026-09` | исходное ТЗ | verified | `10. РСХБ.Цифра.pdf` |
| 01 | `caseholder-svoe-vino-2026-09` | каталог, эталоны, case eval | received/profiled | `Dataset/00_raw/01_...`, raw manifest v1 |
| 02 | `rvk-telegram-2026-09-15` | field images, события и оценки | received/profiled | `Dataset/00_raw/02_...`, raw manifest v1 |
| 03 | `manual-store-captures` | контролируемые полочные фото | planned | reserved |
| 04 | `svoe-vino-web-snapshots` | только закрытие пробелов | planned after gap audit | reserved |
| 05 | `retail-alcohol-detection-kaggle` | retail domain/detection | registered, not downloaded | reserved |
| 06 | `wine-images-126k-hf` | clean bottle/image-text | registered, not downloaded | reserved |
| 07 | `x-wines` | metadata/recommendations/labels | registered, not downloaded | reserved |
| 08 | `winesensed-hf` | research-only multimodal pilot | registered, not downloaded | reserved |
| 09 | `rf100-wine-labels` | label elements/OCR | registered, not downloaded | reserved |
| 10 | `open-food-facts-wine-ru` | selected Russian wine products | registered, not downloaded | reserved |

Подробная оценка внешних кандидатов: [`EXTERNAL-DATASETS-ASSESSMENT.md`](EXTERNAL-DATASETS-ASSESSMENT.md).
