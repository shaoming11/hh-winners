#!/usr/bin/env python3
"""Dev tool: run one primitive in the sim and dump frames.  e.g.
   python3 scripts/try_step.py transfer carousel_pick scale
   python3 scripts/try_step.py pour developer
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import imageio
import numpy as np

from bench.config import load
from bench.hal.sim import make_sim_bench
from bench.motion.player import MotionLock
from bench.motion.stations import load_or_plan
from bench.process.transfer import ArmTask
from bench.paths import OUT_DIR


def main():
    cfg = load()
    b = make_sim_bench(cfg)
    b.connect()
    plans = load_or_plan(cfg)
    lock = MotionLock()
    w = b.sim
    frames = []
    def snap(tag):
        frames.append((tag, w.render("overview")))
        print(f"    [{w.t:6.2f} s] {tag}")
    w.hooks.append(lambda: None)
    what = sys.argv[1]
    if what == "transfer":
        src, dst = sys.argv[2], sys.argv[3]
        role = "transfer" if src.startswith("carousel") or dst.startswith("carousel") else "pourer"
        task = ArmTask(b, role, plans, lock, cfg)
        snap("start")
        task.pick(src); snap("picked")
        task.place(dst); snap("placed")
        task.park(); snap("parked")
        print("held:", w.held, " beaker on scale:", w.beaker_on_scale(), " events:", w.events[-4:])
    for i, (tag, img) in enumerate(frames):
        imageio.imwrite(OUT_DIR / f"try_{i}_{tag}.png", img)
    print("frames in", OUT_DIR)


if __name__ == "__main__":
    main()
