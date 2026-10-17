"""100 mL (OD 56) beaker parts: TT-04 v4 (4 pockets at r84, keyed to the printed TT-02 deck by pins in its drain holes),
WS-02 v3 (dia 56.6 locating ring), CAL-02 v2 (dia 56 probe)."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
PLA = design.materials.itemByName('PLA (FDM)')
CX, CY, Z0 = 175.0, 370.0, 58.6
RP, RB, W = 84.0, 28.3, 2.4          # pocket pitch radius, pocket ID/2 (56 + 0.6), wall
P_ANG = [22.5 + 90 * k for k in range(4)]       # pockets over 4 of the deck's 8 drain holes (deck-local angles)
PIN_ANG = [67.5 + 90 * k for k in range(4)]     # dowel screws into the other 4 drain holes (r88, dia 5.0)
def pol(r, a): return (CX + r * math.cos(math.radians(a)), CY + r * math.sin(math.radians(a)))
tt = Part('TT-04 beaker locator ring', (CX, CY, Z0))
tt.cyl(CX, CY, Z0, Z0 + 3.1, 100.0, JOIN, 60.0)                # web annulus r60-100, 3.1 thick (as v3)
for a in P_ANG:
    x, y = pol(RP, a)
    tt.cyl(x, y, Z0, Z0 + 3.1, RB + W)                        # pocket floor
    tt.cyl(x, y, Z0 + 3.1, Z0 + 12.0, RB + W, JOIN, RB)       # pocket wall, 8.9 tall
    tt.holes([(x, y)], Z0 + 3.1, Z0 - 0.1, 6.0)               # drain over the deck drain hole
for a in PIN_ANG:
    x, y = pol(88.0, a)
    tt.holes([(x, y)], Z0 + 3.1, Z0 - 0.1, 4.5)               # M4x10 dropped through as a locating dowel into the deck's dia-5 drain hole
tt.body.name = 'TT-04'
for a in P_ANG:
    x, y = pol(RP, a)
    spec_fillet(tt, (x - RB - W - 1, y - RB - W - 1, Z0 + 2.9, x + RB + W + 1, y + RB + W + 1, Z0 + 3.3), 1.5, 'pocket wall roots')
out.append('TT-04 ' + process4(tt.c, [], r_out=1.5, r_in=1.5, ch=0.4, r_top=0.8))
b = tt.c.bRepBodies.item(0); b.material = PLA; bb = b.boundingBox
out.append('TT-04 v4 %.1f cm3 bodies %d, outer radius %.1f (deck rim inner 115.6)' % (b.volume, tt.c.bRepBodies.count, RP + RB + W))
try: design.snapshots.add()
except Exception: pass
print('\n'.join(out + FLOG))
LIBO = [x for x in root.occurrences if x.component.name == 'HW-LIB (masters, hidden)'][0]
Mm = {x.component.name: x.component for x in LIBO.component.occurrences}
ttc = [o for o in root.occurrences if o.component.name == 'TT-04 beaker locator ring'][0].component
nm = 'SHCS ISO 4762 M4x12' if 'SHCS ISO 4762 M4x12' in Mm else None
for a in PIN_ANG:
    x, y = pol(88.0, a)
    m = C.Matrix3D.create(); m.translation = C.Vector3D.create((x - CX) / 10, (y - CY) / 10, 3.1 / 10)   # head on the web top, shank -Z (M4x12 master as stand-in for M4x10)
    if nm: ttc.occurrences.addExistingComponent(Mm[nm], m)
print('dowels', nm)
