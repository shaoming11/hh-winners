"""Grasp-offset parametric study: shorten the wrist-flex-axis -> grasp-centre offset by moving the grasp centre toward
the jaw hinge along the finger direction e1 (equivalent to a shorter jaw/palm + fingers).  Kinematic margins only."""
import sys, os, math
import numpy as np
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'fusion_bridge'))
import layout_lib as L, topdown as T, planner as P
t = 'B'; A = L.ARM[t]; G = P.GRASP[t]
C0 = A.c0[56].copy(); PALM0 = T.PALM; WF = np.array(A.p[3])
pan = A.pan
def off_now(): return float(np.linalg.norm(A.c0[56] - WF))
print('geometry: wrist-flex axis point', WF.round(1), 'jaw hinge', G.gp.round(1), 'grasp centre (56)', C0.round(1))
print('  wrist-flex -> grasp centre %.1f mm; wrist-flex -> jaw hinge %.1f mm; hinge -> centre along finger %.1f, sideways %.1f'
      % (np.linalg.norm(C0 - WF), np.linalg.norm(G.gp - WF), (C0 - G.gp) @ G.e1, (C0 - G.gp) @ G.e2))
def side_pour(rim_z, h, r):
    best = None
    for sign in (1, -1):
        lip = np.r_[pan[0], pan[1] - r, rim_z + h]
        pairs = [(lip + o * np.array([math.cos(p), math.sin(p), 0]), p) for p in np.radians(np.arange(-180, 180, 15)) for o in (0.0, -10.0)]
        for x in L.pour_manifolds(t, (0, 0, 0), 56, 30.0, sign, None, None, d_weight=0.0, pairs=pairs):
            if x['drift'] <= 25 and (best is None or x['minmargin'] > best[0]): best = (round(x['minmargin'], 1), ['pan', 'sh', 'el', 'fl', 'ro'][int(np.argmin(x['per']))])
    return best
def td_pour(rim_z, h, r):
    b = T.best_td_pour(t, (0, 0, 0), (pan[0], pan[1] - r), rim_z, (h,), psis_rel=(0,), inward=True)
    b2 = T.best_td_pour(t, (0, 0, 0), (pan[0], pan[1] - r), rim_z, (h,), psis_rel=(0,), inward=False)
    c = [x for x in (b, b2) if x]
    if not c: return None
    x = max(c, key=lambda y: y['margin']); return (round(x['margin'], 1), x['binding'])
for target in (150, 130, 115, 100, 85):
    # move the grasp centre along -e1 to reach the target offset (closest achievable)
    best_s, err = 0, 1e9
    for s in np.arange(0, 120, 0.5):
        dd = abs(np.linalg.norm(C0 - s * G.e1 - WF) - target)
        if dd < err: err, best_s = dd, s
    A.c0[56] = C0 - best_s * G.e1; T.PALM = PALM0 - best_s
    o = off_now(); res = {}
    for name, fn, rim, h, rs in (('a side roll -> scale', side_pour, 137.7, 20.0, (180, 240, 300)),
                                 ('b top-down pitch -> scale', td_pour, 137.7, 30.0, (180, 220, 260, 300)),
                                 ('c top-down pitch -> funnel', td_pour, 233.0, 50.0, (180, 220, 260, 300)),
                                 ('d side roll -> funnel', side_pour, 233.0, 50.0, (200, 260, 320))):
        bb = None
        for r in rs:
            x = fn(rim, h, r)
            if x and (bb is None or x[0] > bb[0]): bb = (x[0], x[1], r)
        res[name] = bb
    print('offset target %d -> actual %.1f mm (centre moved %.1f mm toward the hinge%s): %s' % (
        target, o, best_s, ', NOT reachable: hinge itself is %.0f mm away' % np.linalg.norm(G.gp - WF) if err > 3 else '', res), flush=True)
A.c0[56] = C0; T.PALM = PALM0
