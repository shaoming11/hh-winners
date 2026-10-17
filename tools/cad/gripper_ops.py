import json, math, numpy as np, os
from gripper_design import *
F = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grip_frames.json')))
TC, TB, TR = 1.6, 1.8, 1.2       # contact wall, back wall, rib thickness (TPU)
SL = 0.25                         # slot clearance per side (TPU over PLA tongue)
HOLES = [(-6.0, 7.0), (-6.0, 17.0)]
def finger_polys():
    k = math.sqrt(1 + (W / L) ** 2)
    contact = [(0, 0), (L, 0), (L * (1 - TC / W), TC), (0, TC)]
    back = [(0, W), (L, 0), (L * (1 - TB * k / W), 0), (0, W - TB * k)]
    ribs = []
    for u in np.arange(10, L - 8, 9.0):
        vb = W * (1 - u / L) - 0.5; t = math.tan(d2r(15))
        ribs.append([(u - TR / 2, 0.5), (u + TR / 2, 0.5), (u + TR / 2 - t * vb, vb), (u - TR / 2 - t * vb, vb)])
    blk = [(-BLK, 0), (0.5, 0), (0.5, W), (-BLK, W)]
    return contact, back, ribs, blk
def tongue(pad=0.0):
    return [(-BLK - 0.01 - (8 if pad == 0 else 0), 2.0 - pad), (-1.5 + pad, 2.0 - pad), (-1.5 + pad, W - 2.0 + pad), (-BLK - 0.01 - (8 if pad == 0 else 0), W - 2.0 + pad)]
def hexagon(c, af=5.7):
    r = af / math.sqrt(3); return [(c[0] + r * math.cos(d2r(30 + 60 * i)), c[1] + r * math.sin(d2r(30 + 60 * i))) for i in range(6)]
def circ(c, r, n=24): return [(c[0] + r * math.cos(2 * math.pi * i / n), c[1] + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
def build(tag):
    fr = F[tag]; gp = np.array(fr['gp']); e1 = np.array(fr['e1']); e2 = np.array(fr['e2'])
    def W3(P2): return [[float((gp + p[0] * e1 + p[1] * e2)[1]), float((gp + p[0] * e1 + p[1] * e2)[2])] for p in P2]
    def X(z): return float(gp[0] - z)           # g = -x
    def op(kind, P2, z0, z1, **kw): d = {'op': kind, 'poly': W3(P2), 'x0': X(z1), 'x1': X(z0)}; d.update(kw); return d
    parts = []
    contact, back, ribs, blk = finger_polys()
    for side, place, head_hi in (('fixed', lambda P: to_fixed(np.array(P, float)), True), ('moving', lambda P: to_moving_q0(np.array(P, float)), False)):
        ops = [op('new', place(blk), Z0, Z1), op('join', place(contact), Z0, Z1), op('join', place(back), Z0, Z1)]
        ops += [op('join', place(r), Z0, Z1) for r in ribs]
        ops.append(op('cut', place(tongue(SL)), TZ0 - SL, TZ1 + SL))
        for h in HOLES:
            ops.append(op('cut', place(circ(h, 1.6)), Z0 - 1, Z1 + 1))
            if head_hi: ops += [op('cut', place(circ(h, 3.25)), -11.0, Z1 + 1), op('cut', place(hexagon(h)), Z0 - 1, -24.0)]
            else: ops += [op('cut', place(circ(h, 3.25)), Z0 - 1, -27.0), op('cut', place(hexagon(h)), -14.0, Z1 + 1)]
        parts.append({'name': 'GR-03 fin-ray finger TPU (%s %s)' % (tag, side), 'copy': None, 'ops': ops, 'mat': 'TPU'})
    # GR-01: follower with the fixed finger removed, bridge + tongue
    ops = [op('cut', [(30, -80), (160, -80), (160, 80), (30, 80)], -60, 30)]
    bf = [(22, -23), tuple(to_fixed(np.array([[-BLK, 0]]))[0]), tuple(to_fixed(np.array([[-BLK, W]]))[0]), (26, -50)]
    ops.append(op('join', bf, BZ0, BZ1))
    ops.append(op('join', to_fixed(np.array(tongue()[:2] + tongue()[2:], float)), TZ0, TZ1))
    for h in HOLES: ops.append(op('cut', to_fixed(np.array(circ(h, 1.7))), TZ0 - 1, TZ1 + 1))
    parts.append({'name': 'GR-01 gripper body (%s)' % tag, 'copy': 'Wrist_Roll_Follower', 'ops': ops, 'mat': 'PLA (FDM)'})
    # GR-02: stock moving-jaw hub (r < 24) + arm + tongue
    ring = {'op': 'cutring', 'c': W3([(0, 0)])[0], 'r': 24.0, 'x0': X(30), 'x1': X(-60)}
    bm = [(4, 14), tuple(to_moving_q0(np.array([[-BLK, 0]]))[0]), tuple(to_moving_q0(np.array([[-BLK, W]]))[0]), (-13, 9)]
    ops = [ring, op('join', bm, BZ0, BZ1), op('join', to_moving_q0(np.array(tongue(), float)), TZ0, TZ1)]
    for h in HOLES: ops.append(op('cut', to_moving_q0(np.array(circ(h, 1.7))), TZ0 - 1, TZ1 + 1))
    parts.append({'name': 'GR-02 moving jaw (%s)' % tag, 'copy': 'Moving_Jaw', 'ops': ops, 'mat': 'PLA (FDM)'})
    return parts
if __name__ == '__main__':
    out = {t: build(t) for t in 'AB'}
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gripper_ops.json'), 'w'))
    print({t: [(p['name'], len(p['ops'])) for p in v] for t, v in out.items()})
