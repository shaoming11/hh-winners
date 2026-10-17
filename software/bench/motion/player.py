"""Joint-space motion player: rate-limited goal streaming with a tracking guard.

Mirrors the ArmThread rules of software_architecture.md 2.6/3.4: goals change by at most
`max_joint_rate` per tick, only one arm moves at a time (single-mover token), and a tracking
error above 4 deg for 0.3 s stops the move.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from bench.config import Config, load
from bench.hal.base import ARM_JOINTS, Bench, BenchFault

J5 = ARM_JOINTS[:5]


class TrackingError(BenchFault):
    pass


@dataclass
class MotionLock:
    holder: str | None = None

    def acquire(self, role: str) -> None:
        if self.holder not in (None, role):
            raise BenchFault(f"{role} asked to move while {self.holder} holds the motion token")
        self.holder = role

    def release(self, role: str) -> None:
        if self.holder == role:
            self.holder = None


class Player:
    TICK = 0.02                                  # 50 Hz goal stream

    def __init__(self, bench: Bench, role: str, lock: MotionLock, cfg: Config | None = None,
                 speed_scale: float = 1.0):
        self.b = bench
        self.role = role
        self.lock = lock
        self.cfg = cfg or load()
        self.speed_scale = speed_scale
        self.max_rate = float(self.cfg.at("arms.max_joint_rate_dps"))
        s = self.cfg.at("control.safety")
        self.guard_err = float(s["tracking_err_deg"])
        self.guard_s = float(s["tracking_err_s"])
        self.goal = {k: v for k, v in self.b.arms[role].read_positions().items() if k in J5}
        self.history: list[dict[str, float]] = []   # executed goals, for reverse-replay retreat

    @property
    def arm(self):
        return self.b.arms[self.role]

    def q(self) -> np.ndarray:
        p = self.arm.read_positions()
        return np.array([p[j] for j in J5])

    def goal_vec(self) -> np.ndarray:
        return np.array([self.goal[j] for j in J5])

    # ---------------------------------------------------------------- moves
    def move_to(self, q_deg, speed_dps: float = 60.0, settle_tol: float = 2.0,
                settle_timeout: float = 2.5, guard_joints=None) -> None:
        """Smoothstep from the current goal to `q_deg` (5 arm joints) at a peak joint speed
        of `speed_dps` (scaled by speed_scale), then wait until the arm tracks."""
        self.lock.acquire(self.role)
        target = np.asarray(q_deg, float)[:5]
        start = self.goal_vec()
        dq = target - start
        peak = min(speed_dps * self.speed_scale, self.max_rate)
        dur = max(float(np.max(np.abs(dq))) / peak * 1.5, 2 * self.TICK)  # smoothstep peak = 1.5x mean
        n = max(int(math.ceil(dur / self.TICK)), 1)
        err_t = 0.0
        for k in range(1, n + 1):
            u = k / n
            s = u * u * (3 - 2 * u)
            g = start + dq * s
            self._write(g)
            self.b.clock.sleep(self.TICK)
            err_t = self._guard(g, err_t, guard_joints)
        self._settle(target, settle_tol, settle_timeout)

    def follow(self, waypoints, speed_dps: float = 60.0, **kw) -> None:
        for wp in waypoints:
            self.move_to(wp, speed_dps, **kw)

    def hold(self) -> None:
        self._write(self.goal_vec())

    def retreat(self, steps: int = 20, speed_dps: float = 30.0) -> None:
        """Reverse-replay the last executed goals - the universal retreat primitive."""
        path = list(reversed(self.history[-steps:]))
        for g in path:
            self.move_to([g[j] for j in J5], speed_dps, settle_tol=4.0, settle_timeout=0.5)

    def done(self) -> None:
        self.lock.release(self.role)

    # ---------------------------------------------------------------- internals
    def _write(self, g: np.ndarray) -> None:
        goals = {j: float(v) for j, v in zip(J5, g)}
        self.goal.update(goals)
        self.arm.write_goals(goals)
        self.history.append(dict(goals))
        if len(self.history) > 4000:
            del self.history[:2000]

    def _guard(self, g: np.ndarray, err_t: float, joints) -> float:
        q = self.q()
        idx = range(5) if joints is None else [J5.index(j) for j in joints]
        err = max(abs(q[i] - g[i]) for i in idx)
        if err > self.guard_err:
            err_t += self.TICK
            if err_t >= self.guard_s:
                self.hold()
                raise TrackingError(f"{self.role} tracking error {err:.1f} deg for {err_t:.2f} s")
            return err_t
        return 0.0

    def _settle(self, target: np.ndarray, tol: float, timeout: float) -> None:
        t0 = self.b.clock.now()
        while self.b.clock.now() - t0 < timeout:
            if float(np.max(np.abs(self.q() - target))) < tol:
                return
            self.b.clock.sleep(self.TICK)
        err = float(np.max(np.abs(self.q() - target)))
        if err > tol * 2.5:
            raise TrackingError(f"{self.role} did not settle: {err:.1f} deg off after {timeout} s")
