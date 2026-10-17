"""Top-down grasp model for the fin-ray gripper (hand pointing down along the beaker axis) + feasibility map.
Beaker axis = finger direction e1 (pointing down), passing through the side-grasp centre line of the D56 grasp;
rim at the palm (e1 = clear_palm 47 mm from the jaw hinge), so the 74 mm beaker spans e1 = 47..121 and the 65 mm
fingers wrap its upper part.  Pours reuse layout_lib.pour_manifolds with this held-beaker frame."""
import math, json, os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'fusion_bridge'))
import layout_lib as L
import planner as P

H, D = 74.0, 56
GD = json.load(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'gripper_design.json')))
PALM = GD['grip']['56']['clear_palm']           # 47 mm

def td_rel(t):
    """beaker frame in the rest-world frame of link 5 for the top-down grasp: z_b = -e1, origin = beaker bottom"""
    A = L.ARM[t]; G = P.GRASP[t]; c0 = A.c0[56]
    u0 = (c0 - G.gp) @ G.e1                       # e1 coordinate of the side-grasp centre (~71)
    bottom = c0 + (PALM + H - u0) * G.e1
    zb = -G.e1; x = G.g - zb * (G.g @ zb); x /= np.linalg.norm(x); y = np.cross(zb, x)
    M = np.eye(4); M[:3, 0] = x; M[:3, 1] = y; M[:3, 2] = zb; M[:3, 3] = bottom
    return M

def td_grasps(t, off, bottoms, nseed=48, rng=None):
    """IK for beaker bottom at each target with the beaker axis vertical (hand pointing down). returns per target list
    of (q, margins) sorted by min margin"""
    rng = rng or np.random.default_rng(5)
    A = L.ARM[t]; Mrel = td_rel(t)
    T = np.atleast_2d(np.asarray(bottoms, float)) - np.asarray(off, float); K = len(T); TG = np.repeat(T, nseed, 0)
    def resid(Q):
        R, tt = A.fk(Q); pb = R @ Mrel[:3, 3] + tt; zb = (R @ Mrel[:3, :3])[:, :, 2]
        return np.c_[pb - TG, 60 * zb[:, :2]]
    Q, r = L._lm(resid, L.rand_q(t, K * nseed, rng), 150)
    R, _ = A.fk(Q); zb = (R @ Mrel[:3, :3])[:, :, 2]
    ok = (np.linalg.norm(r[:, :3], axis=1) < 0.5) & (zb[:, 2] > 0.999)
    out = []
    for k in range(K):
        sols = []
        for i in range(k * nseed, (k + 1) * nseed):
            if not ok[i]: continue
            qw, m = L.wrap_best(Q[i], t)
            if any(np.max(np.abs(qw - s[0])) < 0.02 for s in sols): continue
            sols.append((qw, m))
        sols.sort(key=lambda s: -s[1].min()); out.append(sols)
    return out

if __name__ == '__main__':
    t = 'B'; pan = L.ARM[t].pan
    rs = list(range(100, 381, 20))
    print('TOP-DOWN GRASP: best min joint margin (deg) vs radius from the base axis (target straight ahead / 45 deg)')
    for zb, name in ((61.7, 'carousel bottom z61.7'), (63.7, 'scale bottom z63.7'), (26.2, 'rack bottom z26.2'), (90.0, 'z90')):
        for b in (0, 45):
            T = [(pan[0] + r * math.sin(math.radians(b)), pan[1] - r * math.cos(math.radians(b)), zb) for r in rs]
            res = td_grasps(t, (0, 0, 0), T)
            print('%-22s b%-3d' % (name, b), ' '.join('%5.1f' % s[0][1].min() if s else '    .' for s in res), flush=True)
    print('r:', rs)
    print('\nPITCH POUR (top-down grasp, lip pinned, drift free <=25): best min margin over theta 40..105')
    Mrel = td_rel(t)
    for rim, hs, name in ((137.7, (25.0, 35.0), 'scale rim 137.7'), (233.0, (50.0, 70.0), 'funnel rim 233')):
        row = []
        for r in range(140, 381, 40):
            best = None
            for h in hs:
                lip = np.r_[pan[0], pan[1] - r, rim + h]
                pairs = [(lip, p) for p in np.radians(np.arange(-180, 180, 10))]
                res = L.pour_manifolds(t, (0, 0, 0), D, 0.0, 1, None, None, d_weight=0.0, pairs=pairs, mrel=Mrel,
                                       seed_fn=lambda bots: td_grasps(t, (0, 0, 0), bots, nseed=24))
                res = [x for x in res if x['drift'] <= 25]
                if res and (best is None or res[0]['minmargin'] > best[0]):
                    x = res[0]; best = (round(x['minmargin'], 1), ['pan', 'sh', 'el', 'fl', 'ro'][int(np.argmin(x['per']))], round(math.degrees(x['psi'])), round(x['drift'], 1), h)
            row.append((r, best)); print(name, r, best, flush=True)

