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
PIN_ANG = [67.5 + 90 * k for k in range(4)]     # pins into the other 4 drain holes (r88, dia 5.0)
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
    tt.cyl(x, y, Z0 - 3.0, Z0, 2.3)                           # locating pin dia 4.6 into the deck's dia-5 drain hole
tt.body.name = 'TT-04'
for a in P_ANG:
    x, y = pol(RP, a)
    spec_fillet(tt, (x - RB - W - 1, y - RB - W - 1, Z0 + 2.9, x + RB + W + 1, y + RB + W + 1, Z0 + 3.3), 1.5, 'pocket wall roots')
out.append('TT-04 ' + process4(tt.c, [], r_out=1.5, r_in=1.5, ch=0.4, r_top=0.8))
b = tt.c.bRepBodies.item(0); b.material = PLA; bb = b.boundingBox
out.append('TT-04 v4 %.1f cm3 bodies %d, outer radius %.1f (deck rim inner 115.6)' % (b.volume, tt.c.bRepBodies.count, RP + RB + W))
# WS-02 v3
ws2 = Part('WS-02 scale pan', (468, 475, 57.7))
ws2.cyl(468, 475, 57.7, 63.7, 40.0)
ws2.cyl(468, 475, 63.7, 71.7, 40.0, JOIN, 38.0)
ws2.cyl(468, 475, 63.7, 71.7, 30.8, JOIN, 28.3)               # locating ring ID 56.6 for the 100 mL beaker
ws2.box(430, 467.5, 57.7, 458, 482.5, 59.2, CUT)
ws2.holes([(463, 475), (473, 475)], 63.7, 59.7, 8.0)
ws2.holes([(463, 475), (473, 475)], 59.7, 57.7, 4.4)
ws2.body.name = 'WS-02'
spec_fillet(ws2, (425, 432, 63.5, 511, 518, 63.9), 1.0, 'ring/lip roots')
out.append('WS-02 ' + process4(ws2.c, [(-38.5, -8, -0.1, -9.5, 8, 1.6)], r_out=1.0, r_in=1.0, ch=0.4, r_top=0.6))
ws2.c.bRepBodies.item(0).material = PLA
ws1o = [o for o in root.occurrences if o.component.name == 'WS-01 scale base'][0]
ji = root.asBuiltJoints.createInput([o for o in root.occurrences if o.component.name == 'WS-02 scale pan'][0], ws1o, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-WS02-WS01'
# CAL-02 v2: dia 56 x 80 grasp body + 60 deg tip
R = 28.0
pr = Part('CAL-02 calibration probe', (-150, 400, 0))
H = R / math.tan(math.radians(30))
pr.cyl(-150, 400, H, H + 80, R, NEW)
c = pr.c
sk = c.sketches.add(c.xZConstructionPlane)
def Pt(px, pz): return sk.modelToSketchSpace(C.Point3D.create(px / 10, 0, pz / 10))
L = sk.sketchCurves.sketchLines
L.addByTwoPoints(Pt(0, 0), Pt(R, H)); L.addByTwoPoints(Pt(R, H), Pt(0, H)); ax = L.addByTwoPoints(Pt(0, H), Pt(0, 0))
ri = c.features.revolveFeatures.createInput(sk.profiles.item(0), ax, JOIN); ri.setAngleExtent(False, C.ValueInput.createByString('360 deg')); ri.participantBodies = [pr.body]; c.features.revolveFeatures.add(ri)
pr.box(-150 + R - 2, 370, H + 5, -150 + R + 10, 430, H + 80.5, CUT)
pr.body = c.bRepBodies.item(0); pr.body.name = 'CAL-02'; pr.body.material = PLA
out.append('CAL-02 v2 %.1f cm3, tip-to-grasp-band centre %.1f mm' % (pr.body.volume, H + 80 - 17))
try: design.snapshots.add()
except Exception: pass
print('\n'.join(out + FLOG))
