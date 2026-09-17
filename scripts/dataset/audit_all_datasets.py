#!/usr/bin/env python3
"""Run cross-source integrity gates and produce the authoritative dataset audit."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from common import write_json


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "Dataset/92_reports"


def load_json(path: str) -> dict:
    target = ROOT / path
    return json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}


def load_jsonl(path: str) -> list[dict]:
    target = ROOT / path
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()] if target.is_file() else []


def check(name: str, condition: bool, detail: str) -> dict:
    return {"name": name, "passed": bool(condition), "detail": detail}


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    checks = []

    svoe = load_jsonl("Dataset/01_svoe_vino_catalog/tables/media.jsonl")
    svoe_live = load_jsonl("Dataset/04_svoe_vino_web_enrichment/tables/live_associations.jsonl")
    checks += [
        check("svoe_media_accounting", len(svoe) == 15770 and all(row.get("label_status") in {"gold_exact_asset_key", "ambiguous_shared_catalog_asset", "out_of_scope_site_media"} for row in svoe), f"{len(svoe)} media rows"),
        check("svoe_training_label_gate", all((not row.get("training_candidate")) or (row.get("label_status") == "gold_exact_asset_key" and row.get("decode_status") == "ok") for row in svoe), "training candidates require exact product asset key and successful decode"),
        check("svoe_live_catalog_complete", len(svoe_live) == 2041 and all(row.get("media_id") for row in svoe_live), f"{len(svoe_live)} current sitemap products with media association"),
    ]

    tg = load_jsonl("Dataset/02_rvk_telegram/tables/media.jsonl")
    tg_scenes = [row for row in tg if row.get("source_role") in {"telegram_photo", "telegram_file_image"}]
    checks += [
        check("telegram_media_accounting", len(tg) == 507 and all(row.get("label_status") and row.get("bbox_status") for row in tg), f"{len(tg)} media rows"),
        check("telegram_scene_supervision_gate", all(not row.get("training_candidate") for row in tg_scenes), f"{len(tg_scenes)} scene images explicitly excluded pending annotation"),
    ]

    retail_media = load_jsonl("Dataset/05_retail_alcohol_detection/tables/media.jsonl")
    retail_boxes = load_jsonl("Dataset/05_retail_alcohol_detection/tables/bboxes.jsonl")
    retail_ids = {row["media_id"] for row in retail_media}
    checks += [
        check("retail_images_decode", len(retail_media) == 1884 and all(row.get("decode_status") == "ok" for row in retail_media), f"{len(retail_media)} images"),
        check("retail_image_annotation_accounting", all(
            (row.get("task") == "classification" and row.get("label_status") in {"provided_named_class", "provided_opaque_class"})
            or (row.get("task") == "detection" and row.get("label_status") == "provided_bbox_label" and int(row.get("valid_bbox_count") or 0) > 0)
            for row in retail_media
        ), "every classification image has a class and every detection image has one or more valid boxes"),
        check("retail_bboxes_valid", len(retail_boxes) == 21441 and all(row.get("validation_status") in {"valid", "clipped_rounding"} for row in retail_boxes), f"{len(retail_boxes)} boxes"),
        check("retail_bbox_referential_labels", all(row.get("media_id") in retail_ids and row.get("class_name") for row in retail_boxes), "every box resolves to an image and has a class label"),
    ]

    xmedia = load_jsonl("Dataset/07_x_wines/tables/slim_media.jsonl")
    xru = load_jsonl("Dataset/07_x_wines/tables/slim_russian_products.jsonl")
    xreview = load_jsonl("Dataset/07_x_wines/tables/russian_crosswalk_review.jsonl")
    checks += [
        check("xwines_image_labels", len(xmedia) == 1007 and all(row.get("decode_status") == "ok" and row.get("label_status") == "gold_external_wine_id" for row in xmedia), f"{len(xmedia)} exact WineID labels"),
        check("xwines_russian_subset", len(xru) == 7 and len(xreview) == 7, f"{len(xru)} Russian products; {len(xreview)} visual crosswalk decisions"),
    ]

    rf_media = load_jsonl("Dataset/09_rf100_wine_labels/tables/media.jsonl")
    rf_boxes = load_jsonl("Dataset/09_rf100_wine_labels/tables/bboxes.jsonl")
    rf_ids = {row["media_id"] for row in rf_media}
    checks += [
        check("rf100_images_decode", len(rf_media) == 4643 and all(row.get("decode_status") == "ok" for row in rf_media), f"{len(rf_media)} images"),
        check("rf100_bboxes_valid", len(rf_boxes) == 25034 and all(row.get("validation_status") == "valid" for row in rf_boxes), f"{len(rf_boxes)} boxes"),
        check("rf100_bbox_referential_labels", all(row.get("media_id") in rf_ids and row.get("category_name") for row in rf_boxes), "every box resolves to an image and has an element label"),
        check("rf100_annotation_accounting", all(row.get("annotation_status") in {"has_element_bboxes", "no_bboxes"} for row in rf_media), "every image has element boxes or explicit negative status"),
    ]

    off_media = load_jsonl("Dataset/10_open_food_facts_wine_ru/tables/media.jsonl")
    off_assoc = load_jsonl("Dataset/10_open_food_facts_wine_ru/tables/associations.jsonl")
    checks += [
        check("open_food_facts_downloaded_images", bool(off_media) and all(row.get("decode_status") == "ok" for row in off_media), f"{len(off_media)} selected front images"),
        check("open_food_facts_product_associations", bool(off_assoc) and all(row.get("association_status") in {"exact_off_barcode_record", "no_selected_front_image"} for row in off_assoc), f"{len(off_assoc)} selected product records"),
    ]

    mavt_summary = load_json("Dataset/11_mavt_ru_wines/tables/SUMMARY.json")
    mavt_products = load_jsonl("Dataset/11_mavt_ru_wines/tables/products.jsonl")
    mavt_memberships = load_jsonl("Dataset/11_mavt_ru_wines/tables/catalog_memberships.jsonl")
    mavt_media = load_jsonl("Dataset/11_mavt_ru_wines/tables/media.jsonl")
    mavt_assoc = load_jsonl("Dataset/11_mavt_ru_wines/tables/product_media_associations.jsonl")
    mavt_verification = load_jsonl("Dataset/11_mavt_ru_wines/review/needs_verification/queue.jsonl")
    mavt_annotation = load_jsonl("Dataset/11_mavt_ru_wines/review/needs_annotation/queue.jsonl")
    mavt_product_ids = {row.get("product_id") for row in mavt_products}
    mavt_media_ids = {row.get("media_id") for row in mavt_media}
    checks += [
        check("mavt_full_sitemap_scan", mavt_summary.get("gates", {}).get("full_sitemap_scan_complete") is True and mavt_summary.get("counts", {}).get("product_urls_scanned") == 4780, "4,780/4,780 sitemap product URLs accounted"),
        check("mavt_russian_products", len(mavt_products) == 763 and len(mavt_memberships) == 763 and all(str(row.get("country") or "").casefold().startswith("россия") for row in mavt_products), f"{len(mavt_products)} explicit source-Russia products"),
        check("mavt_product_media_associations", len(mavt_media) == 760 and len(mavt_assoc) == 760 and all(row.get("product_id") in mavt_product_ids and row.get("media_id") in mavt_media_ids for row in mavt_assoc) and all(row.get("decode_status") == "ok" for row in mavt_media), "760 exact primary associations; zero broken references/decode errors"),
        check("mavt_review_accounting", len(mavt_verification) == 2 and len(mavt_annotation) == 3, "2 contradictory origin values and 3 missing-image products are queued"),
    ]

    amwine_summary = load_json("Dataset/15_aromatny_mir_ru_wines/tables/SUMMARY.json")
    amwine_audit = load_json("Dataset/15_aromatny_mir_ru_wines/tables/AUDIT.json")
    amwine_products = load_jsonl("Dataset/15_aromatny_mir_ru_wines/tables/products.jsonl")
    amwine_media = load_jsonl("Dataset/15_aromatny_mir_ru_wines/tables/media.jsonl")
    amwine_assoc = load_jsonl("Dataset/15_aromatny_mir_ru_wines/tables/product_media_associations.jsonl")
    amwine_review = load_jsonl("Dataset/15_aromatny_mir_ru_wines/review/needs_verification/queue.jsonl")
    amwine_product_ids = {row.get("product_id") for row in amwine_products}
    amwine_media_ids = {row.get("media_id") for row in amwine_media}
    checks += [
        check("amwine_product_catalog", len(amwine_products) == 845 and all(row.get("country") == "Россия" and row.get("external_product_id") for row in amwine_products), "845 parsed Russian cards; one removed redirect accounted"),
        check("amwine_gallery_media", len(amwine_media) == 1760 and all(row.get("decode_ok") is True and row.get("media_type") for row in amwine_media), "1,760/1,760 gallery media decoded with explicit MIME"),
        check("amwine_product_media_associations", len(amwine_assoc) == 1760 and all(row.get("product_id") in amwine_product_ids and row.get("media_id") in amwine_media_ids for row in amwine_assoc), "1,760 associations; zero orphan references"),
        check("amwine_source_audit_and_review", amwine_audit.get("passed") is True and all(amwine_audit.get("checks", {}).values()) and len(amwine_review) == 25 and amwine_summary.get("counts", {}).get("products_with_media_association") == 821, "15/15 source checks; 24 missing-image cards plus one shared exact-image group queued"),
    ]

    alk_summary = load_json("Dataset/16_alkoteka_ru_wines/tables/SUMMARY.json")
    alk_products = load_jsonl("Dataset/16_alkoteka_ru_wines/tables/products.jsonl")
    alk_media = load_jsonl("Dataset/16_alkoteka_ru_wines/tables/media.jsonl")
    alk_assoc = load_jsonl("Dataset/16_alkoteka_ru_wines/tables/associations.jsonl")
    alk_review = load_jsonl("Dataset/16_alkoteka_ru_wines/review/needs_verification/queue.jsonl")
    alk_product_ids = {row.get("product_id") for row in alk_products}
    alk_media_ids = {row.get("media_id") for row in alk_media}
    checks += [
        check("alkoteka_fixed_city_snapshot", alk_summary.get("all_checks_pass") is True and len(alk_products) == 727 and len(alk_media) == 727, "727 Russian products/images in fixed Krasnodar context"),
        check("alkoteka_product_media_associations", len(alk_assoc) == 727 and all(row.get("product_id") in alk_product_ids and row.get("media_id") in alk_media_ids and row.get("image_decode_ok") is True for row in alk_assoc), "727 exact product-media associations"),
        check("alkoteka_identity_gate", sum(row.get("eligible_for_source_sku_supervision_by_identity") is True for row in alk_assoc) == 663 and len(alk_review) == 58, "663 eligible; 53 placeholder items and 5 shared-image groups queued"),
    ]

    master_summary = load_json("Dataset/18_russian_wine_master/tables/SUMMARY.json")
    master_products = load_jsonl("Dataset/18_russian_wine_master/tables/products.jsonl")
    master_media = load_jsonl("Dataset/18_russian_wine_master/tables/media.jsonl")
    master_assoc = load_jsonl("Dataset/18_russian_wine_master/tables/associations.jsonl")
    master_verification = load_jsonl("Dataset/18_russian_wine_master/review/needs_verification/queue.jsonl")
    master_annotation = load_jsonl("Dataset/18_russian_wine_master/review/needs_annotation/queue.jsonl")
    external_slug_violations = [row for row in master_assoc if row.get("exact_current_svoe_slug") and row.get("source_dataset") not in {"01_svoe_vino_catalog", "04_svoe_vino_web_enrichment"}]
    checks += [
        check("russian_master_counts", len(master_products) == 6499 and len(master_media) == 9156 and len(master_assoc) == 11005, "6,499 products; 9,156 media refs; 11,005 associations"),
        check("russian_master_integrity", master_summary.get("all_integrity_checks_pass") is True and all(master_summary.get("integrity_checks", {}).values()), "all 18 master integrity checks pass"),
        check("russian_master_identity_and_slug_gates", sum(row.get("identity_eligible") is True for row in master_assoc) == 10719 and not external_slug_violations, "10,719 identity-eligible associations; zero external Svoe slug assignments"),
        check("russian_master_review_queues", len(master_verification) == 552 and len(master_annotation) == 3, "552 verification and 3 annotation tasks"),
    ]

    winesensed = load_json("Dataset/08_winesensed/tables/SUMMARY.json")
    winesensed_ready = bool(winesensed.get("gates", {}).get("russian_filter_complete"))
    checks.append(check("winesensed_russian_filter", winesensed_ready, "complete" if winesensed_ready else "raw 24-shard download/filter still pending"))

    wi126 = load_json("Dataset/06_wine_images_126k/tables/FILTER-SUMMARY.json")
    checks.append(check("wine_images_126k_filter", wi126.get("source_rows") == 125787 and wi126.get("candidates") == 0, "125,787 metadata rows checked; no Russian candidates"))

    review = load_json("Dataset/92_reports/REVIEW-QUEUES-SUMMARY.json")
    received_sources_ready = all(row["passed"] for row in checks)
    completed_retail_sources = [
        "mavt-ru-wines-2026-09-15",
        "aromatny-mir-russian-wine-web",
        "alkoteka-russian-wine-web-2026-09-15-krasnodar",
    ]
    access_blocked_retail_sources = [
        "krasnoe-i-beloe-russian-wine-web",
        "winelab-russian-wine-web",
        "simplewine-russian-wine-web",
        "luding-russian-wine-web",
    ]
    audit = {
        "audit_date": str(date.today()),
        "checks": checks,
        "checks_passed": sum(row["passed"] for row in checks),
        "checks_total": len(checks),
        "all_sources_fully_processed": False,
        "all_received_sources_fully_processed": received_sources_ready,
        "all_allowed_captures_processed": received_sources_ready,
        "completed_retail_sources": completed_retail_sources,
        "sources_blocked_by_access_controls": access_blocked_retail_sources,
        "planned_sources_pending_pilot": access_blocked_retail_sources,
        "all_media_accounted_for": all(row["passed"] for row in checks if row["name"] not in {"winesensed_russian_filter", "open_food_facts_downloaded_images"}),
        "all_media_supervised_ready": False,
        "frozen_split_ready": False,
        "review_queues": review,
        "hard_blockers": [
            "Telegram scene images require manual SKU verification and bottle boxes",
            "Svoe/RF100 near-duplicate and shared-asset groups must be grouped before split",
            "Open Food Facts Russian-production candidates require manual origin verification",
            "K&B, Winelab, SimpleWine and LUDING require official export/permission because declared-client access stopped at 403/401",
            "License-restricted sources must remain separable in manifests and exports",
        ],
    }
    write_json(REPORTS / "DATASET-AUDIT-2026-09-15.json", audit)

    svoe_summary = load_json("Dataset/01_svoe_vino_catalog/tables/SUMMARY.json").get("counts", {})
    live_summary = load_json("Dataset/04_svoe_vino_web_enrichment/tables/SUMMARY.json").get("counts", {})
    tg_summary = load_json("Dataset/02_rvk_telegram/tables/SUMMARY.json").get("counts", {})
    retail_summary = load_json("Dataset/05_retail_alcohol_detection/tables/SUMMARY.json").get("counts", {})
    rf_summary = load_json("Dataset/09_rf100_wine_labels/tables/SUMMARY.json").get("counts", {})
    off_summary = load_json("Dataset/10_open_food_facts_wine_ru/tables/SUMMARY.json").get("counts", {})
    ws_summary = winesensed.get("counts", {})
    cross_summary = load_json("Dataset/92_reports/CROSS-SOURCE-DUPLICATES-SUMMARY.json")
    md = f"""# Аудит датасетов — 2026-09-15

