"""Repository paths. The simulator reads project files from the checkout only (never ~/fusion_bridge or ~/so101)."""
from pathlib import Path

PKG = Path(__file__).resolve().parent
SIM_ROOT = PKG.parent                       # software/benchsim
REPO = SIM_ROOT.parent.parent               # repository root
LAYOUT_JSON = REPO / 'tools' / 'layout' / 'layout_final.json'
ANIM_PATHS = REPO / 'tools' / 'layout' / 'anim_paths.json'
GRIPPER_DESIGN = REPO / 'software' / 'tools' / 'planner' / 'gripper_design.json'
GRIP_FRAMES = REPO / 'software' / 'tools' / 'planner' / 'grip_frames.json'
PRINTS_V2 = REPO / 'exports' / 'prints_v2'
CONFIG = PKG / 'config'
RUNS = SIM_ROOT / 'runs'
