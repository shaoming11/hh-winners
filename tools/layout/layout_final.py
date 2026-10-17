"""Final layout re-solve (CDR-31 limits, all beakers EISCO 100 mL 56x74, GRIP_H 40, lip drift <= 25 mm).
Evaluates every step of the run for one layout: IK margins, upright Cartesian carries, pour manifolds, and voxel
collisions (scene, beakers, own base, other arm parked).  usage: python -W ignore layout_final.py [out.json]"""
import sys, os, math, json, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'fusion_bridge'))
import layout_lib as L
import layout_study as S
import planner as P

D, H, GH = 56, 74.0, 30.0
CAR_Z = 61.7; SCALE_Z = 63.7
S.CAR_R = 84.0
JN = ['pan', 'shoulder', 'elbow', 'wr_flex', 'wr_roll']
AUGER_RAISE = 25.0

# ---------------------------------------------------------------- layout (world mm, table top Z 0)
LAY = dict(
    d=74.0, a=67.4, b=34.8,                       # arms + X rails north 74; A base +50 X, B base +47 X
    car_c=43.7,                                   # carousel (and E5/auger stand) 43.7 south on Y-left
    car_R=84.0, pick_deg=220.6, auger_deg=40.6, pockets=(220.6, 310.6, 40.6, 130.6), car_centre=(807.9, 523.5),
    scale=(620.0, 407.0), e6_y=440.0,             # scale saddle on the OUTSIDE of Y-right (rotated 90), E6 stays the S1/S2 crossbar
    funnel=(450.0, 282.0), stage_rot=0.0,         # WORK stage as in CAD (unrotated, E6 crossbar)
    rack=None, rack_floor=60.2,                   # RK-03 pockets (beaker bottom Z)
)
def bpan(): return np.array([570.0 + LAY['b'], 525.7 + LAY['d']])
def apan(): return np.array([330.0 + LAY['a'], 525.7 + LAY['d']])
def arc(c, r, bears): return [(c[0] + r * math.sin(math.radians(b)), c[1] - r * math.cos(math.radians(b))) for b in bears]
LAY['rack'] = [(192.3, 394.6), (134.6, 477.1), (108.5, 574.4)]

class Lay(S.Layout):
    def __init__(self):
        super().__init__('final', scale_rot=0.0, d=LAY['d'], a=LAY['a'], b=LAY['b'], car_c=LAY['car_c'], car_phi=LAY['pick_deg'],
                         scale=LAY['scale'], rack=LAY['rack'], rack_z=LAY['rack_floor'], e6_y=LAY['e6_y'], gh43=GH, gh56=GH)
    @property
    def funnel(self): return np.array([LAY['funnel'][0], LAY['funnel'][1], 233.0])
    @property
    def cc(self): return np.array(LAY['car_centre'])
    def group_M(self):
        g = super().group_M()
        g['work'] = S.Mz(LAY['stage_rot'], S.FUN0, (LAY['funnel'][0] - S.FUN0[0], LAY['funnel'][1] - S.FUN0[1], 0))
        g['carousel'] = S.Mz(LAY['pick_deg'], (175.0, 370.0, 0), (LAY['car_centre'][0] - 175.0, LAY['car_centre'][1] - 370.0, 0))
        return g

AUGER_HEAD = ('DH-01', 'DH-02', 'N20')
class World(S.World):
    def __init__(self):
        super().__init__()
        objs = []
        for g, n, Pt in self.objs:
            if n.startswith(('REF-BIN', 'ST-01', 'TL-01')): continue           # removed (coordinator, CDR rev)
            c = Pt.mean(0)
            if n.startswith(('SHCS', 'T-nut')) and 660 < c[0] < 690 and 270 < c[1] < 310: continue      # ST-01 bolts (removed)
            if n.startswith(AUGER_HEAD) or (n.startswith('SHCS ISO 4762 M3x12') and c[0] < 100 and c[2] > 120):
                Pt = Pt + [0, 0, AUGER_RAISE]
            objs.append((g, n, Pt))
        objs = [o for o in objs if not o[1].startswith('TT-04')]
        # PS-01 slides +4 mm along E5 so the DH-01 outlet sits over the r84 auger pocket
        objs = [(g, n, Pt + [4.0, 0, 0]) if (n.startswith(('AG-01',) + AUGER_HEAD) or (n.startswith('SHCS ISO 4762 M3x12') and Pt.mean(0)[0] < 100)) else (g, n, Pt) for g, n, Pt in objs]
        ring = []
        for a in (0, 90, 180, 270):
            c = S.CC0 + 84.0 * np.array([math.cos(math.radians(a)), math.sin(math.radians(a))]); th = np.linspace(0, 2 * math.pi, 90)
            for r in (28.3, 30.3):
                for z in np.arange(58.6, 70.61, 1.5): ring.append(np.c_[c[0] + r * np.cos(th), c[1] + r * np.sin(th), np.full(90, z)])
        objs.append(('carousel', 'TT-04 v4 pocket walls', np.vstack(ring)))
        self.objs = objs
    def build(self, lay, drop=()):
        super().build(lay, drop)
        bk = {}
        for k, a in enumerate(LAY['pockets']):
            if a == LAY['pick_deg']: continue
            ph = math.radians(a + 0.0)
            Mb = np.eye(4); Mb[:3, 3] = np.r_[lay.cc + LAY['car_R'] * np.array([math.cos(ph), math.sin(ph)]), CAR_Z]
            bk['C%d' % a] = (Mb, D, H)
        Mb = np.eye(4); Mb[:3, 3] = np.r_[lay.pick[:2], CAR_Z]; bk['Cpick'] = (Mb, D, H)
        Mb = np.eye(4); Mb[:3, 3] = lay.scale3; bk['S'] = (Mb, D, H)
        for i, p in enumerate(lay.rack):
            Mb = np.eye(4); Mb[:3, 3] = np.r_[p, lay.rack_z]; bk['R%d' % i] = (Mb, D, H)
        self.beakers = bk
        return self

