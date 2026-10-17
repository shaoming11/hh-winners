import os, math
exec(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'parts_lib.py')).read())
exec(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'fillet_lib.py')).read())
POCK = [(670.0, 414.0), (717.0, 495.0), (707.0, 587.0)]
Z0, PT, WALL_H = 20.2, 6.0, 10.0
rk = Part('RK-02 reagent rack', (620, 370, Z0))
# convex hull of the three pocket discs (r 36) + a strip over the rail for the two bolts
pts = []
for (x, y) in POCK:
    for k in range(48):
        a = 2 * math.pi * k / 48; pts.append((x + 37 * math.cos(a), y + 37 * math.sin(a)))
for (x, y) in [(662, 440), (688, 440), (662, 560), (688, 560)]: pts.append((x, y))
P2 = pts
def hull(P):
    P = sorted(map(tuple, P))
    def cross(o, a, b): return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in P:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0: lo.pop()
        lo.append(p)
    for p in reversed(P):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0: up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]
H = hull(P2)
sk = rk.c.sketches.add(rk.plane(Z0))
pp = [rk.P(x, y) for x, y in H]
for i in range(len(pp)): sk.sketchCurves.sketchLines.addByTwoPoints(pp[i], pp[(i + 1) % len(pp)])
ei = rk.c.features.extrudeFeatures.createInput(sk.profiles.item(0), NEW); ei.setDistanceExtent(False, VI(PT)); rk.body = rk.c.features.extrudeFeatures.add(ei).bodies.item(0)
for (x, y) in POCK: rk.cyl(x, y, Z0 + PT, Z0 + PT + WALL_H, 34.0, JOIN, 29.5)   # 4.5 mm walls for the 3 mm lead-in (CDR-15)
rk.holes([(675, 455), (675, 545)], Z0 + PT, Z0 - 1, 5.5)
# stiffening rib under the overhang, outside the rail (x > 688)
# no rib: 6 mm plate overhang 68 mm, 20 N place load -> sigma~1 MPa, delta~0.04 mm (CDR M-24 / CDR-27)
rk.body.name = 'RK-02'
def _ce(r, zw):
    b = rk.c.bRepBodies.item(0)
    return [e for e in b.edges if isinstance(e.geometry, (C.Circle3D, C.Arc3D)) and abs(e.geometry.radius * 10 - r) < 0.05 and abs(e.geometry.center.z * 10 + Z0 - zw) < 0.1]
for kind, r, zw, sizes in (('chamfer', 29.5, Z0 + PT + WALL_H, (3.0, 2.0)), ('fillet', 29.5, Z0 + PT, (1.5, 1.0)), ('fillet', 34.0, Z0 + PT, (1.5, 1.0)), ('fillet', 34.0, Z0 + PT + WALL_H, (1.0, 0.5))):
    ed = _ce(r, zw); ok = 0
    for sz in sizes:
        if ed and guarded_add(rk.c, kind, ed, sz): print('RK-02 %s %.1f on r%.1f z%.1f (%d edges)' % (kind, sz, r, zw, len(ed))); ok = 1; break
    if not ok: print('RK-02 %s FAILED r%.1f z%.1f (%d edges)' % (kind, r, zw, len(ed)))
print('RK-02', process4(rk.c, [], r_out=2.0, r_in=1.5, ch=0.5, r_top=1.0))
rk.c.bRepBodies.item(0).material = design.materials.itemByName('PLA (FDM)')
bb = rk.body.boundingBox
print('vol %.1f cm3, size %.0f x %.0f' % (rk.body.volume, (bb.maxPoint.x - bb.minPoint.x) * 10, (bb.maxPoint.y - bb.minPoint.y) * 10))
# move the reagent reference beakers onto the new pockets
reag = [o for o in root.allOccurrences if o.component.name.startswith('EISCO 100 mL PP beaker x3')][0].component
for f in reversed(list(reag.features)):
    try: f.deleteMe()
    except Exception: pass
for (x, y) in POCK:
    p = Part.__new__(Part); p.c = reag; p.o = (0, 0, 0); p.body = None
    p.cyl(x, y, Z0 + PT, Z0 + PT + 74, 28.0, NEW)
for b in reag.bRepBodies: b.material = design.materials.itemByName('Polypropylene')
# move the rack bolts
G = [o for o in root.allOccurrences if o.component.name.startswith('Measuring')][0].component
lib = [o for o in root.occurrences if o.component.name == 'HW-LIB (masters, hidden)'][0].component
Mm = {o.component.name: o.component for o in lib.occurrences}
for o in list(G.occurrences):
    t = o.transform2.translation
    if abs(t.x * 10 - 675) < 0.5 and (o.component.name.startswith('SHCS ISO 4762 M5x10') or o.component.name.startswith('T-nut')): o.deleteMe()
for y in (455, 545):
    m = C.Matrix3D.create(); m.translation = C.Vector3D.create(67.5, y / 10, (Z0 + PT) / 10); o = G.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M5x12'], m)
    m = C.Matrix3D.create(); m.setWithCoordinateSystem(C.Point3D.create(67.5, y / 10, 1.82), C.Vector3D.create(-1, 0, 0), C.Vector3D.create(0, 1, 0), C.Vector3D.create(0, 0, 1))
    o = G.occurrences.addExistingComponent(Mm['T-nut 2020 drop-in M5'], m)
# re-attach the rack to the frame
frame = [o for o in root.occurrences if o.component.name.startswith('FRAME-2020')][0]
rko = [o for o in root.occurrences if o.component.name == 'RK-02 reagent rack'][0]
ji = root.asBuiltJoints.createInput(rko, frame, None); ji.setAsRigidJointMotion(); j = root.asBuiltJoints.add(ji); j.name = 'FIX-RK02-frame'
print('rack rebuilt; bolts M5x12 at y 455 / 545')
