"""Place part-local CAD STLs (exports/prints_v2) by fitting their features to update13_final.

A mesh is only used as an imported visual if its features land on the layout: cup / pocket / ring circles are
found in the STL (Hough vote on wall vertices, then a least-squares circle refit), matched to the station
centres with a 2-D rigid fit, and the residual is reported. Floors are found as the highest horizontal
faces inside each circle and matched to the recorded beaker-bottom Z.
"""
import math

import numpy as np
from scipy.optimize import least_squares

from . import meshes, paths


def _faces(V, F):
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    n = np.cross(b - a, c - a); area = np.linalg.norm(n, axis=1) / 2
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return (a + b + c) / 3, n, area


def find_circles(V, F, r_lo, r_hi, k, z_band=None, grid=1.0, min_sep=40.0):
    """k circle centres (2-D) of vertical cylindrical walls with radius in [r_lo, r_hi]"""
    cen, n, area = _faces(V, F)
    wall = np.abs(n[:, 2]) < 0.2
    if z_band is not None: wall &= (cen[:, 2] > z_band[0]) & (cen[:, 2] < z_band[1])
    P = cen[wall][:, :2]
    if len(P) > 6000: P = P[np.random.default_rng(0).choice(len(P), 6000, replace=False)]
    lo, hi = P.min(0) - r_hi, P.max(0) + r_hi
    xs = np.arange(lo[0], hi[0], grid); ys = np.arange(lo[1], hi[1], grid)
    G = np.stack(np.meshgrid(xs, ys), -1).reshape(-1, 2)
    votes = np.zeros(len(G))
    for i in range(0, len(G), 4000):
        D = np.linalg.norm(G[i:i + 4000, None, :] - P[None], axis=2)
        votes[i:i + 4000] = ((D > r_lo) & (D < r_hi)).sum(1)
    out = []
    for idx in np.argsort(-votes):
        c = G[idx]
        if all(np.linalg.norm(c - o[0]) > min_sep for o in out):
            d = np.linalg.norm(P - c, axis=1); sel = P[(d > r_lo - 1) & (d < r_hi + 1)]
            fit = least_squares(lambda x: np.linalg.norm(sel - x[:2], axis=1) - x[2], np.r_[c, (r_lo + r_hi) / 2])
            out.append((fit.x[:2], float(fit.x[2]), int(votes[idx])))
        if len(out) == k: break
    return out


def floor_discs(V, F, k, r_lo, r_hi, sep=30.0):
    """find k circular upward-facing floor discs at one height (cup / pocket / pan floors).
    Returns (z_local, [(centre2d, equivalent radius)]) for the best level, or None"""
    cen, n, area = _faces(V, F); up = n[:, 2] > 0.95
    best = None
    for z in np.unique(np.round(cen[up, 2], 1)):
        sel = up & (np.abs(cen[:, 2] - z) < 0.15)
        P, A = cen[sel, :2], area[sel]
        clusters = []
        for i in np.argsort(-A):
            for c in clusters:
                if np.linalg.norm(P[i] - c['seed']) < sep: c['idx'].append(i); break
            else: clusters.append(dict(seed=P[i], idx=[i]))
        out = []
        for c in clusters:
            a = A[c['idx']]; tot = a.sum()
            r_eq = math.sqrt(tot / math.pi)
            if r_lo <= r_eq <= r_hi: out.append(((P[c['idx']] * a[:, None]).sum(0) / tot, r_eq))
        if len(out) == k:
            score = sum(abs(r - (r_lo + r_hi) / 2) for _, r in out)
            if best is None or score < best[2]: best = (float(z), out, score)
    return None if best is None else best[:2]


def floor_z(V, F, c, r):
    """height of the highest upward-facing horizontal face inside the circle (the floor the beaker stands on)"""
    cen, n, area = _faces(V, F)
    sel = (n[:, 2] > 0.95) & (np.linalg.norm(cen[:, :2] - c, axis=1) < r * 0.8)
    return float(np.max(cen[sel, 2])) if sel.any() else None