OPEN = {t: S.OPEN[t][56] for t in 'AB'}; CLOSE = {t: S.CLOSE[t][56] for t in 'AB'}

def upright_track(t, off, q0, pts, step=8.0):
    """Cartesian continuation of the grasp centre through pts (hinge vertical); returns list of q or None"""
    A = L.ARM[t]; c0 = A.c0[56]; q = q0[None].copy(); out = [q0.copy()]
    R, tt = A.fk(q); cur = R[0] @ c0 + tt[0] + off
    for p in pts:
        p = np.asarray(p, float); n = max(1, int(np.ceil(np.linalg.norm(p - cur) / step)))
        for k in range(1, n + 1):
            tg = cur + (p - cur) * k / n - off
            def resid(Q):
                R, tt = A.fk(Q); return np.c_[R @ c0 + tt - tg, 40 * (R @ A.g0)[:, :2]]
            qn, r = L._lm(resid, q, 30)
            if np.abs(r).max() > 0.5 or np.degrees(np.abs(qn - q).max()) > 12: return None
            q = qn; out.append(q[0].copy())
        cur = p
    return out

CLR = {'min': 1e9, 'what': ''}
import topdown as TD
MREL_TDS = {t_: TD.td_rel(t_) for t_ in 'AB'}; MREL_TD = None
def td_track(t, off, q0, pts, step=8.0):
    """top-down: beaker bottom follows pts with the beaker axis vertical"""
    A = L.ARM[t]; Mr = MREL_TDS[t]; q = q0[None].copy(); out = [q0.copy()]
    R, tt = A.fk(q); cur = R[0] @ Mr[:3, 3] + tt[0] + off
    for p in pts:
        p = np.asarray(p, float); n = max(1, int(np.ceil(np.linalg.norm(p - cur) / step)))
        for k in range(1, n + 1):
            tg = cur + (p - cur) * k / n - off
            def resid(Q):
                R, tt = A.fk(Q); return np.c_[R @ Mr[:3, 3] + tt - tg, 60 * (R @ Mr[:3, :3])[:, :2, 2]]
            qn, r = L._lm(resid, q, 30)
            if np.abs(r).max() > 0.5 or np.degrees(np.abs(qn - q).max()) > 12: return None
            q = qn; out.append(q[0].copy())
        cur = p
    return out

_KD = {}
def scene_tree(W):
    from scipy.spatial import cKDTree
    if 'tree' not in _KD:
        G = W.lay.group_M(); pts = []; names = []
        for g, n, Pt in W.objs:
            if g == 'rack': continue
            M = G.get(g); Q = Pt if M is None else Pt @ M[:3, :3].T + M[:3, 3]
            pts.append(Q); names += [n] * len(Q)
        rp, rb = W.rack_points(W.lay); pts.append(rp); names += ['RK-03'] * len(rp)
        _KD['tree'] = cKDTree(np.vstack(pts)); _KD['names'] = np.array(names)
    return _KD['tree'], _KD['names']
def cyl_dist(Mb, Dd, Hh, Pts):
    Lp = (np.c_[Pts, np.ones(len(Pts))] @ np.linalg.inv(Mb).T)[:, :3]
    rho = np.hypot(Lp[:, 0], Lp[:, 1]); dz = np.maximum(np.maximum(Lp[:, 2] - Hh, -Lp[:, 2]), 0)
    return np.hypot(np.maximum(rho - Dd / 2, 0), dz)
