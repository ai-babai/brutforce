# Handoff VINO-006 — AMWine 1.0.0

- Результат: robots-aware snapshot «Ароматного Мира» собран. 845 российских
  карточек имеют точный external SKU и явное поле `Страна: Россия`; все 1 760
  опубликованных gallery images скачаны, декодируются и связаны с product ID.
- Изменённые файлы: `scripts/dataset/crawl_amwine.py`,
  `Dataset/00_raw/15_aromatny_mir_ru_wines/2026-09-15/**`,
  `Dataset/15_aromatny_mir_ru_wines/**`, этот каталог run.
- Данные/артефакты: `source_id=aromatny-mir-russian-wine-web`,
  `source_capture_id=amwine_20260915_001`, dataset `1.0.0`; 2 782 файла в
  safe raw manifest, его SHA-256
  `2ba8edefcd14b5405d326a22260477d473447b61d16f2fb95448445e384d6bf3`.
  Два policy-status файла входят в тот же manifest.
- Проверки: `py_compile` — exit 0; crawler final rebuild — exit 0;
  `tables/AUDIT.json` — `passed=true`, 17/17 checks; повторный SHA-256 audit
  2 782 raw-manifest записей — 0 missing/mismatch; 1 760/1 760 images имеют
  `decode_ok=true` и явный MIME; orphan product/media associations — 0.
  Визуально проверены
  четыре представления одного SKU и один exact-duplicate hard case.
- Не проверено: не выполнена ручная проверка всех gallery images, межисточниковая
  family/variant/rebrand привязка и сопоставление со «Своё Вино»; условия
  обучения/производных и перераспространение требуют отдельного review.
- Риски/допущения: 24 карточки не публикуют изображение; одна выбранная sitemap
  позиция перенаправляет в категорию и учтена как failure; один exact image
  опубликован для двух разных SKU (брют/полусухое) и исключён из доверенного
  exact-SKU использования до проверки. Счётчики 650+234+2 на листингах выше
  фактических уникальных URL; 117 Russia+brand sitemap-фасетов не расширили
  найденное множество.
- Следующий шаг: `qa_evaluator` независимо проверяет 25 задач в
  `review/needs_verification/queue.jsonl`, начиная с cross-product duplicate,
  затем identity curator строит `wine_family_id`/rebrand связи с другими
  retail-источниками.