def rigid2d(A, B):
    """R, t minimising |R A + t - B| (2-D Kabsch); returns R, t, residuals"""
    A = np.asarray(A, float); B = np.asarray(B, float)
    ca, cb = A.mean(0), B.mean(0); H = (A - ca).T @ (B - cb)
    U, S, Vt = np.linalg.svd(H); d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1, d]) @ U.T; t = cb - R @ ca
    return R, t, np.linalg.norm((A @ R.T + t) - B, axis=1)


def fit_part(fname, targets_xy, target_floor_z, r_lo, r_hi, z_band=None, min_sep=40.0, order_free=True, method='floor'):
    """fit a part with len(targets_xy) circular features. Returns dict(pose, residuals) or None"""
    V, F = meshes.read_stl(paths.PRINTS_V2 / fname)
    k = len(targets_xy)
    if method == 'floor':
        fd = floor_discs(V, F, k, r_lo, r_hi, sep=min_sep)
        if fd is None: return None
        zl, circ = fd[0], [(c, r, 0) for c, r in fd[1]]
    else:
        circ = find_circles(V, F, r_lo, r_hi, k, z_band, min_sep=min_sep)
        if len(circ) < k: return None
        zl = float(np.median([floor_z(V, F, c, r) for c, r, _ in circ]))
    C = np.array([c[0] for c in circ]); T = np.asarray(targets_xy, float)
    best = None
    import itertools
    perms = itertools.permutations(range(k)) if order_free else [tuple(range(k))]
    for p in perms:
        R, t, res = rigid2d(C[list(p)], T)
        if best is None or res.max() < best[2].max(): best = (R, t, res, p)
    R, t, res, p = best
    fz = [zl] * k
    dz = target_floor_z - zl
    yaw = math.degrees(math.atan2(R[1, 0], R[0, 0]))
    return dict(file=fname, yaw_deg=yaw, t_xy=t.tolist(), dz=float(dz), floor_disc_r=[circ[i][1] for i in p],
                residual_xy_mm=res.tolist(), floor_z_local=fz, V=V, F=F)


def transform(fit):
    """apply a fit to its mesh vertices -> world mm"""
    c, s = math.cos(math.radians(fit['yaw_deg'])), math.sin(math.radians(fit['yaw_deg']))
    R = np.array([[c, -s], [s, c]]); V = fit['V'].copy()
    V[:, :2] = V[:, :2] @ R.T + fit['t_xy']; V[:, 2] += fit['dz']
    return V


FITS_JSON = paths.CONFIG / 'mesh_fits.json'