OTHER_PTS = {}
def clearance(W, t, q, q6, ignore=(), held=None, seat=18.0):
    tree, names = scene_tree(W)
    Pa = W.arm_pts(t, q, q6)[::3]
    d, i = tree.query(Pa); k = int(np.argmin(d)); best = (float(d[k]), 'arm x ' + names[i[k]])
    srcs = [('arm', Pa)]
    if held is not None:
        Mb, Dd, Hh = held; Bp = L.cyl_points(Mb, Dd, Hh)
        Lz = (np.c_[Bp, np.ones(len(Bp))] @ np.linalg.inv(Mb).T)[:, 2]; Bs = Bp[Lz > seat]
        if len(Bs):
            d, i = tree.query(Bs); k = int(np.argmin(d))
            if d[k] < best[0]: best = (float(d[k]), 'held beaker x ' + names[i[k]])
            srcs.append(('held beaker', Bs))
    for nm, Ps in srcs:
        for kk, (Mo, Do, Ho) in W.beakers.items():
            if kk in ignore: continue
            dd = cyl_dist(Mo, Do, Ho, Ps).min()
            if dd < best[0]: best = (float(dd), '%s x beaker %s' % (nm, kk))
        o = 'B' if t == 'A' else 'A'
        if o in OTHER_PTS:
            dd = OTHER_PTS[o][0].query(Ps)[0].min()
            if dd < best[0]: best = (float(dd), '%s x parked arm %s' % (nm, o))
    if best[0] < CLR['min']: CLR['min'] = best[0]; CLR['what'] = best[1]
    return best

def seg_check(W, t, qs, q6, held_sign=None, ignore=(), other=None, seat=18.0, clr=False):
    """collision + margin along a joint path (interpolated so no joint moves > 2 deg between checks)"""
    lay = W.lay; coll = {}; mm = 1e9; dense = [qs[0]]
    for a, b in zip(qs[:-1], qs[1:]):
        n = max(1, int(np.ceil(np.degrees(np.abs(b - a).max()) / 2.0)))
        dense += [a + (b - a) * k / n for k in range(1, n + 1)]
    Mrel = None if held_sign is None else (MREL_TDS[t] if held_sign == 'td' else L.held_rel(t, D, GH, held_sign))
    for i, q in enumerate(dense):
        mm = min(mm, L.margins(q, t).min())
        if i % 2 and i != len(dense) - 1: continue
        held = None
        if Mrel is not None:
            R, tt = L.ARM[t].fk(q[None]); Mb = np.eye(4); Mb[:3, :3] = R[0] @ Mrel[:3, :3]; Mb[:3, 3] = R[0] @ Mrel[:3, 3] + tt[0] + lay.off(t)
            held = (Mb, D, H)
        c = W.check(t, q, q6, ignore=ignore, held=held, other=other, seat_ignore=seat)
        for k, v in c.items(): coll[k] = coll.get(k, 0) + v
        if clr and i % 4 == 0: clearance(W, t, q, q6, ignore, held, seat)
    return mm, coll, dense

def binding(q, t):
    m = L.margins(q, t); return float(m.min()), JN[int(np.argmin(m))]

def path_margin(qs, t):
    M = np.array([L.margins(q, t) for q in qs]); j = int(np.argmin(M.min(0))); return float(M.min()), JN[j]