## Короткий вывод

Текущий каталог вин «Своего Вина» обработан полностью по зафиксированному `wines-sitemap.xml`: {live_summary.get('sitemap_urls', 0)} из {live_summary.get('sitemap_urls', 0)} страниц получены и распарсены, ошибок загрузки/парсинга — 0. У всех текущих карточек есть явная связь product→image; {live_summary.get('live_associations_eligible_for_sku_training', 0)} связей проходят автоматический SKU-gate, {live_summary.get('live_associations_with_shared_primary_image', 0)} оставлены на ручную проверку.

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
| Своё Вино, архив | {svoe_summary.get('media', 0)} изображений; {svoe_summary.get('images_gold_labeled', 0)} exact-label; {svoe_summary.get('images_decode_error', 0)} decode error | Базовый каталог {svoe_summary.get('products', 0)} товаров | Не замораживать split до дедупликации/shared review |
| Своё Вино, текущий сайт | {live_summary.get('parsed_products', 0)} карточек; 4 новых изображения | 4 новых товара относительно архива | {live_summary.get('live_associations_eligible_for_sku_training', 0)} связей проходят gate |
| Telegram РВК | {tg_summary.get('media', 0)} изображений, {tg_summary.get('pdf_documents', 0)} PDF; таблицы очищены | 0 verified SKU; {tg_summary.get('scene_images_with_caption_candidates', 0)} слабых кандидатов | Требуется ручная разметка {tg_summary.get('scene_images', 0)} сцен |
| Retail Alcohol Detection | {retail_summary.get('media', 0)} изображений, {retail_summary.get('valid_bboxes', 0)} валидных bottle/product boxes | Нет exact Russian wine SKU | Готов как detector/domain data после split-dedup |
| Wine Images 126K | 125 787 metadata-записей профильтрованы | 0 российских кандидатов | Не добавляется |
| X-Wines Slim 1K | 1 007 exact WineID image-label пар | 7 российских WineID | Готовы внутри X-Wines; cross-source merge запрещён |
| WineSensed | {ws_summary.get('complete_shards', 0)}/{ws_summary.get('expected_shards', 24)} shards, {ws_summary.get('source_rows', 0)} строк проверено | {ws_summary.get('russian_candidate_unique_vintages', 0)} кандидатов | {'Отфильтрован' if winesensed_ready else 'Загрузка/фильтрация не завершена'}; хранить отдельно из-за NC-ND |
| RF100 Wine Labels | {rf_summary.get('media', 0)} изображений, {rf_summary.get('valid_bboxes', 0)} валидных element boxes | Нет SKU/country labels | Готов для label-element detector после near-dup review |
| Open Food Facts | {off_summary.get('decoded_images', 0)} front images | {off_summary.get('russian_brand_candidates', 0)} brand + {off_summary.get('probable_russian_needs_review', 0)} probable | Exact barcode label есть; происхождение требует review |
| МАВТ | 4 780 sitemap-карточек проверено; 763 российских SKU | 760 exact primary images | 2 origin review + 3 missing-image annotation |
| Ароматный Мир | 845 российских SKU; 1 760 gallery images | 1 760 exact source associations | 24 карточки без media + 1 shared-image group в review |
| Алкотека | 727 российских SKU/images, Краснодар | 727 exact source associations | 663 identity-eligible; 58 grouped review tasks |
| Retail access-blocked | K&B 403, Winelab 401, SimpleWine/LUDING 403 | product data не собирались | Нужен официальный export/permission |
| Russian wine master | 6 499 source products; 9 156 media refs | 11 005 associations | 10 719 identity-eligible; 552 verify + 3 annotate |

