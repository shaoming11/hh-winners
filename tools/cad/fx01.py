"""FX-01 E5 joiner plate (replaces the E5 corner bracket that hit TT-01); bridge bolts M5x12 -> M5x10."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py', 'hw_funcs.py'): exec(open(os.path.join(B, f)).read())
out = []
names = [o.component.name for o in lib.occurrences]
if 'SHCS ISO 4762 M5x10' not in names:
    LIB.isLightBulbOn = True; c, r = shcs(5, 10); c.bRepBodies.item(0).material = design.materials.itemByName('Steel'); LIB.isLightBulbOn = False; out.append('M5x10 ' + r)
Mm = {o.component.name: o.component for o in lib.occurrences}
def tr(x, y, z, rz=0):
    m = C.Matrix3D.create()
    if rz: m.setToRotation(math.radians(rz), C.Vector3D.create(0, 0, 1), C.Point3D.create(0, 0, 0))
    t = m.translation; t.x, t.y, t.z = x / 10, y / 10, z / 10; m.translation = t; return m
allo = list(root.allOccurrences)
sad = [x for x in allo if x.component.name == 'SHCS ISO 4762 M5x12' and abs(x.transform2.translation.x * 10 - 255) < 0.6 and abs(x.transform2.translation.y * 10 - 355) < 0.6][0]
tn = min([x for x in allo if x.component.name == 'T-nut 2020 drop-in M5'], key=lambda x: math.dist(x.transform2.translation.asArray(), sad.transform2.translation.asArray()))
inv_s = sad.transform2.copy(); inv_s.invert(); rel_vt = tn.transform2.copy(); rel_vt.transformBy(inv_s)
def bolt_into_top_slot(parent, x, y, seat_z, screw, along_x):
    ms = tr(x, y, seat_z); parent.occurrences.addExistingComponent(Mm[screw], ms)
    mm = rel_vt.copy()
    if along_x:
        rz = C.Matrix3D.create(); rz.setToRotation(math.pi / 2, C.Vector3D.create(0, 0, 1), C.Point3D.create(0, 0, 0)); mm.transformBy(rz)
    up = C.Matrix3D.create(); up.translation = C.Vector3D.create(0, 0, (28.0 - seat_z) / 10 * 0 + 0); mm.transformBy(up)
    # template screw seats at Z28 with its nut against the lip; keep the nut at the lip: shift by (28 - seat) along -z of the screw frame
    sh = C.Matrix3D.create(); sh.translation = C.Vector3D.create(0, 0, (28.0 - seat_z) / 10); mm.transformBy(sh)
    mm.transformBy(ms); parent.occurrences.addExistingComponent(Mm['T-nut 2020 drop-in M5'], mm)
# ---- remove the E5 corner bracket + its screws/T-nuts ----
MS = [x for x in root.allOccurrences if x.component.name.startswith('Measuring')][0].component
n = 0
for o in list(MS.occurrences):
    t = o.transform2.translation
    if o.component.name in ('2020 inside corner bracket', 'SHCS ISO 4762 M5x8', 'T-nut 2020 drop-in M5') and 215 < t.x * 10 < 256 and 295 < t.y * 10 < 335 and t.z * 10 < 25: o.deleteMe(); n += 1
out.append('E5 bracket parts removed: %d' % n)
# ---- FX-01 L plate on the E5 top + Y-left rail top (Z20-25) ----
fx = Part('FX-01 E5 joiner plate', (245, 300, 20))
fx.box(205, 291, 20, 265, 309, 25); fx.box(245, 291, 20, 265, 336, 25)
HE5 = [(215, 300), (231, 300)]; HYL = [(255, 312), (255, 328)]
fx.holes(HE5 + HYL, 25.1, 19.9, 5.5)
fx.body.name = 'FX-01'
spec_fillet(fx, (244, 307, 19.5, 247, 311, 25.5), 5.0, 'L inside corner')
out.append('FX-01 ' + process4(fx.c, [], r_out=3.0, r_in=3.0, ch=0.5, r_top=1.0))
fx.c.bRepBodies.item(0).material = design.materials.itemByName('PLA (FDM)')
for x, y in HE5: bolt_into_top_slot(MS, x, y, 25.0, 'SHCS ISO 4762 M5x10', True)
for x, y in HYL: bolt_into_top_slot(MS, x, y, 25.0, 'SHCS ISO 4762 M5x10', False)
frame = [x for x in root.occurrences if x.component.name.startswith('FRAME-2020 (')][0]
fxo = [x for x in root.occurrences if x.component.name == 'FX-01 E5 joiner plate'][0]
ji = root.asBuiltJoints.createInput(fxo, frame, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-FX01-frame'
# ---- bridge bolts M5x12 -> M5x10 (seat Z25.8, tip 15.8 above the slot bottom) ----
G = [o for o in root.allOccurrences if o.component.name == 'Stage + crossbar brackets'][0].component
k = 0
for o in list(G.occurrences):
    if o.component.name == 'SHCS ISO 4762 M5x12':
        m = o.transform2.copy(); o.deleteMe(); G.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M5x10'], m); k += 1
out.append('bridge bolts -> M5x10: %d' % k)
try: design.snapshots.add()
except Exception: pass
print('\n'.join(out + FLOG))
