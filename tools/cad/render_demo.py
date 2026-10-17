"""Offline renderer for the Update-13 wet-lab demo (numpy + OpenCV painter's rasteriser, no Fusion).
usage: python render_demo.py timeline   -> builds demo_timeline.pkl from anim_paths.json
       python render_demo.py render N K -> renders frames i where i % K == N
       python render_demo.py encode     -> captions + mp4"""
import sys, os, math, json, pickle
import numpy as np, cv2
sys.path.insert(0, os.path.join(os.path.expanduser('~'), 'fusion_bridge'))
BASE = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
W_, H_ = 1920, 1080; FPS = 20
OUTD = os.path.join(BASE, 'demo_frames'); os.makedirs(OUTD, exist_ok=True)

def lazy():
    global P, L, LF, S, TD, LAY
    import planner as P, layout_lib as L, layout_final as LF, layout_study as S, topdown as TD
    LAY = LF.Lay()

# ------------------------------------------------------------------ camera
EYE = np.array([500.0, -560.0, 980.0]); TGT = np.array([500.0, 470.0, 60.0]); UP = np.array([0, 0, 1.0]); FOV = 40.0
def cam():
    f = TGT - EYE; f /= np.linalg.norm(f); r = np.cross(f, UP); r /= np.linalg.norm(r); u = np.cross(r, f)
    return r, u, f
CR, CU, CF = cam(); FL = (H_ / 2) / math.tan(math.radians(FOV / 2))
LIGHT = np.array([-0.35, -0.55, 0.76]); LIGHT /= np.linalg.norm(LIGHT)
def proj(Pts):
    d = Pts - EYE; z = d @ CF
    return np.c_[W_ / 2 + FL * (d @ CR) / z, H_ / 2 - FL * (d @ CU) / z], z

def shade(T, col):
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]); n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    c = (T.mean(1) - EYE); n = np.where(((n * c).sum(1) > 0)[:, None], -n, n)
    k = 0.38 + 0.62 * np.clip(n @ LIGHT, 0, 1)
    return (np.array(col)[None] * k[:, None]).clip(0, 255)

def raster(img, dep, tris, cols, alpha=None):
    """painter's: draw far->near; dep gets the triangle depth"""
    if len(tris) == 0: return
    uv, z = proj(tris.reshape(-1, 3)); uv = uv.reshape(-1, 3, 2); z = z.reshape(-1, 3)
    ok = (z.min(1) > 10); uv, z, cols = uv[ok], z[ok], cols[ok]
    zm = z.mean(1); order = np.argsort(-zm)
    pts = np.round(uv * 4).astype(np.int32)
    for i in order:
        p = pts[i]
        if p[:, 0].max() < 0 or p[:, 0].min() > W_ * 4 or p[:, 1].max() < 0 or p[:, 1].min() > H_ * 4: continue
        c = cols[i]
        cv2.fillConvexPoly(img, p, (float(c[2]), float(c[1]), float(c[0])), lineType=cv2.LINE_8, shift=2)
        cv2.fillConvexPoly(dep, p, float(zm[i]), shift=2)

def cyl(M, r, h, n=28, cap=True, z0=0.0):
    th = np.linspace(0, 2 * math.pi, n + 1)
    a = np.c_[r * np.cos(th[:-1]), r * np.sin(th[:-1])]; b = np.c_[r * np.cos(th[1:]), r * np.sin(th[1:])]
    T = []
    for (x0, y0), (x1, y1) in zip(a, b):
        T += [[(x0, y0, z0), (x1, y1, z0), (x1, y1, h)], [(x0, y0, z0), (x1, y1, h), (x0, y0, h)]]
        if cap: T.append([(0, 0, h), (x0, y0, h), (x1, y1, h)])
    T = np.array(T, float); T4 = np.c_[T.reshape(-1, 3), np.ones(len(T) * 3)] @ M.T
    return T4[:, :3].reshape(-1, 3, 3)