## Контроль разметки

- Svoe: exact-label имеют только media со статусом `gold_exact_asset_key`; 61 shared-asset изображения исключены; 10 222 site assets явно помечены out-of-scope.
- Retail: все {retail_summary.get('valid_bboxes', 0)} бокса валидны; 139 координат были только подрезаны на epsilon из-за округления YOLO.
- RF100: все {rf_summary.get('valid_bboxes', 0)} бокса валидны; один кадр является явным negative без боксов.
- Telegram: {tg_summary.get('scene_images', 0)} реальных сцен, из них {tg_summary.get('scene_images_with_caption_candidates', 0)} имеют лишь event/caption candidates, verified SKU и bbox пока 0.
- X-Wines: каждая из 1 007 картинок имеет точный внешний WineID; семь российских записей прошли визуальный crosswalk review.
- МАВТ/AMWine/Алкотека: чистым product images bbox не нужен; supervision
  задаётся точной source product→media связью. Missing/placeholder/shared assets
  не считаются молча готовыми и направлены в source/master review queues.

Визуальная spot-check QA выполнена на 12 Retail detection-кадрах и на 12 разных
RF100-изображениях, покрывающих все категории, реально присутствующие в bbox.
Систематического сдвига координат не найдено; RF100 остаётся только auxiliary
набором из-за семантической неоднородности upstream-разметки. Подробности:
`BBOX-VISUAL-QA.md`.

