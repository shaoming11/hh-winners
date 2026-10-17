"""Forward/inverse kinematics for the two bench SO-101s, solved directly in the MuJoCo model.

The repo's original planner (software/tools/planner/kin_model.py) worked in Fusion "as-built"
joint angles and needed ~/fusion_bridge/kin.json to resolve axis signs; that file does not
exist outside the original author's machine.  This module re-solves everything natively in the
MJCF frame instead, so it runs anywhere, and motion/calib.py provides the bridge back to the
recorded CAD angles.

Angles are DEGREES at this module's boundary (that is what servos and the docs speak); radians
only inside.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import mujoco
import numpy as np

from ..config import MM, Config, joint_limits_deg, load

ARM_JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"]

# Which gripper-frame axis the held beaker's own axis lies along.
#   side grasp  - the beaker is cradled across the jaw, axis along the hinge (gripper +y)
#   top-down    - the beaker sits in the finger channel, axis along the fingers (gripper +z)
GRASP_AXIS = {"side": np.array([0.0, 1.0, 0.0]), "top_down": np.array([0.0, 0.0, 1.0])}


@dataclass
class IKResult:
    q_deg: np.ndarray
    pos_err_mm: float
    axis_err_deg: float
    ok: bool
    margin_deg: float = 0.0
    binding: str = ""

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (f"IKResult({'ok' if self.ok else 'FAIL'} pos={self.pos_err_mm:.2f}mm "
                f"axis={self.axis_err_deg:.2f}deg margin={self.margin_deg:.1f}deg"
                f"{'/' + self.binding if self.binding else ''})")


class ArmKin:
    """Kinematics for one arm of a compiled bench model."""

    def __init__(self, model: mujoco.MjModel, role: str, cfg: Config | None = None):
        self.m = model
        self.role = role
        self.cfg = cfg or load()
        self.prefix = f"{role}_"
        self.d = mujoco.MjData(model)                   # scratch, never stepped
        self.jids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, self.prefix + j)
                     for j in ARM_JOINTS]
        self.gripper_jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT,
                                             self.prefix + "gripper")
        self.qadr = np.array([model.jnt_qposadr[j] for j in self.jids])
        self.grasp_sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, self.prefix + "grasp")
        self.hinge_sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, self.prefix + "hinge")
        self.gripper_bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY,
                                             self.prefix + "gripper")
        self.limits = joint_limits_deg(self.cfg)
        self.lo = np.array([self.limits[j][0] for j in ARM_JOINTS])
        self.hi = np.array([self.limits[j][1] for j in ARM_JOINTS])

    # ---------------------------------------------------------------- forward
    def _set(self, q_deg) -> None:
        self.d.qpos[self.qadr] = np.radians(np.asarray(q_deg, float))
        mujoco.mj_kinematics(self.m, self.d)

    def fk(self, q_deg) -> tuple[np.ndarray, np.ndarray]:
        """Grasp-site position (mm, world) and the gripper rotation matrix."""
        self._set(q_deg)
        return self.d.site_xpos[self.grasp_sid] / MM, self.d.xmat[self.gripper_bid].reshape(3, 3)

    def grasp_pos(self, q_deg) -> np.ndarray:
        return self.fk(q_deg)[0]

    def beaker_axis(self, q_deg, grasp: str = "side") -> np.ndarray:
        _, R = self.fk(q_deg)
        return R @ GRASP_AXIS[grasp]

    def margin(self, q_deg) -> tuple[float, str]:
        """Degrees to the nearest (5 deg-margined) joint limit, and the binding joint."""
        q = np.asarray(q_deg, float)
        d = np.minimum(q - self.lo, self.hi - q)
        i = int(np.argmin(d))
        return float(d[i]), ARM_JOINTS[i]

    def in_limits(self, q_deg) -> bool:
        return self.margin(q_deg)[0] >= 0.0

    # ---------------------------------------------------------------- inverse
    def ik(self, target_mm, axis_world=None, grasp: str = "side", q0=None,
           iters: int = 220, tol_mm: float = 0.25, axis_weight: float = 120.0,
           clamp: bool = True) -> IKResult:
        """Damped least squares: put the grasp site on `target_mm` with the held beaker's
        axis along `axis_world` (default: straight up)."""
        tgt = np.asarray(target_mm, float) * MM
        want = np.array([0.0, 0.0, 1.0]) if axis_world is None else np.asarray(axis_world, float)
        want = want / np.linalg.norm(want)
        gax = GRASP_AXIS[grasp]
        q = np.zeros(5) if q0 is None else np.radians(np.asarray(q0, float)).copy()

        def residual(qq: np.ndarray) -> np.ndarray:
            self.d.qpos[self.qadr] = qq
            mujoco.mj_kinematics(self.m, self.d)
            p = self.d.site_xpos[self.grasp_sid]
            R = self.d.xmat[self.gripper_bid].reshape(3, 3)
            a = R @ gax
            return np.concatenate([(p - tgt) * 1000.0, axis_weight * np.cross(a, want)])

        lam = 1e-2
        r = residual(q)
        for _ in range(iters):
            J = np.zeros((len(r), 5))
            for k in range(5):
                dq = q.copy(); dq[k] += 1e-5
                J[:, k] = (residual(dq) - r) / 1e-5
            try:
                step = np.linalg.solve(J.T @ J + lam * np.eye(5), -J.T @ r)
            except np.linalg.LinAlgError:         # pragma: no cover
                break
            q_new = q + np.clip(step, -0.25, 0.25)
            if clamp:
                q_new = np.clip(q_new, np.radians(self.lo), np.radians(self.hi))
            r_new = residual(q_new)
            if np.linalg.norm(r_new) < np.linalg.norm(r):
                q, r, lam = q_new, r_new, max(lam * 0.6, 1e-5)
            else:
                lam *= 2.5
                if lam > 1e4:
                    break
            if np.linalg.norm(r[:3]) < tol_mm and np.linalg.norm(r[3:]) < axis_weight * 0.01:
                break

        q_deg = np.degrees(q)
        pos_err = float(np.linalg.norm(r[:3]))
        a = self.beaker_axis(q_deg, grasp)
        axis_err = float(math.degrees(math.acos(float(np.clip(a @ want, -1, 1)))))
        mg, who = self.margin(q_deg)
        return IKResult(q_deg, pos_err, axis_err, pos_err < 2.0 and axis_err < 3.0 and mg >= 0,
                        mg, who)

    def ik_topdown(self, target_mm, q0=None, max_lean_deg: float = 35.0, iters: int = 220,
                   tol_mm: float = 0.25) -> IKResult:
        """Top-down grasp IK: grasp site on `target_mm`, fingers pointing down-ish, with the
        gripper's jaw-opening axis (x, the finger-face normal) held HORIZONTAL so the finger
        faces stay vertical planes - a vertical beaker then fits between them at any lean.
        The lean about the hinge is free (soft-limited to `max_lean_deg`) and is used by the
        multi-seed caller to maximise the joint margin."""
        tgt = np.asarray(target_mm, float) * MM
        q = np.zeros(5) if q0 is None else np.radians(np.asarray(q0, float)).copy()
        cmax = math.cos(math.radians(max_lean_deg))

        def residual(qq):
            self.d.qpos[self.qadr] = qq
            mujoco.mj_kinematics(self.m, self.d)
            p = self.d.site_xpos[self.grasp_sid]
            R = self.d.xmat[self.gripper_bid].reshape(3, 3)
            x_z = R[2, 0]                               # face normal's vertical component
            z_z = R[2, 2]                               # fingers point -z: need z up (z_z > 0)
            lean_pen = max(0.0, cmax - z_z) * 150.0
            return np.concatenate([(p - tgt) * 1000.0, [120.0 * x_z, lean_pen]])

        lam = 1e-2
        r = residual(q)
        for _ in range(iters):
            J = np.zeros((len(r), 5))
            for k in range(5):
                dq = q.copy(); dq[k] += 1e-5
                J[:, k] = (residual(dq) - r) / 1e-5
            try:
                step = np.linalg.solve(J.T @ J + lam * np.eye(5), -J.T @ r)
            except np.linalg.LinAlgError:  # pragma: no cover
                break
            q_new = np.clip(q + np.clip(step, -0.25, 0.25), np.radians(self.lo), np.radians(self.hi))
            r_new = residual(q_new)
            if np.linalg.norm(r_new) < np.linalg.norm(r):
                q, r, lam = q_new, r_new, max(lam * 0.6, 1e-5)
            else:
                lam *= 2.5
                if lam > 1e4:
                    break
            if np.linalg.norm(r[:3]) < tol_mm and abs(r[3]) < 1.0 and r[4] < 1.0:
                break
        q_deg = np.degrees(q)
        pos_err = float(np.linalg.norm(r[:3]))
        _, R = self.fk(q_deg)
        lean = math.degrees(math.acos(float(np.clip(R[2, 2], -1, 1))))
        face_tilt = math.degrees(math.asin(float(np.clip(abs(R[2, 0]), 0, 1))))
        mg, who = self.margin(q_deg)
        ok = pos_err < 2.0 and face_tilt < 2.0 and lean <= max_lean_deg + 2 and mg >= 0
        return IKResult(q_deg, pos_err, face_tilt, ok, mg, who)

    def ik_topdown_multi(self, target_mm, seeds: int = 16, **kw) -> IKResult:
        rng = np.random.default_rng(1)
        from .calib import park_mjcf_deg
        starts = [np.zeros(5), park_mjcf_deg(self.cfg), np.array([0, -30, 30, 80, -45.0]),
                  np.array([0, -45, 20, 85, 45.0])]
        while len(starts) < seeds:
            starts.append(rng.uniform(self.lo * 0.7, self.hi * 0.7))
        best = None
        for q0 in starts:
            res = self.ik_topdown(target_mm, q0=q0, **kw)
            if best is None or (res.ok and (not best.ok or res.margin_deg > best.margin_deg)) \
                    or (not best.ok and not res.ok and res.pos_err_mm < best.pos_err_mm):
                best = res
        return best

    def ik_multi(self, target_mm, axis_world=None, grasp: str = "side", seeds: int = 14,
                 rng: np.random.Generator | None = None, **kw) -> IKResult:
        """IK from several seeds, keeping the solution with the largest joint margin."""
        rng = rng or np.random.default_rng(0)
        from .calib import park_mjcf_deg
        park = park_mjcf_deg(self.cfg)
        starts = [np.zeros(5), park, np.array([0, 40, -80, 40, 0.0]),
                  np.array([0, -30, 60, -30, 0.0])]
        while len(starts) < seeds:
            starts.append(rng.uniform(self.lo * 0.7, self.hi * 0.7))
        best: IKResult | None = None
        for q0 in starts[:seeds]:
            res = self.ik(target_mm, axis_world, grasp, q0=q0, **kw)
            if res.ok and (best is None or res.margin_deg > best.margin_deg):
                best = res
            elif best is None:
                best = res
            elif not best.ok and res.pos_err_mm < best.pos_err_mm:
                best = res
        return best  # type: ignore[return-value]


class BenchKin:
    """Both arms against one compiled model (physics-free; used for planning and checks)."""

    def __init__(self, model: mujoco.MjModel | None = None, cfg: Config | None = None):
        self.cfg = cfg or load()
        if model is None:
            from ..paths import BENCH_XML
            model = mujoco.MjModel.from_xml_path(str(BENCH_XML))
        self.m = model
        self.arms = {r: ArmKin(model, r, self.cfg) for r in ("pourer", "transfer")}

    def __getitem__(self, role: str) -> ArmKin:
        return self.arms[role]
