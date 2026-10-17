"""Bridge between the repo's recorded CAD joint angles and the MuJoCo/servo joint angles.

The verified Update-13 motion plan lives in tools/layout/anim_paths.json as "CAD" joint angles
(the Fusion as-built convention of software/tools/planner/kin_model.py).  Converting them needs
the per-joint sign and offset that the original code recovered from ~/fusion_bridge/kin.json -
a file that does not exist outside the author's machine.

It is recoverable without it.  kin_model.AXES_A records the six joint axis LINES of arm A in
bench world coordinates at the CAD zero pose, and the CAD world frame is the same frame the sim
uses (Update 13 only translated the arm rails: +67.4/+74.0 for the pourer, +34.8/+74.0 for the
transfer arm - tools/layout/layout_final.py:19).  So we only have to find the MJCF joint angles
q* whose axis lines coincide with those, giving

    q_mjcf = s_j * q_cad + q*_j          (s_j = +-1, from the axis directions)

Run this module directly to print the calibration and its residuals.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

import mujoco
import numpy as np
from scipy.optimize import least_squares

from ..config import MM, Config, load
from ..paths import ANIM_JSON, BENCH_XML
from .kinematics import ARM_JOINTS, ArmKin

# Joint axis lines of arm A at the CAD zero pose, in pre-Update-13 bench world mm.
# Verbatim from software/tools/planner/kin_model.py:8-9.
AXES_CAD_A = [
    ((330.0, 525.7, 47.3), (0, 0, 1)),
    ((351.2, 494.3, 139.4), (1, 0, 0)),
    ((352.7, 606.8, 168.4), (1, 0, 0)),
    ((354.8, 472.3, 172.5), (1, 0, 0.017)),
    ((337.2, 448.9, 172.0), (0, 1, 0)),
    ((318.1, 387.2, 191.4), (1, 0, 0)),
]
CAD_ARM_B_DX = 240.0           # kin_model.py:23 - arm B is arm A translated +240 mm in X
CAD_OFFSET = {"pourer": (67.4, 74.0, 0.0), "transfer": (34.8, 74.0, 0.0)}
CAD_JOINTS = ["pan", "shoulder", "elbow", "wr_flex", "wr_roll"]

# Result of calibrate() on the built bench model (identical for both arms, 2.8 mm residual).
# q_mjcf = q_cad + CANONICAL_OFFSET_DEG.  Re-derive with `python3 -m bench.motion.calib`.
CANONICAL_OFFSET_DEG = np.array([-2.94, -88.17, 88.69, 0.07, 2.81])


def cad_to_mjcf(q_cad_deg) -> np.ndarray:
    """CAD (Fusion as-built) joint angles -> MJCF / LeRobot-calibrated joint angles, degrees."""
    return np.asarray(q_cad_deg, float) + CANONICAL_OFFSET_DEG


def mjcf_to_cad(q_mjcf_deg) -> np.ndarray:
    return np.asarray(q_mjcf_deg, float) - CANONICAL_OFFSET_DEG


def park_mjcf_deg(cfg: Config | None = None) -> np.ndarray:
    cfg = cfg or load()
    return cad_to_mjcf(cfg.at("arms.park_cad_deg"))


@dataclass
class ArmCalib:
    role: str
    sign: np.ndarray            # per joint, +-1
    offset_deg: np.ndarray      # MJCF angle at CAD zero
    axis_residual_mm: float
    axis_residual_deg: float

    def to_mjcf(self, q_cad_deg) -> np.ndarray:
        return self.sign * np.asarray(q_cad_deg, float) + self.offset_deg

    def to_cad(self, q_mjcf_deg) -> np.ndarray:
        return (np.asarray(q_mjcf_deg, float) - self.offset_deg) / self.sign


def cad_axes(role: str) -> list[tuple[np.ndarray, np.ndarray]]:
    """The six CAD axis lines for one arm, moved into final bench world coordinates."""
    dx = 0.0 if role == "pourer" else CAD_ARM_B_DX
    ox, oy, oz = CAD_OFFSET[role]
    out = []
    for (p, d) in AXES_CAD_A:
        pt = np.array([p[0] + dx + ox, p[1] + oy, p[2] + oz], float)
        dv = np.array(d, float)
        out.append((pt, dv / np.linalg.norm(dv)))
    return out


def _sim_axes(arm: ArmKin, q_deg) -> list[tuple[np.ndarray, np.ndarray]]:
    arm._set(q_deg)
    jids = arm.jids + [arm.gripper_jid]
    return [(arm.d.xanchor[j] / MM, arm.d.xaxis[j].copy()) for j in jids]


def calibrate(arm: ArmKin, verbose: bool = False) -> ArmCalib:
    target = cad_axes(arm.role)

    def residual(q5: np.ndarray) -> np.ndarray:
        sim = _sim_axes(arm, q5)
        r: list[float] = []
        # joints 1..5 constrain the pose (joint 0 is the vertical pan axis, pose-invariant)
        for k in range(1, 6):
            ps, ds = sim[k]
            pc, dc = target[k]
            s = 1.0 if ds @ dc >= 0 else -1.0       # lines, so direction sign is free
            r += list(20.0 * (ds * s - dc))         # direction mismatch, weighted
            v = ps - pc
            r += list(v - dc * (v @ dc))            # offset perpendicular to the axis (mm)
        return np.array(r)

    best = None
    for seed in ([0, 0, 0, 0, 0], [0, 90, -90, 0, 0], [0, -90, 90, 0, 0],
                 [0, 45, -45, 45, 0], [0, -45, 45, -45, 90], [0, 90, -90, 0, 90]):
        sol = least_squares(residual, np.array(seed, float), xtol=1e-12, ftol=1e-12)
        if best is None or sol.cost < best.cost:
            best = sol
    q_star = best.x                                  # type: ignore[union-attr]

    # The stored CAD axis directions are geometric, not positive-rotation directions (the
    # original code took the signs from kin.json probes).  Searching all 32 sign combinations
    # against the recorded q_pick poses of anim_paths.json lands every pick on its station only
    # for all-positive signs (mean 20 mm, beaker axis vertical to 0.01), so the map is simply
    # q_mjcf = q_cad + q*.
    sign = np.ones(5)

    r = residual(q_star)
    deg_err = float(np.degrees(np.max(np.abs(r.reshape(5, 6)[:, :3] / 20.0))))
    mm_err = float(np.max(np.linalg.norm(r.reshape(5, 6)[:, 3:], axis=1)))
    if verbose:
        print(f"  {arm.role}: q* = {np.round(q_star, 2)} deg, signs {sign.astype(int)}, "
              f"axis residual {mm_err:.2f} mm / {deg_err:.2f} deg")
    return ArmCalib(arm.role, sign, q_star, mm_err, deg_err)


# ------------------------------------------------------------------ recorded plan
ANIM_TO_ROLE = {"A": "pourer", "B": "transfer"}      # layout_final.py:458 - tags are inverted


def load_anim() -> dict:
    return json.loads(ANIM_JSON.read_text())


def recorded_poses() -> list[dict]:
    """Flatten anim_paths.json into one record per step with its CAD key poses."""
    anim = load_anim()
    out = []
    for st in anim["steps"]:
        out.append({
            "step": st["step"],
            "role": ANIM_TO_ROLE[st["arm"]],
            "grasp": st.get("grasp", "side"),
            "q_pick": st.get("q_pick"),
            "q_pour55": st.get("q_pour55"),
            "q_pour105": st.get("q_pour105"),
            "grip_h": st.get("grip_h"),
            "clearance_mm": st.get("clearance_mm"),
            "paths": st["anim_paths"],
            "raw": st,
        })
    return out


def main() -> None:  # pragma: no cover - CLI
    cfg = load()
    model = mujoco.MjModel.from_xml_path(str(BENCH_XML))
    print("CAD <-> MJCF joint calibration (axis-line fit, no kin.json needed)")
    cals = {}
    for role in ("pourer", "transfer"):
        arm = ArmKin(model, role, cfg)
        cals[role] = calibrate(arm, verbose=True)
    print("\nper-joint map  q_mjcf = sign * q_cad + offset")
    for role, c in cals.items():
        print(f"  {role}:")
        for i, jn in enumerate(ARM_JOINTS):
            print(f"    {jn:<14s} {CAD_JOINTS[i]:<9s} sign {int(c.sign[i]):+d}  "
                  f"offset {c.offset_deg[i]:+8.2f} deg")


if __name__ == "__main__":
    main()
