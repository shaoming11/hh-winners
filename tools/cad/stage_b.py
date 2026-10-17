"""Stage v2 part B: ST-11 sled, ST-12 servo bridge, ST-13 crank, ST-14 rod, ST-15 spacer; servo pose; hardware; joints.
Slider-crank: crank r=50 at (450,77), rod L=80; WORK (crank 0 deg, sled pin Y207) / ERUPT (crank 180 deg, pin Y107)."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
PLA = design.materials.itemByName('PLA (FDM)'); STEEL = design.materials.itemByName('Steel')
LIBO = [x for x in root.occurrences if x.component.name == 'HW-LIB (masters, hidden)'][0]
Mm = {x.component.name: x.component for x in LIBO.component.occurrences}
YC, R, L = 77.0, 50.0, 80.0
PIN_W = YC + R + L          # 207 sled pin at WORK
def add_in(comp, origin, name, M_world):
    """place a library component inside `comp` (whose occurrence sits at `origin`), given a world transform"""
    t = M_world.translation; t.x -= origin[0] / 10; t.y -= origin[1] / 10; t.z -= origin[2] / 10; M_world.translation = t
    return comp.occurrences.addExistingComponent(Mm[name], M_world)
def tr(x, y, z): m = C.Matrix3D.create(); m.translation = C.Vector3D.create(x / 10, y / 10, z / 10); return m
# ---------------- masters: F625ZZ bearing, ST-08 1 mm spacer ----------------
LIBO.isLightBulbOn = True
def simple_master(name, r_out, r_in, h, mat, flange=None):
    if name in Mm: return
    o = LIBO.component.occurrences.addNewComponent(C.Matrix3D.create()); c = o.component; c.name = name
    sk = c.sketches.add(c.xYConstructionPlane); sk.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(0, 0, 0), r_out / 10); sk.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(0, 0, 0), r_in / 10)
    prof = [p for p in sk.profiles if p.profileLoops.count == 2][0]
    ei = c.features.extrudeFeatures.createInput(prof, NEW); ei.setDistanceExtent(False, VI(h)); c.features.extrudeFeatures.add(ei)
    if flange:
        pi = c.constructionPlanes.createInput(); pi.setByOffset(c.xYConstructionPlane, VI(h - 1)); pl = c.constructionPlanes.add(pi)
        sk = c.sketches.add(pl); sk.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(0, 0, 0), flange / 10); sk.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(0, 0, 0), r_out / 10)
        prof = [p for p in sk.profiles if p.profileLoops.count == 2][0]
        ei = c.features.extrudeFeatures.createInput(prof, JOIN); ei.setDistanceExtent(False, VI(1)); c.features.extrudeFeatures.add(ei)
    c.bRepBodies.item(0).material = mat; Mm[name] = c
simple_master('F625ZZ flanged bearing 5x16x5', 8.0, 2.5, 5.0, STEEL, flange=9.0)
simple_master('ST-08 bearing race spacer', 3.6, 2.65, 1.0, PLA)
LIBO.isLightBulbOn = False
# ---------------- remove previous attempt ----------------
for o in list(root.occurrences):
    if o.component.name in ('ST-11 stage sled', 'ST-12 servo bridge', 'ST-13 crank', 'ST-14 connecting rod', 'ST-15 pivot spacer'): o.deleteMe()
for j in list(root.asBuiltJoints):
    if j.name.startswith(('ST-', 'FIX-ST1', 'FIX-PAYLOAD')): j.deleteMe()
# ---------------- ST-11 sled (at WORK) ----------------
sl = Part('ST-11 stage sled', (450, 282, 0))
sl.box(381, 196, 3, 519, 350, 9)                       # plate slung between the rails, 3 mm above the table
sl.box(381, 196, 3, 386, 350, 26); sl.box(514, 196, 3, 519, 350, 26)       # walls up to the riders
sl.box(357, 196, 20, 386, 350, 26); sl.box(514, 196, 20, 543, 350, 26)     # riders on the S1/S2 rail tops
sl.box(367.2, 201, 15.5, 372.8, 345, 20); sl.box(527.2, 201, 15.5, 532.8, 345, 20)   # guide tabs in the top T-slots
sl.cyl(450, 282, 9, 13, 69.5, JOIN, 65.5)              # ST-07 catch-well locating ring (ID 131)
sl.cyl(450, PIN_W, 9, 54, 9.0)                          # rod pin post dia 18
sl.holes([(450, PIN_W)], 54, 39, 5.3)
sl.box(445.85, 194, 43.5, 454.15, PIN_W + 4.7, 48.5, CUT)   # captive M5 hex-nut slot from the south face
sl.body.name = 'ST-11'
spec_fillet(sl, (439, 194, 8.5, 461, 220, 10.5), 6.0, 'pin post base (Z-tension pillar)')
spec_fillet(sl, (380, 195, 8.5, 388, 351, 10.5), 3.0, 'west wall root'); spec_fillet(sl, (512, 195, 8.5, 520, 351, 10.5), 3.0, 'east wall root')
out.append('ST-11 ' + process4(sl.c, [(-5.5, -89, 43, 5.5, -70, 49)], r_out=2.0, r_in=1.5, ch=0.5, r_top=1.0))
sl.c.bRepBodies.item(0).material = PLA
# ---------------- ST-12 servo bridge ----------------
br = Part('ST-12 servo bridge', (450, 65, 20))
br.box(357, 35, 20, 543, 96, 27.3)
br.box(439.5, 46.5, 19.9, 460.5, 87.5, 27.4, CUT)       # servo body window
EARS = [(450 - 4.95, YC - 34.3), (450 + 4.95, YC - 34.3), (450 - 4.95, YC + 14.3), (450 + 4.95, YC + 14.3)]
br.holes(EARS, 27.3, 19.9, 3.4)
RB = [(370, 45), (370, 86), (530, 45), (530, 86)]
br.holes(RB, 27.3, 19.9, 5.5); br.holes(RB, 27.3, 25.8, 10.0)
for (x0, x1) in ((381, 435), (465, 519)):
    br.box(x0, 35, 12, x1, 40, 20); br.box(x0, 91, 12, x1, 96, 20)      # stiffening ribs between the rails
br.body.name = 'ST-12'
out.append('ST-12 ' + process4(br.c, [], r_out=2.0, r_in=1.5, ch=0.5, r_top=1.0))
br.c.bRepBodies.item(0).material = PLA
# ---------------- ST-13 crank (pointing +Y = WORK) ----------------
cr = Part('ST-13 crank', (450, YC, 48))
cr.cyl(450, YC, 48, 54, 12.0); cr.box(443, YC, 48, 457, YC + R, 54); cr.cyl(450, YC + R, 48, 54, 8.0)
HORN = [(450 - 4.95, YC - 4.95), (450 + 4.95, YC - 4.95), (450 - 4.95, YC + 4.95), (450 + 4.95, YC + 4.95)]
cr.holes(HORN, 54, 47.9, 3.4); cr.holes(HORN, 54, 51, 6.0); cr.holes([(450, YC)], 54, 47.9, 7.0)
cr.holes([(450, YC + R)], 54, 47.9, 5.3)
cr.body.name = 'ST-13'
out.append('ST-13 ' + process4(cr.c, [], r_out=1.5, r_in=1.5, ch=0.4, r_top=0.8))
cr.c.bRepBodies.item(0).material = PLA
# ---------------- ST-14 connecting rod ----------------
rd = Part('ST-14 connecting rod', (450, YC + R, 58))
rd.box(443, YC + R, 58, 457, PIN_W, 64); rd.cyl(450, YC + R, 58, 64, 10.0); rd.cyl(450, PIN_W, 58, 64, 10.0)
for y in (YC + R, PIN_W):
    rd.cyl(450, y, 57.9, 64.1, 8.0, CUT)                # F625ZZ bore
    rd.cyl(450, y, 63, 64.1, 9.1, CUT)                  # flange recess
rd.body.name = 'ST-14'
out.append('ST-14 ' + process4(rd.c, [], r_out=1.5, r_in=1.0, ch=0.4, r_top=0.8))
rd.c.bRepBodies.item(0).material = PLA
# ---------------- ST-15 pivot spacer (4 mm, inner race) - one component, two occurrences ----------------
sp = Part('ST-15 pivot spacer', (450, YC + R, 54))
sp.cyl(450, YC + R, 54, 58, 3.6, NEW, 2.65); sp.body = sp.c.bRepBodies.item(0); sp.body.name = 'ST-15'; sp.body.material = PLA
spo = [x for x in root.occurrences if x.component.name == 'ST-15 pivot spacer'][0]
# ---------------- stage servo: upright between the rails, shaft at (450,77), body toward -X? body along +Y ----------------
sv = [o for o in root.allOccurrences if o.component.name.startswith('FlashHobby M45CHW') and 'Servos' in o.fullPathName and abs(o.transform2.translation.x * 10 - 175) > 1][0]
m = C.Matrix3D.create(); m.setWithCoordinateSystem(C.Point3D.create(45.0, YC / 10, 0), C.Vector3D.create(0, 1, 0), C.Vector3D.create(-1, 0, 0), C.Vector3D.create(0, 0, 1))
sv.transform2 = m
# ---------------- hardware ----------------
G = [o for o in root.allOccurrences if o.component.name == 'Stage + crossbar brackets'][0].component
for x, y in EARS:     # ear bolts: head on the ear top (Z31.3), nyloc under the bridge plate
    G.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M3x16'], tr(x, y, 31.3)); G.occurrences.addExistingComponent(Mm['Nyloc nut DIN 985 M3'], tr(x, y, 16.0))
allo = list(root.allOccurrences)
sad = [x for x in allo if x.component.name == 'SHCS ISO 4762 M5x12' and abs(x.transform2.translation.x * 10 - 255) < 0.6 and abs(x.transform2.translation.y * 10 - 355) < 0.6][0]
tn = min([x for x in allo if x.component.name == 'T-nut 2020 drop-in M5'], key=lambda x: math.dist(x.transform2.translation.asArray(), sad.transform2.translation.asArray()))
inv_s = sad.transform2.copy(); inv_s.invert(); rel_vt = tn.transform2.copy(); rel_vt.transformBy(inv_s)
up = C.Matrix3D.create(); up.translation = C.Vector3D.create(0, 0, 0.22)
for x, y in RB:
    ms = tr(x, y, 25.8); G.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M5x12'], ms)
    mm = rel_vt.copy(); mm.transformBy(up); mm.transformBy(ms); G.occurrences.addExistingComponent(Mm['T-nut 2020 drop-in M5'], mm)
crc = cr.c
for x, y in HORN: add_in(crc, cr.o, 'SHCS ISO 4762 M3x8', tr(x, y, 51))
add_in(crc, cr.o, 'Nyloc nut DIN 985 M5', tr(450, YC + R, 43))
add_in(crc, cr.o, 'SHCS ISO 4762 M5x25', tr(450, YC + R, 65))
add_in(crc, cr.o, 'ST-08 bearing race spacer', tr(450, YC + R, 64))
slc = sl.c
add_in(slc, sl.o, 'Hex nut ISO 4032 M5', tr(450, PIN_W, 43.6))
add_in(slc, sl.o, 'SHCS ISO 4762 M5x25', tr(450, PIN_W, 65))
add_in(slc, sl.o, 'ST-08 bearing race spacer', tr(450, PIN_W, 64))
rdc = rd.c
for y in (YC + R, PIN_W): add_in(rdc, rd.o, 'F625ZZ flanged bearing 5x16x5', tr(450, y, 59))
m2 = tr(450, PIN_W, 54); spo2 = root.occurrences.addExistingComponent(sp.c, m2)
# ---------------- payload: ST-04 carrier keeps ST-05 / ST-07 well / flask / funnel; tray body removed ----------------
car = [o for o in root.occurrences if o.component.name in ('ST-04', 'ST-PAYLOAD carrier (was ST-04)')][0]
car.component.name = 'ST-PAYLOAD carrier (was ST-04)'
for b in list(car.component.bRepBodies):
    try: b.deleteMe()
    except Exception as e: out.append('tray body delete: %s' % e)
for o in list(root.allOccurrences):
    if o.component.name in ('REF-BOTTLE', 'REF-ROD') and 'ST-PAYLOAD' in o.fullPathName:
        mm = o.transform2; t = mm.translation; t.x = t.x - 75.0; mm.translation = t; o.transform2 = mm     # move the props off the bench (west)
# ---------------- joints ----------------
s1 = [o for o in root.occurrences if o.component.name == 'FRAME-2020 stage rail S1'][0]
slo = [o for o in root.occurrences if o.component.name == 'ST-11 stage sled'][0]
bro = [o for o in root.occurrences if o.component.name == 'ST-12 servo bridge'][0]
cro = [o for o in root.occurrences if o.component.name == 'ST-13 crank'][0]
rdo = [o for o in root.occurrences if o.component.name == 'ST-14 connecting rod'][0]
def rigid(a, b, name):
    ji = root.asBuiltJoints.createInput(a, b, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = name
rigid(bro, s1, 'FIX-ST12-S1'); rigid(car, slo, 'FIX-PAYLOAD-SLED'); rigid(spo, cro, 'FIX-ST15-CRANK'); rigid(spo2, slo, 'FIX-ST15-SLED')
ji = root.asBuiltJoints.createInput(slo, s1, None); ji.setAsSliderJointMotion(F.JointDirections.YAxisJointDirection); root.asBuiltJoints.add(ji).name = 'ST-SLIDE'
hub = [f for f in cro.bRepBodies.item(0).faces if isinstance(f.geometry, C.Cylinder) and abs(f.geometry.radius * 10 - 12.0) < 0.05][0]
ji = root.asBuiltJoints.createInput(cro, bro, F.JointGeometry.createByNonPlanarFace(hub, F.JointKeyPointTypes.MiddleKeyPoint)); ji.setAsRevoluteJointMotion(F.JointDirections.ZAxisJointDirection); root.asBuiltJoints.add(ji).name = 'ST-CRANK'
for p in (sl, br, cr, rd):
    b = p.c.bRepBodies.item(0); out.append('%s %.1f cm3, bodies %d' % (p.c.name, b.volume, p.c.bRepBodies.count))
try: design.snapshots.add()
except Exception: pass
print('\n'.join(out + FLOG))
