"""Collision-aware grasp & motion planning for the two SO-101s (numpy + scipy)."""
import json, os, math, sys
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'fusion_bridge'))
from kin_model import Arm, T, rot
from grasp_model import Grasp, sample_tris, meshes

VOX = 2.5
LO = np.array([-10.0, 40.0, -20.0]); HI = np.array([920.0, 760.0, 360.0])
SHAPE = np.ceil((HI - LO) / VOX).astype(int)
def to_idx(P):
    return np.floor((P - LO) / VOX).astype(int)
def make_grid(points, dilate=1):
    g = np.zeros(SHAPE, bool)
    ij = to_idx(points); ok = np.all((ij >= 0) & (ij < SHAPE), axis=1); ij = ij[ok]
    g[ij[:, 0], ij[:, 1], ij[:, 2]] = True
    if dilate: g = ndimage.binary_dilation(g, iterations=dilate)
    return g
def hits(grid, P):
    ij = to_idx(P); ok = np.all((ij >= 0) & (ij < SHAPE), axis=1)
    ij = ij[ok]; return int(grid[ij[:, 0], ij[:, 1], ij[:, 2]].sum())

M = meshes()
# ---- static scene (beakers handled analytically) ----
SKIP = ('EISCO 100 mL PP beaker', 'REF-BEAKER', 'EISCO 50 mL beaker on scale', 'SHCS ISO 4762 M4x20', 'CSK ISO 10642 M4x20', 'T-nut 2020 drop-in M4')
NO_AUGER = os.environ.get('NO_AUGER') == '1'
def _keep(o):
    if o['name'].startswith(SKIP): return False
    if NO_AUGER and o['name'] in ('DH-01 yeast auger head', 'DH-02 auger screw', 'N20 6V 60rpm gearmotor'): return False
    if NO_AUGER and o['name'] == 'SHCS ISO 4762 M3x12' and min(p[2] for t in o['tris'] for p in t) > 120: return False
    return True
def _pts(o):
    P = sample_tris(o['tris'], 1.5)
    if NO_AUGER and o['name'].startswith('WS-01'): P = P[P[:, 2] < 46]
    return P
scene_pts = np.vstack([_pts(o) for o in M['scene'] if _keep(o)] +
                      [sample_tris(o['tris'], 1.5) for o in M['carousel'] if o['name'] != 'REF-BEAKER'])
SCENE = make_grid(scene_pts, 1)
SCENE_RAW = make_grid(scene_pts, 0)
# carousel beaker centres (after the 22.5 deg index)
CAR = []
for o in M['carousel']:
    if o['name'] == 'REF-BEAKER':
        P = np.array(o['tris']).reshape(-1, 3); CAR.append(((P[:, 0].max() + P[:, 0].min()) / 2, (P[:, 1].max() + P[:, 1].min()) / 2))
# ---- arm link point clouds (rest pose) ----
ARMP = {}
for tag in 'AB':
    ARMP[tag] = {lk: sample_tris(tr, 3.0) for lk, tr in M['arms'][tag].items()}
GRASP = {t: Grasp(t) for t in 'AB'}
GSOL = {t: {D: GRASP[t].solve(D) for D in (43.0, 56.0)} for t in 'AB'}

class Beaker:
    def __init__(self, name, D, H, pos):
        self.name, self.D, self.H = name, D, H; self.M = np.eye(4); self.M[:3, 3] = pos
        z = np.linspace(0, H, int(H / 3) + 1); th = np.linspace(0, 2 * math.pi, 28, endpoint=False)
        Z, TH = np.meshgrid(z, th); r = D / 2
        self.local = np.c_[(r * np.cos(TH)).ravel(), (r * np.sin(TH)).ravel(), Z.ravel()]
    def axis_pt(self, h):
        return (self.M @ np.array([0, 0, h, 1]))[:3]
    def world(self):
        return (np.c_[self.local, np.ones(len(self.local))] @ self.M.T)[:, :3]
    def contains(self, P, margin=1.5):
        Mi = np.linalg.inv(self.M); L = (np.c_[P, np.ones(len(P))] @ Mi.T)[:, :3]
        return int(((np.hypot(L[:, 0], L[:, 1]) < self.D / 2 + margin) & (L[:, 2] > -margin) & (L[:, 2] < self.H + margin)).sum())

