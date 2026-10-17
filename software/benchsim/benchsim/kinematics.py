"""Forward/inverse kinematics, joint margins, collisions and clearance for the two arms, on the full bench model.

All queries use a private MjData so they never disturb a running simulation. Inputs and reports are mm/deg;
joint vectors are MJCF radians (6 values: 5 arm joints + gripper).

Margin rule (docs/demo_process.md 3): degrees to the nearest joint limit, where the limit is the URDF limit
minus 5 deg. Picks, places and pours need >= 10 deg, carries >= 5 deg.
"""
import math

import mujoco
import numpy as np

from . import scene, state
from .units import m, mm

LIMIT_INSET_DEG = 5.0
RULE = {'pick': 10.0, 'place': 10.0, 'pour': 10.0, 'carry': 5.0, 'approach': 5.0, 'retreat': 5.0, 'park': 5.0}
JN = state.ARM_JOINTS


def rot_to_quat(R):
    q = np.zeros(4); mujoco.mju_mat2Quat(q, np.asarray(R, float).reshape(9)); return q


class Kin:
    def __init__(self, model, park=None):
        self.m = model; self.d = mujoco.MjData(model); state.reset(model, self.d)
        self.base_qpos = self.d.qpos.copy()
        self.qadr = {a: state.qadr(model, a) for a in scene.ARMS}
        self.dofadr = {a: np.array([model.jnt_dofadr[model.joint('%s/%s' % (a, j)).id] for j in JN]) for a in scene.ARMS}
        self.range = {a: np.array([model.jnt_range[model.joint('%s/%s' % (a, j)).id] for j in JN]) for a in scene.ARMS}
        self.geoms = {}; bodies = {}
        for g in range(model.ngeom):
            if model.geom_contype[g] == 0 and model.geom_conaffinity[g] == 0: continue
            bn = model.body(model.geom_bodyid[g]).name
            owner = bn.split('/')[0] if '/' in bn else ('beaker:' + bn[7:] if bn.startswith('beaker_') else 'scene')
            self.geoms.setdefault(owner, []).append(g); bodies[g] = bn
        self.body_of = bodies
        self.held = None
        self.beaker_override = {}               # name -> (pos m, quat) for beakers moved away from their start

    # ------------------------------------------------------------------ configuration
    def set(self, arm, q, other=None, held=None):
        """arm joints q (6); other = {arm: q}; held = (beaker, T_site_beaker, site) to place a beaker on the gripper"""
        d = self.d; d.qpos[:] = self.base_qpos
        d.qpos[self.qadr[arm]] = q
        for a, qo in (other or {}).items(): d.qpos[self.qadr[a]] = qo
        for name, (p, quat) in self.beaker_override.items():
            adr = self.m.jnt_qposadr[self.m.joint('beaker_' + name).id]; d.qpos[adr:adr + 3] = p; d.qpos[adr + 3:adr + 7] = quat
        mujoco.mj_kinematics(self.m, d)
        if held is not None:
            name, T, site = held
            sp = d.site('%s/%s' % (arm, site)); R = sp.xmat.reshape(3, 3); p = sp.xpos
            Rb = R @ T[:3, :3]; pb = p + R @ T[:3, 3]
            adr = self.m.jnt_qposadr[self.m.joint('beaker_' + name).id]
            d.qpos[adr:adr + 3] = pb; d.qpos[adr + 3:adr + 7] = rot_to_quat(Rb)
            mujoco.mj_kinematics(self.m, d)
        mujoco.mj_comPos(self.m, d)             # cdof / subtree_com for mj_jacSite
        self.held = held
        return d

    def site(self, arm, q, site):
        self.set(arm, q); s = self.d.site('%s/%s' % (arm, site))
        return mm(s.xpos.copy()), s.xmat.reshape(3, 3).copy()

    # ------------------------------------------------------------------ margins
    def margins(self, arm, q):
        lo = self.range[arm][:5, 0] + math.radians(LIMIT_INSET_DEG); hi = self.range[arm][:5, 1] - math.radians(LIMIT_INSET_DEG)
        q = np.asarray(q)[:5]
        return np.degrees(np.minimum(q - lo, hi - q))

    def min_margin(self, arm, q):
        mg = self.margins(arm, q); j = int(np.argmin(mg)); return float(mg[j]), JN[j]

    def in_limits(self, arm, q):
        r = self.range[arm]; q = np.asarray(q)
        return bool(np.all(q[:5] >= r[:5, 0] - 1e-9) and np.all(q[:5] <= r[:5, 1] + 1e-9))

    # ------------------------------------------------------------------ IK
    def ik(self, arm, site, pos_mm, z_axis=None, x_axis=None, q0=None, iters=200, tol_mm=0.05, w_ori=100.0, z_sign_free=False,
           lock_roll=None, max_dev=None, soft_dir=None, soft_w=0.05):
        """bounded least squares (scipy trf, analytic MuJoCo Jacobian) on the 5 arm joints: site position (mm) and
        optionally its z (and x) axis direction. z_sign_free accepts +-z_axis. Orientation residuals are scaled to
        w_ori mm per radian. Returns (q, pos_err_mm, ang_err_deg)."""
        from scipy.optimize import least_squares
        q = np.array(q0 if q0 is not None else state.park_q(), float)
        tgt = np.asarray(pos_mm, float); sid = self.m.site('%s/%s' % (arm, site)).id
        dof = self.dofadr[arm][:5]; lo, hi = self.range[arm][:5, 0], self.range[arm][:5, 1]
        zt = None if z_axis is None else np.asarray(z_axis, float) / np.linalg.norm(z_axis)
        xt = None if x_axis is None else np.asarray(x_axis, float) / np.linalg.norm(x_axis)
        if z_sign_free and zt is not None:
            self.set(arm, q); zt = zt if self.d.site_xmat[sid].reshape(3, 3)[:, 2] @ zt >= 0 else -zt
        jp = np.zeros((3, self.m.nv)); jr = np.zeros((3, self.m.nv)); qq = q.copy()
        W = np.eye(3)                            # soft_dir: position error along this direction is weighted soft_w
        if soft_dir is not None:
            sd = np.asarray(soft_dir, float) / np.linalg.norm(soft_dir); W = np.eye(3) - (1 - soft_w) * np.outer(sd, sd)

        def fk(x):
            qq[:5] = x; self.set(arm, qq); return self.d.site_xpos[sid] * 1000, self.d.site_xmat[sid].reshape(3, 3)

        def res(x):
            p, R = fk(x); r = [W @ (p - tgt)]
            if zt is not None: r.append(w_ori * np.cross(R[:, 2], zt))
            if xt is not None: r.append(w_ori * np.cross(R[:, 0], xt))
            return np.concatenate(r)

        def jac(x):
            p, R = fk(x); mujoco.mj_jacSite(self.m, self.d, jp, jr, sid); J = [W @ jp[:, dof] * 1000]
            for axis, t in ((R[:, 2], zt), (R[:, 0], xt)):
                if t is None: continue
                # d(a x t)/dq = -[t]x (w x a) = -[t]x (-[a]x w) -> [t]x [a]x Jr
                ax = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
                tx = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]])
                J.append(w_ori * tx @ ax @ jr[:, dof])
            return np.vstack(J)
        x0 = np.clip(q[:5], lo + 1e-9, hi - 1e-9)
        if max_dev is not None:                  # continuation: stay on the seed's branch
            lo = np.maximum(lo, x0 - max_dev); hi = np.minimum(hi, x0 + max_dev); x0 = np.clip(x0, lo + 1e-9, hi - 1e-9)
        if lock_roll is not None: lo, hi = lo.copy(), hi.copy(); lo[4] = x0[4] - 1e-9; hi[4] = x0[4] + 1e-9
        sol = least_squares(res, x0, jac=jac, bounds=(lo, hi), method='trf', xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=max(iters, 50))
        q[:5] = sol.x; p, R = fk(sol.x)
        ang = 0.0
        if zt is not None: ang = math.degrees(math.acos(np.clip(R[:, 2] @ zt, -1, 1)))
        self.set(arm, q)
        return q, float(np.linalg.norm(W @ (p - tgt)) if soft_dir is not None else np.linalg.norm(p - tgt)), ang

    # ------------------------------------------------------------------ collisions and clearance
    def _held_pairs(self, arm):
        """geom pairs ignored for a held beaker: the beaker and this arm's gripper bodies"""
        return set()

    def contacts(self, arm, q, other=None, held=None, ignore_beakers=(), ignore_bodies=()):
        """penetrating contacts involving the moving arm or its held beaker; returns list of (a, b, depth_mm)"""
        self.set(arm, q, other, held); mujoco.mj_collision(self.m, self.d)
        hb = 'beaker_' + held[0] if held else None; out = []
        for i in range(self.d.ncon):
            c = self.d.contact[i]
            if c.dist >= 0: continue
            b1, b2 = self.body_of.get(c.geom1, ''), self.body_of.get(c.geom2, '')
            mine = lambda b: b.startswith(arm + '/') or (hb is not None and b == hb)
            if not (mine(b1) or mine(b2)): continue
            pair = {b1, b2}
            if hb in pair and any(b.startswith(arm + '/') for b in pair): continue
            if any(('beaker_' + k) in pair for k in ignore_beakers): continue
            if any(x in pair for x in ignore_bodies): continue
            out.append((b1, b2, float(-c.dist * 1000)))
        return out

    def clearance(self, arm, q, other=None, held=None, ignore_beakers=(), ignore_bodies=(), distmax=60.0, seat_mm=None):
        """minimum true distance (mm) from the arm (and held beaker) to everything else, and what it is"""
        d = self.set(arm, q, other, held)
        mine = list(self.geoms.get(arm, []))
        if held: mine += self.geoms['beaker:' + held[0]]
        skip_owner = {arm} | ({'beaker:' + held[0]} if held else set()) | {'beaker:' + k for k in ignore_beakers}
        others = [g for o, gs in self.geoms.items() if o not in skip_owner for g in gs if self.body_of[g] not in ignore_bodies]
        if not others or not mine: return float('inf'), ''
        A = np.array(mine); B = np.array(others)
        pa = d.geom_xpos[A]; pb = d.geom_xpos[B]; ra = self.m.geom_rbound[A]; rb = self.m.geom_rbound[B]
        D = np.linalg.norm(pa[:, None] - pb[None], axis=2) - ra[:, None] - rb[None]
        best = (distmax, ''); fromto = np.zeros(6)
        for i, j in zip(*np.nonzero(D < m(distmax))):
            g1, g2 = int(A[i]), int(B[j])
            b1 = self.body_of[g1]
            if held and b1 == 'beaker_' + held[0] and seat_mm is not None:
                pass
            dist = mujoco.mj_geomDistance(self.m, d, g1, g2, m(distmax), fromto) * 1000
            if dist < best[0]:
                best = (dist, '%s x %s' % (self._label(g1), self._label(g2)))
        return float(best[0]), best[1]

    def _label(self, g):
        n = self.m.geom(g).name; b = self.body_of[g]
        return '%s(%s)' % (b, n) if n else b
