#!/usr/bin/env python3
"""Prepare a reproducible, read-only source bundle for the wine vision pilot.

It reads authoritative catalog metadata and selected real-scene originals from
Sigma, rejects source hashes present in frozen eval provenance, and writes only
the pilot root.  It makes no model/API calls and never alters the source data.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


REMOTE = "lct@217.26.30.220"
DATASET_ROOT = "/srv/lct/data/roman/vino/current/Dataset"
SOURCE_ID = "caseholder-svoe-vino-2026-09"
ROOT = Path("/Users/skif/ml-data/brutforce/vision-pilot-20260924")
GALLERY = Path("/Users/skif/.codex/worktrees/d0db/v001/projects/brutfors/dataset-examples/dataset-gallery-2026-09-23/manifest.json")
EVAL_PROVENANCE = Path("/Users/skif/ml-data/brutforce/eval-v1/private/provenance-v1.json")

# Every identity link below is a source01 gold association.  The script resolves
# the product/media records at run time instead of copying any inferred linkage.
IDENTITY_SLUGS = [
    "fanagoriya-primum-alveus-blanc-de-blancs-2017-shardone-igristoe-bryut-beloe-12",
    "fanagoriya-fanagoriya-bryut-beloe-sovinon-blan-igristoe-bryut-beloe-11-13",
    "fanagoriya-primum-alveus-brut-2014-shardone-igristoe-bryut-beloe-12",
    "fanagoriya-brule-cuve-brut-rozovoe-merlo-igristoe-bryut-rozovoe-12",
    "fanagoriya-dekanter-rkatsiteli-2019-beloe-suhoe-135",
    "fanagoriya-dekanter-saperavi-2017-krasnoe-suhoe-135",
    "vibes-montepulchano-kaberne-fran-pti-verdo",
    "vibes-riesling-silvaner-2022",
    "zb-vajn-roze-suhoe-rozovoe",
    "zb-vajn-vajt-suhoe-beloe",
]

# These are source paths and screen observations copied verbatim from the
# 2026-09-23 gallery.  They are generic real contexts, never claimed to depict
# the target SKU.  Reuse across jobs is explicit in jobs.jsonl.
SCENES = [
    ("retail-00143", "05_retail_alcohol_detection/media/source_extract/datasets/detection/images/00143.jpg", "8ce9bcae704a425fd65391eb3d27fe3f5573d7ef455bb859fe8cecea5c7fb5ff", {"kind": "retail_shelf", "wine_visible": "yes", "wine_bottles": "multiple", "label_visible": "partial", "non_wine_bottles": "no", "lighting_issue": "none", "angle_or_occlusion": "none", "use_for": "real_scene", "reason": "A well-lit retail shelf densely stocked with many wine bottles, useful as a real-world scene despite small label text."}, {"setting": "retail shelf", "composition": "dense shelf", "label_scale": "small/partial"}),
    ("retail-00126", "05_retail_alcohol_detection/media/source_extract/datasets/detection/images/00126.jpg", "66eacebc410fdc13fe17b1af9ad7688be3977057bef1ffcff769b8bdd647bdff", {"kind": "retail_shelf", "wine_visible": "yes", "wine_bottles": "multiple", "label_visible": "partial", "non_wine_bottles": "yes", "lighting_issue": "none", "angle_or_occlusion": "none", "use_for": "real_scene", "reason": "Retail shelf with many sparkling wine bottles and some non-wine items, labels partially readable."}, {"setting": "retail shelf", "composition": "crowded shelf", "distractors": "other beverages"}),
    ("retail-00030", "05_retail_alcohol_detection/media/source_extract/datasets/detection/images/00030.jpg", "8f5fba1af210873720d75082cb82bfd448ad2ee2978506c1e0a9ba23b4aaf8cd", {"kind": "retail_shelf", "wine_visible": "yes", "wine_bottles": "multiple", "label_visible": "partial", "non_wine_bottles": "uncertain", "lighting_issue": "none", "angle_or_occlusion": "none", "use_for": "real_scene", "reason": "A retail shelf displaying multiple wine bottles with visible labels, suitable as a real-world scene example."}, {"setting": "retail shelf", "composition": "front-facing shelf", "label_scale": "small/partial"}),
    ("retail-00136", "05_retail_alcohol_detection/media/source_extract/datasets/detection/images/00136.jpg", "2a7820ff82af46dda6ffaa988cc42e3e608ee855c45404594312ae6957430dd5", {"kind": "retail_shelf", "wine_visible": "yes", "wine_bottles": "multiple", "label_visible": "partial", "non_wine_bottles": "no", "lighting_issue": "glare", "angle_or_occlusion": "angled", "use_for": "real_scene", "reason": "Retail shelf densely stocked with wine bottles, labels partially readable but many angled or obscured by glare."}, {"setting": "retail shelf", "camera_angle": "angled", "lighting": "glare", "occlusion": "partial"}),
    ("retail-00106", "05_retail_alcohol_detection/media/source_extract/datasets/detection/images/00106.jpg", "f61f0527a83f1818f4a7d37dbf47f290890e2454107af6e5d969aac6e582dc66", {"kind": "retail_shelf", "wine_visible": "yes", "wine_bottles": "multiple", "label_visible": "partial", "non_wine_bottles": "no", "lighting_issue": "glare", "angle_or_occlusion": "angled", "use_for": "real_scene", "reason": "Retail shelf densely stocked with wine bottles, showing real-world lighting and partial label visibility."}, {"setting": "retail shelf", "camera_angle": "angled", "lighting": "glare"}),
    ("telegram-2024-09-28", "00_raw/02_rvk_telegram/ChatExport_2026-09-15/photos/photo_103@28-09-2024_16-42-38.jpg", "c8512306ed1fbc54daadd8cdf1658b2cbdd93da1171627796e058962083226b1", {"kind": "retail_shelf", "wine_visible": "yes", "wine_bottles": "multiple", "label_visible": "clear", "non_wine_bottles": "no", "lighting_issue": "glare", "angle_or_occlusion": "none", "use_for": "real_scene", "reason": "Multiple wine bottles with clear labels are lined up on a retail counter, though window reflections create some glare."}, {"setting": "retail counter", "lighting": "window glare", "composition": "multiple bottles"}),
    ("telegram-2024-08-13", "00_raw/02_rvk_telegram/ChatExport_2026-09-15/photos/photo_80@13-08-2024_23-53-11.jpg", "51b4c7d44a1f139dd77c91c713732bada53e1d8830ec2f1108bb4526e913c169", {"kind": "staged_group", "wine_visible": "yes", "wine_bottles": "multiple", "label_visible": "clear", "non_wine_bottles": "no", "lighting_issue": "glare", "angle_or_occlusion": "none", "use_for": "real_scene", "reason": "A staged row of multiple wine bottles on a table with visible labels and some window glare."}, {"setting": "tabletop lineup", "lighting": "window glare", "composition": "multiple bottles"}),
    ("telegram-2024-12-13", "00_raw/02_rvk_telegram/ChatExport_2026-09-15/photos/photo_134@13-12-2024_10-50-40.jpg", "86d781b95283ca97365b3a7f967e19ae562b361491e7d57f5d756d1bcfa028b3", {"kind": "staged_group", "wine_visible": "yes", "wine_bottles": "multiple", "label_visible": "clear", "non_wine_bottles": "no", "lighting_issue": "glare", "angle_or_occlusion": "none", "use_for": "label_study", "reason": "Staged lineup of multiple wine bottles with readable labels, though window glare and reflections affect lighting."}, {"setting": "tabletop lineup", "lighting": "glare/reflections", "composition": "multiple bottles"}),
    ("telegram-2023-03-27", "00_raw/02_rvk_telegram/ChatExport_2026-09-15/photos/photo_4@27-03-2023_11-46-32.jpg", "24de6345ab55972d5e91d121691a248e4ae658113d5275cbed51e7b5f397a56f", {"kind": "candid_scene", "wine_visible": "yes", "wine_bottles": "multiple", "label_visible": "clear", "non_wine_bottles": "no", "lighting_issue": "glare", "angle_or_occlusion": "angled", "use_for": "real_scene", "reason": "Candid event photo showing multiple wine bottles with readable labels, though some glare and angled perspectives are present."}, {"setting": "candid event", "camera_angle": "angled", "lighting": "glare"}),
]

SCENARIO_PAIRS = [
    ("retail_shelf_partial_label", "retail-00143", {"setting": "retail shelf", "target_object_count": 1, "label_visibility": "partial but readable", "other_bottles": "present"}),
    ("tabletop_glare", "telegram-2024-08-13", {"setting": "tabletop", "target_object_count": 1, "lighting": "window glare/reflections", "label_visibility": "readable"}),
    ("crowded_shelf", "retail-00126", {"setting": "crowded retail shelf", "target_object_count": 1, "other_beverages": "present", "label_visibility": "small but readable"}),
    ("counter_glare", "telegram-2024-09-28", {"setting": "retail counter", "target_object_count": 1, "lighting": "window glare", "label_visibility": "readable"}),
    ("front_shelf", "retail-00030", {"setting": "front-facing retail shelf", "target_object_count": 1, "label_visibility": "partial but readable"}),
    ("angled_glare_shelf", "retail-00136", {"setting": "retail shelf", "target_object_count": 1, "camera_angle": "angled", "lighting": "glare", "occlusion": "partial"}),
    ("lineup_reflections", "telegram-2024-12-13", {"setting": "tabletop lineup", "target_object_count": 1, "lighting": "glare/reflections", "label_visibility": "readable"}),
    ("candid_angled", "telegram-2023-03-27", {"setting": "candid event", "target_object_count": 1, "camera_angle": "angled", "lighting": "glare", "label_visibility": "readable"}),
    ("angled_shelf_glare", "retail-00106", {"setting": "retail shelf", "target_object_count": 1, "camera_angle": "angled", "lighting": "glare", "label_visibility": "partial but readable"}),
    ("tabletop_glare_alt", "telegram-2024-08-13", {"setting": "tabletop", "target_object_count": 1, "lighting": "window glare", "composition": "closer crop", "label_visibility": "readable"}),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> str:
    return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE).stdout


def eval_hashes() -> set[str]:
    # The frozen provenance file is inspected only for hashes; no case labels or
    # evaluation answers are read into the pilot manifest.
    return set(re.findall(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", EVAL_PROVENANCE.read_text()))


def remote_catalog() -> dict[str, dict]:
    payload = r'''import json
base="/srv/lct/data/roman/vino/current/Dataset/01_svoe_vino_catalog/tables/"
want=set(json.loads(r''' + repr(json.dumps(IDENTITY_SLUGS)) + r'''))
products={}
with open(base+"products.jsonl") as f:
  for line in f:
    row=json.loads(line)
    if row.get("slug") in want: products[row["product_id"]]=row
media={}
with open(base+"media.jsonl") as f:
  for line in f:
    row=json.loads(line); media[row["media_id"]]=row
found={}
with open(base+"associations.jsonl") as f:
  for line in f:
    a=json.loads(line); product=products.get(a.get("product_id")); image=media.get(a.get("media_id"))
    if not product or not image or product["slug"] in found: continue
    if a.get("grade")!="gold" or not a.get("eligible_for_supervised_training"): continue
    if image.get("variant")!="original" or image.get("resource_status")!="ok" or image.get("decode_status")!="ok": continue
    if image.get("mode")!="RGB": continue
    found[product["slug"]]={"product":product,"association":a,"media":image}
print(json.dumps(found,ensure_ascii=False))'''
    encoded = base64.b64encode(payload.encode()).decode()
    remote_command = f"python3 -c \"import base64;exec(base64.b64decode('{encoded}'))\""
    return json.loads(run(["ssh", "-o", "BatchMode=yes", REMOTE, remote_command]))


def copy_remote(relative_path: str, destination: Path) -> None:
    remote_path = f"{REMOTE}:{DATASET_ROOT}/{relative_path}"
    subprocess.run(["scp", "-q", "-o", "BatchMode=yes", remote_path, str(destination)], check=True)


def scaled_rgb(source: Path, destination: Path) -> tuple[int, int, str]:
    with Image.open(source) as image:
        width, height = image.size
        rgb = image.convert("RGB")
        rgb.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        rgb.save(destination, "WEBP", quality=92, method=6)
    return width, height, sha256(destination)


def row_common(image_id: str, role: str, path: str, digest: str, source_group: str, source: dict, observed: dict) -> dict:
    return {
        "image_id": image_id, "role": role, "path": path, "thumbnail_path": None,
        "origin": "real", "slug": None, "scenario_ids": [], "identity_reference_id": None,
        "scene_reference_id": None, "requested_conditions": {}, "observed_conditions": observed,
        "model": None, "provider": None, "cost_usd": None, "latency_ms": None,
        "qc": {"status": "pending", "reason": "Requires visual review before generation."},
        "split": "train_candidate", "parent_ids": [], "source": source,
        "sha256": digest, "source_group": source_group,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root
    identity_dir = root / "refs" / "identity"
    scene_dir = root / "refs" / "scenes"
    identity_dir.mkdir(parents=True, exist_ok=True)
    scene_dir.mkdir(parents=True, exist_ok=True)
    forbidden_hashes = eval_hashes()
    catalog = remote_catalog()
    missing = set(IDENTITY_SLUGS) - set(catalog)
    if missing:
        raise RuntimeError(f"Missing suitable gold/original identity sources: {sorted(missing)}")

    rows, source_rows, identity_ids, scene_ids = [], [], {}, {}
    with tempfile.TemporaryDirectory(prefix="vision-pilot-sources-") as temporary:
        temporary_dir = Path(temporary)
        for index, slug in enumerate(IDENTITY_SLUGS, 1):
            record = catalog[slug]
            product, association, media = record["product"], record["association"], record["media"]
            raw = temporary_dir / f"identity-{index}.source"
            copy_remote(media["relative_path"], raw)
            if sha256(raw) != media["sha256"]:
                raise RuntimeError(f"Source hash mismatch for {slug}")
            image_id = f"identity-{index:02d}-{slug}"
            local = identity_dir / f"{index:02d}-{slug}.webp"
            source_width, source_height, local_hash = scaled_rgb(raw, local)
            source = {
                "source_id": SOURCE_ID, "source_uri": f"dataset://{SOURCE_ID}/{media['relative_path']}",
                "product_id": product["product_id"], "association_id": association["association_id"],
                "association_grade": association["grade"], "association_method": association["method"],
                "eligible_for_supervised_training": association["eligible_for_supervised_training"],
                "media_id": media["media_id"], "asset_group_id": media["asset_group_id"],
                "source_sha256": media["sha256"], "source_dimensions": {"width": source_width, "height": source_height},
                "source_mode": media["mode"], "source_variant": media["variant"],
                "label_status": media["label_status"],
                "catalog_text": {key: product.get(key) for key in ("wine_name", "winery", "category", "color", "region", "grapes", "description", "photo_filenames")},
                "uncertainty": {"vintage": "Use only if readable on the label; catalog name may contain a year but it is not separately verified.", "label_readability": "pending visual review"},
            }
            row = row_common(image_id, "identity_reference", str(local.relative_to(root)), local_hash, "source01_svoe_catalog", source, {"kind": "clean_catalog_reference", "wine_visible": "yes", "wine_bottles": "one", "label_visible": "pending_visual_review"})
            row["slug"] = slug
            rows.append(row); source_rows.append({"image_id": image_id, "role": row["role"], "path": row["path"], "source": source, "sha256": local_hash})
            identity_ids[slug] = image_id

        for index, (scene_id, relative_path, expected_hash, observed, intended) in enumerate(SCENES, 1):
            if expected_hash in forbidden_hashes:
                raise RuntimeError(f"Scene is in frozen eval provenance: {scene_id}")
            raw = temporary_dir / f"scene-{index}.source"
            copy_remote(relative_path, raw)
            actual_hash = sha256(raw)
            if actual_hash != expected_hash:
                raise RuntimeError(f"Gallery/source hash mismatch for {scene_id}")
            local = scene_dir / f"{index:02d}-{scene_id}.webp"
            source_width, source_height, local_hash = scaled_rgb(raw, local)
            image_id = f"scene-{index:02d}-{scene_id}"
            source = {
                "source_id": "dataset-2026-09-17", "source_uri": f"dataset://dataset-2026-09-17/{relative_path}",
                "source_sha256": actual_hash, "source_dimensions": {"width": source_width, "height": source_height},
                "gallery_manifest": str(GALLERY), "training_eligibility": "unverified_for_generation; selected as real-scene reference only",
                "exact_target_sku_link": None, "uncertainty": {"target_sku_in_source_scene": "not asserted", "scene_observation": "gallery screen note, pending visual review"},
            }
            row = row_common(image_id, "scene_reference", str(local.relative_to(root)), local_hash, "real_scene", source, observed)
            row["requested_conditions"] = intended
            rows.append(row); source_rows.append({"image_id": image_id, "role": row["role"], "path": row["path"], "source": source, "sha256": local_hash})
            scene_ids[scene_id] = image_id

    jobs = []
    for index, slug in enumerate(IDENTITY_SLUGS, 1):
        product = catalog[slug]["product"]
        producer = product.get("winery") or ""
        wine = product.get("wine_name") or ""
        pair_start = (2 * (index - 1)) % len(SCENARIO_PAIRS)
        selected_scenarios = [
            SCENARIO_PAIRS[pair_start],
            SCENARIO_PAIRS[(pair_start + 1) % len(SCENARIO_PAIRS)],
        ]
        for scenario_name, scene_key, conditions in selected_scenarios:
            job_number = len(jobs) + 1
            jobs.append({
                "job_id": f"pilot-{job_number:03d}-{slug}-{scenario_name}", "slug": slug,
                "identity_reference_id": identity_ids[slug], "scene_reference_id": scene_ids[scene_key],
                "scenario_ids": [scenario_name], "requested_conditions": conditions,
                "prompt": f"Use the identity reference as the sole product-identity authority and the scene reference only for setting, lighting, and camera feel. Create one target bottle only: {producer} — {wine}. Preserve every visible producer, wine-name, and vintage character exactly as in the identity reference; do not invent a vintage if it is not readable. Put the target bottle in a believable {conditions['setting']} scene. Keep the target label readable enough for recognition. Do not copy any other bottle, label, logo, or text from the scene reference.",
            })

    for path, content in ((root / "refs-manifest.jsonl", rows), (root / "sources.jsonl", source_rows), (root / "jobs.jsonl", jobs)):
        path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in content))
    print(json.dumps({"root": str(root), "identities": len(identity_ids), "scenes": len(scene_ids), "jobs": len(jobs), "eval_hashes_checked": len(forbidden_hashes)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
