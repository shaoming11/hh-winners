"""Pitch pour ("the way a person pours"): wrist roll frozen at the upright-grasp value, the beaker tilts about the
grasp axis (parallel to the pitch axes) using shoulder + elbow + wrist flex; pan keeps the receiver on the arm's radial
line.  Lip pinned exactly (planar 3R + pan).  Joint limits not enforced in the solve; margins reported."""
import math
import numpy as np
import layout_lib as L

H, D, R_ = 74.0, 56, 28.0

def _lip_resid(A, Mrel, roll, lip_t, th, d_fixed):
    cz = math.cos(math.radians(th))
    def resid(Q4):
        Q = np.c_[Q4, np.full(len(Q4), roll)]
        Rm, tt = A.fk(Q); Rb = Rm @ Mrel[:3, :3]; pb = Rm @ Mrel[:3, 3] + tt; ax = Rb[:, :, 2]
        if th < 3 or d_fixed is not None and th < 3:
            dv = np.broadcast_to(d_fixed, ax.shape)
        else:
            h = ax - ax[:, 2:3] * np.array([0, 0, 1.0]); dv = h / np.maximum(np.linalg.norm(h, axis=1, keepdims=True), 1e-9)
        av = np.cross(np.array([0, 0, 1.0]), dv)
        lip = pb + H * ax + R_ * np.cross(av, ax)
        return np.c_[lip - lip_t, 60 * (ax[:, 2] - cz)]
    return resid

def _lm4(resid, Q4, iters, step=0.1, lam=1e-4):
    N = len(Q4)
    for _ in range(iters):
        r = resid(Q4); J = np.zeros((N, r.shape[1], 4))
        for k in range(4):
            dQ = Q4.copy(); dQ[:, k] += 1e-5; J[:, :, k] = (resid(dQ) - r) / 1e-5
        A_ = np.einsum('nri,nrj->nij', J, J) + lam * np.eye(4); b = -np.einsum('nri,nr->ni', J, r)
        Q4 = Q4 + np.clip(np.linalg.solve(A_, b[..., None])[..., 0], -step, step)
    return Q4, resid(Q4)

def pitch_pour(t, off, sign, q_up, lip_xy, rim_z, h_pour, h_hi, gh, outward):
    """q_up: an upright grasp pose (sets roll + branch).  Path: upright with lip at h_hi -> tilt to 55 at h_hi ->
    descend to h_pour -> tilt 55..105.  Returns dict(path=[...], seg idx, ok, maxstep) or None"""
    A = L.ARM[t]; Mrel = L.held_rel(t, D, gh, sign); roll = q_up[4]; off = np.asarray(off, float)
    d0 = np.r_[outward[:2] / np.linalg.norm(outward[:2]), 0.0]
    q4 = q_up[None, :4].copy(); path = []; maxstep = 0.0
    def go(lip_w, th, iters=40):
        nonlocal q4, maxstep
        res = _lip_resid(A, Mrel, roll, lip_w - off, th, d0)
        qn, r = _lm4(res, q4, iters)
        if np.abs(r).max() > 0.5: return False
        maxstep = max(maxstep, np.degrees(np.abs(qn - q4).max())); q4 = qn
        path.append(np.r_[q4[0], roll]); return True
    lip_hi = np.r_[lip_xy, rim_z + h_hi]; lip_lo = np.r_[lip_xy, rim_z + h_pour]
    if not go(lip_hi, 0.0, 150): return None
    k_up = 0
    for th in np.arange(5.0, 55.01, 5.0):
        if not go(lip_hi, th): return None
    k55h = len(path) - 1; ms_tilt = maxstep; maxstep = 0
    for z in np.arange(h_hi - 2, h_pour - 0.01, -2.0):
        if not go(np.r_[lip_xy, rim_z + z], 55.0): return None
    if abs(path and 0) or True: pass
    k55 = len(path) - 1; ms_desc = maxstep; maxstep = 0
    for th in np.arange(56.0, 105.01, 1.0):
        if not go(lip_lo, th): return None
    return dict(path=path, k55h=k55h, k55=k55, step_pour=maxstep, step_tilt=ms_tilt, step_desc=ms_desc)
