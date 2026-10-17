"""Fin-ray gripper layout in the grip plane (x = e1, y = e2, hinge at origin; z = coordinate along the hinge g)."""
import numpy as np, math, json, os
d2r = math.radians
def R(a): c, s = math.cos(a), math.sin(a); return np.array([[c, -s], [s, c]])
PHI = 25.0            # fixed contact line direction (deg)
B_F = np.array([46.2, -18.2])   # fixed finger base, contact-side corner
L, W, BLK = 65.0, 24.0, 12.0    # finger length, base width, base block depth
Z0, Z1 = -36.0, -2.0            # finger extent along the hinge
TZ0, TZ1 = -21.5, -16.5         # tongue (PLA) slab
BZ0, BZ1 = -30.0, -8.0          # bridge slab
BETA43, QC43 = 12.5, -60.0      # bisector and contact angle for the 43 mm beaker
SQUEEZE = 4.0                   # extra servo travel past contact (fin-ray wrap), firmware only
d = np.array([math.cos(d2r(PHI)), math.sin(d2r(PHI))]); nb = np.array([math.sin(d2r(PHI)), -math.cos(d2r(PHI))])  # nb: toward the back
def finger_local():
    """finger in (u along contact, v toward back) coordinates"""
    tri = [(0, 0), (L, 0), (0, W)]
    blk = [(-BLK, 0), (0, 0), (0, W), (-BLK, W)]
    # ribs: from contact wall to back wall, leaning 15 deg toward the base
    ribs = []
    for u in np.arange(10, L - 8, 9.0):
        vb = W * (1 - u / L)            # back wall height at u
        ribs.append(((u, 0), (u - math.tan(d2r(15)) * vb, vb)))
    return tri, blk, ribs
def to_fixed(P): P = np.atleast_2d(P); return B_F + P[:, :1] * d + P[:, 1:] * nb
def mirror(P, beta):
    a = d2r(beta); M = np.array([[math.cos(2 * a), math.sin(2 * a)], [math.sin(2 * a), -math.cos(2 * a)]]); return np.atleast_2d(P) @ M.T
def to_moving_q0(P):
    """moving finger at q = 0: mirror the fixed layout about the 43 mm bisector, then undo the closing rotation"""
    return mirror(to_fixed(P), BETA43) @ R(-d2r(QC43)).T
def centre(D, beta):
    """beaker centre on the bisector touching the fixed contact line"""
    off = -float(np.cross(d, -B_F))     # signed distance of the hinge from the contact line (inner side +)
    n_in = np.array([-math.sin(d2r(PHI)), math.cos(d2r(PHI))]); off = float(n_in @ (np.zeros(2) - B_F))
    s = (off - D / 2) / -math.sin(d2r(beta - PHI)); return s * np.array([math.cos(d2r(beta)), math.sin(d2r(beta))]), off
def design():
    out = {'PHI': PHI, 'B_F': B_F.tolist(), 'L': L, 'W': W, 'BLK': BLK, 'Z': [Z0, Z1], 'TZ': [TZ0, TZ1], 'BZ': [BZ0, BZ1], 'SQUEEZE': SQUEEZE, 'grip': {}}
    off = centre(43, BETA43)[1]
    for D in (43.0, 56.0):
        # choose the bisector so the beaker clears the palm by >= 45 mm (43) / 47 mm (56)
        if D == 43.0: beta = BETA43
        else:
            s_need = 47 + D / 2; beta = PHI - math.degrees(math.asin((off - D / 2) / s_need))
        c, _ = centre(D, beta)
        q = QC43 + 2 * (beta - BETA43)      # moving contact line rotates twice the bisector change
        out['grip'][str(int(D))] = {'beta': beta, 'q_contact': q, 'q_open': q + 14.0, 'centre2d': c.tolist(),
                                    'clear_palm': float(np.linalg.norm(c) - D / 2), 'contact_u': float(d @ (c - B_F))}
    tri, blk, ribs = finger_local()
    out['tri'], out['blk'], out['ribs'] = tri, blk, [list(map(list, r)) for r in ribs]
    return out
if __name__ == '__main__':
    o = design(); json.dump(o, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gripper_design.json'), 'w'), indent=1)
    for k, g in o['grip'].items(): print(k, {a: (round(b, 1) if isinstance(b, float) else [round(x, 1) for x in b]) for a, b in g.items()})
    print('hinge offset from fixed contact line %.1f' % centre(43, BETA43)[1])
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    from grasp_model import Grasp
    G = Grasp('A')
    def pl(P): v = P - G.gp; z = v @ G.g; m = (z > -30) & (z < -8); return np.c_[v[m] @ G.e1, v[m] @ G.e2]
    fig, axs = plt.subplots(1, 3, figsize=(21, 7))
    tri, blk, ribs = finger_local()
    for ax, (title, D) in zip(axs, (('open (q=0)', None), ('43 mm beaker', 43), ('56 mm beaker', 56))):
        F = pl(G.fj); F = F[F[:, 0] < 30]; ax.scatter(F[:, 0], F[:, 1], s=0.2, c='0.6')
        q = 0 if D is None else o['grip'][str(D)]['q_contact']
        Mj = pl(G.moving(d2r(q))); r = np.hypot(Mj[:, 0], Mj[:, 1]); Mj = Mj[r < 24]; ax.scatter(Mj[:, 0], Mj[:, 1], s=0.2, c='0.6')
        for poly, c in ((tri, 'tab:orange'), (blk, 'tab:red')):
            P = to_fixed(np.array(poly)); ax.fill(P[:, 0], P[:, 1], alpha=0.35, color=c)
            P = to_moving_q0(np.array(poly)) @ R(d2r(q)).T; ax.fill(P[:, 0], P[:, 1], alpha=0.35, color=c)
        for a, b in ribs:
            P = to_fixed(np.array([a, b])); ax.plot(P[:, 0], P[:, 1], 'k', lw=0.8)
            P = to_moving_q0(np.array([a, b])) @ R(d2r(q)).T; ax.plot(P[:, 0], P[:, 1], 'k', lw=0.8)
        if D:
            c = o['grip'][str(D)]['centre2d']; ax.add_patch(plt.Circle(c, D / 2, fill=False, color='g', lw=2))
        ax.plot(0, 0, 'k+', ms=20); ax.set_aspect('equal'); ax.grid(); ax.set_title(title + ('' if D is None else '  q=%.1f' % q)); ax.set_xlim(-60, 120); ax.set_ylim(-60, 100)
    fig.savefig('gripper2d.png', dpi=70)