class Run:
    def __init__(self):
        self.lay = Lay(); self.W = World().build(self.lay); self.W.grid = self.W.raw
        self.park = {t: S.park_pose(self.W, t) for t in 'AB'}
        self.og = {t: self.W.other_grid(t, self.park[t]) for t in 'AB'}
        self.steps = []
    def other(self, t): return self.og['B' if t == 'A' else 'A']
    def zsafe(self): return 175.0

    def grasp_options(self, t, xy, zb, ignore):
        tg = np.r_[xy, zb + GH]
        sols = L.grasp_all(t, self.lay.off(t), [tg], D, nseed=48)[0]
        good = []
        for q, m, s in sols:
            if m.min() < 10: continue
            c = self.W.check(t, q, OPEN[t], ignore=ignore, other=self.other(t))
            if c: continue
            good.append((q, m, s))
        return tg, good

    def transfer(self, t, label, src_xy, src_zb, src_key, dst_xy, dst_zb, sign=None, dst_key=None, route=(), z_hi=175.0, gh=None):
        global GH
        if gh is not None: GH = gh
        """pick at src (descend from zsafe), upright carry at zsafe, place at dst; returns record"""
        lay = self.lay; off = lay.off(t)
        tg_s, gs = self.grasp_options(t, src_xy, src_zb, (src_key,))
        ign = (src_key, dst_key)
        tg_d, gd = self.grasp_options(t, dst_xy, dst_zb, ign)
        best = None
        for qs_, ms, ss in gs:
            if sign is not None and ss != sign: continue
            for qd_, md, sd in gd:
                if sd != ss: continue
                up = upright_track(t, off, qs_, [np.r_[tg_s[:2], z_hi]])
                if up is None: continue
                carry = upright_track(t, off, up[-1], [np.asarray(p, float) for p in route] + [np.r_[tg_d[:2], self.zsafe()], tg_d])
                if carry is None: continue
                if np.degrees(np.abs(carry[-1] - qd_).max()) > 5: continue     # landed on another branch
                path = up + carry[1:]
                mm, coll, dense = seg_check(self.W, t, path, CLOSE[t], held_sign=ss, ignore=ign, other=self.other(t))
                # approach from park to above the source with jaws open (joint interpolation), and back
                appr = upright_track(t, off, qs_, [np.r_[tg_s[:2], self.zsafe()]])
                m2, c2, _ = seg_check(self.W, t, [self.park[t], appr[-1]] + appr[::-1], OPEN[t], ignore=(src_key,), other=self.other(t))
                back = upright_track(t, off, qd_, [np.r_[tg_d[:2], self.zsafe()]])
                m3, c3, _ = seg_check(self.W, t, back + [self.park[t]], OPEN[t], ignore=ign, other=self.other(t))
                for c in (c2, c3):
                    for k, v in c.items(): coll['approach/retreat ' + k] = coll.get('approach/retreat ' + k, 0) + v
                pm, pj = path_margin(path, t)
                rec = dict(step=label, arm=t, sign=ss, pick=binding(qs_, t), place=binding(qd_, t), carry=(pm, pj),
                           approach=min(m2, m3), coll=coll, r_src=float(np.hypot(*(tg_s[:2] - lay.pan(t)))),
                           r_dst=float(np.hypot(*(tg_d[:2] - lay.pan(t)))), q_pick=np.degrees(qs_).round(1).tolist(),
                           q_place=np.degrees(qd_).round(1).tolist(),
                           _paths=[(path, CLOSE[t], ss, ign, 18.0), ([self.park[t], appr[-1]] + appr[::-1], OPEN[t], None, (src_key,), 18.0), (back + [self.park[t]], OPEN[t], None, ign, 18.0)])
                key = (not coll, min(rec['pick'][0], rec['place'][0], pm))
                if best is None or key > best[0]: best = (key, rec)
                if not coll and key[1] >= 10: break
            if best and best[0][0] and best[0][1] >= 10: break
        if best is None:
            rec = dict(step=label, arm=t, fail='no in-margin collision-free grasp pair (src %d, dst %d)' % (len(gs), len(gd)))
        else: rec = best[1]
        if '_paths' in rec:
            CLR['min'] = 1e9; CLR['what'] = ''
            for qs, q6, hs, ig, se in rec.pop('_paths'): seg_check(self.W, t, qs, q6, held_sign=hs, ignore=ig, other=None, seat=se, clr=True)
            rec['clearance_mm'] = round(CLR['min'], 1); rec['clearance_at'] = CLR['what']
        self.steps.append(rec); return rec

    def td_transfer(self, t, label, src_xy, src_zb, src_key, dst_xy, dst_zb, dst_key, z_hi=175.0):
        lay = self.lay; off = lay.off(t); ign = (src_key, dst_key)
        def opts(xy, zb):
            out = []
            for q, m in TD.td_grasps(t, off, [np.r_[xy, zb]])[0]:
                if m.min() < 10: continue
                if self.W.check(t, q, OPEN[t], ignore=ign, other=self.other(t)): continue
                out.append((q, m))
            return out
        gs = opts(src_xy, src_zb); gd = opts(dst_xy, dst_zb); best = None
        for qs_, ms in gs:
            for qd_, md in gd:
                up = td_track(t, off, qs_, [np.r_[src_xy, z_hi]])
                if up is None: continue
                pan_ = lay.pan(t); a0 = np.asarray(src_xy) - pan_; a1 = np.asarray(dst_xy) - pan_
                th0, th1 = math.atan2(a0[1], a0[0]), math.atan2(a1[1], a1[0]); r0, r1 = np.linalg.norm(a0), np.linalg.norm(a1)
                dth = (th1 - th0 + math.pi) % (2 * math.pi) - math.pi
                arcp = [np.r_[pan_ + (r0 + (r1 - r0) * u) * np.array([math.cos(th0 + dth * u), math.sin(th0 + dth * u)]), z_hi] for u in np.linspace(0.1, 1.0, 10)]
                dl = td_track(t, off, qd_, [np.r_[dst_xy, z_hi]])
                carry = None if dl is None else [up[-1]] + dl[::-1]
                if carry is None or np.degrees(np.abs(carry[-1] - qd_).max()) > 5: continue
                path = up + carry[1:]
                mm, coll, _ = seg_check(self.W, t, path, CLOSE[t], held_sign='td', ignore=ign, other=self.other(t))
                appr = td_track(t, off, qs_, [np.r_[src_xy, z_hi]])
                m2, c2, _ = seg_check(self.W, t, [self.park[t], appr[-1]] + appr[::-1], OPEN[t], ignore=ign, other=self.other(t))
                back = td_track(t, off, qd_, [np.r_[dst_xy, z_hi]])
                m3, c3, _ = seg_check(self.W, t, back + [self.park[t]], OPEN[t], ignore=ign, other=self.other(t))
                for c in (c2, c3):
                    for k, v in c.items(): coll['approach/retreat ' + k] = coll.get('approach/retreat ' + k, 0) + v
                pm, pj = path_margin(path, t)
                rec = dict(step=label, arm=t, grasp='top-down', pick=binding(qs_, t), place=binding(qd_, t), carry=(pm, pj), approach=min(m2, m3), coll=coll,
                           r_src=float(np.hypot(*(np.asarray(src_xy) - lay.pan(t)))), r_dst=float(np.hypot(*(np.asarray(dst_xy) - lay.pan(t)))),
                           _paths=[(path, CLOSE[t], 'td', ign, 18.0), ([self.park[t], appr[-1]] + appr[::-1], OPEN[t], None, ign, 18.0), (back + [self.park[t]], OPEN[t], None, ign, 18.0)])
                key = (not coll, min(rec['pick'][0], rec['place'][0], pm, m2, m3))
                if best is None or key > best[0]: best = (key, rec)
                if not coll and key[1] >= 10: break
            if best and best[0][0] and best[0][1] >= 10: break
        rec = dict(step=label, arm=t, fail='no top-down solution (src %d, dst %d grasps)' % (len(gs), len(gd))) if best is None else best[1]
        if '_paths' in rec:
            CLR['min'] = 1e9; CLR['what'] = ''
            for qs, q6, hs, ig, se in rec.pop('_paths'): seg_check(self.W, t, qs, q6, held_sign=hs, ignore=ig, other=None, seat=se, clr=True)
            rec['clearance_mm'] = round(CLR['min'], 1); rec['clearance_at'] = CLR['what']
        self.steps.append(rec); return rec

    def pour(self, t, label, src_xy, src_zb, src_key, rim_xy, rim_z, band, tol=25.0, back=True, heights=(), starts=(), lim=20.0, fallback=(), hi=40.0, route=(), dst=None, land_dx=0.0, gh=None):
        """pick at src, carry upright to the pre-pour pose, pour manifold 40..105, return and place back at src"""
        global GH
        if gh is not None: GH = gh
        lay = self.lay; off = lay.off(t)
        tg_s, gs = self.grasp_options(t, src_xy, src_zb, (src_key,))
        res = []
        for sign in (1, -1):
            pairs = []; meta = []
            for h in heights:
                for o in starts:
                    for p in np.radians(np.arange(-180, 180, 5)):
                        dv = np.array([math.cos(p), math.sin(p), 0.0])
                        pairs.append((np.r_[rim_xy, rim_z + h] + o * dv, p)); meta.append((h, o))
            r = L.pour_manifolds(t, off, D, GH, sign, None, None, d_weight=0.0, pairs=pairs, thetas=np.arange(55.0, 105.01, 1.0))
            for x in r:
                x['h'], x['start'] = meta[x['cand']]; x['lip_off_range'] = (x['start'] + x['dlo'], x['start'] + x['dhi'])
            res += [x for x in r if x['drift'] <= tol and -lim <= x['lip_off_range'][0] + land_dx and x['lip_off_range'][1] + land_dx <= lim and x['minmargin'] >= 10]
        res.sort(key=lambda x: -x['minmargin'])
        best = None; tried = 0; best_fail = None; first_hit = None; why = {}
        for x in res:
            if tried > 60: break
            tried += 1
            # pour manifold collisions (receiver beaker ignored only for the beaker contents; keep its body)
            mm, coll, _ = seg_check(self.W, t, list(x['qs'][::2]), CLOSE[t], held_sign=x['sign'], ignore=(src_key,), other=self.other(t), seat=-1)
            if coll:
                if first_hit is None:
                    Mr = L.held_rel(t, D, GH, x['sign'])
                    for k in range(0, len(x['qs']), 2):
                        q = x['qs'][k]; Rr, tt = L.ARM[t].fk(q[None]); Mb = np.eye(4); Mb[:3, :3] = Rr[0] @ Mr[:3, :3]; Mb[:3, 3] = Rr[0] @ Mr[:3, 3] + tt[0] + off
                        c = self.W.check(t, q, CLOSE[t], ignore=(src_key,), held=(Mb, D, H), other=self.other(t), seat_ignore=-1)
                        if c:
                            first_hit = dict(theta=55 + k, counts=c, parts=[(a_, str(b_), n_) for (a_, b_), n_ in S.explain(self.W, t, q, CLOSE[t], (Mb, D, H))]); break
                continue
            # tilt-in (theta 0..40) from the upright pre-pour pose: reconstruct by continuation backwards
            q40 = x['qs'][0]; lip = x['lip']; psi = x['psi']
            desc = lip_lift(t, off, x['sign'], psi, q40, lip, max(hi, x['h'] + 15.0) - x['h'])
            tin = None; m_in = m_d = -99.0
            if desc is not None:
                m_d, c_d, _ = seg_check(self.W, t, desc, CLOSE[t], held_sign=x['sign'], ignore=(src_key,), other=self.other(t), seat=-1)
                if not c_d and m_d >= 10:
                    q55h = desc[0]
                    back = tilt_back(t, off, x['sign'], psi, q55h)
                    if back is not None:
                        m_in, c_in, _ = seg_check(self.W, t, back, CLOSE[t], held_sign=x['sign'], ignore=(src_key,), other=self.other(t), seat=-1)
                        if not c_in and m_in >= 10: tin = back + desc[1:]
                    if tin is None:     # fallback: upright pre-pour above, joint segment to theta 55 (raised lip)
                        Mr = L.held_rel(t, D, GH, x['sign']); Rh, th_ = L.ARM[t].fk(q55h[None]); both = Rh[0] @ Mr[:3, 3] + th_[0] + off
                        for lift in (30.0, 55.0, 80.0):
                            tgp = np.r_[both[:2], both[2] + lift + GH]
                            cands = [c for c in L.grasp_all(t, off, [tgp], D, nseed=32)[0] if c[2] == x['sign']]
                            cands.sort(key=lambda c: np.abs(c[0] - q55h).max())
                            for qp, mp, sp in cands[:2]:
                                if np.degrees(np.abs(qp - q55h).max()) > 90: continue
                                seg = [qp, q55h]
                                m_in, c_in, _ = seg_check(self.W, t, seg, CLOSE[t], held_sign=x['sign'], ignore=(src_key,), other=self.other(t), seat=-1)
                                if not c_in and m_in >= 10: tin = seg + desc[1:]; break
                            if tin is not None: break
            if tin is None:
                why['tilt-in/descend'] = why.get('tilt-in/descend', 0) + 1; continue
            qpre = tin[0]
            for gq, gm, gsn in gs:
                if gsn != x['sign']: continue
                up = upright_track(t, off, gq, [np.r_[tg_s[:2], 300.0]])
                if up is None: continue
                Rp, tp = L.ARM[t].fk(qpre[None]); cpre = Rp[0] @ L.ARM[t].c0[56] + tp[0] + off
                zc = max(self.zsafe(), cpre[2] + 30)
                dh = upright_track(t, off, qpre, [np.r_[cpre[:2], 300.0]])
                carry = None if dh is None else [up[-1]] + dh[::-1]      # joint-space carry at Z 300 (pitch sum + roll constant)
                if carry is None or np.degrees(np.abs(carry[-1] - qpre).max()) > 5:
                    why['carry IK'] = why.get('carry IK', 0) + 1; continue
                m_c, c_c, _ = seg_check(self.W, t, up + carry[1:], CLOSE[t], held_sign=gsn, ignore=(src_key,), other=self.other(t))
                appr = upright_track(t, off, gq, [np.r_[tg_s[:2], self.zsafe()]])
                m_a, c_a, _ = seg_check(self.W, t, [self.park[t], appr[-1]] + appr[::-1], OPEN[t], ignore=(src_key,), other=self.other(t))
                coll = dict(c_c); coll.update({'approach ' + k: v for k, v in c_a.items()})
                rec = dict(step=label, arm=t, sign=gsn, pick=binding(gq, t), carry=path_margin(up + carry[1:], t),
                           pour=(x['minmargin'], JN[int(np.argmin(x['per']))]), tilt_in_descend=min(m_in, m_d), approach=m_a,
                           psi_deg=round(math.degrees(psi)), lip_above_rim=round(x['h'], 1), lip_start_off=x['start'],
                           lip_drift=round(x['drift'], 1), lip_offset_range=[round(v, 1) for v in x['lip_off_range']], landing_offset_mm=round(max(abs(x['lip_off_range'][0] + land_dx), abs(x['lip_off_range'][1] + land_dx)), 1), grip_h=GH, coll=coll,
                           r_src=float(np.hypot(*(tg_s[:2] - lay.pan(t)))), r_rcv=float(np.hypot(*(np.asarray(rim_xy) - lay.pan(t)))),
                           q_pick=np.degrees(gq).round(1).tolist(), q_pour55=np.degrees(x['qs'][0]).round(1).tolist(),
                           q_pour105=np.degrees(x['qs'][-1]).round(1).tolist(),
                           _paths=[(up + carry[1:], CLOSE[t], gsn, (src_key,), 18.0), (tin, CLOSE[t], x['sign'], (src_key,), -1.0), (list(x['qs'][::2]), CLOSE[t], x['sign'], (src_key,), -1.0), ([self.park[t], appr[-1]] + appr[::-1], OPEN[t], None, (src_key,), 18.0)])
                key = (not coll, min(rec['pick'][0], rec['carry'][0], rec['pour'][0], m_in, m_d))
                if best is None or key > best[0]: best = (key, rec)
                if coll: why['carry/approach collision: ' + ','.join(sorted(coll))] = why.get('carry/approach collision: ' + ','.join(sorted(coll)), 0) + 1
                if not coll: break
            if best and best[0][0]: break
        if best is None and fallback:
            h2 = fallback[0][0]; dx2 = 250.0 * math.sqrt(2 * h2 / 9810.0)
            return self.pour(t, label, src_xy, src_zb, src_key, rim_xy, rim_z, band, tol, back, fallback[0], (-dx2 - 6, -dx2, -dx2 + 6), lim, fallback[1:], h2 + 15, route, dst, dx2, gh)
        if best is None:
            rec = dict(step=label, arm=t, fail='no collision-free pour (%d in-margin manifolds, %d tried)' % (len(res), tried), first_manifold_hit=first_hit, reasons=why, best_manifold_margin=(res[0]['minmargin'] if res else None))
        else: rec = best[1]
        if '_paths' in rec:
            CLR['min'] = 1e9; CLR['what'] = ''
            for qs, q6, hs, ig, se in rec.pop('_paths'): seg_check(self.W, t, qs, q6, held_sign=hs, ignore=ig, other=None, seat=se, clr=True)
            rec['clearance_mm'] = round(CLR['min'], 1); rec['clearance_at'] = CLR['what']
        self.steps.append(rec); return rec

