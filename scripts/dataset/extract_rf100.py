#!/usr/bin/env python3
"""Safely extract the mirrored RF100 archive while removing its long prefix."""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "Dataset/00_raw/09_rf100_wine_labels/dataset.tar.gz"
DESTINATION = ROOT / "Dataset/09_rf100_wine_labels/media/source_extract"
PREFIX_PARTS = ("home", "zuppif", "Documents", "Work", "RoboFlow", "ODinW-RF100-challenge", "rf100", "wine-labels")


def main() -> int:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    extracted = 0
    directories = 0
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise RuntimeError(f"unsafe member path: {member.name}")
            if tuple(path.parts[: len(PREFIX_PARTS)]) != PREFIX_PARTS:
                raise RuntimeError(f"unexpected archive prefix: {member.name}")
            relative = PurePosixPath(*path.parts[len(PREFIX_PARTS) :])
            if not relative.parts:
                continue
            target = DESTINATION.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                directories += 1
                continue
            # The upstream tar uses a non-standard type byte for three COCO
            # JSON members.  Windows bsdtar can still materialize them.  Keep
            # those already-extracted files only after an exact size check.
            if target.exists() and target.is_file() and target.stat().st_size == member.size:
                extracted += 1
                continue
            if member.islnk() and member.linkname == member.name and target.exists() and target.is_file():
                # Three annotation files are repeated as malformed self-hardlinks
                # after their regular-file entries.  The first entry is complete.
                continue
            if member.issym() or member.islnk() or member.isdev():
                raise RuntimeError(
                    f"unsupported linked/device member: {member.name}; "
                    f"type={member.type!r}; size={member.size}; linkname={member.linkname!r}; "
                    f"target_size={target.stat().st_size if target.exists() else None}"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"cannot read member: {member.name}")
            temporary = target.with_suffix(target.suffix + ".part")
            with source, temporary.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            temporary.replace(target)
            extracted += 1
    print(f"PASS: extracted {extracted} files and {directories} directory entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
