"""Commanded vs measured, per arm: the tool point from forward kinematics of the last commanded goal and of the
measured joint angles (private MjData, benchsim.kinematics.Kin), their distance in mm and the per-joint differences.

What this can and cannot see. The measured angles come from the servos' own encoders, so a tracking error (stall,
collision, overload, a slow servo) shows up here. A wrong servo zero does not: commanded and measured then agree
while the real arm is off by the calibration error. That is caught physically instead, by the grasp jaw angle and
the scale checks (Errors & checks panel). While an arm moves, the goal streams ahead of the servo, so the distance
is tracking lag; it only counts as an error once the arm has settled.
"""
import math

import numpy as np

from ..kinematics import Kin
from ..state import ARM_JOINTS

SITE = {'pourer': 'grasp_side', 'transfer': 'grasp_td_taught'}
CAVEAT = ('Servo encoders report where each servo believes it is. A tracking error shows here; a wrong zero offset '
          'does not (commanded and measured agree while the real arm is off). The grasp and scale checks catch that.')


class Twin:
    def __init__(self, model):
        self.k = Kin(model)

    def tool(self, arm, q):
        p, _ = self.k.site(arm, np.asarray(q, float), SITE[arm]); return p

    def arm(self, name, q, goal, moving=False):
        p = self.tool(name, q)
        out = dict(site=SITE[name], measured_mm=[round(float(v), 1) for v in p], settled=not moving)
        if goal is None: return out
        g = np.asarray(goal, float); pc = self.tool(name, g); d = p - pc
        out.update(commanded_mm=[round(float(v), 1) for v in pc], error_mm=round(float(np.linalg.norm(d)), 2),
                   error_xyz_mm=[round(float(v), 2) for v in d],
                   joint_err_deg={j: round(math.degrees(float(q[i] - g[i])), 2) for i, j in enumerate(ARM_JOINTS[:5])},
                   jaw_deg=dict(measured=round(math.degrees(float(q[5])), 2), commanded=round(math.degrees(float(g[5])), 2)))
        return out