def tilt_back(t, off, sign, psi, q55, step=2.0):
    """pinned-lip continuation theta 55 -> 0 (lip at its theta-55 position); returns poses theta 0 -> 55"""
    A = L.ARM[t]; Mrel = L.held_rel(t, D, GH, sign); rr = D / 2
    dv = np.array([math.cos(psi), math.sin(psi), 0.0]); av = np.array([-math.sin(psi), math.cos(psi), 0.0])
    R0, t0 = A.fk(q55[None]); Rb = R0[0] @ Mrel[:3, :3]; zz = Rb[:, 2]
    lip0 = R0[0] @ Mrel[:3, 3] + t0[0] + H * zz + rr * np.cross(av, zz)
    q = q55[None].copy(); out = [q55.copy()]
    for th in np.arange(55.0 - step, -0.01, -step):
        ax = math.cos(math.radians(th)) * np.array([0, 0, 1.0]) + math.sin(math.radians(th)) * dv
        def resid(Q):
            R, tt = A.fk(Q); Rb = R @ Mrel[:3, :3]; pb = R @ Mrel[:3, 3] + tt; z2 = Rb[:, :, 2]
            return np.c_[pb + H * z2 + rr * np.cross(av, z2) - lip0, 60 * (z2 - ax)]
        qn, r = L._lm(resid, q, 30, step=0.15, lam=1e-4)
        if np.abs(r).max() > 0.5 or np.degrees(np.abs(qn - q).max()) > 2.0 * step: return None
        q = qn; out.append(q[0].copy())
    return out[::-1]

