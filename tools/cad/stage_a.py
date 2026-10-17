"""Stage v2 part A: M5 nut masters, E6 crossbar + S1/S2 stage rails (with brackets), remove the four-bar."""
import os, math
exec(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'hw_funcs.py')).read())
out = []
# ---- M5 nut masters ----
names = [o.component.name for o in lib.occurrences]
LIB.isLightBulbOn = True
def nut(name, af, h):
    c = newc(name)
    sk = c.sketches.add(c.xYConstructionPlane); hexagon(sk, af); ext(c, sk.profiles.item(0), h)
    sk = c.sketches.add(c.xYConstructionPlane); circ(sk, 0, 0, 2.1); ext(c, smallest(sk), h, F.FeatureOperations.CutFeatureOperation)
    b = c.bRepBodies.item(0); face = [f for f in b.faces if isinstance(f.geometry, C.Cylinder) and abs(f.geometry.radius * 10 - 2.1) < 0.01][0]
    r = thread(c, face, True, force='M5x0.8'); c.bRepBodies.item(0).material = design.materials.itemByName('Steel'); appear(c, 'Steel - Satin'); return r
if 'Hex nut ISO 4032 M5' not in names: out.append('M5 hex nut ' + nut('Hex nut ISO 4032 M5', 8.0, 4.7))
if 'Nyloc nut DIN 985 M5' not in names: out.append('M5 nyloc ' + nut('Nyloc nut DIN 985 M5', 8.0, 5.0))
for L in (12, 16, 25):
    pass
if 'SHCS ISO 4762 M5x25' not in names:
    c, r = shcs(5, 25); c.bRepBodies.item(0).material = design.materials.itemByName('Steel'); out.append('M5x25 ' + r)
LIB.isLightBulbOn = False
Mm = {o.component.name: o.component for o in lib.occurrences}
# ---- remove the four-bar stage ----
root = design.rootComponent
kill_names = ('ST-02', 'ST-03', 'ST-09 stop-post TPU sleeve', 'GA-01 stage angle gauge', 'ST-01', 'ST-06')
for j in list(root.asBuiltJoints):
    if j.name.startswith(('ST-', 'FIX-ST')): j.deleteMe()
for g in list(root.rigidGroups):
    if g.name in ('HW-crank', 'HW-tray'): g.deleteMe()
n = 0
for o in list(root.allOccurrences):
    try:
        nm = o.component.name; p = o.fullPathName
    except Exception: continue
    if nm in kill_names or ('Four-bar' in p and o.childOccurrences.count == 0) or nm.startswith(('REF-GLIDE', 'REF-BEARING-T')) or nm in ('REF-BEAKER-MIX',):
        try: o.deleteMe(); n += 1
        except Exception as e: out.append('could not delete %s: %s' % (nm, e))
for o in list(root.allOccurrences):
    try:
        if o.component.name.startswith('SHCS ISO 4762 M3x12') and 'Four-bar' in o.fullPathName: o.deleteMe(); n += 1
    except Exception: pass
out.append('deleted %d four-bar occurrences' % n)
# ---- frame additions: copy rail bodies ----
frame = [x for x in root.occurrences if x.component.name.startswith('FRAME-2020 (')][0]
def rail_copy(src_name, dx, dy, name, body_name):
    for o in list(root.occurrences):
        if o.component.name == name: o.deleteMe()
    rf = [b for b in frame.component.bRepBodies if b.name == src_name][0]
    tb = F.TemporaryBRepManager.get().copy(rf)
    mv = C.Matrix3D.create(); mv.translation = C.Vector3D.create(dx / 10, dy / 10, 0); F.TemporaryBRepManager.get().transform(tb, mv)
    eo = root.occurrences.addNewComponent(C.Matrix3D.create()); ec = eo.component; ec.name = name
    bf = ec.features.baseFeatures.add(); bf.startEdit(); ec.bRepBodies.add(tb, bf); bf.finishEdit()
    b = ec.bRepBodies.item(0); b.name = body_name; b.material = design.materials.itemByName('Aluminum 6061')
    for j in list(root.asBuiltJoints):
        if j.name == 'FIX-' + body_name: j.deleteMe()
    ji = root.asBuiltJoints.createInput(eo, frame, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-' + body_name
    bb = b.boundingBox; out.append('%s %s-%s' % (body_name, [round(v * 10) for v in bb.minPoint.asArray()], [round(v * 10) for v in bb.maxPoint.asArray()]))
rail_copy('RAIL-X-FRONT', 0, -68.5, 'FRAME-2020 crossbar E6', 'RAIL-E6')          # X265-665, Y430-450
rail_copy('RAIL-Y-LEFT', 115, -260, 'FRAME-2020 stage rail S1', 'RAIL-S1')        # X360-380, Y30-430
rail_copy('RAIL-Y-LEFT', 275, -260, 'FRAME-2020 stage rail S2', 'RAIL-S2')        # X520-540, Y30-430
# ---- brackets with their screws + T-nuts (relative placement copied from a frame bracket) ----
allo = list(root.allOccurrences)
br0 = [x for x in allo if x.component.name == '2020 inside corner bracket' and 'Frame brackets' in x.fullPathName and abs(x.transform2.translation.x * 10 - 265) < 0.5 and abs(x.transform2.translation.y * 10 - 498.5) < 0.5][0]
inv0 = br0.transform2.copy(); inv0.invert()
rel = []
for x in allo:
    if x.component.name in ('SHCS ISO 4762 M5x8', 'T-nut 2020 drop-in M5') and 'Frame brackets' in x.fullPathName and math.dist([v * 10 for v in x.transform2.translation.asArray()], [v * 10 for v in br0.transform2.translation.asArray()]) < 30:
        r = x.transform2.copy(); r.transformBy(inv0); rel.append((x.component.name, r))
HW = [o for o in root.occurrences if o.component.name == 'HARDWARE (bought)'][0].component
grp = [o for o in HW.occurrences if o.component.name == 'Stage + crossbar brackets']
G = grp[0].component if grp else HW.occurrences.addNewComponent(C.Matrix3D.create()).component
G.name = 'Stage + crossbar brackets'
for o in list(G.occurrences): o.deleteMe()
def bracket_at(x, y, xa, ya):
    m = C.Matrix3D.create(); m.setWithCoordinateSystem(C.Point3D.create(x / 10, y / 10, 0), C.Vector3D.create(*xa), C.Vector3D.create(*ya), C.Vector3D.create(0, 0, 1))
    G.occurrences.addExistingComponent(Mm['2020 inside corner bracket'], m)
    for nm, r in rel:
        mm = r.copy(); mm.transformBy(m); G.occurrences.addExistingComponent(Mm[nm], mm)
I, A, B, Cc = ((1, 0, 0), (0, 1, 0)), ((0, 1, 0), (-1, 0, 0)), ((-1, 0, 0), (0, -1, 0)), ((0, -1, 0), (1, 0, 0))
# E6 to the Y rails (inside corners on both faces of E6)
bracket_at(265, 450, *A); bracket_at(265, 430, *I); bracket_at(665, 450, *B); bracket_at(665, 430, *Cc)
# stage rails to E6 south face (Y430)
bracket_at(360, 430, *Cc); bracket_at(380, 430, *I); bracket_at(520, 430, *Cc); bracket_at(540, 430, *I)
out.append('brackets placed: 8 (+%d parts each)' % len(rel))
print('\n'.join(out))
