"""Grasp geometry for the stock SO-101 jaw, from the real meshes (rest pose of arm A/B)."""
import json, os, math, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'fusion_bridge'))
from kin_model import Arm, T

MESH = None
def meshes():
    global MESH
    if MESH is None: MESH = json.load(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'meshes.json')))
    return MESH

def sample_tris(tris, step=1.0):
    t = np.array(tris, float)
    if len(t) == 0: return np.zeros((0, 3))
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    n = np.maximum(1, (area / (step * step)).astype(int))
    reps = np.repeat(np.arange(len(t)), n)
    r1 = np.random.default_rng(0).random(len(reps)); r2 = np.random.default_rng(1).random(len(reps))
    s = np.sqrt(r1)
    P = (1 - s)[:, None] * a[reps] + (s * (1 - r2))[:, None] * b[reps] + (s * r2)[:, None] * c[reps]
    return np.vstack([P, a, b, c])

class Grasp:
    def __init__(self, tag):
        self.arm = Arm(tag)
        m = meshes()
        self.fj = sample_tris(m['fixed_jaw'][tag], 0.8)
        self.mj = sample_tris(m['moving_jaw'][tag], 0.8)
        gp, gd = self.arm.axes[5]
        self.gp = np.array(gp); self.g = np.array(gd) / np.linalg.norm(gd)
        # in-plane basis: e1 = finger direction (projected), e2 = g x e1
        e1 = self.arm.finger - self.g * (self.arm.finger @ self.g); self.e1 = e1 / np.linalg.norm(e1)
        self.e2 = np.cross(self.g, self.e1)
        # contact band along g: where both jaws exist, beyond 25 mm from the hinge
        def gcoord(P): return (P - self.gp) @ self.g
        def rad(P):
            v = P - self.gp; return np.hypot(v @ self.e1, v @ self.e2)
        f_far = self.fj[rad(self.fj) > 25]; m_far = self.mj[rad(self.mj) > 25]
        lo = max(gcoord(f_far).min(), gcoord(m_far).min()); hi = min(gcoord(f_far).max(), gcoord(m_far).max())
        self.band = (lo, hi)

    def moving(self, q6):
        M = T(self.gp, self.g, q6); return (np.c_[self.mj, np.ones(len(self.mj))] @ M.T)[:, :3]

    def fit(self, D, q6):
        """largest opposed-contact circle near diameter D between the jaws at q6 (2D, in the jaw plane, within the band).
        returns (D_max_feasible_center, centre3d) for a circle of diameter D, or None"""
        lo, hi = self.band
        def plane(P):
            gc = (P - self.gp) @ self.g; P = P[(gc > lo) & (gc < hi)]
            return np.c_[(P - self.gp) @ self.e1, (P - self.gp) @ self.e2]
        F2 = plane(self.fj); M2 = plane(self.moving(q6))
        if len(F2) == 0 or len(M2) == 0: return None
        xs = np.arange(10, 95, 1.0); ys = np.arange(-60, 60, 1.0)
        G = np.stack(np.meshgrid(xs, ys), -1).reshape(-1, 2)
        from scipy.spatial import cKDTree
        def near(Q):
            dmin, idx = cKDTree(Q).query(G); return dmin, Q[idx]
        d1, c1 = near(F2); d2, c2 = near(M2)
        v1 = (c1 - G) / np.maximum(d1, 1e-9)[:, None]; v2 = (c2 - G) / np.maximum(d2, 1e-9)[:, None]
        ok = ((v1 * v2).sum(1) < -0.9) & (np.abs(d1 - D / 2) < 0.8) & (np.abs(d2 - D / 2) < 0.8)
        if not ok.any(): return None
        cand = G[ok]; k = np.argmin(cand[:, 0])        # deepest grip (closest to the hinge)
        c = cand[k]; mid = (lo + hi) / 2
        return self.gp + c[0] * self.e1 + c[1] * self.e2 + mid * self.g

    def solve(self, D):
        if meshes().get('finray'):
            dz = json.load(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'gripper_design.json')))
            gd = dz['grip'][str(int(D))]; mid = (dz['Z'][0] + dz['Z'][1]) / 2; c2 = gd['centre2d']
            c = self.gp + c2[0] * self.e1 + c2[1] * self.e2 + mid * self.g
            return {'close': (gd['q_contact'], c), 'open': (gd['q_open'], c)}
        return self.solve_stock(D)
    def solve_stock(self, D):
        """closing angle and grasp centre (rest frame) for a cylinder of diameter D; open angle for D + 14 mm"""
        res = {}
        for name, d in (('close', D), ('open', D + 14)):
            best = None
            for deg in np.arange(-90, 30, 1.0):
                c = self.fit(d, math.radians(deg))
                if c is not None: best = (deg, c); break       # first (most closed) angle at which d fits
            res[name] = best
        return res

if __name__ == '__main__':
    for tag in 'AB':
        G = Grasp(tag)
        print(tag, 'contact band along hinge: %.1f .. %.1f mm (width %.1f)' % (G.band[0], G.band[1], G.band[1] - G.band[0]))
        for D in (43.0, 56.0):
            r = G.solve(D)
            print('  D=%.0f close %s open %s' % (D, None if r['close'] is None else (r['close'][0], np.round(r['close'][1], 1)), None if r['open'] is None else r['open'][0]))