def lip_lift(t, off, sign, psi, q55, lip, dz, step=2.0):
    """theta fixed at 55 deg; lip moved straight up by dz (continuation); returns poses top -> bottom"""
    A = L.ARM[t]; Mrel = L.held_rel(t, D, GH, sign); rr = D / 2
    dv = np.array([math.cos(psi), math.sin(psi), 0.0]); av = np.array([-math.sin(psi), math.cos(psi), 0.0])
    ax = math.cos(math.radians(55)) * np.array([0, 0, 1.0]) + math.sin(math.radians(55)) * dv
    R0, t0 = A.fk(q55[None]); Rb = R0[0] @ Mrel[:3, :3]; zz = Rb[:, 2]
    lip0 = R0[0] @ Mrel[:3, 3] + t0[0] + H * zz + rr * np.cross(av, zz)
    q = q55[None].copy(); out = [q55.copy()]
    for h in np.arange(step, dz + 0.01, step):
        tg = lip0 + [0, 0, h]
        def resid(Q):
            R, tt = A.fk(Q); Rb = R @ Mrel[:3, :3]; pb = R @ Mrel[:3, 3] + tt; z2 = Rb[:, :, 2]
            return np.c_[pb + H * z2 + rr * np.cross(av, z2) - tg, 60 * (z2 - ax)]
        qn, r = L._lm(resid, q, 30, step=0.15, lam=1e-4)
        if np.abs(r).max() > 0.5 or np.degrees(np.abs(qn - q).max()) > 6: return None
        q = qn; out.append(q[0].copy())
    return out[::-1]

