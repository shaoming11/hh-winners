"""Fetch a pinned copy of the upstream SO-101 MuJoCo model and its meshes."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets" / "so101"
API = "https://api.github.com/repos/TheRobotStudio/SO-ARM100"
RAW = "https://raw.githubusercontent.com/TheRobotStudio/SO-ARM100"
MODEL_PATH = "Simulation/SO101/so101_new_calib.xml"


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "wet-lab-reference-sim"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    commit = json.loads(get(f"{API}/commits/main")) ["sha"]
    source = f"{RAW}/{commit}/{MODEL_PATH}"
    xml = get(source)
    (ASSET_DIR / "so101_new_calib.xml").write_bytes(xml)

    files = re.findall(rb'<mesh\s+file="([^"]+\.stl)"', xml)
    checksums: dict[str, str] = {"so101_new_calib.xml": hashlib.sha256(xml).hexdigest()}
    for match in files:
        filename = match.decode("ascii")
        data = get(f"{RAW}/{commit}/Simulation/SO101/assets/{filename}")
        (ASSET_DIR / filename).write_bytes(data)
        checksums[filename] = hashlib.sha256(data).hexdigest()

    license_data = get(f"{RAW}/{commit}/LICENSE")
    (ASSET_DIR / "UPSTREAM_LICENSE").write_bytes(license_data)
    manifest = {
        "repository": "https://github.com/TheRobotStudio/SO-ARM100",
        "commit": commit,
        "model": MODEL_PATH,
        "license_file": "UPSTREAM_LICENSE",
        "sha256": checksums,
    }
    (ASSET_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Fetched SO-101 model and {len(files)} meshes at {commit[:12]}")


if __name__ == "__main__":
    main()
