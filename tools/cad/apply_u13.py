"""Apply the planner-verified layout (Update 13) to the CAD: X rails +74, arms to their verified bases, scale onto E6,
carousel+auger unit loose to the east (rot 220.6 deg), RK-02 -> 3 x RK-03 stands, cleanup of obsolete items."""
import adsk.core as C, adsk.fusion as F, math
root = design.rootComponent
out = []
def V(x, y, z=0): return C.Vector3D.create(x / 10, y / 10, z / 10)
def T(dx, dy, dz=0):
    m = C.Matrix3D.create(); m.translation = V(dx, dy, dz); return m
def R(deg, cx, cy):
    m = C.Matrix3D.create(); m.setToRotation(math.radians(deg), C.Vector3D.create(0, 0, 1), C.Point3D.create(cx / 10, cy / 10, 0)); return m
def ctr(o):
    bb = o.boundingBox; return ((bb.minPoint.x + bb.maxPoint.x) * 5, (bb.minPoint.y + bb.maxPoint.y) * 5, (bb.minPoint.z + bb.maxPoint.z) * 5)
def kill_joints(occs):
    s = set(o.entityToken for o in occs); n = 0
    for j in list(root.asBuiltJoints) + list(root.joints):
        try:
            a, b = j.occurrenceOne, j.occurrenceTwo
            if (a and a.entityToken in s) or (b and b.entityToken in s): j.deleteMe(); n += 1
        except Exception: pass
    return n
def move(occs, M, label):
    occs = [o for o in occs if o is not None]
    kj = kill_joints(occs); ok = 0
    for o in occs:
        g = o.isGrounded
        if g: o.isGrounded = False
        m = o.transform2.copy(); m.transformBy(M); o.transform2 = m
        if g: o.isGrounded = True
        ok += 1
    out.append('%-28s moved %d occurrences (%d joints removed)' % (label, ok, kj))
def rootocc(name): return [o for o in root.occurrences if o.component.name == name]
def grp(name): return [o for o in root.allOccurrences if o.component.name == name][0]
def kids(gname, pred):
    g = grp(gname); return [c for c in g.childOccurrences if pred(c)]
REFG = rootocc('REF')[0]
def refkid(name): return [c for c in REFG.childOccurrences if c.component.name == name]
# ---------- 1. X rails +74 ----------
frame = rootocc('FRAME-2020 (bought, 4 x 400 mm)')[0]
kill_joints([frame])
fc = frame.component
bodies = C.ObjectCollection.create()
for b in fc.bRepBodies:
    if b.name in ('RAIL-X-FRONT', 'RAIL-X-BACK'): bodies.add(b)
mi = fc.features.moveFeatures.createInput2(bodies); mi.defineAsFreeMove(T(0, 74)); fc.features.moveFeatures.add(mi)
out.append('X rails moved +74 (%d bodies)' % bodies.count)
fb = kids('Frame brackets', lambda c: 470 < ctr(c)[1] < 615)
move(fb, T(0, 74), 'frame brackets at X rails')
# ---------- 2. arms ----------
DA = (397.4 - 330.0, 74.0); DB = (604.8 - 570.0, 74.0)
armA = rootocc('REF-SO101-STOCK-A') + refkid('REF-ARM-A') + [o for o in root.occurrences if o.component.name.startswith('GR-') and o.component.name.endswith('(A)') or o.component.name.startswith('GR-03') and '(A ' in o.component.name]
armB = rootocc('REF-SO101-STOCK-B') + refkid('REF-ARM-B') + [o for o in root.occurrences if o.component.name.startswith('GR-') and o.component.name.endswith('(B)') or o.component.name.startswith('GR-03') and '(B ' in o.component.name]
mounts = kids('Arm mounts', lambda c: True)
move(armA + [c for c in mounts if ctr(c)[0] < 450], T(*DA), 'arm A (pourer, west)')
move(armB + [c for c in mounts if ctr(c)[0] >= 450], T(*DB), 'arm B (transfer, east)')
for o in rootocc('CAL-01 arm calibration block'):
    o.deleteMe()