Cross-source audit охватывает {cross_summary.get('total_media_rows', 0)}
media-записей; найдено {cross_summary.get('cross_source_exact_duplicate_groups', 0)}
exact SHA-групп и {cross_summary.get('cross_source_same_dhash_candidate_groups', 0)}
same-dHash кандидатов. Они не должны пересекать split до review; детали —
`CROSS-SOURCE-DUPLICATES-SUMMARY.json` и
`CROSS-SOURCE-DUPLICATES-REVIEW.md`.

## Почему split пока не заморожен

До создания `train/val/test` нужно завершить очереди ручной проверки, построить общий exact/near-duplicate graph и группировать один SKU/винтаж/событие в один split. Иначе одинаковая этикетка или соседние кадры Telegram попадут одновременно в train и test.

Машиночитаемый результат: `DATASET-AUDIT-2026-09-15.json`. Очереди: глобальные
`review_queue_*.jsonl` в этой папке и materialized views в
`Dataset/<NN_source>/review/`.
"""
    (REPORTS / "DATASET-AUDIT-2026-09-15.md").write_text(md, encoding="utf-8", newline="\n")
    print(json.dumps({
        "checks_passed": audit["checks_passed"],
        "checks_total": audit["checks_total"],
        "all_received_sources_fully_processed": audit["all_received_sources_fully_processed"],
        "planned_sources_pending_pilot": len(access_blocked_retail_sources),
    }, ensure_ascii=False, indent=2))
    return 0 if all(row["passed"] for row in checks if row["name"] != "winesensed_russian_filter") else 1


if __name__ == "__main__":
    raise SystemExit(main())
