"""Fetch a pinned copy of the upstream SO-101 MuJoCo model and its meshes."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets" / "so101"
PINNED_MANIFEST = ROOT / "so101_assets.json"
RAW = "https://raw.githubusercontent.com/TheRobotStudio/SO-ARM100"
MODEL_PATH = "Simulation/SO101/so101_new_calib.xml"


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "wet-lab-reference-sim"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main() -> None:
    pinned = json.loads(PINNED_MANIFEST.read_text())
    commit = pinned["commit"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"Invalid pinned SO-101 commit: {commit!r}")
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    expected_hashes = pinned["sha256"]
    xml_path = ASSET_DIR / "so101_new_calib.xml"
    expected_xml_hash = expected_hashes[xml_path.name]
    if not xml_path.exists() or hashlib.sha256(xml_path.read_bytes()).hexdigest() != expected_xml_hash:
        xml = get(f"{RAW}/{commit}/{MODEL_PATH}")
        actual = hashlib.sha256(xml).hexdigest()
        if actual != expected_xml_hash:
            raise ValueError(f"Pinned model hash mismatch: {actual} != {expected_xml_hash}")
        xml_path.write_bytes(xml)
    else:
        xml = xml_path.read_bytes()

    mesh_files = {match.decode("ascii") for match in
                  re.findall(rb'<mesh\s+file="([^"]+\.stl)"', xml)}
    expected_mesh_files = set(expected_hashes) - {xml_path.name}
    if mesh_files != expected_mesh_files:
        missing = sorted(mesh_files - expected_mesh_files)
        extra = sorted(expected_mesh_files - mesh_files)
        raise ValueError(f"Pinned manifest/XML mesh mismatch; unhashed={missing}, unused={extra}")

    downloaded = 0
    for filename in sorted(mesh_files):
        target = ASSET_DIR / filename
        expected_hash = expected_hashes[filename]
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == expected_hash:
            continue
        data = get(f"{RAW}/{commit}/Simulation/SO101/assets/{filename}")
        actual = hashlib.sha256(data).hexdigest()
        if actual != expected_hash:
            raise ValueError(f"Pinned mesh hash mismatch for {filename}: {actual} != {expected_hash}")
        target.write_bytes(data)
        downloaded += 1

    license_path = ASSET_DIR / "UPSTREAM_LICENSE"
    if not license_path.exists():
        license_path.write_bytes(get(f"{RAW}/{commit}/LICENSE"))
    (ASSET_DIR / "manifest.json").write_text(json.dumps(pinned, indent=2) + "\n")
    print(f"Verified pinned SO-101 model and {len(mesh_files)} meshes at {commit[:12]} "
          f"({downloaded} mesh downloads)")


if __name__ == "__main__":
    main()
