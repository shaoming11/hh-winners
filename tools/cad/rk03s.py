"""Loose-station parts (no purchase): RK-03 free-standing reagent rack (3 x 100 mL on an arc r290 about the pouring arm),
SF-01 scale foot (printed 2020 stub that WS-01's saddle bolts onto with 2 x M4x20 into captured M4 nuts / T-nuts)."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
PLA = design.materials.itemByName('PLA (FDM)')
# ---------------- RK-03 (staged at a virtual arm base (1300, 650), pockets facing it) ----------------
AX0, AY0, R = 1300.0, 650.0, 290.0
ZF = 60.2                           # beaker bottom (planner value)
angs = [0.0]
P = [(AX0 + R * math.sin(math.radians(a)), AY0 - R * math.cos(math.radians(a))) for a in angs]
rk = Part('RK-03 reagent stand (x3, free-standing)', (P[0][0], P[0][1], 0))
for i, (x, y) in enumerate(P):
    rk.cyl(x, y, 0, 3.0, 38.0)                       # foot disk (VHB to the table)
    rk.cyl(x, y, 0, ZF, 30.8)                        # column (cavity cut below)
    rk.cyl(x, y, ZF, ZF + 12.0, 30.8, JOIN, 28.3)    # locating wall ID 56.6 x 12
    if i < len(P) - 1:                               # web to the next column (built before it, so everything joins one body)
        x1, y1 = P[i + 1]; L = math.hypot(x1 - x, y1 - y); ux, uy = (x1 - x) / L, (y1 - y) / L; nx, ny = -uy, ux
        poly_xy(rk, [(x + nx * 3, y + ny * 3), (x1 + nx * 3, y1 + ny * 3), (x1 - nx * 3, y1 - ny * 3), (x - nx * 3, y - ny * 3)], 0, 30)
rk.body.name = 'RK-03'
c = rk.c
for x, y in P:                                         # hollow each column: thin 1.6 wall, 2 crossing ribs so the cup floor bridges <= 29 mm
    rk.cyl(x, y, 3.0, 57.0, 29.2, CUT)
    for a in (0, 90):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a)); h = 29.5; w = 0.8
        poly_xy(rk, [(x - h * ca - w * sa, y - h * sa + w * ca), (x + h * ca - w * sa, y + h * sa + w * ca), (x + h * ca + w * sa, y + h * sa - w * ca), (x - h * ca + w * sa, y - h * sa - w * ca)], 3.0, 57.0)
    rk.holes([(x + 15, y + 15)], 3.1, -0.1, 6.0)     # vent so the cavity isn't sealed
rk.body = c.bRepBodies.item(0)
for x, y in P:
    spec_fillet(rk, (x - 32, y - 32, ZF - 0.2, x + 32, y + 32, ZF + 0.2), 1.0, 'cup wall root')
out.append('RK-03 ' + process4(c, [], r_out=1.5, r_in=1.5, ch=0.4, r_top=0.8))
b = c.bRepBodies.item(0); b.material = PLA
out.append('RK-03 %.1f cm3 bodies %d pockets %s (beaker bottom Z%.1f, arc r%.0f about the pouring arm, 78 mm apart)' % (b.volume, c.bRepBodies.count, [tuple(round(v, 1) for v in p) for p in P], ZF, R))
try: design.snapshots.add()
except Exception: pass
print('\n'.join(out + FLOG))