def tilt_in(t, off, sign, lip, psi, q40):
    """continuation theta 40 -> 0 (upright, lip at the same point) for the tilt-in segment; list from 0 to 40"""
    A = L.ARM[t]; Mrel = L.held_rel(t, D, GH, sign); rr = D / 2
    dv = np.array([math.cos(psi), math.sin(psi), 0.0]); av = np.array([-math.sin(psi), math.cos(psi), 0.0])
    q = q40[None].copy(); out = [q40.copy()]
    for th in np.arange(38.0, -0.1, -2.0):
        ax = math.cos(math.radians(th)) * np.array([0, 0, 1.0]) + math.sin(math.radians(th)) * dv
        def resid(Q):
            R, tt = A.fk(Q); Rb = R @ Mrel[:3, :3]; pb = R @ Mrel[:3, 3] + tt; zz = Rb[:, :, 2]
            e = pb + H * zz + rr * np.cross(av, zz) - (lip - off); ed = np.einsum('ni,i->n', e, dv)
            return np.c_[e - ed[:, None] * dv, 60 * (zz - ax)]
        qn, r = L._lm(resid, q, 30, step=0.15, lam=1e-4)
        if np.abs(r).max() > 0.5 or np.degrees(np.abs(qn - q).max()) > 6: return None
        q = qn; out.append(q[0].copy())
    return out[::-1]

