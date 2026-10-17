#!/usr/bin/env python3
"""Reproduce the Update-13 PASS table in the sim: for every planned pose, the joint margin to
the (5 deg-shrunk) limits and the true minimum clearance between the arm (+ held beaker) and
the bench, printed beside the values recorded in tools/layout/anim_paths.json.

  python3 software/scripts/verify_layout.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mujoco
import numpy as np

from bench.config import load
from bench.motion.calib import recorded_poses, cad_to_mjcf
from bench.motion.kinematics import ArmKin
from bench.motion.stations import load_or_plan
from bench.paths import BENCH_XML, OUT_DIR

RULE = {"pick": 10.0, "place": 10.0, "pour": 10.0, "carry": 5.0, "pre": 5.0, "lift": 5.0, "entry": 10.0}


def clearance(model, data, role: str, held: str | None):
    """min distance (mm) from the arm's collision geoms (and the held beaker) to everything else."""
    own = {model.body(f"{role}_{n}").id for n in
           ("base", "shoulder", "upper_arm", "lower_arm", "wrist", "gripper", "moving_jaw_so101_v1")}
    held_b = model.body(f"beaker_{held}").id if held else None
    mine = [g for g in range(model.ngeom)
            if (model.geom_bodyid[g] in own or model.geom_bodyid[g] == held_b)
            and (model.geom_contype[g] | model.geom_conaffinity[g])]
    others = [g for g in range(model.ngeom)
              if model.geom_bodyid[g] not in own and model.geom_bodyid[g] != held_b
              and (model.geom_contype[g] | model.geom_conaffinity[g])
              and mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) != "table"]
    best, who = math.inf, ""
    ft = np.zeros(6)
    for a in mine:
        for b in others:
            d = mujoco.mj_geomDistance(model, data, a, b, 0.08, ft)
            if d < best:
                best = d
                who = f"{mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, a)} x {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, b)}"
    return best * 1000.0, who


