import sys, os, json, math, atexit
atexit.register(lambda: [print(x) for x in LOG])
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'fusion_bridge'))
from planner import *
rng = np.random.default_rng(3)
for t in 'AB':
    for lk in ARMP[t]:
        P = ARMP[t][lk]
        if len(P) > 9000: ARMP[t][lk] = P[rng.choice(len(P), 9000, replace=False)]
FPS = 12
W = World()
CAR.append((237.2, 432.2))
for i, (x, y) in enumerate(CAR): W.beakers['C%d' % i] = Beaker('C%d' % i, 43, 61, (x, y, 60.2))
PICK = 'C%d' % (len(CAR) - 1)
for k, (x, y) in (('dev', (670, 414)), ('soap', (717, 495)), ('water', (707, 587))): W.beakers[k] = Beaker(k, 56, 74, (x, y, 26.2))
SCALE = (468.0, 475.0, 63.7)
FUNNEL = (450.0, 282.0, 233.0)
GRIP_H = {43: 45.0, 56: 52.0}
OPEN = {t: {D: math.radians(GSOL[t][D]['close'][0] + 5) for D in (43.0, 56.0)} for t in 'AB'}   # fin-ray: open 5 deg past contact, vertical approach
CLOSE = {t: {D: math.radians(GSOL[t][D]['close'][0]) for D in (43.0, 56.0)} for t in 'AB'}
LOG = []

frames = []
IGN = {'A': (), 'B': ()}
state = {'tt': 22.5, 'crank': 0.0, 'auger': 0.0, 'foam': 0, 'caption': '', 'scale': None,
         'cam': {'t': (46, 42, 10), 'd': (150, -200, 170), 'ext': 50}, 'liq': {}, 'hide': set()}
def snap():
    f = {'A': list(W.q['A']), 'B': list(W.q['B']), 'tt': state['tt'], 'crank': state['crank'], 'auger': state['auger'],
         'foam': state['foam'], 'cam': state['cam'], 'caption': state['caption'], 'scale': state['scale'], 'hide': sorted(state['hide'])}
    m = W.beakers.get('M'); r = W.beakers.get('R')
    f['b50'] = m.M.tolist() if m else None; f['b50_vis'] = state['liq'].get('M', [])
    f['b100'] = r.M.tolist() if r else None; f['b100_vis'] = state['liq'].get('R', [])
    f['beakers'] = {k: b.M.tolist() for k, b in W.beakers.items()}
    f['ign'] = {k: list(v) for k, v in IGN.items()}
    for tt in 'AB': f['held_' + tt] = W.held[tt][0].name if W.held[tt] else None
    frames.append(f)
def update_held():
    for t in 'AB':
        h = W.held[t]
        if h: h[0].M = GRASP[t].arm.chain(W.q[t], 5) @ h[1]
def seg_check(t, qa, qb, ignore=(), n=None):
    og = W.other_grid(t)
    steps = n or max(2, int(np.max(np.abs(qb - qa)) / math.radians(1.5)) + 1)
    bad = 0
    for i in range(steps + 1):
        q = qa + (qb - qa) * i / steps; save = W.q[t]; W.q[t] = q; update_held()
        c = W.collides(t, q, og, ignore); W.q[t] = save; update_held()
        if c: bad += 1
    return bad
def play(t, qb, secs, fn=None):
    qa = W.q[t].copy(); n = max(1, int(secs * FPS))
    for i in range(1, n + 1):
        u = i / n; s = u * u * (3 - 2 * u); W.q[t] = qa + (qb - qa) * s; update_held()
        if fn: fn(s)
        snap()
def wait(secs, fn=None):
    n = max(1, int(secs * FPS))
    for i in range(1, n + 1):
        if fn: fn(i / n)
        snap()
def cam(c, secs=1.0):
    c0 = state['cam']
    def f(s): state['cam'] = {'t': tuple(a + (b - a) * s for a, b in zip(c0['t'], c['t'])), 'd': tuple(a + (b - a) * s for a, b in zip(c0['d'], c['d'])), 'ext': c0['ext'] + (c['ext'] - c0['ext']) * s}
    wait(secs, f)