def td_pour(t, off, lip, psi, q_up, dmax_allowed=25.0, th_hi=105.0, pinned=True):
    """continuation from the upright top-down grasp (lip at `lip`) to theta 105; lip height + lateral pinned, lip free
    along d (drift). returns dict(qs 40..105, margin, binding, maxstep, drift) or None"""
    A = L.ARM[t]; Mrel = td_rel(t); off = np.asarray(off, float)
    d = np.array([math.cos(psi), math.sin(psi), 0]); av = np.array([-math.sin(psi), math.cos(psi), 0]); lp = np.asarray(lip, float) - off
    q = np.array([q_up]); qs = []; maxstep = 0.0; drift = 0.0
    for th in list(np.arange(2.0, 40.0, 2.0)) + list(np.arange(40.0, th_hi + 0.01, 1.0)):
        ax = math.cos(math.radians(th)) * np.array([0, 0, 1.0]) + math.sin(math.radians(th)) * d
        def resid(Q):
            R, tt = A.fk(Q); Rb = R @ Mrel[:3, :3]; pb = R @ Mrel[:3, 3] + tt; zz = Rb[:, :, 2]
            e = pb + H * zz + 28 * np.cross(av, zz) - lp; ed = np.einsum('ni,i->n', e, d)
            return np.c_[e, 60 * (zz - ax)] if pinned else np.c_[e - ed[:, None] * d, 60 * (zz - ax)]
        qn, r = L._lm(resid, q, 40, step=0.15, lam=1e-4)
        if np.abs(r).max() > 0.5: return None
        R, tt = A.fk(qn); Rb = R @ Mrel[:3, :3]; pb = R @ Mrel[:3, 3] + tt; zz = Rb[:, :, 2]
        e = (pb + H * zz + 28 * np.cross(av, zz) - lp)[0] @ d
        if th >= 40:
            if qs: maxstep = max(maxstep, np.degrees(np.abs(qn[0] - qs[-1]).max()))
            qs.append(qn[0].copy()); drift = max(drift, abs(e))
        q = qn
    M = np.array([L.margins(x, t) for x in qs])
    return dict(qs=qs, margin=float(M.min()), binding=['pan', 'shoulder', 'elbow', 'wr_flex', 'wr_roll'][int(np.argmin(M.min(0)))],
                maxstep=maxstep, drift=drift)

def best_td_pour(t, off, rim_xy, rim_z, hs, psis_rel=(0, -10, 10, 180), inward=True):
    pan = L.ARM[t].pan[:2] + np.asarray(off, float)[:2]
    u = np.asarray(rim_xy) - pan; base = math.atan2(-u[1], -u[0]) if inward else math.atan2(u[1], u[0])
    best = None
    for h in hs:
        for dp in psis_rel:
            psi = base + math.radians(dp); d = np.array([math.cos(psi), math.sin(psi), 0])
            lip = np.r_[rim_xy, rim_z + h]; bot = lip - [0, 0, H] - 28 * d
            for q, m in td_grasps(t, off, [bot])[0][:4]:
                r = td_pour(t, off, lip, psi, q)
                if r is None or r['maxstep'] > 2.0 or r['drift'] > 25: continue
                r.update(h=h, psi=math.degrees(psi), q_up=q, up_margin=float(m.min()))
                if best is None or r['margin'] > best['margin']: best = r
    return best
