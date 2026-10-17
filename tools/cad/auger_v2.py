"""CDR v2 of the west auger station: AG-01 (CDR-03), DH-01 (CDR-02/05), DH-02 (CDR-04)."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
# ---------------- AG-01 v2 (CDR-03) ----------------
ag = Part('AG-01 auger stand', (20, 235, 0))
ag.box(20, 235, 0, 110, 315, 12)                      # foot 90 x 80
ag.box(40, 250, 12, 70, 275, 135)                     # post 30 x 25
vpoly_xz(ag, [(70, 12), (110, 12), (70, 100)], 258.5, 266.5)    # +X gusset 8 thick, 40 root -> 0 at Z100
vpoly_yz(ag, [(275, 12), (315, 12), (275, 100)], 51, 59)        # +Y gusset
ag.box(70, 282, 0, 270, 312, 16)                      # bar 30 x 16 to the saddle
ag.box(238, 290, 0, 270, 335, 28)                     # saddle Y290-335
ag.box(244.7, 289, 0, 265.3, 336, 20.2, CUT)          # rail channel
ag.holes([(255, 300), (255, 322)], 28, 18, 5.5)       # M5 into T-nuts
ag.holes([(255, 300), (255, 322)], 28, 26.5, 10.0)    # dia 10 x 1.5 counterbores
ag.holes([(48, 262.5), (62, 262.5)], 135, 125, 2.5)   # M3 pilots for DH-01
ag.body.name = 'AG-01'
spec_fillet(ag, (35, 245, 11, 75, 280, 13.5), 8.0, 'post-to-foot root (Z-tension pillar)')
spec_fillet(ag, (69, 256, 12, 112, 269, 101), 3.0, '+X gusset to post/foot')
spec_fillet(ag, (49, 274, 12, 61, 317, 101), 3.0, '+Y gusset to post/foot')
spec_fillet(ag, (68, 280, 11, 240, 314, 17), 3.0, 'bar roots')
out.append('AG-01 ' + process4(ag.c, [(224.7, 54, -1, 245.3, 101, 21.2)], r_out=2.0, r_in=2.0, ch=0.6, r_top=1.2))
# ---------------- DH-01 v2 (CDR-02 / CDR-05) ----------------
dh = Part('DH-01 yeast auger head', (40, 250, 135))
dh.box(40, 250, 135, 100, 299, 148)                   # bridge
dh.ycyl(87, 155, 299, 381, 10.5)                      # tube (r 10.5 for the 14 bore + crown)
dh.box(62, 299, 135, 104, 340, 152)                   # web under the tube, 42 wide (M-02; >=700 mm2 at Y299)
dh.box(67, 310, 160, 107, 350, 205)                   # hopper block
vpoly_xz(dh, [(81, 160.5), (93, 160.5), (105, 181.3), (105, 206), (69, 206), (69, 181.3)], 312, 348, CUT)   # 60 deg walls -> 12 slot
dh.box(81, 312, 150, 93, 344, 161, CUT)               # slot hopper -> bore, Y312-344
dh.ycyl(87, 155, 302, 378, 7.0, CUT)                  # bore 14
vpoly_xz(dh, [(87 - 4.95, 155 + 4.95), (87 + 4.95, 155 + 4.95), (87, 155 + 7.9)], 302, 378, CUT)   # 45 deg teardrop crown
dh.holes([(87, 370)], 155, 140, 10.0)                 # outlet
dh.holes([(48, 262.5), (62, 262.5)], 148, 134, 3.4)   # M3 clearance
pi = dh.c.constructionPlanes.createInput(); pi.setByOffset(dh.c.xZConstructionPlane, VI((300 - 250) * dh.c.xZConstructionPlane.geometry.normal.y)); pl = dh.c.constructionPlanes.add(pi); pl.isLightBulbOn = False
sk = dh.c.sketches.add(pl)
for (x, r) in [(87, 2.25), (82.5, 0.85), (91.5, 0.85)]:
    sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(C.Point3D.create((x - 40) / 10, (300 - 250) / 10, (155 - 135) / 10)), r / 10)
col = C.ObjectCollection.create()
for p in sk.profiles: col.add(p)
ei = dh.c.features.extrudeFeatures.createInput(col, CUT); ei.setSymmetricExtent(VI(8), True); ei.participantBodies = [dh.body]; dh.c.features.extrudeFeatures.add(ei)
dh.body.name = 'DH-01'
spec_fillet(dh, (60, 297, 134, 106, 342, 170), 3.0, 'web to bridge/tube/hopper')
out.append('DH-01 ' + process4(dh.c, [], r_out=1.5, r_in=1.5, ch=0.5, r_top=1.0))
for p in (ag, dh):
    p.c.bRepBodies.item(0).material = design.materials.itemByName('PLA (FDM)')
    b = p.c.bRepBodies.item(0).boundingBox
    out.append('%s %.1f cm3 (%.0f,%.0f,%.0f)-(%.0f,%.0f,%.0f)' % (p.c.name, p.c.bRepBodies.item(0).volume, b.minPoint.x * 10 + p.o[0], b.minPoint.y * 10 + p.o[1], b.minPoint.z * 10 + p.o[2], b.maxPoint.x * 10 + p.o[0], b.maxPoint.y * 10 + p.o[1], b.maxPoint.z * 10 + p.o[2]))
# ---------------- DH-02 v2 (CDR-04) ----------------
for o in list(root.occurrences):
    if o.component.name == 'DH-02 auger screw': o.deleteMe()
m = C.Matrix3D.create(); r = C.Matrix3D.create(); r.setToRotateTo(C.Vector3D.create(0, 0, 1), C.Vector3D.create(0, 1, 0)); m.transformBy(r)
t = C.Matrix3D.create(); t.translation = C.Vector3D.create(8.7, 30.3, 15.5); m.transformBy(t)
o = root.occurrences.addNewComponent(m); c = o.component; c.name = 'DH-02 auger screw'
L, PITCH, ROUT, HUB, T, COL = 65.0, 16.0, 6.0, 3.5, 3.6, 12.0
sk = c.sketches.add(c.xZConstructionPlane)
line = sk.sketchCurves.sketchLines.addByTwoPoints(sk.modelToSketchSpace(C.Point3D.create(0, 0, COL / 10)), sk.modelToSketchSpace(C.Point3D.create(0, 0, L / 10)))
path = c.features.createPath(line)
pi = c.constructionPlanes.createInput(); pi.setByOffset(c.xYConstructionPlane, VI(COL)); pl = c.constructionPlanes.add(pi); pl.isLightBulbOn = False
sk2 = c.sketches.add(pl)
sk2.sketchCurves.sketchLines.addTwoPointRectangle(sk2.modelToSketchSpace(C.Point3D.create(-ROUT / 10, -T / 20, COL / 10)), sk2.modelToSketchSpace(C.Point3D.create(ROUT / 10, T / 20, COL / 10)))
si = c.features.sweepFeatures.createInput(sk2.profiles.item(0), path, NEW); si.twistAngle = C.ValueInput.createByString('%g deg' % (360.0 * (L - COL) / PITCH))
body = c.features.sweepFeatures.add(si).bodies.item(0)
sk3 = c.sketches.add(c.xYConstructionPlane); sk3.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(0, 0, 0), HUB / 10)
ei = c.features.extrudeFeatures.createInput(sk3.profiles.item(0), JOIN); ei.setDistanceExtent(False, VI(L)); ei.participantBodies = [body]; c.features.extrudeFeatures.add(ei)
sk4 = c.sketches.add(c.xYConstructionPlane); sk4.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(0, 0, 0), 0.45)
ei = c.features.extrudeFeatures.createInput(sk4.profiles.item(0), JOIN); ei.setDistanceExtent(False, VI(COL)); ei.participantBodies = [body]; c.features.extrudeFeatures.add(ei)
sk5 = c.sketches.add(c.xYConstructionPlane); R = 0.155; f = 0.105; ang = math.acos(f / R)
arc = sk5.sketchCurves.sketchArcs.addByCenterStartSweep(C.Point3D.create(0, 0, 0), C.Point3D.create(f, R * math.sin(ang), 0), 2 * math.pi - 2 * ang)
sk5.sketchCurves.sketchLines.addByTwoPoints(arc.startSketchPoint, arc.endSketchPoint)
ei = c.features.extrudeFeatures.createInput(sk5.profiles.item(0), CUT); ei.setDistanceExtent(False, VI(8)); ei.participantBodies = [body]; c.features.extrudeFeatures.add(ei)
body = c.bRepBodies.item(0)
ed = [e for e in body.edges if isinstance(e.geometry, C.Circle3D) and abs(e.geometry.radius * 10 - 4.5) < 0.05 and abs(e.geometry.center.z * 10 - COL) < 0.05]
if ed and guarded_add(c, 'fillet', ed, 2.0): out.append('DH-02 collar-to-hub R2')
elif ed and guarded_add(c, 'fillet', ed, 1.0): out.append('DH-02 collar-to-hub R1 ** FALLBACK')
else: out.append('DH-02 collar-to-hub fillet FAILED (%d edges)' % len(ed))
body = c.bRepBodies.item(0); body.name = 'DH-02'; body.material = design.materials.itemByName('PLA (FDM)')
bb = o.bRepBodies.item(0).boundingBox
out.append('DH-02 %.2f cm3 world (%.1f,%.1f,%.1f)-(%.1f,%.1f,%.1f)' % (body.volume, bb.minPoint.x * 10, bb.minPoint.y * 10, bb.minPoint.z * 10, bb.maxPoint.x * 10, bb.maxPoint.y * 10, bb.maxPoint.z * 10))
# ---------------- joints ----------------
frame = [x for x in root.occurrences if x.component.name.startswith('FRAME-2020')][0]
ago = [x for x in root.occurrences if x.component.name == 'AG-01 auger stand'][0]
dho = [x for x in root.occurrences if x.component.name == 'DH-01 yeast auger head'][0]
aug = [x for x in root.occurrences if x.component.name == 'DH-02 auger screw'][0]
for j in list(root.asBuiltJoints):
    if j.name in ('FIX-AG01-frame', 'FIX-DH01-AG01', 'AUGER-spin'): j.deleteMe()
def rigid(a, b, name):
    ji = root.asBuiltJoints.createInput(a, b, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = name
rigid(ago, frame, 'FIX-AG01-frame'); rigid(dho, ago, 'FIX-DH01-AG01')
hub = max([f for f in aug.bRepBodies.item(0).faces if isinstance(f.geometry, C.Cylinder)], key=lambda f: f.area)
ji = root.asBuiltJoints.createInput(aug, dho, F.JointGeometry.createByNonPlanarFace(hub, F.JointKeyPointTypes.MiddleKeyPoint))
ji.setAsRevoluteJointMotion(F.JointDirections.CustomJointDirection, hub); root.asBuiltJoints.add(ji).name = 'AUGER-spin'
print('\n'.join(out + FLOG))
