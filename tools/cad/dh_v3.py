"""DH-01 v3 / DH-02 v3: auger driven by the user's Feetech FB5311M-360 continuous servo (replaces the N20).
Servo body horizontal (+X), shaft along +Y on the auger axis (x87, z155); 25T Al disc horn bolted to a dia-22 flange on DH-02."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
AX, AZ = 87.0, 155.0
Y_HORN = 299.0            # horn outer face = flange contact face
Y_TUBE = 307.5            # tube / bore start (flange 299-303, M3 heads to 306)
# ---------------- DH-01 v3 ----------------
dh = Part('DH-01 yeast auger head', (40, 250, 135))
dh.box(40, 250, 135, 130, 299, 148)                   # bridge, extended to X130 to carry the servo wall
dh.box(64, 282.3, 135, 130, 287.3, 172)               # servo mounting wall: ears seat on its -Y face (Y282.3); servo+auger slide in along +Y
dh.box(78, 287.3, 135, 115.5, 307.6, 172)             # bell housing (narrowed so the ear nuts at X72.7/121.3 sit on the open wall face)
dh.box(62, 299, 135, 104, 340, 152)                   # web under the tube (CDR-02) - before the tube so it joins
dh.ycyl(AX, AZ, Y_TUBE, 381, 10.5)                    # tube
dh.box(67, 310, 160, 107, 350, 205)                   # hopper block
vpoly_xz(dh, [(81, 160.5), (93, 160.5), (105, 181.3), (105, 206), (69, 206), (69, 181.3)], 312, 348, CUT)
dh.box(81, 312, 150, 93, 344, 161, CUT)               # slot hopper -> bore
dh.ycyl(AX, AZ, Y_TUBE - 0.1, 378, 7.0, CUT)          # bore 14
vpoly_xz(dh, [(AX - 4.95, AZ + 4.95), (AX + 4.95, AZ + 4.95), (AX, AZ + 7.9)], Y_TUBE - 0.1, 378, CUT)
dh.holes([(AX, 370)], AZ, 140, 10.0)                  # outlet
dh.holes([(45, 270), (65, 270)], 148, 134, 3.4)       # M3x25 through-bolts into hex nuts in the PS-01 post
dh.box(75.5, 250, 143.5, 117.4, 292.5, 149, CUT)      # servo body pocket in the bridge (body Z145-165)
dh.box(75.5, 282, 143.5, 117.4, 292.5, 166.5, CUT)    # body window through the wall and into the bell (body ends Y291.5)
dh.box(69.0, 249, 144.4, 125.5, 282.5, 152, CUT)      # ear relief along the whole insertion travel (ears Z>=145.65)
dh.ycyl(AX, AZ, 287.0, Y_TUBE + 0.01, 12.5, CUT)      # bore of the bell: horn (r10), flange (r11), M3 heads
dh.box(69, 287.3, 144.5, 76.5, 291.5, 148.1, CUT)      # relief for the west ear nuts in the bridge top
dh.box(117.5, 287.3, 144.5, 125, 291.5, 148.1, CUT)    # relief for the east ear nuts
for x in (72.7, 121.3):                               # servo ear pilots, M3 self-tap 2.5 x 5 deep
    for z in (150.05, 159.95):
        pass
pi = dh.c.constructionPlanes.createInput(); pi.setByOffset(dh.c.xZConstructionPlane, VI((282.3 - 250) * dh.c.xZConstructionPlane.geometry.normal.y)); pl = dh.c.constructionPlanes.add(pi); pl.isLightBulbOn = False
sk = dh.c.sketches.add(pl)
for x in (72.7, 121.3):
    for z in (150.05, 159.95):
        sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(C.Point3D.create((x - 40) / 10, (282.3 - 250) / 10, (z - 135) / 10)), 0.17)
col = C.ObjectCollection.create()
for p in sk.profiles: col.add(p)
sg = dh.c.xZConstructionPlane.geometry.normal.y
ei = dh.c.features.extrudeFeatures.createInput(col, CUT); ei.setSymmetricExtent(VI(12.0), True)   # through the 5 mm wall either way   # pilots go +Y into the wall from its -Y face; ei.participantBodies = [dh.body]; dh.c.features.extrudeFeatures.add(ei)
for x in (72.7, 121.3):
    for z in (150.05, 159.95):
        dh.ycyl(x, z, 276.0, 289.0, 1.7, CUT)          # servo-ear through-holes (M3x16 + nyloc)
dh.body.name = 'DH-01'
spec_fillet(dh, (60, 297, 134, 106, 342, 170), 3.0, 'web to bridge/tube/hopper')
spec_fillet(dh, (62, 280, 147, 69, 284, 149.5), 3.0, 'servo wall root (-Y face, west of ears)')
spec_fillet(dh, (125.5, 280, 147, 132, 284, 149.5), 3.0, 'servo wall root (-Y face, east of ears)')
spec_fillet(dh, (125.5, 286, 147, 132, 290, 149.5), 3.0, 'servo wall root (+Y face, east of nuts)')
KEEP = [(28.5, 36.8, 9, 37, 42, 13.6), (77, 36.8, 9, 85.5, 42, 13.6), (34.5, -1, 7.5, 78.5, 44, 15.5), (28.5, -1, 8.5, 86, 33, 17.5), (34.5, 31, 7.5, 78.5, 43.5, 32.5), (33.5, 36, 6.5, 60.5, 58.5, 33.5)]   # servo pocket, window, horn clearance (local)
out.append('DH-01 ' + process4(dh.c, KEEP, r_out=1.5, r_in=1.5, ch=0.5, r_top=1.0))
out.append('DH-01 bodies: %d' % dh.c.bRepBodies.count)
b = dh.c.bRepBodies.item(0); b.material = design.materials.itemByName('PLA (FDM)'); bb = b.boundingBox
out.append('DH-01 v3 %.1f cm3 (%.0f,%.0f,%.0f)-(%.0f,%.0f,%.0f)' % (b.volume, bb.minPoint.x * 10 + 40, bb.minPoint.y * 10 + 250, bb.minPoint.z * 10 + 135, bb.maxPoint.x * 10 + 40, bb.maxPoint.y * 10 + 250, bb.maxPoint.z * 10 + 135))
# ---------------- DH-02 v3: flange + collar + flights (no D-bore) ----------------
for o in list(root.occurrences):
    if o.component.name == 'DH-02 auger screw': o.deleteMe()
m = C.Matrix3D.create(); r = C.Matrix3D.create(); r.setToRotateTo(C.Vector3D.create(0, 0, 1), C.Vector3D.create(0, 1, 0)); m.transformBy(r)
t = C.Matrix3D.create(); t.translation = C.Vector3D.create(AX / 10, Y_HORN / 10, AZ / 10); m.transformBy(t)
o = root.occurrences.addNewComponent(m); c = o.component; c.name = 'DH-02 auger screw'
FL, COL0, COL1, L, PITCH, ROUT, HUB, T = 4.0, 4.0, 7.5, 69.0, 16.0, 6.0, 4.0, 3.6   # flights start after the M3 heads (Y303-306)
sk = c.sketches.add(c.xZConstructionPlane)
line = sk.sketchCurves.sketchLines.addByTwoPoints(sk.modelToSketchSpace(C.Point3D.create(0, 0, COL1 / 10)), sk.modelToSketchSpace(C.Point3D.create(0, 0, L / 10)))
path = c.features.createPath(line)
pi = c.constructionPlanes.createInput(); pi.setByOffset(c.xYConstructionPlane, VI(COL1)); pl = c.constructionPlanes.add(pi); pl.isLightBulbOn = False
sk2 = c.sketches.add(pl)
sk2.sketchCurves.sketchLines.addTwoPointRectangle(sk2.modelToSketchSpace(C.Point3D.create(-ROUT / 10, -T / 20, COL1 / 10)), sk2.modelToSketchSpace(C.Point3D.create(ROUT / 10, T / 20, COL1 / 10)))
si = c.features.sweepFeatures.createInput(sk2.profiles.item(0), path, NEW); si.twistAngle = C.ValueInput.createByString('%g deg' % (360.0 * (L - COL1) / PITCH))
body = c.features.sweepFeatures.add(si).bodies.item(0)
def zcyl(r, z0, z1, op=JOIN):
    pi = c.constructionPlanes.createInput(); pi.setByOffset(c.xYConstructionPlane, VI(z0)); pl = c.constructionPlanes.add(pi); pl.isLightBulbOn = False
    s = c.sketches.add(pl); s.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(0, 0, 0), r / 10)
    ei = c.features.extrudeFeatures.createInput(s.profiles.item(0), op); ei.setDistanceExtent(False, VI(z1 - z0)); ei.participantBodies = [body]; c.features.extrudeFeatures.add(ei)
zcyl(HUB, 0, L)                    # hub dia 8
zcyl(11.0, 0, FL)                  # flange dia 22 x 4 (prints on the bed)
s = c.sketches.add(c.xYConstructionPlane)
for sx in (1, -1):
    for sy in (1, -1): s.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(sx * 0.495, sy * 0.495, 0), 0.17)
colh = C.ObjectCollection.create()
for p in s.profiles:
    if p.areaProperties().area < 0.2: colh.add(p)
ei = c.features.extrudeFeatures.createInput(colh, CUT); ei.setDistanceExtent(False, VI(FL)); ei.participantBodies = [body]; c.features.extrudeFeatures.add(ei)
body = c.bRepBodies.item(0)
for rr in (0.5, 0.3):
    ed = [e for e in body.edges if isinstance(e.geometry, C.Circle3D) and abs(e.geometry.radius * 10 - 4.0) < 0.05 and abs(e.geometry.center.z * 10 - FL) < 0.05]
    if ed and guarded_add(c, 'fillet', ed, rr): out.append('DH-02 flange-to-hub R%.1f' % rr); break
body = c.bRepBodies.item(0); body.name = 'DH-02'; body.material = design.materials.itemByName('PLA (FDM)')
bb = o.bRepBodies.item(0).boundingBox
out.append('DH-02 v3 %.2f cm3 world (%.1f,%.1f,%.1f)-(%.1f,%.1f,%.1f)' % (body.volume, bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10, bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10))
# ---------------- servo: copy the standard-size servo master, place it ----------------
LIB = [x for x in root.occurrences if x.component.name == 'HW-LIB (masters, hidden)'][0]; lib = LIB.component
Mm = {x.component.name: x.component for x in lib.occurrences}
NAME = 'Feetech FB5311M-360 + 25T Al disc horn'
if NAME not in Mm:
    LIB.isLightBulbOn = True
    oc = lib.occurrences.addNewComponentCopy(Mm['FlashHobby M45CHW + 25T disc horn'], C.Matrix3D.create()); oc.component.name = NAME; Mm[NAME] = oc.component
    LIB.isLightBulbOn = False
MS = [x for x in root.allOccurrences if x.component.name.startswith('Measuring')][0].component
for x in list(MS.occurrences):
    if x.component.name.startswith(('N20', NAME)): x.deleteMe()
    elif x.component.name.startswith('SHCS ISO 4762 M3x8') and x.transform2.translation.y * 10 > 295 and x.transform2.translation.x * 10 < 100: x.deleteMe()
# local X -> world -X, local Y -> world +Z, local Z -> world +Y ; local origin = shaft axis at case bottom
ms = C.Matrix3D.create()
ms.setWithCoordinateSystem(C.Point3D.create(AX / 10, (Y_HORN - 48.0) / 10, AZ / 10), C.Vector3D.create(-1, 0, 0), C.Vector3D.create(0, 0, 1), C.Vector3D.create(0, 1, 0))
MS.occurrences.addExistingComponent(Mm[NAME], ms)
# 4 x M3x8 flange -> tapped horn (heads on the +Y flange face at Y303, pointing -Y)
for sx in (1, -1):
    for sz in (1, -1):
        mm = C.Matrix3D.create()
        mm.setWithCoordinateSystem(C.Point3D.create((AX + sx * 4.95) / 10, (Y_HORN + FL) / 10, (AZ + sz * 4.95) / 10), C.Vector3D.create(1, 0, 0), C.Vector3D.create(0, 0, -1), C.Vector3D.create(0, 1, 0))   # head +Y on the flange face, shank -Y into the horn
        if 'SHCS ISO 4762 M3x8' in Mm: MS.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M3x8'], mm)
for x in list(MS.occurrences):
    if x.component.name in ('SHCS ISO 4762 M3x16', 'Nyloc nut DIN 985 M3', 'SHCS ISO 4762 M3x25', 'Hex nut ISO 4032 M3'): x.deleteMe()
for x in (72.7, 121.3):
    for z in (150.05, 159.95):
        m1 = C.Matrix3D.create(); m1.setWithCoordinateSystem(C.Point3D.create(x / 10, 27.83, z / 10), C.Vector3D.create(1, 0, 0), C.Vector3D.create(0, 0, 1), C.Vector3D.create(0, -1, 0))
        MS.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M3x16'], m1)
        m2 = C.Matrix3D.create(); m2.setWithCoordinateSystem(C.Point3D.create(x / 10, 28.73, z / 10), C.Vector3D.create(1, 0, 0), C.Vector3D.create(0, 0, -1), C.Vector3D.create(0, 1, 0))
        MS.occurrences.addExistingComponent(Mm['Nyloc nut DIN 985 M3'], m2)
for x in (45, 65):
    m1 = C.Matrix3D.create(); m1.translation = C.Vector3D.create(x / 10, 27.0, 14.8); MS.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M3x25'], m1)
    m2 = C.Matrix3D.create(); m2.translation = C.Vector3D.create(x / 10, 27.0, 12.365); MS.occurrences.addExistingComponent(Mm['Hex nut ISO 4032 M3'], m2)
out.append('servo + horn screws placed (M3x8 master %s)' % ('found' if 'SHCS ISO 4762 M3x8' in Mm else 'MISSING - add 4 x M3x8 by hand'))
# ---------------- joints ----------------
ago = [x for x in root.occurrences if x.component.name == 'PS-01 auger post'][0]
dho = [x for x in root.occurrences if x.component.name == 'DH-01 yeast auger head'][0]
aug = [x for x in root.occurrences if x.component.name == 'DH-02 auger screw'][0]
for j in list(root.asBuiltJoints):
    if j.name in ('FIX-DH01-AG01', 'FIX-DH01-PS01', 'AUGER-spin'): j.deleteMe()
ji = root.asBuiltJoints.createInput(dho, ago, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-DH01-PS01'
hub = [f for f in aug.bRepBodies.item(0).faces if isinstance(f.geometry, C.Cylinder) and abs(f.geometry.radius * 10 - 11.0) < 0.05][0]
ji = root.asBuiltJoints.createInput(aug, dho, F.JointGeometry.createByNonPlanarFace(hub, F.JointKeyPointTypes.MiddleKeyPoint))
ji.setAsRevoluteJointMotion(F.JointDirections.CustomJointDirection, hub); root.asBuiltJoints.add(ji).name = 'AUGER-spin'
print('\n'.join(out + FLOG))