def main(out_json=None):
    t0 = time.time(); R = Run(); lay = R.lay
    pk = lay.pick[:2]; sc = lay.scale; rim_s = SCALE_Z + H; F = lay.funnel
    for t in 'AB': OTHER_PTS[t] = (__import__('scipy.spatial', fromlist=['cKDTree']).cKDTree(R.W.arm_pts(t, R.park[t], 0.0)),)
    print('pans A', lay.pan('A'), 'B', lay.pan('B'), 'park', {t: np.degrees(R.park[t]).round(0).tolist() for t in 'AB'}, flush=True)
    # parked arms vs carousel turning / auger: clearance of the parked poses to the scene and the carousel beakers
    park_clr = {t: clearance(R.W, t, R.park[t], 0.0) for t in 'AB'}
    dxs = 250.0 * math.sqrt(2 * 45.0 / 9810.0)
    sp = dict(heights=(45.0,), starts=(-dxs - 6, -dxs, -dxs + 6), lim=20.0, tol=15.0, hi=60.0, land_dx=dxs, gh=40.0, fallback=((55.0,),))
    def fpd(h, gh):
        dx = 250.0 * math.sqrt(2 * h / 9810.0)
        return dict(heights=(h,), starts=(-dx - 6, -dx, -dx + 6), lim=40.0, tol=15.0, hi=h + 15, land_dx=dx, gh=gh, fallback=((80.0,),))
    TR, PO = 'B', 'A'      # transfer arm (east, top-down) = model tag B; pourer (west, side grasp) = model tag A
    zc = 82.0
    seq = [
        ('carousel: P1 (empty) to the pick pocket; arms parked', None),
        ('1  transfer arm: P1 carousel -> scale (top-down)', lambda: R.td_transfer(TR, '1  transfer arm (east): P1 carousel -> scale (top-down)', pk, CAR_Z, 'Cpick', sc, SCALE_Z, 'S', z_hi=zc)),
        ('2  pourer: developer -> scale', lambda: R.pour(PO, '2  pourer (west): developer rack -> pour onto P1 -> rack (grip 40, lip 45)', lay.rack[0], lay.rack_z, 'R0', sc, rim_s, (15.0, 70.0), **sp)),
        ('3  pourer: P1 -> funnel', lambda: R.pour(PO, '3  pourer (west): P1 scale -> pour into funnel -> scale (grip 30, lip 65)', sc, SCALE_Z, 'S', F[:2], F[2], (50.0, 100.0), **fpd(65.0, 30.0))),
        ('4  transfer arm: P1 scale -> carousel', lambda: R.td_transfer(TR, '4  transfer arm (east): P1 scale -> carousel (top-down)', sc, SCALE_Z, 'S', pk, CAR_Z, 'Cpick', z_hi=zc)),
        ('carousel: P2 to auger, dose yeast (DH-01 underside z160), P2 to pick; arms parked', None),
        ('5  transfer arm: P2 carousel -> scale', lambda: R.td_transfer(TR, '5  transfer arm (east): P2 carousel -> scale (top-down)', pk, CAR_Z, 'Cpick', sc, SCALE_Z, 'S', z_hi=zc)),
        ('6  pourer: water -> scale', lambda: R.pour(PO, '6  pourer (west): water rack -> pour onto P2 -> rack (grip 40, lip 45)', lay.rack[2], lay.rack_z, 'R2', sc, rim_s, (15.0, 70.0), **sp)),
        ('7  pourer: P2 -> funnel', lambda: R.pour(PO, '7  pourer (west): P2 scale -> pour into funnel -> scale (grip 30, lip 65)', sc, SCALE_Z, 'S', F[:2], F[2], (50.0, 100.0), **fpd(65.0, 30.0))),
        ('8  transfer arm: P2 scale -> carousel', lambda: R.td_transfer(TR, '8  transfer arm (east): P2 scale -> carousel (top-down)', sc, SCALE_Z, 'S', pk, CAR_Z, 'Cpick', z_hi=zc)),
    ]
    for lab, fn in seq:
        if fn is None:
            R.steps.append(dict(step=lab, arm='-', park_clearance_mm={t: round(park_clr[t][0], 1) for t in 'AB'},
                                park_clearance_at={t: park_clr[t][1] for t in 'AB'}, park_margin={t: binding(R.park[t], t) for t in 'AB'}))
        else: fn()
        print(R.steps[-1], round(time.time() - t0), flush=True)
    print('total %.0f s' % (time.time() - t0))
    if out_json:
        old = json.load(open(out_json)) if os.path.exists(out_json) else {}
        old.update(dict(layout={k: (v if not isinstance(v, np.ndarray) else v.tolist()) for k, v in LAY.items()},
                        pans={t: lay.pan(t).tolist() for t in 'AB'}, park_deg={t: np.degrees(R.park[t]).round(1).tolist() for t in 'AB'},
                        grip_h=GH, steps=R.steps))
        json.dump(old, open(out_json, 'w'), indent=1, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    return R

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
