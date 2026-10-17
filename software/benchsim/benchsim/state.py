"""Named poses and the initial state of the bench model."""
import math

import mujoco
import numpy as np

from . import cadmap, layout, scene

ARM_JOINTS = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper']


def park_q(params=None):
    """park pose in MJCF joints (6, rad): anim_paths park (CAD) mapped with cadmap, gripper at the CAD open angle"""
    P = params or layout.load_params()
    q = cadmap.cad_to_mj(np.radians(P['arm']['park_deg_cad']))
    return np.r_[q, cadmap.cad_gripper_to_mj(math.radians(-33.28))]


def qadr(model, arm):
    return np.array([model.joint('%s/%s' % (arm, j)).qposadr[0] for j in ARM_JOINTS])


def actadr(model, arm):
    return np.array([model.actuator('%s/%s' % (arm, j)).id for j in ARM_JOINTS])


def reset(model, data, params=None):
    """arms parked, actuators holding, everything else at the model reference pose"""
    mujoco.mj_resetData(model, data)
    q = park_q(params)
    for arm in scene.ARMS:
        data.qpos[qadr(model, arm)] = q; data.ctrl[actadr(model, arm)] = q
    j = model.joint('scale_flex')                 # start the load-cell flexure at its static deflection
    data.qpos[j.qposadr[0]] = -model.body('scale_pan').mass[0] * 9.81 / model.jnt_stiffness[j.id]
    mujoco.mj_forward(model, data)
