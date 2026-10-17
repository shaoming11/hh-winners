"""STL reading and small procedural meshes (all in millimetres; the scene converts with benchsim.units)."""
import math
import struct

import numpy as np


def read_stl(path):
    """return (V, F): unique vertices (n, 3) float and faces (m, 3) int"""
    b = open(path, 'rb').read()
    if b[:5] == b'solid' and b'facet' in b[:4096] and b'vertex' in b[:4096]:
        v = [list(map(float, ln.split()[1:4])) for ln in b.decode(errors='ignore').splitlines() if ln.strip().startswith('vertex')]
        tri = np.array(v, float).reshape(-1, 3, 3)
    else:
        n = struct.unpack('<I', b[80:84])[0]
        a = np.frombuffer(b[84:84 + n * 50], dtype=np.dtype([('n', '<3f4'), ('v', '<9f4'), ('a', '<u2')]))
        tri = a['v'].reshape(-1, 3, 3).astype(float)
    flat = tri.reshape(-1, 3)
    key = np.round(flat, 4)
    V, inv = np.unique(key, axis=0, return_inverse=True)
    F = inv.reshape(-1, 3)
    keep = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    return V, F[keep]


def flip(F):
    return F[:, ::-1].copy()


def frustum(r0, r1, h, n=48, z0=0.0, closed=True):
    """solid frustum (convex), axis +Z, bottom radius r0 at z0, top radius r1 at z0 + h"""
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    bot = np.c_[r0 * np.cos(th), r0 * np.sin(th), np.full(n, z0)]
    top = np.c_[r1 * np.cos(th), r1 * np.sin(th), np.full(n, z0 + h)]
    V = np.vstack([bot, top, [[0, 0, z0], [0, 0, z0 + h]]])
    F = []
    for i in range(n):
        j = (i + 1) % n
        F += [[i, j, n + j], [i, n + j, n + i]]
        if closed: F += [[2 * n, j, i], [2 * n + 1, n + i, n + j]]
    return V, np.array(F)


def tube(r_in, r_out, h, n=48, z0=0.0):
    """open-ended thick tube (visual only)"""
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    rings = [np.c_[r * np.cos(th), r * np.sin(th), np.full(n, z)] for r, z in ((r_out, z0), (r_out, z0 + h), (r_in, z0 + h), (r_in, z0))]
    V = np.vstack(rings); F = []
    for k in range(4):
        a, b = k * n, ((k + 1) % 4) * n
        for i in range(n):
            j = (i + 1) % n
            F += [[a + i, a + j, b + j], [a + i, b + j, b + i]]
    return V, np.array(F)
