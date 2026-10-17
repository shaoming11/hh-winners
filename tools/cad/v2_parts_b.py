"""CDR v2: ST-01 fins (CDR-07), ST-09 (CDR-08), CAL-01/CAL-02 (CDR-33), GA-01 gauge (CDR-09), EL-02 (CDR-48)."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
PLA = design.materials.itemByName('PLA (FDM)'); TPU = design.materials.itemByName('TPU 95A (FDM)')
ABS = design.materials.itemByName('ABS Plastic')
def occ(name): return [o for o in root.allOccurrences if o.component.name == name][0]
def wrap(o, origin):
    p = Part.__new__(Part); p.c = o.component; p.o = origin; p.body = o.component.bRepBodies.item(0); return p
def cone_seat(part, x, y, ztop, d=8.0):
    """90 deg conical seat, dia d at the surface ztop, cut downward"""
    c = part.c; sgn = c.xZConstructionPlane.geometry.normal.y
    pi = c.constructionPlanes.createInput(); pi.setByOffset(c.xZConstructionPlane, VI((y - part.o[1]) * sgn)); pl = c.constructionPlanes.add(pi); pl.isLightBulbOn = False
    sk = c.sketches.add(pl)
    def Pt(px, pz): return sk.modelToSketchSpace(C.Point3D.create((px - part.o[0]) / 10, (y - part.o[1]) / 10, (pz - part.o[2]) / 10))
    a, b2, cc = Pt(x, ztop + 0.01), Pt(x + d / 2, ztop + 0.01), Pt(x, ztop - d / 2)
    L = sk.sketchCurves.sketchLines
    l1 = L.addByTwoPoints(a, b2); L.addByTwoPoints(b2, cc); ax = L.addByTwoPoints(cc, a)
    ri = c.features.revolveFeatures.createInput(sk.profiles.item(0), ax, CUT); ri.setAngleExtent(False, C.ValueInput.createByString('360 deg'))
    ri.participantBodies = [part.body]; c.features.revolveFeatures.add(ri)
# ---------------- ST-01 v2: stop-post fins Z35.3 -> 54 (CDR-07) ----------------
st1 = wrap(occ('ST-01'), (656, 142, 0))
for (y0, y1, box) in ((115.0, 127.5, (645, 113, 35, 661, 129.5, 55)), (156.5, 169.0, (645, 154.5, 35, 661, 171, 55))):
    st1.box(647, y0, 35.3, 659, y1, 54.0)
for box, lab in (((645, 113, 35.0, 661, 129.5, 55), 'fin -Y'), ((645, 154.5, 35.0, 661, 171, 55), 'fin +Y')):
    spec_fillet(st1, box, 3.0, lab + ' to post/web')
    spec_fillet(st1, box, 1.0, lab + ' free edges', kind='convex')
out.append('ST-01 v2 vol %.1f cm3' % st1.c.bRepBodies.item(0).volume)
# ---------------- ST-09 TPU sleeve x2 (CDR-08) ----------------
s9 = Part('ST-09 stop-post TPU sleeve', (653, 112, 54))
s9.cyl(653, 112, 54, 68, 9.15 + 1.2, NEW, 9.15)
s9.body.name = 'ST-09'; s9.body.material = TPU
m = C.Matrix3D.create(); m.translation = C.Vector3D.create(65.3, 17.2, 5.4)
root.occurrences.addExistingComponent(s9.c, m)
out.append('ST-09 %.2f cm3 x2' % s9.body.volume)
# ---------------- CAL-01 arm calibration block (x2, arm A and arm B) (CDR-33) ----------------
cal = Part('CAL-01 arm calibration block', (280, 440, 0))
cal.box(280, 440, 0, 380, 492, 12)                    # base on the table, in front of the arm base (base Y>=493.3)
cal.box(300, 491, 7.1, 360, 504, 12.9)                # key into the X-front rail -Y side slot (Z10 centre, 5.8 tall)
cal.box(280, 440, 12, 300, 460, 110)                  # tower 20 x 20 x 98
spec_fillet(cal, (278, 438, 11, 302, 462, 13.5), 5.0, 'tower base (Z-tension pillar)')
for (x, y, z) in ((290, 450, 110), (370, 450, 12), (370, 484, 12), (290, 484, 12)): cone_seat(cal, x, y, z)
out.append('CAL-01 ' + process4(cal.c, [], r_out=2.0, r_in=2.0, ch=0.6, r_top=1.0))
cal.c.bRepBodies.item(0).material = PLA
m = C.Matrix3D.create(); m.translation = C.Vector3D.create(28.0 + 24.0, 44.0, 0)
oB = root.occurrences.addExistingComponent(cal.c, m)
for o in root.occurrences:
    if o.component.name == 'CAL-01 arm calibration block': o.isLightBulbOn = False   # removed before runs; not in the planner scene
# ---------------- CAL-02 calibration probe (CDR-33) ----------------
pr = Part('CAL-02 calibration probe', (-150, 400, 0))
H = 21.5 / math.tan(math.radians(30))
pr.cyl(-150, 400, H, H + 80, 21.5, NEW)
c = pr.c; sgn = c.xZConstructionPlane.geometry.normal.y
sk = c.sketches.add(c.xZConstructionPlane)
def Pt(px, pz): return sk.modelToSketchSpace(C.Point3D.create(px / 10, 0, pz / 10))
L = sk.sketchCurves.sketchLines
L.addByTwoPoints(Pt(0, 0), Pt(21.5, H)); L.addByTwoPoints(Pt(21.5, H), Pt(0, H)); ax = L.addByTwoPoints(Pt(0, H), Pt(0, 0))
ri = c.features.revolveFeatures.createInput(sk.profiles.item(0), ax, JOIN); ri.setAngleExtent(False, C.ValueInput.createByString('360 deg')); ri.participantBodies = [pr.body]; c.features.revolveFeatures.add(ri)
pr.box(-150 + 19.5, 380, H + 5, -150 + 30, 420, H + 80.5, CUT)   # 2 mm flat for rotation reference
pr.body = c.bRepBodies.item(0); pr.body.name = 'CAL-02'; pr.body.material = PLA
out.append('CAL-02 %.1f cm3, tip-to-grasp-band centre %.1f mm' % (pr.body.volume, H + 80 - 17 - 0))
# ---------------- GA-01 stage angle gauge (CDR-09) ----------------
ga = Part('GA-01 stage angle gauge', (-150, 250, 0))
def pol(r, a): return (-150 + r * math.cos(math.radians(a)), 250 + r * math.sin(math.radians(a)))
poly_xy(ga, [(-150, 250), pol(80, 0), pol(80, 36.87), pol(70, 36.87), pol(70, 45), pol(80, 45), pol(80, 52), (-150, 250)][:-1], 0, 3, NEW)
ga.body = ga.c.bRepBodies.item(0); ga.body.name = 'GA-01'; ga.body.material = PLA
# ---------------- EL-02 electronics box envelope (bought ABS box) (CDR-48) ----------------
el = Part('EL-02 electronics box (bought ABS)', (25, 602, 0))
el.box(25, 602, 0, 225, 692, 60, NEW); el.box(27, 604, 2, 223, 690, 58, CUT)
el.body.name = 'EL-02'; el.body.material = ABS
for p in (pr, ga):
    for o in root.occurrences:
        if o.component == p.c: o.isLightBulbOn = False
print('\n'.join(out + FLOG))
