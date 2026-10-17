import adsk.core as C, adsk.fusion as F
root = design.rootComponent
out = []
def occ(name, nested=False):
    src = root.allOccurrences if nested else root.occurrences
    r = [o for o in src if o.component.name == name]
    return r
def one(name, nested=False): return occ(name, nested)[0]
def rigid(a, b, name):
    try:
        ji = root.asBuiltJoints.createInput(a, b, None); ji.setAsRigidJointMotion(); j = root.asBuiltJoints.add(ji); j.name = name; out.append('rigid    %s' % name)
    except Exception as e: out.append('FAILED   %s: %s' % (name, str(e)[:80]))
def cyl_face(o, r_mm, near=None, axis=None):
    best = None
    for b in o.bRepBodies:
        for f in b.faces:
            g = f.geometry
            if isinstance(g, C.Cylinder) and abs(g.radius * 10 - r_mm) < 0.15:
                if axis and abs(abs(sum(p * q for p, q in zip(g.axis.asArray(), axis))) - 1) > 0.02: continue
                d = 0 if near is None else ((g.origin.x * 10 - near[0]) ** 2 + (g.origin.y * 10 - near[1]) ** 2)
                if best is None or d < best[0]: best = (d, f)
    return best[1] if best else None
def revolute(a, b, face, name):
    try:
        geo = F.JointGeometry.createByNonPlanarFace(face, F.JointKeyPointTypes.MiddleKeyPoint)
        ji = root.asBuiltJoints.createInput(a, b, geo); ji.setAsRevoluteJointMotion(F.JointDirections.CustomJointDirection, face)
        j = root.asBuiltJoints.add(ji); j.name = name; out.append('REVOLUTE %s' % name)
    except Exception as e: out.append('FAILED   %s: %s' % (name, str(e)[:100]))
# clear stale fixed joints we are about to redefine (keep the stage ones)
keep = {'FIX-ST12-S1', 'FIX-ST15-CRANK', 'ST-CRANK', 'FIX-PAYLOAD-SLED', 'FIX-ST15-SLED', 'ST-SLIDE'}
for j in list(root.asBuiltJoints):
    if j.name not in keep: j.deleteMe()
frame = one('FRAME-2020 (bought, 4 x 400 mm)'); table = one('REF-TABLE', True)
# frame members
for nm, jn in (('FRAME-2020 crossbar E6', 'FIX-E6-frame'), ('FRAME-2020 stage rail S1', 'FIX-S1-frame'), ('FRAME-2020 stage rail S2', 'FIX-S2-frame')): rigid(one(nm), frame, jn)
# arms: base on the X rails; our gripper parts ride the stock links (which keep their 6 revolute joints); stock jaws hidden
for X in ('A', 'B'):
    st = one('REF-SO101-STOCK-' + X); assy = st.childOccurrences.item(0)
    rigid(st, frame, 'FIX-ARM%s-rails' % X)
    fol = [c for c in assy.childOccurrences if c.component.name.startswith('Wrist_Roll_Follower')][0]
    mj = [c for c in assy.childOccurrences if c.component.name.startswith('Moving_Jaw')][0]
    fol.isLightBulbOn = False; mj.isLightBulbOn = False
    g1 = one('GR-01 gripper body (%s)' % X); g2 = one('GR-02 moving jaw (%s)' % X)
    rigid(g1, fol, 'FIX-GR01%s-wristroll' % X); rigid(g2, mj, 'FIX-GR02%s-gripperjaw' % X)
    rigid(one('GR-03 fin-ray finger TPU (%s fixed)' % X), g1, 'FIX-GR03%s-fixed' % X)
    rigid(one('GR-03 fin-ray finger TPU (%s moving)' % X), g2, 'FIX-GR03%s-moving' % X)