def main() -> int:
    cfg = load()
    model = mujoco.MjModel.from_xml_path(str(BENCH_XML))
    data = mujoco.MjData(model)
    plans = load_or_plan(cfg)
    arms = {r: ArmKin(model, r, cfg) for r in ("pourer", "transfer")}
    rec = {r["step"]: r for r in recorded_poses()}
    park = cad_to_mjcf(cfg.at("arms.park_cad_deg"))

    def put_beaker(name, xy, z):
        jid = model.joint(f"beaker_{name}_free").id
        adr = model.jnt_qposadr[jid]
        data.qpos[adr:adr + 3] = [xy[0] / 1000.0, xy[1] / 1000.0, z / 1000.0]
        data.qpos[adr + 3:adr + 7] = [1, 0, 0, 0]

    def pose(role, q, held=None, beaker_rel=None, p1_on_scale=False):
        """set both arms (other parked), optionally attach a beaker at the grasp site.
        For scale-side checks P1 sits on the pan (that is what is being poured into)."""
        mujoco.mj_resetData(model, data)
        if p1_on_scale:
            sc = cfg.at("stations.scale")
            put_beaker("P1", sc["pan_xy"], sc["beaker_bottom_z"])
        for r in arms:
            arms[r]._set(park)
            data.qpos[arms[r].qadr] = np.radians(park)
        data.qpos[arms[role].qadr] = np.radians(q)
        # jaw open (side) / wide open (top-down) at picks; held beakers are gripped at contact
        jaw = 20.0 if held else (62.0 if plans_grasp == "top_down" else 34.0)
        data.qpos[model.joint(f"{role}_gripper").qposadr[0]] = math.radians(jaw)
        mujoco.mj_kinematics(model, data)
        if held:
            g = data.site_xpos[model.site(f"{role}_grasp").id]
            R = data.xmat[model.body(f"{role}_gripper").id].reshape(3, 3)
            axis = R[:, 1] if plans_grasp == "side" else R[:, 2]
            bottom = g - axis * (beaker_rel / 1000.0)
            jid = model.joint(f"beaker_{held}_free").id
            adr = model.jnt_qposadr[jid]
            data.qpos[adr:adr + 3] = bottom
            # orient the beaker's z along `axis`
            z = axis / np.linalg.norm(axis)
            x = np.cross([0, 1, 0], z); x = x / (np.linalg.norm(x) or 1)
            y = np.cross(z, x)
            Rb = np.column_stack([x, y, z]); q4 = np.zeros(4)
            mujoco.mju_mat2Quat(q4, Rb.ravel()); data.qpos[adr + 3:adr + 7] = q4
            mujoco.mj_kinematics(model, data)
        mujoco.mj_forward(model, data)

    rows = []
    recorded = {
        "pourer:rack_developer": ("P_dev", "developer"), "pourer:rack_water": ("P_wat", "water"),
        "pourer:scale": ("P_fun", "P1"), "transfer:carousel_pick": ("T1", "P1"), "transfer:scale": ("T2", "P1"),
        "pourer:pour_scale": ("P_dev", "developer"), "pourer:pour_funnel": ("P_fun", "P2"),
    }
    print(f"{'pose':<34}{'margin':>8} {'binding':<14}{'rule':>5} {'clear mm':>9}  {'recorded':<24} {'verdict'}")
    print("-" * 110)
    all_ok = True
    for key, plan in plans.items():
        role = key.split(":")[0]
        step, beaker = recorded.get(key, ("", "P1"))
        r = rec.get(step, {})
        raw = r.get("raw", {})
        global plans_grasp
        if hasattr(plan, "thetas"):
            plans_grasp = "side"
            worst = (1e9, "", 1e9, "", 0.0)
            for th, q in zip(plan.thetas[::5], plan.qs[::5]):
                pose(role, q, beaker, plan.grip_h, p1_on_scale=(plan.receiver == "scale"))
                m, who = arms[role].margin(q)
                c, cw = clearance(model, data, role, beaker)
                if m < worst[0]:
                    worst = (m, who, c, cw, th) if c >= worst[2] else (m, who, worst[2], worst[3], th)
                if c < worst[2]:
                    worst = (worst[0], worst[1], c, cw, worst[4])
            m, who, c, cw, th = worst
            ok = m >= RULE["pour"] and c > 0
            all_ok &= ok
            rp = raw.get("pour", [None])[0]; rc = r.get("clearance_mm")
            print(f"{key + ' (theta sweep)':<34}{m:>8.1f} {who:<14}{RULE['pour']:>5.0f} {c:>9.1f}  "
                  f"{('%.1f deg / %.1f mm' % (rp, rc)) if rp else '-':<24} {'PASS' if ok else 'FAIL'}  ({cw})")
            rows.append((key, m, c))
            continue
        plans_grasp = plan.grasp
        for kind, pz, held in (("pre", plan.pre, None), ("grasp", plan.grasp_pose, None),
                               ("lift", plan.lift, beaker), ("carry", plan.carry, beaker)):
            pose(role, pz.q, held, plan.grip_h,
                 p1_on_scale=(key == "pourer:scale" and kind in ("pre", "grasp")))
            m, who = arms[role].margin(pz.q)
            c, cw = clearance(model, data, role, held)
            rule = RULE["pick"] if kind == "grasp" else RULE["carry"]
            ok = m >= rule and c > 0.0
            all_ok &= ok
            recd = ""
            if kind == "grasp" and raw.get("pick"):
                recd = f"{raw['pick'][0]:.1f} deg / {r.get('clearance_mm', float('nan')):.1f} mm"
            elif kind == "carry" and raw.get("carry"):
                recd = f"{raw['carry'][0]:.1f} deg"
            print(f"{key + ':' + kind:<34}{m:>8.1f} {who:<14}{rule:>5.0f} {c:>9.1f}  {recd:<24} "
                  f"{'PASS' if ok else 'FAIL'}  ({cw})")
            rows.append((f"{key}:{kind}", m, c))
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "verify_layout.json").write_text(json.dumps(
        [{"pose": k, "margin_deg": round(m, 2), "clearance_mm": round(c, 2)} for k, m, c in rows], indent=1))
    print("\nALL PASS" if all_ok else "\nSOME POSES FAIL the margin/clearance rules")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
