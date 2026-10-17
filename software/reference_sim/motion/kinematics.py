"""Joint-limited differential inverse kinematics for the official SO-101 MJCF."""
from __future__ import annotations

from dataclasses import dataclass
import math

import mujoco
import numpy as np

from world import BenchWorld


ARM_JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")


class IKError(RuntimeError):
    pass


@dataclass(frozen=True)
class IKResult:
    q_rad: np.ndarray
    position_error_mm: float
    axis_error_deg: float
    min_joint_margin_deg: float
    iterations: int

    def degrees(self) -> np.ndarray:
        return np.degrees(self.q_rad)


class ArmKinematics:
    """FK and damped least-squares IK using the same model as the simulator."""

    def __init__(self, world: BenchWorld, arm: str):
        if arm not in ("pourer", "transfer"):
            raise ValueError(f"Unknown arm: {arm}")
        self.world = world
        self.model = world.model
        self.arm = arm
        self.joint_ids = np.asarray([
            mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, f"{arm}_{name}")
            for name in ARM_JOINTS
        ], dtype=int)
        if np.any(self.joint_ids < 0):
            raise ValueError(f"Scene is missing {arm} SO-101 joints")
        self.qpos_ids = self.model.jnt_qposadr[self.joint_ids].astype(int)
        self.dof_ids = self.model.jnt_dofadr[self.joint_ids].astype(int)
        self.limits = self.model.jnt_range[self.joint_ids].copy()
        self.site_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_SITE, f"{arm}_gripperframe")
        if self.site_id < 0:
            raise ValueError(f"Scene is missing {arm}_gripperframe")
        self.data = mujoco.MjData(self.model)
        self.jacp = np.zeros((3, self.model.nv))
        self.jacr = np.zeros((3, self.model.nv))

    def _forward(self, q_rad: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        self.data.qpos[:] = self.world.data.qpos
        self.data.qvel[:] = 0
        self.data.qpos[self.qpos_ids] = q_rad
        mujoco.mj_forward(self.model, self.data)
        pos = self.data.site_xpos[self.site_id].copy()
        rot = self.data.site_xmat[self.site_id].reshape(3, 3).copy()
        return pos, rot

    def current_q(self) -> np.ndarray:
        return self.world.data.qpos[self.qpos_ids].copy()

    def forward(self, q_rad: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Return gripperframe position in meters and rotation matrix in world frame."""
        return self._forward(self.current_q() if q_rad is None else np.asarray(q_rad, float))

    def joint_margins_deg(self, q_rad: np.ndarray) -> np.ndarray:
        q_deg = np.degrees(q_rad)
        limits_deg = np.degrees(self.limits)
        return np.minimum(q_deg - limits_deg[:, 0], limits_deg[:, 1] - q_deg)

    def _iterate(self, target_xyz: np.ndarray, q0: np.ndarray, *, target_z: np.ndarray | None,
                 position_tol_m: float, axis_tol_deg: float, max_iterations: int,
                 damping: float, axis_weight_m: float) -> IKResult:
        lo, hi = self.limits[:, 0], self.limits[:, 1]
        q = np.clip(np.asarray(q0, float), lo, hi)
        if target_z is not None:
            target_z = np.array(target_z, dtype=float, copy=True)
            target_z /= np.linalg.norm(target_z)
            helper = np.array([0.0, 0.0, 1.0]) if abs(target_z[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
            basis1 = np.cross(target_z, helper)
            basis1 /= np.linalg.norm(basis1)
            basis2 = np.cross(target_z, basis1)
            basis = np.vstack((basis1, basis2))

        pos_err = float("inf")
        axis_err = float("inf")
        for iteration in range(1, max_iterations + 1):
            pos, rot = self._forward(q)
            pos_error = target_xyz - pos
            pos_err = float(np.linalg.norm(pos_error))
            if target_z is None:
                axis_error_vec = None
                axis_err = 0.0
            else:
                tool_z = rot[:, 2]
                axis_error_vec = np.cross(tool_z, target_z)
                axis_err = math.degrees(math.acos(float(np.clip(tool_z @ target_z, -1.0, 1.0))))
            if pos_err <= position_tol_m and axis_err <= axis_tol_deg:
                break

            mujoco.mj_jacSite(self.model, self.data, self.jacp, self.jacr, self.site_id)
            jpos = self.jacp[:, self.dof_ids]
            error = pos_error
            jac = jpos
            if target_z is not None:
                # At the solution, a small angular velocity moves the tool axis toward target_z.
                jaxis = basis @ self.jacr[:, self.dof_ids]
                eaxis = basis @ axis_error_vec
                jac = np.vstack((jpos, axis_weight_m * jaxis))
                error = np.concatenate((pos_error, axis_weight_m * eaxis))
            gram = jac @ jac.T + damping * np.eye(jac.shape[0])
            try:
                delta = jac.T @ np.linalg.solve(gram, error)
            except np.linalg.LinAlgError:
                break
            delta = np.clip(delta, -0.14, 0.14)
            q = np.clip(q + delta, lo, hi)

        margins = self.joint_margins_deg(q)
        return IKResult(q, pos_err, axis_err, float(margins.min()), iteration)

    def solve_position(self, target_xyz_m: tuple[float, float, float] | np.ndarray,
                       q0: np.ndarray | None = None, *, position_tol_mm: float = 2.0,
                       max_iterations: int = 240) -> IKResult:
        target = np.asarray(target_xyz_m, float)
        result = self._iterate(target, self.current_q() if q0 is None else q0,
                              target_z=None, position_tol_m=position_tol_mm / 1000,
                              axis_tol_deg=180, max_iterations=max_iterations,
                              damping=1e-4, axis_weight_m=0.0)
        if result.position_error_mm > position_tol_mm:
            raise IKError(f"{self.arm} target missed by {result.position_error_mm:.1f} mm")
        return result

    def solve_position_axis(self, target_xyz_m: tuple[float, float, float] | np.ndarray,
                            target_tool_z: np.ndarray, q0: np.ndarray | None = None, *,
                            position_tol_mm: float = 3.0, axis_tol_deg: float = 2.0,
                            max_iterations: int = 300) -> IKResult:
        result = self._iterate(np.asarray(target_xyz_m, float),
                              self.current_q() if q0 is None else q0,
                              target_z=target_tool_z, position_tol_m=position_tol_mm / 1000,
                              axis_tol_deg=axis_tol_deg, max_iterations=max_iterations,
                              damping=1e-4, axis_weight_m=0.08)
        if result.position_error_mm > position_tol_mm or result.axis_error_deg > axis_tol_deg:
            raise IKError(f"{self.arm} pose missed: {result.position_error_mm:.1f} mm, "
                          f"tool-axis error {result.axis_error_deg:.1f} deg")
        return result

    def solve_line(self, start_xyz_m: np.ndarray, end_xyz_m: np.ndarray, q0: np.ndarray,
                   *, step_mm: float = 20.0, target_tool_z: np.ndarray | None = None,
                   axis_tol_deg: float = 2.0) -> list[IKResult]:
        """Solve a Cartesian line by continuation, preserving the selected joint branch."""
        start, end = np.asarray(start_xyz_m, float), np.asarray(end_xyz_m, float)
        distance_mm = np.linalg.norm(end - start) * 1000
        count = max(1, math.ceil(distance_mm / step_mm))
        results = []
        q = np.asarray(q0, float)
        for i in range(1, count + 1):
            target = start + (end - start) * (i / count)
            if target_tool_z is None:
                result = self.solve_position(target, q)
            else:
                result = self.solve_position_axis(target, target_tool_z, q,
                                                  axis_tol_deg=axis_tol_deg)
            results.append(result)
            q = result.q_rad
        return results