def grasp_solutions(t, target, D, ignore):
    """collision-free IK solutions (q) for the grasp-centre at target with the hinge vertical"""
    sols = []
    og = W.other_grid(t)
    seeds = [W.q[t]] + [np.r_[rng.uniform(-1.8, 1.8, 5), 0] for _ in range(60)]
    for hs in (1, -1):
        for s in seeds:
            q, e, ge = ik_grasp(t, target, hs, s, D)
            if e > 0.8 or ge > 0.02 or np.max(np.abs(q[:5])) > 2.8: continue
            q[5] = W.q[t][5]
            if any(np.max(np.abs(q[:5] - p[:5])) < 0.05 for p in sols): continue
            if W.collides(t, q, og, ignore) == 0: sols.append(q)
    sols.sort(key=lambda q: np.max(np.abs(q[:5] - W.q[t][:5])))
    return sols
def line_pose(t, q_ref, delta, D):
    """same orientation as q_ref, grasp centre shifted by delta (Cartesian)"""
    arm = GRASP[t].arm; c0 = GSOL[t][D]['close'][1]
    c = (arm.chain(q_ref, 5) @ np.append(c0, 1))[:3] + np.asarray(delta)
    hs = 1 if (arm.chain(q_ref, 5)[:3, :3] @ GRASP[t].g)[2] > 0 else -1
    q, e, ge = ik_grasp(t, c, hs, q_ref, D); q[5] = q_ref[5]; return q, e
def free(t, q, og, ignore):
    save = W.q[t]; W.q[t] = q; update_held(); c = W.collides(t, q, og, ignore); W.q[t] = save; update_held(); return c == 0
def edge_free(t, qa, qb, og, ignore, step=math.radians(1.5)):
    n = max(1, int(np.max(np.abs(qb[:5] - qa[:5])) / step))
    return all(free(t, qa + (qb - qa) * i / n, og, ignore) for i in range(1, n + 1))
def rrt_connect(t, qa, qb, ignore=(), iters=2500, eps=math.radians(10)):
    og = W.other_grid(t); lo, hi = -2.8, 2.8
    Ta, Tb = [qa.copy()], [qb.copy()]; Pa, Pb = [-1], [-1]
    def extend(Tr, Pr, q):
        d = np.array([np.linalg.norm(x[:5] - q[:5]) for x in Tr]); i = int(d.argmin()); qn = Tr[i]
        step = q - qn; L = np.linalg.norm(step[:5])
        qnew = q.copy() if L <= eps else qn + step * (eps / L); qnew[5] = qa[5]
        if edge_free(t, qn, qnew, og, ignore): Tr.append(qnew); Pr.append(i); return len(Tr) - 1
        return None
    for it in range(iters):
        qr = np.r_[rng.uniform(lo, hi, 5), qa[5]] if rng.random() > 0.15 else Tb[-1].copy()
        ia = extend(Ta, Pa, qr)
        if ia is None: Ta, Tb, Pa, Pb = Tb, Ta, Pb, Pa; continue
        # connect the other tree greedily
        while True:
            ib = extend(Tb, Pb, Ta[ia])
            if ib is None: break
            if np.linalg.norm(Tb[ib][:5] - Ta[ia][:5]) < 1e-6:
                def trace(Tr, Pr, i):
                    out = []
                    while i != -1: out.append(Tr[i]); i = Pr[i]
                    return out
                A_ = trace(Ta, Pa, ia)[::-1]; B_ = trace(Tb, Pb, ib)
                path = A_ + B_[1:]
                if np.linalg.norm(path[0][:5] - qa[:5]) > 1e-6: path = path[::-1]
                # shortcut
                for _ in range(120):
                    if len(path) < 3: break
                    i, j = sorted(rng.choice(len(path), 2, replace=False))
                    if j - i > 1 and edge_free(t, path[i], path[j], og, ignore): path = path[:i + 1] + path[j:]
                return path
        Ta, Tb, Pa, Pb = Tb, Ta, Pb, Pa
    return None