out.append('CAL-01 removed (dropped)')
# ---------- 3. scale onto E6 ----------
meas = grp('Measuring + auger station')
sc_hw = [c for c in meas.childOccurrences if 390 < ctr(c)[0] < 515 and 430 < ctr(c)[1] < 525]
scale = rootocc('WS-01 scale base') + rootocc('WS-02 scale pan') + [o for o in rootocc('ANIM-beaker100') if 440 < ctr(o)[0] < 500 and 440 < ctr(o)[1] < 510] + sc_hw
move(scale, T(152, -68), 'scale -> E6 south (620,407)')
for o in rootocc('SF-01 scale foot (printed 2020 stub)') + rootocc('RK-03 reagent rack (free-standing)'): o.deleteMe()
# ---------- 4. carousel + auger unit ----------
aug_hw = [c for c in meas.childOccurrences if ctr(c)[0] < 140 and 240 < ctr(c)[1] < 395]
servos = grp('Servos'); car_servo = [c for c in servos.childOccurrences if ctr(c)[0] < 300 and ctr(c)[1] > 250]
auger = rootocc('FRAME-2020 aux rail E5') + rootocc('PS-01 auger post') + rootocc('DH-01 yeast auger head') + rootocc('DH-02 auger screw') + aug_hw
move(auger, T(4, 0), 'auger +4 (outlet over r84 pocket)')
carousel = rootocc('PRINT') + rootocc('TT-02-deck') + rootocc('TT-03 horn spacer') + rootocc('TT-04 beaker locator ring') + rootocc('REF-BEAKERS-TT (100 mL x4)') + refkid('REF-LAZY-SUSAN') + refkid('REF-SERVO-TT') + car_servo
M = R(220.6, 175, 370); M.transformBy(T(807.9 - 175, 523.5 - 370))
move(carousel + auger, M, 'carousel unit (rot 220.6)')
# saddle bolts / FX-01 that tied the carousel and E5 to Y-left are unused now
sb = kids('Saddle bolts', lambda c: ctr(c)[0] < 300)
for c in sb: c.deleteMe()
for o in rootocc('FX-01 E5 joiner plate'): o.deleteMe()
for c in [c for c in meas.childOccurrences if 200 < ctr(c)[0] < 270 and 285 < ctr(c)[1] < 340 and ctr(c)[2] > 18]: c.deleteMe()
out.append('removed %d saddle bolts + FX-01 and its screws' % len(sb))
# ---------- 5. rack: RK-02 -> 3 stands ----------
for o in rootocc('RK-02 reagent rack'): o.deleteMe()
for c in [c for c in meas.childOccurrences if abs(ctr(c)[0] - 675) < 8 and 440 < ctr(c)[1] < 560]: c.deleteMe()
old_b = [o for o in root.allOccurrences if o.component.name.startswith('EISCO 100 mL PP beaker x3')]
for o in old_b: o.isLightBulbOn = False
st = rootocc('RK-03 reagent stand (x3, free-standing)')[0]
b100 = [o for o in root.occurrences if o.component.name == 'ANIM-beaker100'][0].component
P = [(192.3, 394.6), (134.6, 477.1), (108.5, 574.4)]
st.transform2 = T(*P[0]); comp = st.component
for x, y in P[1:]: root.occurrences.addExistingComponent(comp, T(x, y))
for x, y in P: root.occurrences.addExistingComponent(b100, T(x, y, 60.2))
out.append('RK-03 stands placed at %s (+ 3 x 100 mL beakers at Z60.2); old 3-beaker body hidden (%d)' % (P, len(old_b)))
# ---------- 6. misc ----------
move(rootocc('EL-02 electronics box (bought ABS)'), T(-215, 0), 'EL-02 box west')
for c in refkid('REF-BIN'): c.isLightBulbOn = False
try: design.snapshots.add(); out.append('snapshot ok')
except Exception as e: out.append('snapshot: %s' % e)
print('\n'.join(out))
