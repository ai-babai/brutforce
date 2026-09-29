#!/usr/bin/env python3
"""Download/verify the pinned public runtime archives for Docker or Mac."""
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

folder, mode, profile = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
public_url = "https://disk.yandex.ru/d/dHAXDPcitS-ZJQ"
api = "https://cloud-api.yandex.net/v1/disk/public/resources"
remote_path = "/transfer-publication-parts-20260928"
manifest_sha = "71cc254993393e1b4ffc8b013a2ab729679e061ce11aa65aa87ef99ef6ddc332"
names = ["01-recognition-data.tar.gz"] + [
    f"02-recognition-weights.tar.part-{i:03d}" for i in range(6)
] + ["02-recognition-weights.tar.sha256"]
if profile == "full":
    names += ["03-display-catalog.tar.gz", "04-display-media.tar",
              "05-text-recommendations.tar.gz"]
elif profile != "scoring":
    raise SystemExit("Unknown bootstrap profile")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def listing():
    query = urlencode({"public_key": public_url, "path": remote_path, "limit": 100})
    with urlopen(f"{api}?{query}", timeout=45) as response:
        items = json.load(response)["_embedded"]["items"]
    return {item["name"]: item["file"] for item in items if item["type"] == "file"}


links = None


def obtain(name, expected):
    global links
    target = folder / name
    if target.is_file() and digest(target) == expected:
        print(f"Verified cached {name}", flush=True)
        return
    if mode == "offline":
        raise SystemExit(f"Missing or corrupt local archive: {name}")
    if links is None:
        links = listing()
    if name not in links:
        raise SystemExit(f"Missing public bundle file: {name}")
    print(f"Downloading {name}", flush=True)
    partial = folder / (name + ".download")
    h = hashlib.sha256()
    with urlopen(links[name], timeout=120) as source, partial.open("wb") as dest:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            dest.write(chunk)
            h.update(chunk)
    if h.hexdigest() != expected:
        partial.unlink()
        raise SystemExit(f"SHA-256 mismatch: {name}")
    partial.replace(target)


obtain("SHA256SUMS", manifest_sha)
checksums = {name: sha for sha, name in (
    line.split("  ", 1) for line in (folder / "SHA256SUMS").read_text().splitlines()
)}
for name in names:
    obtain(name, checksums[name])

expected_stream = (folder / "02-recognition-weights.tar.sha256").read_text().split()[0]
stream_hash = hashlib.sha256()
for i in range(6):
    with (folder / f"02-recognition-weights.tar.part-{i:03d}").open("rb") as part:
        for chunk in iter(lambda: part.read(1024 * 1024), b""):
            stream_hash.update(chunk)
if stream_hash.hexdigest() != expected_stream:
    raise SystemExit("Combined weights tar SHA-256 mismatch")
print("Runtime archives and combined weights verified", flush=True)