def fit_all():
    """placement of every imported part-local STL, with how it was verified. Poses are world mm:
    yaw about +Z, then translation (x, y, z) applied to the STL's own coordinates."""
    from .layout import load_bench
    b = load_bench(); st = b['stations']; P = b['params']; out = []

    def rec(part, fname, body, yaw, t, verified, residual, note=''):
        out.append(dict(part=part, file=fname, body=body, yaw_deg=float(yaw), t=[float(v) for v in t], verified=verified,
                        residual_mm=None if residual is None else float(residual), note=note))
    f = fit_part('RK-03_reagent_rack.stl', [st['rack_%d' % i]['xy'] for i in (1, 2, 3)], st['rack_1']['z'], 20, 31.5)
    rec('RK-03 reagent rack', f['file'], 'world', f['yaw_deg'], f['t_xy'] + [f['dz']], 'fit: 3 cup floors to update13_final rack_stands + floor Z',
        max(f['residual_xy_mm']), 'cup floor r %.2f at local Z %.1f' % (f['floor_disc_r'][0], f['floor_z_local'][0]))
    c = st['carousel_centre']['xy']
    pk = [(c[0] + P['carousel']['pitch_r'] * math.cos(math.radians(a)), c[1] + P['carousel']['pitch_r'] * math.sin(math.radians(a)))
          for a in P['carousel']['pocket_ids_deg']]
    f = fit_part('TT-04_beaker-ring-v4-4x100mL_qty1.stl', pk, st['carousel_pick']['z'], 27.5, 31.5, min_sep=60, method='walls')
    rec('TT-04 v4 beaker ring', f['file'], 'carousel', f['yaw_deg'], [f['t_xy'][0] - c[0], f['t_xy'][1] - c[1], f['dz']],
        'fit: 4 pocket bores to the r84 pockets + floor Z', max(f['residual_xy_mm']),
        'body frame = carousel deck at angle 0; bore r %.2f, locating ribs r 28.25' % np.mean(f['floor_disc_r']))
    rec('TT-02 carousel deck', 'TT-02_carousel-deck_qty1.stl', 'carousel', 0.0, [0, 0, P['carousel']['deck_z'][0]],
        'concentric with the carousel axis (symmetric part); Z = ring base - 7', None)
    f = fit_part('WS-02_scale-pan-v3-100mL_qty1.stl', [st['scale_pan']['xy']], st['scale_pan']['z'], 20, 31.5, method='walls')
    rec('WS-02 v3 scale pan', f['file'], 'scale_pan', 0.0, [f['t_xy'][0] - st['scale_pan']['xy'][0], 0.0, f['dz']],
        'ring centre and floor Z: floor lands on the update13_final beaker bottom Z 63.7', 0.0,
        'locating ring r %.2f; one feature, so yaw is free (part is symmetric)' % f['floor_disc_r'][0])
    fun = st['funnel']['xy']
    V, F = meshes.read_stl(paths.PRINTS_V2 / 'ST-11_stage-sled_qty1_SUPPORTS.stl')
    ring = find_circles(V, F, 64.0, 70.0, 1, z_band=(9, 14))[0]
    rec('ST-11 stage sled', 'ST-11_stage-sled_qty1_SUPPORTS.stl', 'sled', 0.0, [0, 0, 0],
        'part frame = tools/cad/stage_b.py origin (450, 282, 0); catch-well ring centre found at local (%.2f, %.2f)' % tuple(ring[0]),
        float(np.linalg.norm(ring[0])), 'sled body origin is the funnel axis at WORK')
    for part, fname, body, t in (('ST-12 servo bridge', 'ST-12_servo-bridge_qty1.stl', 'world', [450, 65, 20]),
                                 ('ST-13 crank', 'ST-13_crank_qty1.stl', 'crank', [0, 0, 0]),
                                 ('ST-14 connecting rod', 'ST-14_connecting-rod_qty1.stl', 'rod', [0, 0, 0])):
        rec(part, fname, body, 0.0, t, 'part frame = tools/cad/stage_b.py Part origin (explicit world coordinates)', None)
    sz = P['stage']['sled_plate_z'][1]
    rec('ST-07 catch well', 'ST-07_catch-well_qty1.stl', 'sled', 0.0, [0, 0, sz], 'concentric in the ST-11 locating ring (symmetric part); Z = sled plate top', None)
    rec('ST-05 flask collar', 'ST-05_flask-collar_qty1.stl', 'sled', 0.0, [0, 0, sz + 2], 'concentric, on the catch-well floor (assumed 2 mm)', None)
    rec('TT-01 v2 turntable base', 'TT-01_turntable-base-v2_qty1.stl', 'world', b['carousel_rotation_deg'], [c[0], c[1], 0],
        'assumed: local origin on the carousel axis, rotated with the unit by update13_final carousel.rotation_deg', None,
        'orientation not independently verified')
    return out


if __name__ == '__main__':
    import json
    rows = fit_all()
    FITS_JSON.write_text(json.dumps(rows, indent=1) + '\n')
    for r in rows:
        print('%-26s body %-10s yaw %8.2f t %-28s residual %s  %s' % (r['part'], r['body'], r['yaw_deg'], np.round(r['t'], 2).tolist(),
              'n/a' if r['residual_mm'] is None else '%.3f mm' % r['residual_mm'], r['verified']))
