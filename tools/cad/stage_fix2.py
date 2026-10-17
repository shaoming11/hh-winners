"""Fixes from the first stage clash check: carrier tray body, sled v2 (thin walls, shallow tabs), drop E6 bracket at (265,430), nut rotations."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
PLA = design.materials.itemByName('PLA (FDM)')
LIBO = [x for x in root.occurrences if x.component.name == 'HW-LIB (masters, hidden)'][0]
Mm = {x.component.name: x.component for x in LIBO.component.occurrences}
YC, R, L = 77.0, 50.0, 80.0; PIN_W = YC + R + L
def tr(x, y, z, rotz=0.0):
    m = C.Matrix3D.create()
    if rotz: m.setToRotation(math.radians(rotz), C.Vector3D.create(0, 0, 1), C.Point3D.create(0, 0, 0))
    t = m.translation; t.x, t.y, t.z = x / 10, y / 10, z / 10; m.translation = t; return m
# (a) carrier: remove the old tray body
car = [o for o in root.occurrences if o.component.name == 'ST-PAYLOAD carrier (was ST-04)'][0]
for b in list(car.component.bRepBodies):
    try: car.component.features.removeFeatures.add(b); out.append('removed carrier body %s' % b.name)
    except Exception as e: out.append('remove failed: %s' % e)
out.append('carrier bodies left: %d' % car.component.bRepBodies.count)
# (b) sled v2
for j in list(root.asBuiltJoints):
    if j.name in ('ST-SLIDE', 'FIX-PAYLOAD-SLED', 'FIX-ST15-SLED'): j.deleteMe()
sl = Part('ST-11 stage sled', (450, 282, 0))
sl.box(381, 196, 3, 519, 350, 9)
sl.box(381, 196, 3, 383.5, 350, 26); sl.box(516.5, 196, 3, 519, 350, 26)            # 2.5 mm walls: 133 mm between them for the dia-130 well
sl.box(357, 196, 20, 383.5, 350, 26); sl.box(516.5, 196, 20, 543, 350, 26)
sl.box(367.3, 201, 17, 372.7, 345, 20); sl.box(527.3, 201, 17, 532.7, 345, 20)        # tabs 5.4 wide x 3 deep in the slot opening
sl.cyl(450, 282, 9, 13, 68.5, JOIN, 65.5)
sl.cyl(450, PIN_W, 9, 54, 9.0)
sl.holes([(450, PIN_W)], 54, 39, 5.3)
sl.box(445.85, 194, 43.5, 454.15, PIN_W + 4.7, 48.5, CUT)
sl.body.name = 'ST-11'
spec_fillet(sl, (439, 194, 8.5, 461, 220, 10.5), 6.0, 'pin post base (Z-tension pillar)')
spec_fillet(sl, (382, 195, 8.5, 385, 351, 10.5), 1.0, 'west wall root'); spec_fillet(sl, (515, 195, 8.5, 518, 351, 10.5), 1.0, 'east wall root')
out.append('ST-11 ' + process4(sl.c, [(-5.5, -89, 43, 5.5, -70, 49), (-70, -90, 8.5, 70, 70, 13.5), (-84.5, -87, 15.5, -75.5, 65, 21), (75.5, -87, 15.5, 84.5, 65, 21)], r_out=2.0, r_in=1.0, ch=0.5, r_top=1.0))
sl.c.bRepBodies.item(0).material = PLA
def add_in(comp, origin, name, M):
    t = M.translation; t.x -= origin[0] / 10; t.y -= origin[1] / 10; t.z -= origin[2] / 10; M.translation = t
    return comp.occurrences.addExistingComponent(Mm[name], M)
add_in(sl.c, sl.o, 'Hex nut ISO 4032 M5', tr(450, PIN_W, 43.6, 30))       # flats facing the slot walls
add_in(sl.c, sl.o, 'SHCS ISO 4762 M5x25', tr(450, PIN_W, 65))
add_in(sl.c, sl.o, 'ST-08 bearing race spacer', tr(450, PIN_W, 64))
s1 = [o for o in root.occurrences if o.component.name == 'FRAME-2020 stage rail S1'][0]
slo = [o for o in root.occurrences if o.component.name == 'ST-11 stage sled'][0]
sp2 = [o for o in root.occurrences if o.component.name == 'ST-15 pivot spacer' and abs(o.transform2.translation.y * 10 - PIN_W) < 1]
ji = root.asBuiltJoints.createInput(car, slo, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-PAYLOAD-SLED'
if sp2:
    ji = root.asBuiltJoints.createInput(sp2[0], slo, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-ST15-SLED'
bot = [f for f in slo.bRepBodies.item(0).faces if isinstance(f.geometry, C.Plane) and abs(f.geometry.normal.z) > 0.99 and abs(f.boundingBox.minPoint.z * 10 - 3) < 0.05 and abs(f.boundingBox.maxPoint.z * 10 - 3) < 0.05]
bot = max(bot, key=lambda f: f.area)
ji = root.asBuiltJoints.createInput(slo, s1, F.JointGeometry.createByPlanarFace(bot, None, F.JointKeyPointTypes.CenterKeyPoint))
ji.setAsSliderJointMotion(F.JointDirections.CustomJointDirection, root.yConstructionAxis); root.asBuiltJoints.add(ji).name = 'ST-SLIDE'
out.append('ST-11 v2 %.1f cm3 bodies %d' % (sl.c.bRepBodies.item(0).volume, sl.c.bRepBodies.count))
# (c) drop the E6 bracket at (265,430) (its leg reached TT-01) with its screws/T-nuts
G = [o for o in root.allOccurrences if o.component.name == 'Stage + crossbar brackets'][0].component
n = 0
for o in list(G.occurrences):
    t = o.transform2.translation; x, y = t.x * 10, t.y * 10
    if 255 < x < 290 and 400 < y < 431: o.deleteMe(); n += 1
out.append('removed %d items of the (265,430) bracket' % n)
# (d) TT-01 ear nuts rotated 30 deg to match the pockets
SGc = [o for o in root.allOccurrences if o.component.name == 'Servos'][0].component
for o in list(SGc.occurrences):
    if o.component.name == 'Hex nut ISO 4032 M3':
        t = o.transform2.translation; x, y, z = t.x * 10, t.y * 10, t.z * 10; o.deleteMe()
        SGc.occurrences.addExistingComponent(Mm['Hex nut ISO 4032 M3'], tr(x, y, z, 30))
try: design.snapshots.add()
except Exception: pass
print('\n'.join(out + FLOG))
