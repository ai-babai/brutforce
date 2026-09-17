# Контракт данных Vino

Статус: краткое описание. Канонический исполняемый контракт находится в
[`../../Dataset/CONTRACT.md`](../../Dataset/CONTRACT.md), а реестр источников —
в [`../../Dataset/REGISTRY.yaml`](../../Dataset/REGISTRY.yaml).

## Роли данных

- `catalog_reference` — разрешённые эталонные изображения позиций, из которых
  строится поисковый индекс.
- `train` — изображения, допустимые для обучения/fine-tuning.
- `validation` — выбор модели, preprocessing, гиперпараметров и порогов.
- `public_test` — публичная оценка; не используется для обучения и настройки.
- `holdout` — локальная untouched выборка, доступная только для редких gates.
- `private_test` — закрытая выборка кейсодержателя; не копируется в остальные
  роли и не используется для tuning.

Один файл может иметь только одну evaluation-роль, кроме отдельно обоснованного
`catalog_reference`: эталон участвует в индексе, но не является query-примером.

## Минимальный manifest record

```json
{
  "manifest_version": "1.0.0",
  "source_id": "caseholder-catalog-2026-09",
  "image_id": "img_000001",
  "product_id": "product_000001",
  "slug": "wine-slug",
  "identity_group_id": "identity_000001",
  "near_duplicate_group_id": null,
  "role": "catalog_reference",
  "relative_path": "00_raw/01_svoe_vino_caseholder/example.jpg",
  "sha256": "<64 lowercase hex>",
  "bytes": 0,
  "media_type": "image/jpeg",
  "width": 0,
  "height": 0,
  "source_type": "caseholder",
  "rights_status": "provided_for_case",
  "received_at": "2026-09-15",
  "quality_status": "pending_review",
  "parent_image_id": null
}
```

Закрытые URL, токены, локальные абсолютные пути и персональные данные в
versioned manifest не записываются.

## Инварианты

- `image_id` уникален и неизменяем.
- `slug` совпадает с каталожным API и не выводится из имени файла, если это не
  подтверждено схемой.
- SHA-256 относится к точным байтам файла; производная получает новый `image_id`
  и `parent_image_id`.
- Один SHA-256 не встречается под разными product identity без явного конфликта.
- Все query-изображения имеют expected `slug` либо явную метку unknown.
- Дубликаты и производные не пересекают evaluation splits.
- Near-duplicate family фиксируется до анализа финального holdout либо строится
  прозрачным, versioned алгоритмом.

## Каталожная запись

Минимально ожидаются стабильный `slug`, производитель, название/линейка,
регион, сорт/купаж, описание, рейтинг Роскачества, рекомендация сочетания и
ссылка на эталонное изображение. Реальные поля и nullable-семантика будут
зафиксированы после schema profiling.

## Версионирование

Manifest и split имеют semantic version и SHA-256. Любая замена байтов,
переименование идентичности, изменение ground truth или роли данных создаёт
новую версию и changelog; старый результат эксперимента остаётся связан со
старой версией.
