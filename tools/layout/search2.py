import numpy as np, math, json
rng = np.random.default_rng(7)
def d(a, b): return float(np.hypot(*(np.array(a, float) - np.array(b, float))))
def bearing_ok(base, p, lim=100):
    v = np.array(p) - base; return abs(math.degrees(math.atan2(v[0], -v[1]))) <= lim
def rect_clear(p, r, R): return not (R[0] - r < p[0] < R[2] + r and R[1] - r < p[1] < R[3] + r)
TABLE = (-200, -30, 1630, 730)
def on_table(p, r): return TABLE[0] + r < p[0] < TABLE[2] - r and TABLE[1] + r < p[1] < TABLE[3] - r
out = []
for it in range(3_000_000):
    ya = 525.7 if rng.random() < 0.5 else 599.7
    xr = (ya - 525.7)                       # X rails move with ya
    rails = [(245, 290, 265, 690), (665, 270, 685, 670), (265, 498 + xr, 665, 518 + xr), (265, 568 + xr, 665, 588 + xr)]
    dy = rng.uniform(-60, 40)
    stage = (350, 30 + dy, 550, 450 + dy)
    obst = rails + [stage]
    xa, xb = rng.uniform(310, 620, 2)
    if abs(xa - xb) < 200: continue
    A = np.array([xa, ya]); B = np.array([xb, ya]); F = np.array([450, 282 + dy])
    if not (300 <= d(B, F) <= 335 and bearing_ok(B, F)): continue
    th = rng.uniform(-math.pi, math.pi); S = B + 285 * np.array([math.cos(th), math.sin(th)])
    if not (185 <= d(A, S) <= 290 and bearing_ok(A, S) and bearing_ok(B, S) and on_table(S, 45)): continue
    if not all(rect_clear(S, 45, R) for R in obst): continue
    ph = rng.uniform(-math.pi, math.pi); P = A + rng.uniform(190, 285) * np.array([math.cos(ph), math.sin(ph)])
    if not bearing_ok(A, P): continue
    u = rng.uniform(-math.pi, math.pi); uv = np.array([math.cos(u), math.sin(u)]); Cc = P - 84 * uv
    AUG = Cc - 84 * uv; AUGX = Cc - 200 * uv          # auger head + post reach ~115 beyond the auger pocket
    if not (on_table(Cc, 122) and on_table(AUGX, 30)): continue
    if not all(rect_clear(Cc, 122, R) and rect_clear(AUGX, 40, R) for R in obst): continue
    if d(Cc, S) < 122 + 50 or d(AUGX, S) < 90 or d(Cc, A) < 122 + 70 or d(Cc, B) < 122 + 70 or d(AUGX, A) < 150 or d(AUGX, B) < 150: continue
    ok = False
    for k in range(40):
        t0 = rng.uniform(-math.pi, math.pi); sgn = rng.choice([-1, 1])
        pts = [B + 290 * np.array([math.cos(t0 + sgn * j * 0.27), math.sin(t0 + sgn * j * 0.27)]) for j in range(3)]
        if all(bearing_ok(B, q) and on_table(q, 40) and all(rect_clear(q, 40, R) for R in obst) and d(q, S) > 95 and d(q, Cc) > 170 and d(q, AUGX) > 90 and d(q, A) > 140 for q in pts):
            ok = True; break
    if not ok: continue
    sc = -abs(d(A, S) - 240) - abs(d(A, P) - 240) - abs(d(B, F) - 318) - 0.3 * abs(dy)
    out.append((sc, dict(ya=ya, A=A.round(1).tolist(), B=B.round(1).tolist(), stage_dy=round(dy, 1), F=F.round(1).tolist(), S=S.round(1).tolist(),
                        C=Cc.round(1).tolist(), pick=P.round(1).tolist(), auger_pocket=AUG.round(1).tolist(), rack=[q.round(1).tolist() for q in pts],
                        dAS=round(d(A, S)), dAP=round(d(A, P)), dBF=round(d(B, F)), dBR=290, dBS=285)))
out.sort(key=lambda x: -x[0]); print(len(out), 'feasible')
for s, b in out[:6]: print(round(s), b)
json.dump([b for s, b in out[:30]], open('cands2.json', 'w'), indent=1)
