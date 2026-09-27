#!/usr/bin/env python3
"""Prepare an immutable catalog-release-1 alpha overlay from reviewed local originals.

Selections are private JSONL: {id, path, sha256, source_ref}. No network or ML
inference is performed here. Without --write the command only checks inputs.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from PIL import Image, ImageOps, features

from catalog_data import json_bytes, safe_file, sha


ROLES = {"thumbnail": ("400", 400), "card": ("800", 800), "original": ("original", 1600)}
HEX = re.compile(r"[a-f0-9]{64}\Z")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SOURCE_REF = re.compile(r"[A-Za-z0-9_:./-]{1,200}\Z")
REPO = Path(__file__).resolve().parent.parent


def image_spec(data, role):
    digest = hashlib.sha256(data).hexdigest()
    with Image.open(io.BytesIO(data)) as im:
        im.load()
        width, height = im.size
        if im.format != "WEBP" or "A" not in im.getbands():
            raise ValueError("encoded image has no real transparency")
        verify_alpha(im)
        if max(width, height) > ROLES[role][1] or width * height > 25_000_000 or len(data) > 20 << 20:
            raise ValueError("encoded image exceeds catalog bounds")
    return {"path": f"{ROLES[role][0]}/{digest}.webp", "sha256": digest,
            "bytes": len(data), "width": width, "height": height, "mime_type": "image/webp"}


def verify_alpha(im):
    alpha = im.getchannel("A")
    histogram = alpha.histogram()
    pixels = im.width * im.height
    if (sum(histogram[:16]) < pixels // 100 or sum(histogram[240:]) < pixels // 100
            or alpha.getpixel((0, 0)) > 15):
        raise ValueError("source needs visible bottle and truly transparent background; manual review required")


def encode_selection(path, expected):
    if sha(path) != expected:
        raise ValueError("selection SHA256 mismatch")
    if path.stat().st_size > 20 << 20:
        raise ValueError("selection exceeds input byte bound")
    with Image.open(path) as original:
        # Some upstream originals are larger than the public 25 MP bound;
        # decode at most 40 MP, then downsize to the existing 1600 px limit.
        if original.width * original.height > 40_000_000:
            raise ValueError("selection exceeds pixel bound")
        oriented = ImageOps.exif_transpose(original)
        rgba = oriented.convert("RGBA")
        verify_alpha(rgba)
        if max(rgba.size) > 1600:
            rgba.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        result = {}
        for role, (_, bound) in ROLES.items():
            target = rgba.copy()
            if role != "original":
                target.thumbnail((bound, bound), Image.Resampling.LANCZOS)
            # Preserve the exact upstream WebP when no orientation/resize is needed.
            if role == "original" and original.format == "WEBP" and original.size == target.size and oriented.size == original.size and original.getexif().get(274, 1) == 1:
                data = path.read_bytes()
            else:
                out = io.BytesIO()
                target.save(out, format="WEBP", quality=82, method=6, exact=True)
                data = out.getvalue()
            result[role] = (image_spec(data, role), data)
        return result


def install_media(root, key, data, digest):
    parent = root / "media" / key.split("/")[0]
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("media role directory is missing or symlinked")
    target = root / "media" / key
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or sha(target) != digest:
            raise ValueError("existing content-addressed media differs")
        return
    fd, name = tempfile.mkstemp(prefix=".alpha-", dir=parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.chmod(name, 0o644)
        os.link(name, target)  # Exclusive: never replace a previously installed asset.
    except FileExistsError:
        if target.is_symlink() or sha(target) != digest:
            raise ValueError("concurrent media installation differs")
    finally:
        os.unlink(name)


def prepare(root, base_version, base_sha, version, selection_file, source_root, write):
    if not VERSION.fullmatch(version) or not VERSION.fullmatch(base_version) or base_version == version:
        raise ValueError("base and new version must be distinct safe identifiers")
    root = root.absolute()
    if root.resolve() != root or source_root.resolve() != source_root.absolute():
        raise ValueError("symlinked roots are forbidden")
    if any(path.absolute().is_relative_to(REPO) for path in (root, source_root, selection_file)):
        raise ValueError("source/selection/catalog data must remain outside Git")
    base = root / "releases" / base_version
    if not HEX.fullmatch(base_sha) or sha(safe_file(base, "manifest.json")) != base_sha:
        raise ValueError("base manifest is not the pinned SHA256")
    manifest = json.loads(safe_file(base, "manifest.json").read_bytes())
    if manifest["schema_version"] != "catalog-release-1" or manifest["catalog_version"] != base_version:
        raise ValueError("base release schema/version mismatch")
    files = {item["path"]: item for item in manifest["files"]}
    expected = {"wines.jsonl", "aliases.json", "catalog.json", "internal/display-policy.json", "PREPARATION.md"}
    if set(files) != expected:
        raise ValueError("unexpected base release files")
    for name, spec in files.items():
        content = safe_file(base, name).read_bytes()
        if len(content) != spec["bytes"] or hashlib.sha256(content).hexdigest() != spec["sha256"]:
            raise ValueError("base metadata integrity failure")
    base_media = {x["path"]: x for x in manifest["media"]}
    if len(base_media) != len(manifest["media"]):
        raise ValueError("duplicate base media")
    rows = [json.loads(line) for line in safe_file(base, "wines.jsonl").read_text().splitlines() if line]
    ids = {row["id"]: row for row in rows}
    if len(ids) != len(rows):
        raise ValueError("duplicate canonical ID")
    selections = [json.loads(line) for line in selection_file.read_text().splitlines() if line.strip()]
    if not selections:
        raise ValueError("no selections")
    assets, provenance = {}, []
    for selection in sorted(selections, key=lambda x: x["id"]):
        wine_id = selection["id"]
        if wine_id not in ids or any(x["id"] == wine_id for x in provenance):
            raise ValueError("unknown or duplicate selection ID")
        digest = selection["sha256"]
        source_ref = selection["source_ref"]
        if not HEX.fullmatch(digest) or not isinstance(source_ref, str) or not SOURCE_REF.fullmatch(source_ref):
            raise ValueError("selection needs SHA256 and source provenance reference")
        path = safe_file(source_root, selection["path"])
        variants = encode_selection(path, digest)
        wine = ids[wine_id]
        old = wine["image"]
        if old["path"] not in base_media or {v["role"] for v in old["variants"]} != set(ROLES):
            raise ValueError("base wine has incomplete media roles")
        for role, (spec, data) in variants.items():
            key = spec["path"]
            if key in assets and assets[key][1] != data:
                raise ValueError("media hash collision")
            assets[key] = (spec, data)
        original = variants["original"][0]
        wine["image"] = {**original, "variants": [{"role": role, **variants[role][0]} for role in ROLES]}
        provenance.append({"id": wine_id, "source_sha256": digest, "source_ref": source_ref,
                           "old_master": old["path"], "new_master": original["path"]})
    catalog = json.loads(safe_file(base, "catalog.json").read_bytes())
    catalog["catalog_version"] = version
    prep = safe_file(base, "PREPARATION.md").read_text() + (
        "\n## Alpha overlay\n\nReviewed upstream originals; no opaque source was composited. "
        "Unselected wines keep their previous media. Inspect full coverage before promotion.\n\n"
        f"Base: {base_version}; source selection SHA256: {sha(selection_file)}. "
        f"Generator SHA256: {sha(Path(__file__))}; Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; "
        f"Pillow: {Image.__version__}; libwebp: {features.version('webp')}. "
        "Every row records source identity and previous master for rollback.\n\n"
        "```jsonl\n" + "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in provenance) + "```\n"
    )
    contents = {"wines.jsonl": ("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)).encode(),
                "aliases.json": safe_file(base, "aliases.json").read_bytes(),
                "catalog.json": json_bytes(catalog),
                "internal/display-policy.json": safe_file(base, "internal/display-policy.json").read_bytes(),
                "PREPARATION.md": prep.encode()}
    media = dict(base_media)
    for key, (spec, _) in assets.items():
        if key in media and media[key] != spec:
            raise ValueError("existing media metadata conflict")
        media[key] = spec
    release = {"schema_version": "catalog-release-1", "catalog_version": version,
               "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                         for name, data in sorted(contents.items())],
               "media": [media[key] for key in sorted(media)]}
    manifest_bytes = json_bytes(release)
    target = root / "releases" / version
    if target.exists() or target.is_symlink():
        raise ValueError("new version already exists; immutable release cannot be replaced")
    if write:
        if (root / "media").is_symlink() or not (root / "media").is_dir():
            raise ValueError("shared media root is missing or symlinked")
        for key, (spec, data) in assets.items():
            install_media(root, key, data, spec["sha256"])
        if target.parent.is_symlink() or not target.parent.is_dir():
            raise ValueError("release root is missing or symlinked")
        with tempfile.TemporaryDirectory(prefix=version + "-", dir=target.parent) as tmp:
            stage = Path(tmp)
            for name, data in contents.items():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(0o644)
            (stage / "manifest.json").write_bytes(manifest_bytes)
            (stage / "manifest.json").chmod(0o644)
            stage.chmod(0o755)
            stage.rename(target)
    return {"version": version, "baseManifestSHA256": sha(base / "manifest.json"),
            "manifestSHA256": hashlib.sha256(manifest_bytes).hexdigest(),
            "canonical": len(rows), "selected": len(provenance), "newMedia": len(assets),
            "status": "materialized-not-imported" if write else "dry-run-no-writes"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="existing shared catalog root")
    parser.add_argument("--base-version", required=True)
    parser.add_argument("--base-manifest-sha256", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--write", action="store_true", help="write immutable media and new release")
    args = parser.parse_args()
    if args.write:
        import fcntl
        # Share the existing materializer's lock; never modify an accepted release.
        with (args.root / ".prepare.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = prepare(args.root, args.base_version, args.base_manifest_sha256,
                             args.version, args.selection, args.source_root, True)
    else:
        result = prepare(args.root, args.base_version, args.base_manifest_sha256,
                         args.version, args.selection, args.source_root, False)
    print(json.dumps(result, ensure_ascii=False))
