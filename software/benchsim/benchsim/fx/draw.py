"""Drawing into a rendered scene copy (mjvScene), in mm. Geoms added here exist only in this frame's scene: they have
no mass, no collision and no effect on the model or the data. ``hide`` blanks the scene copy of a model geom (the
model's own rgba is untouched), so a look can replace it.
"""
import math

import mujoco
import numpy as np

I3 = np.eye(3).reshape(9)
G = mujoco.mjtGeom


def hash01(*k):
    """deterministic pseudo-random number in [0, 1) from integers: stable jitter, so nothing flickers between frames"""
    h = 2166136261
    for v in k:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
        h ^= h >> 13; h = (h * 0x5BD1E995) & 0xFFFFFFFF; h ^= h >> 15
    return h / 4294967296.0


def hash01v(*k):
    """hash01 over integer arrays (broadcast), same values as hash01 element by element"""
    h = np.full(np.broadcast(*[np.asarray(v) for v in k]).shape, 2166136261, np.uint64); M = np.uint64(0xFFFFFFFF)
    for v in k:
        v = np.asarray(v).astype(np.int64).astype(np.uint64) & M
        h = ((h ^ v) * np.uint64(16777619)) & M
        h ^= h >> np.uint64(13); h = (h * np.uint64(0x5BD1E995)) & M; h ^= h >> np.uint64(15)
    return h / 4294967296.0


def rot_z_to(v):
    """3x3 rotation taking +Z to the unit vector v"""
    v = np.asarray(v, float); v = v / (np.linalg.norm(v) or 1.0); z = np.array([0, 0, 1.0])
    c = float(z @ v)
    if c > 1 - 1e-9: return np.eye(3)
    if c < -1 + 1e-9: return np.diag([1.0, -1.0, -1.0])
    a = np.cross(z, v); s = np.linalg.norm(a); a /= s; K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + s * K + (1 - c) * K @ K


class Canvas:
    def __init__(self, scn):
        self.scn = scn; self.full = False

    def _next(self):
        s = self.scn
        if s.ngeom >= s.maxgeom: self.full = True; return None
        return s.geoms[s.ngeom]

    def geom(self, kind, size_mm, pos_mm, rgba, R=None, emission=0.0, specular=0.5, shininess=0.5, reflectance=0.0, matid=-1, model=None):
        g = self._next()
        if g is None: return None
        size = np.zeros(3); s = np.asarray(size_mm, float) / 1000.0; size[:len(s)] = s
        mat = I3 if R is None else np.asarray(R, float).reshape(9)
        mujoco.mjv_initGeom(g, int(kind), size, np.asarray(pos_mm, float) / 1000.0, mat, np.asarray(rgba, np.float32))
        g.emission = emission; g.specular = specular; g.shininess = shininess; g.reflectance = reflectance
        if matid >= 0 and model is not None: self.material(g, model, matid)
        self.scn.ngeom += 1
        return g

    @staticmethod
    def material(g, model, matid):
        g.matid = matid
        tex = int(model.mat_texid[matid, int(mujoco.mjtTextureRole.mjTEXROLE_RGB)])
        g.texid = tex; g.texrepeat[:] = model.mat_texrepeat[matid]; g.texuniform = int(model.mat_texuniform[matid])

    def sphere(self, p, r, rgba, **kw): return self.geom(G.mjGEOM_SPHERE, [r], p, rgba, **kw)

    def spheres(self, P, r, rgba, emission=0.0, specular=0.5, shininess=0.5):
        """many spheres at once: P (n, 3) mm, r (n,) mm, rgba (n, 4) or (4,)"""
        P = np.asarray(P, float) / 1000.0; n = len(P)
        if n == 0: return
        size = np.zeros((n, 3)); size[:, 0] = np.broadcast_to(np.asarray(r, float) / 1000.0, (n,))
        rgba = np.broadcast_to(np.asarray(rgba, np.float32), (n, 4)); s = self.scn; init = mujoco.mjv_initGeom; k = int(G.mjGEOM_SPHERE)
        for i in range(n):
            if s.ngeom >= s.maxgeom: self.full = True; return
            g = s.geoms[s.ngeom]; init(g, k, size[i], P[i], I3, rgba[i])
            g.emission = emission; g.specular = specular; g.shininess = shininess; s.ngeom += 1

    def ellipsoid(self, p, radii, rgba, R=None, **kw): return self.geom(G.mjGEOM_ELLIPSOID, radii, p, rgba, R=R, **kw)

    def box(self, p, half, rgba, R=None, **kw): return self.geom(G.mjGEOM_BOX, half, p, rgba, R=R, **kw)

    def cylinder(self, p, r, half_h, rgba, R=None, **kw): return self.geom(G.mjGEOM_CYLINDER, [r, half_h], p, rgba, R=R, **kw)

    def capsule(self, a, b, r, rgba, **kw):
        """capsule from point a to point b (mm)"""
        a = np.asarray(a, float); b = np.asarray(b, float); d = b - a; L = float(np.linalg.norm(d))
        if L < 1e-6: return self.sphere(a, r, rgba, **kw)
        return self.geom(G.mjGEOM_CAPSULE, [r, L / 2], (a + b) / 2, rgba, R=rot_z_to(d), **kw)

    def tube(self, pts, radii, rgba, **kw):
        """capsule chain through pts with a radius per point (the segment takes the mean of its ends)"""
        for i in range(len(pts) - 1): self.capsule(pts[i], pts[i + 1], 0.5 * (radii[i] + radii[i + 1]), rgba, **kw)

    # ---------------------------------------------------------------- model geoms in the scene copy
    def find(self, gid):
        s = self.scn; ot = int(mujoco.mjtObj.mjOBJ_GEOM)
        return [s.geoms[i] for i in range(s.ngeom) if s.geoms[i].objtype == ot and s.geoms[i].objid == gid]

    def hide(self, gid):
        for g in self.find(gid): g.rgba[3] = 0.0; g.size[:] = 0.0


def lerp(a, b, t): return np.asarray(a, float) + (np.asarray(b, float) - np.asarray(a, float)) * float(t)


def smooth(x):
    x = min(max(x, 0.0), 1.0); return x * x * (3 - 2 * x)


def ring(n, phase=0.0):
    """n unit vectors around +Z"""
    a = phase + 2 * math.pi * np.arange(n) / n; return np.c_[np.cos(a), np.sin(a), np.zeros(n)]