# ------------------------------------------------------------------ scene
COL = {'frame': (150, 155, 165), 'stage': (90, 160, 110), 'carousel': (70, 120, 200), 'deck': (90, 140, 215), 'scale': (60, 60, 66),
       'pan': (190, 190, 195), 'auger': (210, 120, 60), 'funnel': (215, 215, 225), 'flask': (200, 225, 240), 'arm': (238, 238, 232),
       'arm2': (70, 70, 74), 'finray': (245, 140, 40), 'rack': (150, 110, 190), 'table': (225, 214, 196), 'misc': (120, 120, 130)}
DECK = ('TT-02', 'TT-03', 'TT-04 v4', '25T Al disc horn')
SLED = ('REF-FLASK', 'REF-FUNNEL', 'ST-05', 'REF-WELL', 'REF-BEAKER-MIX', 'REF-ROD')
def colour(n, g):
    if g in ('xrails', 'yrail_L', 'yrail_R', 'e6') or n.startswith(('FRAME', '2020', 'BESSEY')): return COL['frame']
    if n.startswith(('DH-', 'AG-01', 'N20')): return COL['auger']
    if n.startswith('REF-FUNNEL'): return COL['funnel']
    if n.startswith('REF-FLASK'): return COL['flask']
    if g == 'carousel': return COL['deck'] if n.startswith(DECK) else COL['carousel']
    if g == 'scale': return COL['pan'] if n.startswith('WS-02') else COL['scale']
    if g == 'work': return COL['stage']
    return COL['misc']

DECK2 = ('TT-02', 'TT-03', 'TT-04')
SLED2 = ('ST-11', 'ST-05', 'ST-06', 'REF-FLASK', 'REF-FUNNEL', 'REF-WELL', 'REF-ROD')
def colour2(n):
    if n.startswith(('FRAME', '2020', 'BESSEY', 'JG-')): return COL['frame']
    if n.startswith(('DH-', 'PS-01', 'Feetech')): return COL['auger']
    if n.startswith('REF-FUNNEL'): return COL['funnel']
    if n.startswith(('REF-FLASK', 'REF-GRAD')): return COL['flask']
    if n.startswith(DECK2): return COL['deck']
    if n.startswith(('TT-', 'REF-LAZY')): return COL['carousel']
    if n.startswith('WS-02'): return COL['pan']
    if n.startswith(('WS-01', 'Load cell')): return COL['scale']
    if n.startswith(('ST-', 'REF-WELL')): return COL['stage']
    if n.startswith(('RK-',)): return COL['rack']
    return COL['misc']

def build_scene():
    lazy()
    Mu = json.load(open(os.path.join(BASE, 'meshes_u13.json')))
    stat, deck, sled = [], [], []
    stand = None
    for o in Mu['scene']:
        n = o['name']
        if n.startswith(('EISCO', 'REF-BEAKER', 'ANIM-')): continue
        T = np.array(o['tris'], float); cols = shade(T, colour2(n))
        if n.startswith('RK-03'): stand = T if stand is None else np.concatenate([stand, T])
        tgt = deck if n.startswith(DECK2) or (n.startswith('25T') and T.reshape(-1, 3)[:, 0].mean() > 700 and T.reshape(-1, 3)[:, 2].mean() < 60) else (sled if n.startswith(SLED2) else stat)
        tgt.append((T, cols))
    # RK-03 v2 is being rebuilt: only stand #1 is in the export -> copy it to stands #2 and #3
    if stand is not None:
        c1 = np.array(LF.LAY['rack'][0])
        for p in LF.LAY['rack'][1:]:
            T = stand + np.r_[np.array(p) - c1, 0]; stat.append((T, shade(T, COL['rack'])))
    T = np.array([[(-400, -100, -0.5), (1400, -100, -0.5), (1400, 760, -0.5)], [(-400, -100, -0.5), (1400, 760, -0.5), (-400, 760, -0.5)]], float)
    stat.insert(0, (T, np.array([COL['table'], COL['table']], float)))
    for t in 'AB':
        T = np.array(P.M['arms'][t]['L0'], float) + LAY.off(t); stat.append((T, shade(T, COL['arm2'])))
    cat = lambda lst: (np.concatenate([a for a, b in lst]), np.concatenate([b for a, b in lst]))
    return cat(stat), cat(deck), cat(sled)

