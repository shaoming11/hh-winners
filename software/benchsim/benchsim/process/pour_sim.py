"""Tilt actuator for the pour controller: theta (deg) -> pourer joint goal along a planned pour manifold.

``ManifoldTilt`` only needs an ArmBackend and a (theta, q) table, so it drives the simulated or the real arm. The
table comes from a Planner.plan_pour plan (``manifold_table``): the 'tilt-in 0->40' segment (joint-linear from the
upright pre-pour pose into the 40 deg manifold pose; theta of each configuration from forward kinematics of the
held beaker) followed by the 'pour manifold 40->105' segment (one IK solution per degree). Between table entries the
joint vector is interpolated linearly in theta.
"""
import math

import numpy as np

TILT_SEG = 'tilt-in 0->40'
MANIFOLD_SEG = 'pour manifold 40->105'


def manifold_table(planner, segs, info, arm='pourer'):
    """(thetas, qs) for theta 0..105 from a pour plan. theta = angle of the held beaker's axis from vertical, with the
    beaker in the grasp frame the planner assumed (beaker axis = sign * site z, bottom grip_h below the site)."""
    from ..trajectories import _held_T
    by = {s['name']: s for s in segs}
    qs = list(by[TILT_SEG]['qs']) + list(by[MANIFOLD_SEG]['qs'][1:])
    T = _held_T(info['sign'], info['grip_h_used'])
    th = []
    for q in qs:
        _, R = planner.K.site(arm, q, 'grasp_side'); u = R @ T[:3, :3][:, 2]
        th.append(math.degrees(math.acos(float(np.clip(u[2], -1, 1)))))
    th = np.array(th); qs = np.array(qs)
    if np.any(np.diff(th) <= 0): raise ValueError('pour table theta is not monotonic: %s' % np.round(th, 2))
    return th, qs


class ManifoldTilt:
    def __init__(self, arm, thetas, qs, q6_hold, min_step_deg=0.01):
        self.arm = arm; self.th = np.asarray(thetas, float); self.qs = np.asarray(qs, float); self.q6 = float(q6_hold)
        self.min_step = min_step_deg; self.last = None; self.commands = 0

    @property
    def theta_range(self): return float(self.th[0]), float(self.th[-1])

    def q_of(self, theta_deg):
        t = min(max(float(theta_deg), self.th[0]), self.th[-1])
        q = np.array([np.interp(t, self.th, self.qs[:, j]) for j in range(self.qs.shape[1])]); q[5] = self.q6
        return q

    def set_theta(self, theta_deg):
        if self.last is not None and abs(theta_deg - self.last) < self.min_step: return
        self.arm.set_goal(self.q_of(theta_deg)); self.last = float(theta_deg); self.commands += 1
