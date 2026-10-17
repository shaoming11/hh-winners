#!/usr/bin/env python3
"""Run the Wet Lab Bench demo.

  python3 software/scripts/run_demo.py --backend sim            # the full 10-step run in MuJoCo
  python3 software/scripts/run_demo.py --backend sim --record   # ... and write a video
  mjpython  software/scripts/run_demo.py --backend sim --approve --view  # ... live, in a window
  python3 software/scripts/run_demo.py --backend sim --only 1 2 # a subset of steps
  python3 software/scripts/run_demo.py --backend real --speed 0.25   # hardware, 25 % speed
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.config import load
from bench.paths import OUT_DIR


def recipe_from_plan(plan, base: dict | None) -> dict:
    """The sequencer runs the fixed 10-step choreography; the plan sets its quantities."""
    r = dict(base or {})
    for st in plan.steps:
        if st.op == "dose_liquid":
            r[f"{st.args['reagent']}_g"] = float(st.args["grams"])
        elif st.op == "dose_powder":
            r["yeast_g"] = float(st.args["grams"])
        elif st.op == "wait":
            r["activate_s"] = float(st.args["seconds"])
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["sim", "real"], default="sim")
    ap.add_argument("--speed", type=float, default=1.0, help="motion speed scale (0.25 = quarter)")
    ap.add_argument("--only", nargs="*", help="step prefixes to run, e.g. 1 2 3")
    ap.add_argument("--record", action="store_true", help="sim: write out/run.mp4")
    ap.add_argument("--fps", type=int, default=20)
    ap.add_argument("--view", "--live", dest="view", action="store_true",
                    help="sim: live MuJoCo window (start the script with mjpython on macOS)")
    ap.add_argument("--rt", "--realtime", dest="rt", type=float, default=1.0,
                    help="--view: wall seconds per bench second (1 = real time, 4 = 4x, 0 = flat out)")
    ap.add_argument("--camera", default="free",
                    help="--view: start camera: free|overview|webcam|top|scale_cam")
    ap.add_argument("--no-snap", action="store_true",
                    help="skip the offscreen camera renders (vision check + notebook stills)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--recipe", help="JSON recipe {developer_g, yeast_g, water_g, activate_s}")
    ap.add_argument("--no-fill", action="store_true", help="sim: don't pre-load the reagents")
    ap.add_argument("--protocol", help="plain-English protocol -> LLM plan -> validator -> approval")
    ap.add_argument("--approve", action="store_true", help="skip the interactive approval prompt")
    ap.add_argument("--operator", default="")
    ap.add_argument("--start-paused", action="store_true",
                    help="--view: open the window paused; press SPACE in it to start the bench")
    args = ap.parse_args()

    if args.view:
        # the passive viewer needs the Cocoa main thread, which only the mjpython
        # trampoline leaves free; launch_passive would raise deep in the run otherwise
        import mujoco.viewer
        if sys.platform == "darwin" and mujoco.viewer._MJPYTHON is None:
            print("--view needs the passive viewer: re-run with `mjpython`, not `python3`")
            return 4

    cfg = load()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    recipe = json.loads(args.recipe) if args.recipe else None

    if args.backend == "sim":
        from bench.hal.sim import make_sim_bench
        b = make_sim_bench(cfg, seed=args.seed)
        if not args.no_fill:
            # the operator's rough hand loads (demo_process.md 5.2)
            b.sim.fill("developer", "developer", 70.0)
            b.sim.fill("water", "water", 65.0)
            b.sim.fill("soap", "soap", 20.0)
    else:
        from bench.hal.real import make_real_bench
        b = make_real_bench(cfg)
    b.connect()

    live = None
    if args.view and b.sim is not None:
        # opened before the plan/approval so the parked bench is on screen while we wait
        from sim.viewer import LiveView
        live = LiveView(b.sim, factor=args.rt, camera=args.camera, start_paused=args.start_paused)
        b.sim.hooks.append(live.tick)
    recorder = None
    if args.record and b.sim is not None:
        from sim.viewer import Recorder
        recorder = Recorder(b.sim, OUT_DIR / "run.mp4", fps=args.fps)
        b.sim.hooks.append(recorder.tick)

    # ---- the AI layer: protocol text -> plan -> deterministic validator -> operator approval
    from bench.agent.notebook import Notebook
    from bench.agent.validator import Validator
    from bench.agent.vocab import preset_elephant_toothpaste
    nb = Notebook(operator=args.operator, protocol_text=args.protocol or "")
    if args.protocol:
        from bench.agent.llm import plan_from_text
        plan = plan_from_text(args.protocol)
        if plan.notes:
            print("note:", plan.notes)
    else:
        r = recipe or cfg.at("recipe")
        plan = preset_elephant_toothpaste(r.get("developer_g", 39.0), r.get("yeast_g", 7.0),
                                          r.get("water_g", 30.0), r.get("activate_s", 60.0))
    verdict = Validator(cfg).check(plan)
    nb.set_plan(plan, verdict)
    print(f"plan ({plan.source}): {plan.title}")
    for i, st in enumerate(plan.steps, 1):
        print(f"  {i:2d}. {st}")
    print("validator:", "PASS" if verdict.ok else "FAIL", "-", verdict.summary)
    for pr in verdict.problems:
        print("   !", pr)
    if not verdict.ok:
        nb.finish(type("R", (), {"doses": {}, "steps": [], "outcome": "rejected by validator",
                                 "faults": verdict.problems})())
        return 2
    if not args.approve:
        ans = input("Approve this plan and start the bench? [y/N] ").strip().lower()
        if ans != "y":
            print("not approved - nothing moves")
            return 3
    nb.approve(args.operator or "operator")
    recipe = recipe_from_plan(plan, recipe)

    from bench.process.sequencer import Sequencer
    def log(s):
        line = f"[{b.clock.now():7.1f}s] {s}"
        print(line); nb.log(line)
    def on_step(name, status):
        if recorder:
            recorder.mark(name, status)
        if b.sim is not None and status == "start" and not args.no_snap:
            # the camera check before every pick: is a beaker where the plan expects one?
            from bench.agent.vision import beaker_present
            img = b.sim.render("scale_cam")
            ok, score = beaker_present(img, (0, 0, img.shape[1], img.shape[0]))
            nb.snapshot("scale_cam", img, name)
    seq = Sequencer(b, cfg, recipe, speed=args.speed, log=log, on_step=on_step)
    rec = seq.run(only=args.only)
    if b.sim is not None:
        rec.doses["foam_height_mm_sim"] = round(b.sim.chem.foam_h_mm, 1)
        if not args.no_snap:
            from bench.agent.vision import foam_height_px
            img = b.sim.render("webcam")
            h_px, _ = foam_height_px(img)
            nb.snapshot("webcam_final", img, "ERUPT")
            rec.doses["foam_height_px"] = h_px
    if recorder:
        recorder.close()
        print(f"video: {recorder.path}")
    page = nb.finish(rec, ({"spilled_g": round(b.sim.chem.spilled_total_g, 2),
                            "flask": {k: round(v, 2) for k, v in b.sim.chem.vessels["flask"].contents.items()}}
                           if b.sim else None))
    print(f"notebook: {page.with_suffix('.html')}")

    out = OUT_DIR / f"run_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps({
        "backend": args.backend, "outcome": rec.outcome, "recipe": rec.recipe, "doses": rec.doses,
        "faults": rec.faults, "sim_seconds": b.clock.now(), "wall_seconds": round(rec.wall_s, 1),
        "steps": [{"name": s.name, "status": s.status, "t0": round(s.t_start, 2),
                   "t1": round(s.t_end, 2)} for s in rec.steps],
        "sim_state": ({"spilled_g": round(b.sim.chem.spilled_total_g, 2),
                       "foam_mm": round(b.sim.chem.foam_h_mm, 1),
                       "flask": {k: round(v, 2) for k, v in b.sim.chem.vessels["flask"].contents.items()}}
                      if b.sim else None),
    }, indent=1))
    print(f"\n{rec.outcome.upper()} in {b.clock.now():.0f} s of bench time  -> {out}")
    print("doses:", json.dumps(rec.doses))
    if live:
        live.wait()          # hold the eruption on screen
        live.close()
    return 0 if rec.outcome == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