def go(t, q_goal, secs, ignore=(), D=43.0):
    """joint move with collision fallback: direct -> via lifted -> via rest"""
    qa = W.q[t].copy()
    if seg_check(t, qa, q_goal, ignore) == 0:
        play(t, q_goal, secs); return
    for lift in (60, 110, 160):
        qa_up, e1 = line_pose(t, qa, (0, 0, lift), D); qb_up, e2 = line_pose(t, q_goal, (0, 0, lift), D)
        if e1 < 1 and e2 < 1 and seg_check(t, qa, qa_up, ignore) == 0 and seg_check(t, qa_up, qb_up, ignore) == 0 and seg_check(t, qb_up, q_goal, ignore) == 0:
            play(t, qa_up, secs * 0.35); play(t, qb_up, secs * 0.5); play(t, q_goal, secs * 0.35); return
    rest = READY[t].copy() if t in READY else np.r_[np.zeros(5), W.q[t][5]]; rest[5] = W.q[t][5]
    if seg_check(t, qa, rest, ignore) == 0 and seg_check(t, rest, q_goal, ignore) == 0:
        play(t, rest, secs * 0.6); play(t, q_goal, secs * 0.6); return
    path = rrt_connect(t, qa, q_goal, ignore)
    if path:
        L = sum(np.linalg.norm(path[i + 1][:5] - path[i][:5]) for i in range(len(path) - 1))
        for i in range(1, len(path)):
            seg = np.linalg.norm(path[i][:5] - path[i - 1][:5]); play(t, path[i], max(0.3, secs * 1.4 * seg / max(L, 1e-6)))
        LOG.append('rrt path for arm %s: %d waypoints' % (t, len(path))); return
    LOG.append('WARN no collision-free path for arm %s (%d bad samples direct)' % (t, seg_check(t, qa, q_goal, ignore))); print(LOG[-1], flush=True)
    play(t, q_goal, secs)

READY = {}
def make_ready(t):
    pan = np.array(GRASP[t].arm.axes[0][0]); og = W.other_grid(t); best = None
    for r in (90, 110, 130):
        for z in (200, 230, 260):
            tg = pan + np.array([0, -r, 0]); tg[2] = z
            for hs in (1, -1):
                for k in range(20):
                    s = np.zeros(6) if k == 0 else np.r_[rng.uniform(-1.8, 1.8, 5), 0]
                    q, e, ge = ik_grasp(t, tg, hs, s, 43.0)
                    if e > 1 or ge > 0.03 or np.max(np.abs(q[:5])) > 2.8: continue
                    q[5] = OPEN[t][43.0]
                    if W.collides(t, q, og) == 0:
                        c = np.linalg.norm(q[:5])
                        if best is None or c < best[0]: best = (c, q)
    READY[t] = best[1]; LOG.append('ready pose %s: %s' % (t, np.degrees(best[1][:5]).round(0)))
def home(t, secs=2.0):
    q = READY[t].copy(); q[5] = W.q[t][5]; go(t, q, secs)
def pick(t, bk, D, secs=2.5):
    """approach horizontally along the finger, close on the beaker, lift"""
    target = W.beakers[bk].axis_pt(GRIP_H[int(D)])
    q = W.q[t].copy(); q[5] = OPEN[t][D]; play(t, q, 0.4)
    sols = grasp_solutions(t, target, D, ignore=(bk,))
    if not sols: LOG.append('WARN no grasp for %s on %s' % (t, bk)); print(LOG[-1], flush=True); return False
    for qg in sols:
        qg[5] = OPEN[t][D]
        qpre, e = line_pose(t, qg, (0, 0, 55), D)          # straight down over the beaker
        if e < 1 and W.collides(t, qpre, W.other_grid(t)) == 0 and seg_check(t, qpre, qg, ignore=(bk,)) == 0: break
    else:
        LOG.append('WARN no clear pre-grasp for %s on %s' % (t, bk)); qpre = qg
    go(t, qpre, secs, D=D)
    IGN[t] = (bk,); play(t, qg, 1.0)
    qc = qg.copy(); qc[5] = CLOSE[t][D]; play(t, qc, 0.6)
    W.held[t] = (W.beakers[bk], np.linalg.inv(GRASP[t].arm.chain(W.q[t], 5)) @ W.beakers[bk].M)
    qup, e = line_pose(t, qc, (0, 0, 70), D)
    if seg_check(t, qc, qup) == 0: play(t, qup, 1.0)
    IGN[t] = (); return True