class World:
    def __init__(self):
        self.q = {'A': np.zeros(6), 'B': np.zeros(6)}
        self.beakers = {}
        self.held = {'A': None, 'B': None}     # (beaker, M_rel to L5 frame)
    def link_points(self, tag, q, links=('L1', 'L2', 'L3', 'L4', 'L5', 'L6')):
        arm = GRASP[tag].arm; out = []
        for k, lk in enumerate(('L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6')):
            if lk not in links: continue
            n = min(k, 5) if lk != 'L6' else 5
            Mx = arm.chain(q, n)
            if lk == 'L6': Mx = Mx @ T(arm.axes[5][0], arm.axes[5][1], q[5])
            P = ARMP[tag][lk]; out.append((np.c_[P, np.ones(len(P))] @ Mx.T)[:, :3])
        return np.vstack(out)
    def collides(self, tag, q, other_grid, ignore=(), report=False):
        P = self.link_points(tag, q)
        n = hits(SCENE, P) + hits(other_grid, P)
        why = []
        if report and n: why.append('scene/arm %d' % n)
        for b in self.beakers.values():
            if b.name in ignore or (self.held[tag] and self.held[tag][0] is b): continue
            c = b.contains(P)
            if c: n += c; why.append('%s %d' % (b.name, c))
        h = self.held[tag]
        if h:
            b = h[0]; Bfull = b.world()
            Lz = (np.c_[Bfull, np.ones(len(Bfull))] @ np.linalg.inv(b.M).T)[:, 2]; Bp = Bfull[Lz > 18]   # seated part may touch its pocket (scene only)
            c = hits(SCENE_RAW, Bp) + hits(other_grid, Bfull); n += c
            if c: why.append('held-vs-scene %d' % c)
            for o in self.beakers.values():
                if o is b or o.name in ignore: continue
                cc = o.contains(Bp, 0.5); n += cc
                if cc: why.append('held-vs-%s %d' % (o.name, cc))
        return (n, why) if report else n
    def other_grid(self, tag):
        o = 'B' if tag == 'A' else 'A'
        return make_grid(self.link_points(o, self.q[o], ('L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6')), 1)

def ik_grasp(tag, target, hinge_sign, q0, D, extra_rot=None):
    """grasp-centre at target with the hinge vertical (beaker axis vertical)"""
    arm = GRASP[tag].arm; c0 = GSOL[tag][D]['close'][1]; g0 = GRASP[tag].g
    tgt = np.asarray(target, float)
    def resid(q):
        Mx = arm.chain(q, 5); c = (Mx @ np.append(c0, 1))[:3]; g = Mx[:3, :3] @ g0
        return np.r_[c - tgt, 40 * np.cross(g, [0, 0, hinge_sign])]
    q = np.array(q0, float)
    for _ in range(200):
        r = resid(q); J = np.zeros((6, 5))
        for k in range(5):
            dq = np.zeros(6); dq[k] = 1e-4; J[:, k] = (resid(q + dq) - r) / 1e-4
        q[:5] += np.clip(np.linalg.solve(J.T @ J + 1e-3 * np.eye(5), -J.T @ r), -0.25, 0.25)
        if np.linalg.norm(r) < 0.05: break
    r = resid(q); return q, float(np.linalg.norm(r[:3])), float(np.linalg.norm(r[3:]) / 40)

def finger_world(tag, q):
    arm = GRASP[tag].arm; return arm.chain(q, 5)[:3, :3] @ GRASP[tag].e1