out.append('stock SO-101 jaws hidden (replaced by GR-01/GR-02)')
# stage: connecting rod pivots
rod = one('ST-14 connecting rod'); crank = one('ST-13 crank'); sled = one('ST-11 stage sled')
f1 = cyl_face(rod, 8.0, (450, 127), (0, 0, 1)) or cyl_face(rod, 2.5, (450, 127), (0, 0, 1))
f2 = cyl_face(rod, 8.0, (450, 207), (0, 0, 1)) or cyl_face(rod, 2.5, (450, 207), (0, 0, 1))
if f1: revolute(rod, crank, f1, 'ST-ROD-crankpin')
if f2: revolute(rod, sled, f2, 'ST-ROD-sledpin')
# scale on E6
ws1 = one('WS-01 scale base'); ws2 = one('WS-02 scale pan')
rigid(ws1, one('FRAME-2020 crossbar E6'), 'FIX-WS01-E6'); rigid(ws2, ws1, 'FIX-WS02-WS01')
lc = [o for o in root.allOccurrences if o.component.name.startswith('Load cell')]
if lc: rigid(lc[0], ws1, 'FIX-LOADCELL-WS01')
b100 = occ('ANIM-beaker100')
for o in b100:
    bb = o.boundingBox; cx, cy, cz = (bb.minPoint.x + bb.maxPoint.x) * 5, (bb.minPoint.y + bb.maxPoint.y) * 5, bb.minPoint.z * 10
    if abs(cx - 620) < 5 and abs(cy - 407) < 5: rigid(o, ws2, 'FIX-BEAKER-scale')
# carousel unit (loose on the table)
tt1 = one('TT-01', True); tt2 = one('TT-02-deck')
rigid(tt1, table, 'FIX-TT01-table')
ls = occ('REF-LAZY-SUSAN', True)
if ls: rigid(ls[0], tt1, 'FIX-LAZYSUSAN-TT01')
cs = [o for o in root.allOccurrences if o.component.name == 'FlashHobby M45CHW + 25T disc horn' and o.boundingBox.minPoint.x * 10 > 600]
if cs: rigid(cs[0], tt1, 'FIX-CAROUSELSERVO-TT01')
fc = cyl_face(tt2, 4.5, (807.9, 523.5), (0, 0, 1))
if fc: revolute(tt2, tt1, fc, 'CAROUSEL-spin')
else: out.append('FAILED   CAROUSEL-spin: no centre bore face')
rigid(one('TT-03 horn spacer'), tt2, 'FIX-TT03-TT02'); rigid(one('TT-04 beaker locator ring'), tt2, 'FIX-TT04-TT02')
rigid(one('REF-BEAKERS-TT (100 mL x4)'), one('TT-04 beaker locator ring'), 'FIX-BEAKERS-TT04')
# auger unit
e5 = one('FRAME-2020 aux rail E5'); ps = one('PS-01 auger post'); dh1 = one('DH-01 yeast auger head'); dh2 = one('DH-02 auger screw')
rigid(e5, table, 'FIX-E5-table'); rigid(ps, e5, 'FIX-PS01-E5'); rigid(dh1, ps, 'FIX-DH01-PS01')
fs = [o for o in root.allOccurrences if o.component.name.startswith('Feetech FB5311M')]
if fs: rigid(fs[0], dh1, 'FIX-AUGERSERVO-DH01')
fa = cyl_face(dh2, 11.0)
if fa: revolute(dh2, dh1, fa, 'AUGER-spin')
# loose stations
for i, o in enumerate(occ('RK-03 reagent stand (x3, free-standing)')):
    rigid(o, table, 'FIX-RK03-%d-table' % (i + 1))
    bb = o.boundingBox; cx, cy = (bb.minPoint.x + bb.maxPoint.x) * 5, (bb.minPoint.y + bb.maxPoint.y) * 5
    for b in b100:
        bb2 = b.boundingBox
        if abs((bb2.minPoint.x + bb2.maxPoint.x) * 5 - cx) < 5 and abs((bb2.minPoint.y + bb2.maxPoint.y) * 5 - cy) < 5: rigid(b, o, 'FIX-BEAKER-RK03-%d' % (i + 1))
for nm in ('EL-02 electronics box (bought ABS)', 'CAL-02 calibration probe', 'REF-GRAD-CYL-100 (glass)'):
    rigid(one(nm), table, 'FIX-%s-table' % nm.split()[0])
try: design.snapshots.add()
except Exception: pass
print('\n'.join(out))
print('TOTAL joints:', root.asBuiltJoints.count, 'revolute:', [j.name for j in root.asBuiltJoints if j.jointMotion.jointType == 1], 'slider:', [j.name for j in root.asBuiltJoints if j.jointMotion.jointType == 2])