def place(t, pos, D, secs=2.5):
    b = W.held[t][0]
    target = np.array(pos) + np.array([0, 0, GRIP_H[int(D)]])
    sols = grasp_solutions(t, target, D, ignore=(b.name,))
    if not sols: LOG.append('WARN no place pose for %s' % t); return
    qp = sols[0]; qp[5] = W.q[t][5]
    qabove, e = line_pose(t, qp, (0, 0, 60), D)
    go(t, qabove, secs, D=D); play(t, qp, 1.0)
    W.held[t] = None; b.M = np.eye(4); b.M[:3, 3] = pos
    IGN[t] = (b.name,)
    qo = qp.copy(); qo[5] = OPEN[t][D]; play(t, qo, 0.5)
    qback, e = line_pose(t, qo, (0, 0, 60), D)            # lift straight off
    if seg_check(t, qo, qback, ignore=(b.name,)) == 0: play(t, qback, 0.9)
    IGN[t] = ()
def pour_pose(t, receiver_pt, D, tilt_sign):
    """grasp-centre location such that the lowest rim point after a 100 deg roll sits 12 mm above receiver_pt"""
    b = W.held[t][0]; arm = GRASP[t].arm
    hg = GRIP_H[int(D)]; top = b.H; r = b.D / 2
    G = np.array(receiver_pt, float) + np.array([0, 0, 60])
    for _ in range(6):
        pan = np.array(arm.axes[0][0]); f = G - pan; f[2] = 0; f /= np.linalg.norm(f)
        R = rot(f, tilt_sign * math.radians(100))
        th = np.linspace(0, 2 * math.pi, 48); rim = np.c_[r * np.cos(th), r * np.sin(th), np.full(48, top - hg)]
        rim = rim @ R.T; low = rim[np.argmin(rim[:, 2])]
        G = np.array(receiver_pt) + np.array([0, 0, 12]) - low
    return G
def pour(t, receiver_pt, D, fill=None, secs=2.4):
    best = None
    for sign in (1, -1):
        G = pour_pose(t, receiver_pt, D, sign)
        sols = grasp_solutions(t, G, D, ignore=('M',) if W.held[t][0].name != 'M' else ())
        for qp in sols:
            qp[5] = W.q[t][5]; qt = qp.copy(); qt[4] += sign * math.radians(100)
            bad = seg_check(t, qp, qt, ignore=('M',) if receiver_pt is not None else ())
            if best is None or bad < best[0]: best = (bad, qp, qt)
            if bad == 0: break
        if best and best[0] == 0: break
    if best is None: LOG.append('WARN no pour pose for %s' % t); return
    if best[0]: LOG.append('WARN pour tilt for %s touches something in %d samples' % (t, best[0]))
    go(t, best[1], 2.2, D=D)
    IGN[t] = ('M',) if W.held[t][0].name != 'M' else ()
    play(t, best[2], 1.2); wait(secs, fill); play(t, best[1], 1.0)
    IGN[t] = ()

# ======================= storyboard =======================
def cap(s):
    state['caption'] = s; print('[%5d] %s' % (len(frames), s), flush=True)
CAM_MID = {'t': (47, 46, 14), 'd': (120, -170, 130), 'ext': 30}
CAM_OVER = {'t': (46, 42, 10), 'd': (150, -200, 170), 'ext': 50}
CAM_AUG = {'t': (16, 38, 12), 'd': (130, -190, 150), 'ext': 34}
CC = np.array([175.0, 370.0]); CZ = 60.2
# carousel membership: beaker name -> pocket home angle (deg, at tt = 0); meshes were exported at tt = 22.5
CARSET = {}
for k in list(W.beakers):
    if k.startswith('C'):
        p = W.beakers[k].M[:2, 3] - CC; CARSET[k] = round((math.degrees(math.atan2(p[1], p[0])) - 22.5) / 22.5) * 22.5
