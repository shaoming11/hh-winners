"""CAD planner convention -> official SO-101 (so101_new_calib) joint convention.

The CAD planner (software/tools/planner/kin_model.py and the missing ~/fusion_bridge/layout_lib.py) measures every
joint angle from the Fusion *as-built* pose of arm A, about six joint axes measured from the geometry
(``AXES_A``). Joint directions were sign-calibrated with a +10 deg probe stored in ~/fusion_bridge/kin.json,
which is not in the repository. So the mapping is

    q_mj[j] = o[j] + s[j] * q_cad[j]

with o = the as-built pose expressed in MJCF joint values (fitted here from AXES_A) and s = +-1 per joint
(unknown from the files present; inferred in benchsim.trajectories from joint limits and station endpoints).

``fit_asbuilt`` places the upstream MJCF arm with its pan axis on the CAD arm-A pan axis and its base facing -Y,
then solves the four pitch/roll joint values and the base height that put the MJCF joint axes on the CAD axes.
The pan offset is fixed at 0 (the planner's own URDF mapping, tools/layout/urdf_limits.py, sets it to 0 by
construction). Residuals are reported per axis; ``python -m benchsim.cadmap`` writes config/cad_asbuilt_fit.json.
"""
import ast
import json
import math
import sys

import mujoco
import numpy as np
from scipy.optimize import least_squares

from . import assets, paths

KIN_MODEL = paths.REPO / 'software' / 'tools' / 'planner' / 'kin_model.py'
FIT_JSON = paths.CONFIG / 'cad_asbuilt_fit.json'
JOINTS = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper']
ARM_B_DX = 240.0          # kin_model.Arm: arm B = arm A + 240 mm in X (as built)


def load_axes():
    """AXES_A from kin_model.py, read with ast (the module itself imports the missing kin.json)"""
    tree = ast.parse(KIN_MODEL.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'AXES_A' for t in node.targets):
            return [(np.array(p, float), np.array(d, float) / np.linalg.norm(d)) for p, d in ast.literal_eval(node.value)]
    raise RuntimeError('AXES_A not found in %s' % KIN_MODEL)


def base_rotation(yaw_deg):
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


class ArmFK:
    """upstream single-arm model with a world placement (mm in, mm out)"""

    def __init__(self, pan_xy, base_z, yaw_deg=-90.0, pan_axis_in_base=(38.8353, 0.0)):
        self.m = mujoco.MjModel.from_xml_path(str(assets.model_xml())); self.d = mujoco.MjData(self.m)
        self.R = base_rotation(yaw_deg)
        self.o = np.r_[np.asarray(pan_xy, float) - (self.R[:2, :2] @ np.asarray(pan_axis_in_base)), base_z]

    def set(self, q):
        self.d.qpos[:] = 0; self.d.qpos[:len(q)] = q; mujoco.mj_kinematics(self.m, self.d)

    def axes(self, q):
        self.set(q)
        return [(self.R @ (self.d.xanchor[j] * 1000) + self.o, self.R @ self.d.xaxis[j]) for j in range(self.m.njnt)]

    def body_pose(self, name, q):
        """world pose (R, p_mm) of a body"""
        self.set(q); b = self.m.body(name).id
        return self.R @ self.d.xmat[b].reshape(3, 3), self.R @ (self.d.xpos[b] * 1000) + self.o


def _line_res(p, a, cp, ca):
    v = p - cp; v = v - ca * (v @ ca)
    return v, math.degrees(math.acos(min(1.0, abs(float(a @ ca)))))


def fit_asbuilt(base_z0=22.4):
    AX = load_axes(); pan_xy = AX[0][0][:2]

    def res(x):
        fk = ArmFK(pan_xy, x[4]) if not hasattr(res, 'fk') else res.fk
        res.fk = fk; fk.o[2] = x[4]
        A = fk.axes(np.r_[0.0, x[:4], 0.0]); r = []
        for j in range(1, 6):
            v, _ = _line_res(A[j][0], A[j][1], *AX[j]); r += list(v); r += list(50 * np.cross(A[j][1], AX[j][1]))
        return np.array(r)
    best = None
    for s in ([-90, 90, 0, 0], [90, -90, 0, 0], [-90, -90, 0, 0], [90, 90, 0, 0]):
        r = least_squares(res, np.r_[np.radians(s), base_z0])
        if best is None or r.cost < best.cost: best = r
    x = best.x; q0 = np.r_[0.0, [(v + math.pi) % (2 * math.pi) - math.pi for v in x[:4]]]
    fk = ArmFK(pan_xy, x[4]); A = fk.axes(np.r_[q0, 0.0]); rows = []
    for j in range(6):
        v, ang = _line_res(A[j][0], A[j][1], *AX[j])
        rows.append(dict(joint=JOINTS[j], line_dist_mm=round(float(np.linalg.norm(v)), 2), axis_angle_deg=round(ang, 2),
                         mj_dir=np.round(A[j][1], 4).tolist(), cad_dir=np.round(AX[j][1], 4).tolist()))
    return dict(q0_deg=np.round(np.degrees(q0), 3).tolist(), base_z=round(float(x[4]), 2), pan_xy=pan_xy.tolist(),
                residuals=rows, fit_cost=float(best.cost))


def load_fit():
    if not FIT_JSON.exists():
        raise FileNotFoundError('%s missing: run python -m benchsim.cadmap' % FIT_JSON)
    return json.loads(FIT_JSON.read_text())


def gripper_offset_deg():
    from .layout import load_params
    return load_params()['gripper']['cad_to_mj_offset_deg']


def asbuilt_q(fit=None):
    """MJCF joint vector (6, rad) of the CAD as-built pose, gripper at CAD q6 = 0"""
    fit = fit or load_fit()
    return np.r_[np.radians(fit['q0_deg']), math.radians(gripper_offset_deg())]


def to_body_frame(points_world_mm, body, fit=None, q6_cad=0.0):
    """express as-built world points (arm A, mm) in the frame of an MJCF body (mm), at the as-built pose"""
    fit = fit or load_fit(); fk = ArmFK(fit['pan_xy'], fit['base_z'])
    q = asbuilt_q(fit); q[5] += q6_cad
    R, p = fk.body_pose(body, q)
    return (np.asarray(points_world_mm, float) - p) @ R


if __name__ == '__main__':
    f = fit_asbuilt()
    if '--write' in sys.argv or len(sys.argv) == 1:
        FIT_JSON.write_text(json.dumps(f, indent=1) + '\n'); print('wrote', FIT_JSON)
    print('as-built pose in MJCF joints (deg):', f['q0_deg'], ' base z %.2f mm' % f['base_z'])
    for r in f['residuals']:
        print('  %-14s line distance %5.2f mm   axis angle %5.2f deg' % (r['joint'], r['line_dist_mm'], r['axis_angle_deg']))


# Joint direction signs s[j] (CAD -> MJCF). Not recoverable from kin.json (absent). Inferred by
# benchsim.trajectories: of the 32 sign combinations only all +1 keeps every recorded pick/place frame within
# the MJCF joint limits, and it is the unique minimum of the station endpoint error (see the kinematics report).
SIGNS = np.array([1.0, 1.0, 1.0, 1.0, 1.0])


def cad_to_mj(q_cad, fit=None):
    """CAD planner joint angles (5, rad, relative to the as-built pose) -> MJCF joint values (5, rad)"""
    fit = fit or load_fit()
    return np.radians(fit['q0_deg'])[:5] + SIGNS * np.asarray(q_cad, float)[:5]


def cad_gripper_to_mj(q6_cad):
    return math.radians(gripper_offset_deg()) + float(q6_cad)
