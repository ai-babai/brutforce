from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jfif", ".png", ".webp", ".tif", ".tiff", ".heic"}


def sha256_file(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, value: str, length: int = 20) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def relative_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def image_probe(path: Path, calculate_dhash: bool = False) -> dict[str, Any]:
    from PIL import Image, ImageFile

    ImageFile.LOAD_TRUNCATED_IMAGES = False
    Image.MAX_IMAGE_PIXELS = 200_000_000
    result: dict[str, Any] = {
        "decode_status": "error",
        "image_format": None,
        "width": None,
        "height": None,
        "mode": None,
        "dhash64": None,
        "decode_error": None,
    }
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            result.update(
                decode_status="ok",
                image_format=image.format,
                width=image.width,
                height=image.height,
                mode=image.mode,
            )
            if calculate_dhash:
                gray = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
                pixels = list(gray.getdata())
                bits = 0
                for row in range(8):
                    for col in range(8):
                        bits = (bits << 1) | int(pixels[row * 9 + col] > pixels[row * 9 + col + 1])
                result["dhash64"] = f"{bits:016x}"
    except Exception as exc:  # decoder errors are data, not pipeline failures
        result["decode_error"] = f"{type(exc).__name__}: {exc}"[:500]
    return result


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                stream.write("\n")
                count += 1
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return count


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