def set_tt(a):
    state['tt'] = a
    for k, h in CARSET.items():
        if k in W.beakers:
            th = math.radians(h + a); W.beakers[k].M[:3, 3] = (CC[0] + 88.0 * math.cos(th), CC[1] + 88.0 * math.sin(th), CZ)
def turn(a1, secs):
    a0 = state['tt']; wait(secs, lambda s: set_tt(a0 + (a1 - a0) * s))
def name_of(home):
    return [k for k, h in CARSET.items() if abs((h - home + 180) % 360 - 180) < 1][0]
def swap_in(k_new, hide_ref):
    """make carousel beaker k_new the tracked beaker 'M'"""
    W.beakers['M'] = W.beakers.pop(k_new); W.beakers['M'].name = 'M'; CARSET['M'] = CARSET.pop(k_new); state['hide'].add(hide_ref)
P1, P2 = name_of(22.5), name_of(112.5)
set_tt(0.0)
make_ready('A'); make_ready('B'); W.q['A'] = READY['A'].copy(); W.q['B'] = READY['B'].copy()
cap('Wet Lab Bench: automatic elephant-toothpaste run'); wait(1.5)
cap('1  Carousel indexes an empty beaker to arm A (servo ramped, walled pockets)')
swap_in(P1, 'REF-BEAKERS-TT:2+REF-BEAKER:2')
turn(22.5, 2.0); wait(0.3)
cap('2  Arm A grips the beaker and sets it on the scale')
del CARSET['M']
pick('A', 'M', 43.0); place('A', SCALE, 43.0); home('A')
state['scale'] = 0.0
cam(CAM_MID)
def reagent_pour(key, label, grams, levels):
    cap(label)
    W.beakers['R'] = W.beakers.pop(key); W.beakers['R'].name = 'R'; state['hide'].add('REAGENT-%s' % key); state['liq']['R'] = ['liq5']
    slot = W.beakers['R'].M[:3, 3].copy()
    pick('B', 'R', 56.0)
    s0 = state['scale'] or 0.0
    def fill(s):
        k = min(len(levels), int(s * len(levels)) + 1); state['liq']['M'] = [l for l in state['liq'].get('M', []) if not l.startswith('liq')] + [levels[k - 1]]
        state['liq']['R'] = ['liq%d' % max(1, 5 - int(3 * s))]; state['scale'] = s0 + grams * s
    pour('B', np.array(SCALE) + np.array([0, 0, 61]), 56.0, fill)
    place('B', slot, 56.0)
    b = W.beakers.pop('R'); b.name = key; W.beakers[key] = b; state['hide'].discard('REAGENT-%s' % key)
    home('B')
reagent_pour('dev', '3  Arm B pours 12 % developer onto the scale until it reads 40.0 g', 40.0, ['liq2', 'liq3', 'liq4', 'liq5'])
def to_flask(label, arm='A', back=None):
    cap(label)
    pick(arm, 'M', 43.0)
    v0 = list(state['liq'].get('M', []))
    def drain(s):
        state['liq']['M'] = v0 if s < 0.6 else []; state['scale'] = None
    pour(arm, np.array(FUNNEL), 43.0, drain)
    if back is None:
        place(arm, SCALE, 43.0); state['scale'] = 0.0
    else:
        home(arm, 2.5); place(arm, back, 43.0)
    home(arm)
