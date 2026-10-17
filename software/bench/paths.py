"""Shared paths."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = ROOT / "software/sim"
BENCH_XML = SIM_DIR / "bench.xml"
LAYOUT_JSON = ROOT / "tools/layout/layout_final.json"
ANIM_JSON = ROOT / "tools/layout/anim_paths.json"
PLANNER_DIR = ROOT / "software/tools/planner"
OUT_DIR = ROOT / "software/out"