def build_scene_old():
    lazy()
    G = LAY.group_M(); stat, deck, sled = [], [], []
    for o in P.M['scene']:
        n = o['name']
        if n.startswith(P.SKIP) or n.startswith(('REF-BIN', 'ST-01', 'TL-01', 'RK-02', 'EISCO')): continue
        g = L.group_of(o); c0 = np.array(o['tris']).reshape(-1, 3).mean(0)
        if g == 'fixed' and n.startswith(S.WORK_NAMES[:-1]): g = 'work'
        if n.startswith(('FlashHobby', '25T', 'SHCS ISO 4762 M3x12', 'SHCS ISO 4762 M5x20')) and g == 'fixed' and c0[1] < 260 and c0[0] > 600: g = 'work'
        if n.startswith(('SHCS', 'T-nut')) and 660 < c0[0] < 690 and 270 < c0[1] < 310: continue
        T = np.array(o['tris'], float)
        if n.startswith(LF.AUGER_HEAD) or (n.startswith('SHCS ISO 4762 M3x12') and c0[0] < 100 and c0[2] > 120): T = T + [0, 0, LF.AUGER_RAISE]
        if n.startswith(('AG-01',) + LF.AUGER_HEAD) or (n.startswith('SHCS ISO 4762 M3x12') and c0[0] < 100): T = T + [4.0, 0, 0]
        Mg = G.get(g)
        if Mg is not None: T = (np.c_[T.reshape(-1, 3), np.ones(T.size // 3)] @ Mg.T)[:, :3].reshape(-1, 3, 3)
        cols = shade(T, colour(n, g))
        tgt = sled if (g == 'work' and n.startswith(SLED)) else (deck if (g == 'carousel' and n.startswith(DECK)) else stat)
        tgt.append((T, cols))
    for o in P.M['carousel']:
        if o['name'] in ('REF-BEAKER',) or o['name'].startswith('TT-04'): continue
        T = np.array(o['tris'], float); Mg = G['carousel']
        T = (np.c_[T.reshape(-1, 3), np.ones(T.size // 3)] @ Mg.T)[:, :3].reshape(-1, 3, 3)
        deck.append((T, shade(T, colour(o['name'], 'carousel'))))
    # TT-04 v4 pocket walls (4 pockets, r84) - rotate with the deck
    cc = LAY.cc
    for a in LF.LAY['pockets']:
        c = cc + 84 * np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])
        Mx = np.eye(4); Mx[:3, 3] = (c[0], c[1], 58.6)
        T = cyl(Mx, 30.3, 12.0, n=24, cap=False); deck.append((T, shade(T, COL['deck'])))
    # rack stands (foot r38, column, cup OD 61.6)
    for p in LF.LAY['rack']:
        Mx = np.eye(4); Mx[:3, 3] = (p[0], p[1], 0)
        for r, h, z0 in ((38, 6, 0), (14, 52, 6), (30.8, 70.2, 52)):
            T = cyl(Mx, r, h, n=24, z0=z0); stat.append((T, shade(T, COL['rack'])))
    # table top
    T = np.array([[(-300, -100, -0.5), (1400, -100, -0.5), (1400, 760, -0.5)], [(-300, -100, -0.5), (1400, 760, -0.5), (-300, 760, -0.5)]], float)
    stat.insert(0, (T, np.array([COL['table'], COL['table']], float)))
    # arm bases (static)
    for t in 'AB':
        T = np.array(P.M['arms'][t]['L0'], float) + LAY.off(t); stat.append((T, shade(T, COL['arm2'])))
    cat = lambda lst: (np.concatenate([a for a, b in lst]), np.concatenate([b for a, b in lst]))
    return cat(stat), cat(deck), cat(sled)

ARMCOL = {'L1': 'arm2', 'L2': 'arm', 'L3': 'arm', 'L4': 'arm2', 'L5': 'finray', 'L6': 'finray'}
def arm_tris(t, q, q6, ARMT):
    arm = P.GRASP[t].arm; out_T, out_C = [], []
    qq = np.r_[q[:5], q6]
    for k, lk in enumerate(('L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6')):
        if lk == 'L0': continue
        n = min(k, 5) if lk != 'L6' else 5
        Mx = arm.chain(qq, n)
        if lk == 'L6': Mx = Mx @ P.T(arm.axes[5][0], arm.axes[5][1], qq[5])
        T, base = ARMT[t][lk]
        Tw = (np.c_[T.reshape(-1, 3), np.ones(T.size // 3)] @ Mx.T)[:, :3].reshape(-1, 3, 3) + LAY.off(t)
        out_T.append(Tw); out_C.append(shade(Tw, COL[ARMCOL[lk]]))
    return out_T, out_C

LIQ = {'dev': (60, 120, 230), 'water': (120, 190, 240), 'soap': (230, 80, 160), 'yeast': (205, 170, 90), 'mix': (150, 110, 200)}
def beaker_tris(Mb, level, liq):
    g = cyl(Mb, 28.0, 74.0, n=28, cap=False); gb = cyl(Mb, 28.0, 1.5, n=28, cap=True)
    lt, lc = None, None
    if level > 0.5:
        lt = cyl(Mb, 26.5, max(1.0, level), n=24, cap=True, z0=1.5); lc = shade(lt, LIQ.get(liq, LIQ['mix']))
    return np.concatenate([g, gb]), lt, lc

# ------------------------------------------------------------------ timeline
def timeline():
    lazy()
    A = json.load(open(os.path.join(BASE, 'anim_paths.json')))
    st = {s['step']: s for s in A['steps']}
    park = {t: np.array(A['park'][t]) for t in 'AB'}; OPN = A['open']; CLS = A['close']
    frames = []
    q = {t: park[t].copy() for t in 'AB'}; q6 = {t: OPN[t] for t in 'AB'}
    held = {'A': None, 'B': None}
    cc = LAY.cc; pick_a = LF.LAY['pick_deg']
    bk = {}   # name -> dict(M or attach, level, liq, tt (carousel pocket rel angle or None))
    def pocket_xy(rel):        # rel = pocket angle in world when tt=0
        return cc + 84 * np.array([math.cos(math.radians(rel)), math.sin(math.radians(rel))])
    tt = [0.0]
    car_home = {'P1': 220.6, 'P2': 130.6}
    for k, a in car_home.items(): bk[k] = dict(car=a, level=0.0, liq='mix')
    for i, (nm, liq) in enumerate((('dev', 'dev'), ('soap', 'soap'), ('water', 'water'))):
        Mx = np.eye(4); Mx[:3, 3] = (*LF.LAY['rack'][i], LF.LAY['rack_floor']); bk[nm] = dict(M=Mx, level=50.0, liq=liq)
    cap = ['']; scale = [None]; extra = {'stage': 0.0, 'foam': 0.0, 'auger': 0.0, 'stream': None}
    def bstate():
        out = {}
        for k, b in bk.items():
            if 'car' in b:
                a = b['car'] + tt[0]; Mx = np.eye(4); Mx[:3, 3] = (*pocket_xy(a), LF.CAR_Z); out[k] = (Mx, b['level'], b['liq'])
            elif 'att' in b:
                t, Mrel = b['att']; Mc = P.GRASP[t].arm.chain(np.r_[q[t][:5], 0], 5) @ Mrel; Mc = Mc.copy(); Mc[:3, 3] += LAY.off(t)
                out[k] = (Mc, b['level'], b['liq'])
            else: out[k] = (b['M'], b['level'], b['liq'])
        return out
    def snap(n=1):
        for _ in range(n):
            frames.append(dict(q={t: q[t].copy() for t in 'AB'}, q6=dict(q6), tt=tt[0], bk=bstate(), cap=cap[0], scale=scale[0], **{k: v for k, v in extra.items()}))
    def move(t, path, deg_per_frame=3.0, fn=None):
        path = [np.array(p) for p in path]
        seq = []
        for a, b in zip(path[:-1], path[1:]):
            n = max(1, int(math.ceil(np.degrees(np.abs(b - a).max()) / deg_per_frame)))
            seq += [a + (b - a) * (k / n) for k in range(1, n + 1)]
        for i, qq in enumerate(seq):
            q[t] = qq
            if fn: fn((i + 1) / len(seq))
            snap()
    def grip(t, val, n=8):
        a = q6[t]
        for k in range(1, n + 1): q6[t] = a + (val - a) * k / n; snap()
    def attach(t, name, held_kind, gh):
        Mw = bstate()[name][0]
        Mrel = np.linalg.inv(P.GRASP[t].arm.chain(np.r_[q[t][:5], 0], 5) @ np.eye(4)) @ (Mw - np.r_[[0, 0, 0, 0]] * 0 - np.pad(LAY.off(t)[:, None], ((0, 1), (3, 0))))
        bk[name] = dict(att=(t, Mrel), level=bk[name]['level'], liq=bk[name]['liq'])
    def release(name):
        Mw = bstate()[name][0]; bk[name] = dict(M=Mw.copy(), level=bk[name]['level'], liq=bk[name]['liq'])
    def turn(to, secs):
        a0 = tt[0]; n = int(secs * FPS)
        for k in range(1, n + 1):
            u = k / n; s = u * u * (3 - 2 * u); tt[0] = a0 + (to - a0) * s; snap()
    def park_to_car(name):
        b = bk[name]; Mw = b['M']; a = math.degrees(math.atan2(Mw[1, 3] - cc[1], Mw[0, 3] - cc[0])) - tt[0]
        bk[name] = dict(car=a, level=b['level'], liq=b['liq'])
    def transfer(rec, name, cap_txt, to_carousel=False):
        cap[0] = cap_txt
        ap, carry, back = [p['qs'] for p in rec['anim_paths'][1:2]] + [rec['anim_paths'][0]['qs']] + [rec['anim_paths'][2]['qs']]
        t = 'B'
        move(t, ap); grip(t, CLS[t])
        if name in bk and 'car' in bk[name]:
            Mw = bstate()[name][0]; bk[name] = dict(M=Mw, level=bk[name]['level'], liq=bk[name]['liq'])
        Mw = bstate()[name][0]; Mc = P.GRASP[t].arm.chain(np.r_[q[t][:5], 0], 5); Mc = Mc.copy(); Mc[:3, 3] += LAY.off(t)
        bk[name] = dict(att=(t, np.linalg.inv(Mc) @ Mw), level=bk[name]['level'], liq=bk[name]['liq'])
        move(t, carry, 2.5)
        release(name)
        if to_carousel: park_to_car(name)
        grip(t, OPN[t]); move(t, back)
    def pour(rec, name, recv, cap_a, cap_b, cap_c, grams_from, grams_to, level_to_recv, final_recv_liq=None, return_xy=None):
        t = 'A'
        ap = rec['anim_paths'][3]['qs']; carry = rec['anim_paths'][0]['qs']; tin = rec['anim_paths'][1]['qs']; man = rec['anim_paths'][2]['qs']
        cap[0] = cap_a; move(t, ap); grip(t, CLS[t])
        if name in ('P1', 'P2'): scale[0] = 0.0
        Mw = bstate()[name][0]; Mc = P.GRASP[t].arm.chain(np.r_[q[t][:5], 0], 5).copy(); Mc[:3, 3] += LAY.off(t)
        bk[name] = dict(att=(t, np.linalg.inv(Mc) @ Mw), level=bk[name]['level'], liq=bk[name]['liq'])
        move(t, carry, 2.5); move(t, tin, 2.0)
        cap[0] = cap_b; lv0 = bk[name]['level']; rv0 = bk[recv]['level'] if recv in bk else 0.0
        def fl(u):
            bk[name]['level'] = lv0 * (1 - u)
            if recv in bk: bk[recv]['level'] = rv0 + (level_to_recv - rv0) * u
            if final_recv_liq and recv in bk and u > 0.3: bk[recv]['liq'] = final_recv_liq
            if grams_from is not None: scale[0] = grams_from + (grams_to - grams_from) * u
            Mb = bstate()[name][0]; ax = Mb[:3, 2]; lip = Mb[:3, 3] + 74 * ax
            extra['stream'] = lip.tolist() if u < 0.98 else None
        move(t, man, 1.2, fl); snap(int(1.2 * FPS)); extra['stream'] = None
        cap[0] = cap_c
        move(t, man[::-1], 3.0); move(t, tin[::-1], 2.5); move(t, carry[::-1], 2.5)
        release(name); grip(t, OPN[t]); move(t, ap[::-1])
    # ---------------- storyboard
    cap[0] = 'Wet Lab Bench: elephant toothpaste demo (Update 13 layout). Soap + dye pre-loaded in REF-FLASK-250 under the funnel'; snap(int(2.5 * FPS))
    cap[0] = 'Carousel: M45CHW servo turns TT-02 deck on TT-01 (lazy Susan); TT-04 v4 brings empty beaker P1 to the pick pocket'
    turn(0.0, 1.5)
    transfer(st['T1'], 'P1', 'Step 1  Transfer arm (east, SO-101 + GR-01/02/03 fin-ray, top-down grip): P1 TT-04 v4 -> WS-02 pan; WS-01 load cell tares 0.0 g')
    scale[0] = 0.0; snap(int(0.8 * FPS))
    pour(st['P_dev'], 'dev', 'P1', 'Step 2a  Pourer (west, side grip GRIP_H 40): lifts 12 % developer beaker from reagent stand RK-03 #1',
         'Step 2b  Pourer roll-pours developer into P1 on WS-02: load cell + HX711 closed loop stops at 40.0 g',
         'Step 2c  Pourer returns the developer beaker to RK-03 #1 and parks', 0.0, 40.0, 42.0)
    pour(st['P_fun'], 'P1', 'FUNNEL', 'Step 3a  Pourer picks P1 (40 g developer) off WS-02 (GRIP_H 30); scale reads 0 g removal check',
         'Step 3b  Pourer tilts P1 over REF-FUNNEL-EISCO4 (lip 65 mm above rim): developer into REF-FLASK-250 on ST-11 sled',
         'Step 3c  Pourer sets empty P1 back on WS-02 and parks', None, None, 0.0)
    scale[0] = 0.0
    transfer(st['T2'], 'P1', 'Step 4  Transfer arm (top-down): empty P1 WS-02 -> TT-04 v4 pick pocket', to_carousel=True)
    scale[0] = None
    cap[0] = 'Carousel: M45CHW turns TT-02 -90 deg: clean beaker P2 stops under DH-01 auger head (PS-01 stand, +25 mm)'
    turn(-90.0, 2.0)
    cap[0] = 'Auger: FB5311M-360 servo turns DH-02 screw in DH-01: commanded revs -> 7 g dry yeast (verified on WS-02 in step 5)'
    n = int(3.0 * FPS)
    for k in range(n): bk['P2']['level'] = 8.0 * (k + 1) / n; bk['P2']['liq'] = 'yeast'; extra['auger'] = k * 30.0; snap()
    cap[0] = 'Carousel: M45CHW turns TT-02 +180 deg (S-curve): P2 with yeast to the pick pocket'
    turn(90.0, 3.0)
    transfer(st['T1'], 'P2', 'Step 5  Transfer arm (top-down): P2 TT-04 v4 -> WS-02; load cell + HX711 confirm 7.0 g yeast')
    scale[0] = 7.0; snap(int(0.8 * FPS))
    pour(st['P_wat'], 'water', 'P2', 'Step 6a  Pourer lifts the warm-water beaker from reagent stand RK-03 #3',
         'Step 6b  Pourer roll-pours warm water onto the yeast in P2: load cell closed loop stops at 37.0 g',
         'Step 6c  Pourer returns the water beaker to RK-03 #3 and parks', 7.0, 37.0, 38.0, final_recv_liq='yeast')
    pour(st['P_fun'], 'P2', 'FUNNEL', 'Step 7a  Pourer picks activated yeast P2 off WS-02 (GRIP_H 30)',
         'Step 7b  Pourer pours the yeast through REF-FUNNEL-EISCO4 into REF-FLASK-250 (soap, dye, developer inside)',
         'Step 7c  Pourer sets empty P2 back on WS-02 and parks', None, None, 0.0)
    scale[0] = 0.0
    transfer(st['T2'], 'P2', 'Step 8  Transfer arm (top-down): empty P2 WS-02 -> TT-04 v4; both arms park', to_carousel=True)
    scale[0] = None
    cap[0] = 'Stage: M45CHW servo on ST-12 bridge turns ST-13 crank; ST-14 rod slides ST-11 sled on S1/S2 rails from WORK to ERUPT'
    n = int(3.0 * FPS)
    for k in range(n): u = (k + 1) / n; extra['stage'] = u * u * (3 - 2 * u); snap()
    cap[0] = 'Eruption! Foam rises from REF-FLASK-250 in the ST-05 collar on the ST-11 sled; overflow into the ST-07 catch well'
    n = int(4.0 * FPS)
    for k in range(n): extra['foam'] = (k + 1) / n; snap()
    snap(int(1.5 * FPS))
    pickle.dump(frames, open(os.path.join(BASE, 'demo_timeline.pkl'), 'wb'))
    print('frames', len(frames), '%.1f s' % (len(frames) / FPS))

# ------------------------------------------------------------------ render
def render(N, K):
    lazy()
    frames = pickle.load(open(os.path.join(BASE, 'demo_timeline.pkl'), 'rb'))
    (ST, SC), (DT, DC), (WT, WC) = build_scene()
    # static layer once
    simg = np.zeros((H_, W_, 3), np.uint8); simg[:] = (250, 247, 244); sdep = np.full((H_, W_), 1e9, np.float32)
    raster(simg, sdep, ST[:2], SC[:2]); raster(simg, sdep, ST[2:], SC[2:])
    ARMT = {t: {lk: (np.array(P.M['arms'][t][lk], float), None) for lk in ('L1', 'L2', 'L3', 'L4', 'L5', 'L6')} for t in 'AB'}
    cc = LAY.cc
    for i in range(N, len(frames), K):
        out = os.path.join(OUTD, 'f%05d.png' % i)
        if os.path.exists(out): continue
        f = frames[i]
        Ts, Cs = [], []
        for t in 'AB':
            a, b = arm_tris(t, np.array(f['q'][t]), f['q6'][t], ARMT); Ts += a; Cs += b
        R = np.eye(4); c, s = math.cos(math.radians(f['tt'])), math.sin(math.radians(f['tt']))
        R[:2, :2] = [[c, -s], [s, c]]; R[:2, 3] = cc - R[:2, :2] @ cc
        Td = (np.c_[DT.reshape(-1, 3), np.ones(DT.size // 3)] @ R.T)[:, :3].reshape(-1, 3, 3); Ts.append(Td); Cs.append(shade(Td, COL['deck']))
        sy = -100.0 * f['stage']
        Ts.append(WT + [0, sy, 0]); Cs.append(WC)
        glass = []
        for name, (Mb, lvl, liq) in f['bk'].items():
            g, lt, lc = beaker_tris(np.array(Mb), lvl, liq); glass.append(g)
            if lt is not None: Ts.append(lt); Cs.append(lc)
        if f['foam'] > 0:
            Mx = np.eye(4); Mx[:3, 3] = (450.0, 282.0 + sy, 160.0)
            for kk in range(6):
                rr = 18 + 30 * f['foam'] * (1 - kk / 8); h = 20 + 140 * f['foam'] * (kk + 1) / 6
                T = cyl(Mx, rr, h, n=20, z0=h - 25); Ts.append(T); Cs.append(shade(T, (250, 240, 120)))
        T = np.concatenate(Ts); C = np.concatenate(Cs)
        dimg = simg.copy(); ddep = sdep.copy()
        # draw dynamic into a separate layer then composite by depth
        lay_img = np.zeros_like(simg); lay_dep = np.full_like(sdep, 1e9)
        raster(lay_img, lay_dep, T, C)
        m = lay_dep < sdep; dimg[m] = lay_img[m]; ddep[m] = lay_dep[m]
        # glass: translucent overlay
        if glass:
            G = np.concatenate(glass); gimg = np.zeros_like(simg); gdep = np.full_like(sdep, 1e9)
            raster(gimg, gdep, G, shade(G, (200, 225, 245)))
            m = gdep < ddep + 0.5
            dimg[m] = (0.62 * dimg[m] + 0.38 * gimg[m]).astype(np.uint8)
            edge = cv2.morphologyEx((gdep < 1e8).astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
            dimg[edge & m] = (120, 140, 160)
        if f['stream'] is not None:
            lip = np.array(f['stream']); pts = np.array([lip, lip - [0, 0, 60]])
            uv, z = proj(pts); cv2.line(dimg, tuple(np.int32(uv[0])), tuple(np.int32(uv[1])), (220, 150, 80), 5, cv2.LINE_AA)
        cv2.imwrite(out, dimg)
        print(i, flush=True)

def encode():
    from PIL import Image, ImageDraw, ImageFont
    import subprocess
    frames = pickle.load(open(os.path.join(BASE, 'demo_timeline.pkl'), 'rb'))
    CAPD = os.path.join(BASE, 'demo_cap'); os.makedirs(CAPD, exist_ok=True)
    def font(sz):
        for f in ('segoeuib.ttf', 'arialbd.ttf'):
            try: return ImageFont.truetype(f, sz)
            except Exception: pass
        return ImageFont.load_default()
    F1, F2 = font(28), font(40)
    for i, f in enumerate(frames):
        im = Image.open(os.path.join(OUTD, 'f%05d.png' % i)).convert('RGB'); d = ImageDraw.Draw(im, 'RGBA')
        d.rectangle([0, 0, im.width, 60], fill=(20, 24, 32, 220)); d.text((24, 14), f['cap'], font=F1, fill=(255, 255, 255))
        if f['scale'] is not None:
            txt = 'WS-01 / HX711  %5.1f g' % f['scale']; w = d.textlength(txt, font=F2)
            d.rounded_rectangle([im.width - w - 50, im.height - 78, im.width - 18, im.height - 18], 10, fill=(10, 60, 30, 230))
            d.text((im.width - w - 34, im.height - 73), txt, font=F2, fill=(120, 255, 160))
        im.save(os.path.join(CAPD, 'f%05d.png' % i))
    ff = r"C:\Program Files\Shutter Encoder\Library\ffmpeg.exe"
    out = os.path.join(os.path.expanduser('~'), 'Downloads', 'wet_lab_demo_FINAL.mp4')
    subprocess.run([ff, '-y', '-framerate', str(FPS), '-i', os.path.join(CAPD, 'f%05d.png'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', out], check=True, capture_output=True)
    print('wrote', out, os.path.getsize(out) // 1024, 'KB')

if __name__ == '__main__':
    if sys.argv[1] == 'timeline': timeline()
    elif sys.argv[1] == 'render': render(int(sys.argv[2]), int(sys.argv[3]))
    elif sys.argv[1] == 'encode': encode()