th = math.radians(22.5 + 22.5)
to_flask('4  Arm A pours the measured developer into the flask and returns the beaker to the carousel', back=(CC[0] + 88 * math.cos(th), CC[1] + 88 * math.sin(th), CZ))
# the returned beaker rides the carousel again; the yeast beaker (pocket home 112.5) becomes the tracked one
b = W.beakers.pop('M'); b.name = P1; W.beakers[P1] = b; CARSET[P1] = 22.5; state['hide'].discard('REF-BEAKERS-TT:2+REF-BEAKER:2'); state['liq']['M'] = []
swap_in(P2, 'REF-BEAKERS-TT:2+REF-BEAKER:4')
cam(CAM_AUG)
cap('5  Carousel turns +45 deg: a clean beaker stops under the auger outlet')
turn(67.5, 2.0); wait(0.3)
cap('6  Auger meters 7 g of dry yeast (calibrated revolutions; solids only)')
def aug(s):
    state['auger'] = 900 * s; k = min(4, int(s * 4.999)); state['liq']['M'] = ['yeast%d' % k] if k else []
wait(4.0, aug)
cap('7  Carousel turns -135 deg (slow S-curve) to bring the yeast to arm A')
turn(-67.5, 4.0); wait(0.3)
cam(CAM_MID)
cap('8  Arm A sets the yeast on the scale: reads 7.0 g (closed-loop check)')
del CARSET['M']
pick('A', 'M', 43.0); place('A', SCALE, 43.0); home('A')
wait(1.0, lambda s: state.__setitem__('scale', 7.0 * s))
reagent_pour('water', '9  Arm B adds warm water until the scale reads 37.0 g', 30.0, ['liq1', 'liq2', 'liq3', 'liq4'])
to_flask('10  Arm A pours the activated yeast into the flask')
cam(CAM_OVER)
cap('11  The stage carries the flask out toward the audience')
wait(3.0, lambda s: state.__setitem__('crank', 73.74 * s * s * (3 - 2 * s)))
cap('12  Eruption!')
wait(3.0, lambda s: state.__setitem__('foam', min(8, 1 + int(s * 8))))
wait(1.5)
for f in frames:
    f['hide'] = f['hide']
sweep = np.zeros(SHAPE, bool)
for f in frames[::2]:
    for t in 'AB':
        Pp = W.link_points(t, np.array(f[t])); ij = to_idx(Pp); ok = np.all((ij >= 0) & (ij < SHAPE), axis=1); ij = ij[ok]; sweep[ij[:, 0], ij[:, 1], ij[:, 2]] = True
    for key, D, H in (('b50', 43, 61), ('b100', 56, 74)):
        if f[key] is not None:
            b = Beaker('x', D, H, (0, 0, 0)); b.M = np.array(f[key]); Pp = b.world(); ij = to_idx(Pp); ok = np.all((ij >= 0) & (ij < SHAPE), axis=1); ij = ij[ok]; sweep[ij[:, 0], ij[:, 1], ij[:, 2]] = True
np.save(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'sweep.npy'), ndimage.binary_dilation(sweep, iterations=2))
json.dump({'fps': FPS, 'frames': frames, 'foam_at': (449.9, 102.1, 162.0)}, open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'frames.json'), 'w'))
print('frames', len(frames), '%.1f s' % (len(frames) / FPS))
print('\n'.join(LOG) if LOG else 'no warnings')
# final audit: re-check every 2nd frame, both arms, against scene + other arm + all beakers
bad = []
Wa = World()
for k, b in W.beakers.items(): Wa.beakers[k] = b
for i, f in enumerate(frames):
    if i % 2: continue
    Wa.q['A'] = np.array(f['A']); Wa.q['B'] = np.array(f['B'])
    Wa.beakers = {}
    for k, m in f['beakers'].items():
        D, H = (56, 74) if k in ('R', 'dev', 'soap', 'water') else (43, 61)
        b = Beaker(k, D, H, (0, 0, 0)); b.M = np.array(m); Wa.beakers[k] = b
    for t in 'AB':
        og = Wa.other_grid(t)
        # beakers held by this arm (within 5 mm of the grasp centre) and the one being grasped are allowed to touch the jaws
        ign = tuple(f['ign'][t]) + tuple(k for k in ('M', 'R') if f.get('held_' + t) == k)
        n, why = Wa.collides(t, Wa.q[t], og, ignore=ign, report=True)
        if n: bad.append((i, t, why))
print('audit: %d of %d checked frames have a collision' % (len(set(b[0] for b in bad)), len(frames) // 2))
for b in bad[:25]: print('  frame', b)
