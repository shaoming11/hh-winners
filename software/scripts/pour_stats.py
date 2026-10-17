#!/usr/bin/env python3
"""Pour accuracy: N closed-loop pours to a target, reporting mean +- SD (docs/pitch.md).

  python3 software/scripts/pour_stats.py --n 10 --target 39
Runs in the sim; the same loop runs on hardware with --backend real.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

from bench.config import load
from bench.motion.player import MotionLock
from bench.motion.stations import StationPlanner, load_or_plan
from bench.paths import OUT_DIR
from bench.process.pour import PourController
from bench.process.scale import Scale
from bench.process.transfer import ArmTask


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["sim", "real"], default="sim")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--target", type=float, default=39.0)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    cfg = load(); plans = load_or_plan(cfg)
    if args.backend == "sim":
        from bench.hal.sim import make_sim_bench
        b = make_sim_bench(cfg, seed=args.seed)
    else:
        from bench.hal.real import make_real_bench
        b = make_real_bench(cfg)
    b.connect()
    quiet = lambda s: None
    lock = MotionLock()
    tr = ArmTask(b, "transfer", plans, lock, cfg, log=quiet)
    po = ArmTask(b, "pourer", plans, lock, cfg, log=quiet)
    scale = Scale(b, cfg); planner = StationPlanner(cfg)
    tr.transfer("carousel_pick", "scale")
    results = []
    for i in range(args.n):
        if b.sim is not None:
            # fresh reagent each time, receiver emptied (the operator would rinse P1)
            b.sim.chem.vessels["developer"].contents = {}; b.sim.fill("developer", "developer", 70.0)
            b.sim.chem.vessels["P1"].contents = {}; b.sim._apply_mass("P1")
        po.pick("rack_developer")
        ctl = PourController(b, po.player, scale, plans["pourer:pour_scale"], cfg, quiet, planner,
                             via=[plans["pourer:scale"].carry.q])
        ctl.enter()
        scale.tare()
        lg = ctl.pour_to(args.target, f"#{i + 1}")
        ctl.leave(); po.place("rack_developer"); po.park()
        truth = b.sim.chem.vessels["P1"].total_g if b.sim is not None else float("nan")
        results.append({"measured_g": round(lg.settled_g, 3), "true_g": round(truth, 3),
                        "theta_first": round(lg.theta_first, 1), "theta_cut": round(lg.theta_cut, 1),
                        "topups": lg.topups, "outcome": lg.outcome, "seconds": round(lg.duration_s, 1)})
        print(f"pour {i + 1:2d}: measured {lg.settled_g:6.2f} g  true {truth:6.2f} g  "
              f"first drop {lg.theta_first:.1f} cut {lg.theta_cut:.1f} top-ups {lg.topups}  {lg.outcome}")
    m = np.array([r["measured_g"] for r in results]); t = np.array([r["true_g"] for r in results])
    print(f"\n{args.n} pours to {args.target} g: measured {m.mean():.2f} +- {m.std(ddof=1):.2f} g "
          f"(error {m.mean() - args.target:+.2f}), true {t.mean():.2f} +- {t.std(ddof=1):.2f} g, "
          f"max |error| {np.abs(m - args.target).max():.2f} g")
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "pour_stats.json").write_text(json.dumps({"target": args.target, "backend": args.backend,
                                                          "results": results}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
