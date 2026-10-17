"""Priority-1 study: side-grasp wrist-roll pours with a high lip (current gripper, offset ~162 mm).
Sweeps lip height, GRIP_H and roll direction; full voxel collision (1-voxel dilation, real fin-ray meshes) against
receiver, scale, funnel, flask, frame and the parked other arm; stream landing with vx 0.25 m/s; lip drift < 15 mm."""
import sys, os, math, json, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'fusion_bridge'))
import layout_final as F, layout_lib as L, layout_study as S
t0 = time.time()
R = F.Run(); lay = R.lay; W = R.W
G = 9810.0; VX = 250.0
def land_dx(h): return VX * math.sqrt(2 * h / G)
CASES = [('scale pour (B)', 'B', lay.scale, F.SCALE_Z + 74.0, (35.0, 45.0, 55.0, 70.0), 20.0, 'R0'),
         ('funnel pour (A)', 'A', lay.funnel[:2], 233.0, (50.0, 65.0, 80.0, 100.0), 40.0, 'S')]
OUT = {}
for name, t, rc, rim, hs, land_lim, src in CASES:
    best = None; n_kin = 0; n_tried = 0; fails = {}
    for gh in (20.0, 30.0, 40.0):
        F.GH = gh
        for h in hs:
            dx = land_dx(h)
            for sign in (1, -1):
                pairs = []; meta = []
                for o in (-dx - 6, -dx, -dx + 6):
                    for p in np.radians(np.arange(-180, 180, 5)):
                        dv = np.array([math.cos(p), math.sin(p), 0.0])
                        pairs.append((np.r_[rc, rim + h] + o * dv, p)); meta.append(o)
                res = L.pour_manifolds(t, lay.off(t), 56, gh, sign, None, None, d_weight=0.0, pairs=pairs)
                for x in res:
                    o = meta[x['cand']]
                    lo, hi = o + x['dlo'] + dx, o + x['dhi'] + x['dhi'] * 0 + dx
                    x['land'] = max(abs(lo), abs(hi)); x['o'] = o
                res = [x for x in res if x['drift'] < 15 and x['land'] <= land_lim and x['minmargin'] >= 10]
                n_kin += len(res)
                res.sort(key=lambda x: -x['minmargin'])
                for x in res[:6]:
                    n_tried += 1
                    mm, coll, _ = F.seg_check(W, t, list(x['qs'][::2]), F.CLOSE[t], held_sign=sign, ignore=(src,), other=R.other(t), seat=-1)
                    if coll:
                        k = tuple(sorted(coll)); fails[k] = fails.get(k, 0) + 1; continue
                    F.CLR['min'] = 1e9; F.CLR['what'] = ''
                    F.seg_check(W, t, list(x['qs'][::2]), F.CLOSE[t], held_sign=sign, ignore=(src,), other=None, seat=-1, clr=True)
                    rec = dict(lip_above_rim=h, grip_h=gh, sign=sign, psi=round(math.degrees(x['psi'])), margin=round(x['minmargin'], 1),
                               binding=F.JN[int(np.argmin(x['per']))], clearance_mm=round(F.CLR['min'], 1), clearance_at=F.CLR['what'],
                               landing_offset_mm=round(x['land'], 1), lip_drift=round(x['drift'], 1), start_off=round(x['o'], 1),
                               r_receiver=round(float(np.hypot(*(np.asarray(rc) - lay.pan(t)))), 1))
                    key = (rec['clearance_mm'] >= 3, rec['margin'])
                    if best is None or key > best[0]: best = (key, rec)
                    break
            print(name, 'gh', gh, 'h', h, 'best so far', None if best is None else best[1], round(time.time() - t0), flush=True)
    OUT[name] = dict(best=None if best is None else best[1], kinematic_candidates=n_kin, collision_checked=n_tried,
                     collision_fail_kinds={'+'.join(k): v for k, v in fails.items()})
    print(name, OUT[name], flush=True)
json.dump(OUT, open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'roll_pour_study.json'), 'w'), indent=1)
