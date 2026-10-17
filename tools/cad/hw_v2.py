"""CDR hardware: ISO 7380 M4x20 front row (CDR-11), M3x20 DH-01 (CDR-01), deck M3x12 (CDR-24),
M5 saddle bolts at the v2 positions/counterbores (CDR-03/06), materials (CDR-22)."""
import os, math
exec(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'hw_funcs.py')).read())
log = []
LIB.isLightBulbOn = True
M = {o.component.name: o.component for o in lib.occurrences}
# --- ISO 7380 M4x20 button head master ---
if 'BHCS ISO 7380 M4x20' not in M:
    c = newc('BHCS ISO 7380 M4x20')
    sk = c.sketches.add(c.xZConstructionPlane)
    pts = [(0, 2.2), (1.9, 2.2), (3.3, 1.5), (3.8, 0.5), (3.8, 0), (2.0, 0), (2.0, -20), (0, -20)]
    pp = [sk.modelToSketchSpace(P(x, 0, z)) for x, z in pts]
    for i in range(len(pp)): sk.sketchCurves.sketchLines.addByTwoPoints(pp[i], pp[(i + 1) % len(pp)])
    ax = sk.sketchCurves.sketchLines.addByTwoPoints(sk.modelToSketchSpace(P(0, 0, 5)), sk.modelToSketchSpace(P(0, 0, -25))); ax.isConstruction = True
    ri = c.features.revolveFeatures.createInput(sk.profiles.item(0), ax, F.FeatureOperations.NewBodyFeatureOperation); ri.setAngleExtent(False, C.ValueInput.createByString('360 deg')); c.features.revolveFeatures.add(ri)
    sk3 = c.sketches.add(plane_at(c, 2.2)); hexagon(sk3, 2.5); ext(c, sk3.profiles.item(0), -1.3, F.FeatureOperations.CutFeatureOperation)
    b = c.bRepBodies.item(0)
    face = [f for f in b.faces if isinstance(f.geometry, C.Cylinder) and abs(f.geometry.radius * 10 - 2.0) < 0.01][0]
    log.append('BHCS thread: %s' % thread(c, face, False)); appear(c, 'Steel - Satin'); c.bRepBodies.item(0).material = design.materials.itemByName('Steel')
    M['BHCS ISO 7380 M4x20'] = c
if 'SHCS ISO 4762 M3x20' not in M:
    c, r = shcs(3, 20); c.bRepBodies.item(0).material = design.materials.itemByName('Steel'); M['SHCS ISO 4762 M3x20'] = c; log.append('M3x20 master built')
LIB.isLightBulbOn = False
# --- front-row arm screws -> button heads seated on the boss at Z36.2 ---
G = [o for o in root.allOccurrences if o.component.name == 'Arm mounts'][0].component
n = 0
for o in list(G.occurrences):
    t = o.transform2.translation
    if o.component.name.startswith('CSK ISO 10642 M4x20') and abs(t.y * 10 - 508.5) < 1.0:
        x, y = t.x, t.y; o.deleteMe()
        m = C.Matrix3D.create(); m.translation = C.Vector3D.create(x, y, 3.62); G.occurrences.addExistingComponent(M['BHCS ISO 7380 M4x20'], m); n += 1
log.append('front-row CSK -> ISO 7380 button head: %d' % n)
# --- DH-01 screws M3x12 -> M3x20 (head seat Z148) ---
MS = [o for o in root.allOccurrences if o.component.name.startswith('Measuring')][0].component
n = 0
for o in list(MS.occurrences):
    t = o.transform2.translation
    if o.component.name == 'SHCS ISO 4762 M3x12' and t.z * 10 > 140:
        x, y = t.x, t.y; o.deleteMe()
        m = C.Matrix3D.create(); m.translation = C.Vector3D.create(x, y, 14.8); MS.occurrences.addExistingComponent(M['SHCS ISO 4762 M3x20'], m); n += 1
log.append('DH-01 M3x12 -> M3x20: %d' % n)
# --- AG-01 saddle bolts to (255,300)/(255,322), heads in the 1.5 mm counterbores (Z26.5) ---
ag = [o for o in MS.occurrences if abs(o.transform2.translation.x * 10 - 255) < 0.5 and 280 < o.transform2.translation.y * 10 < 340]
for o in list(ag): o.deleteMe()
for y in (300, 322):
    m = C.Matrix3D.create(); m.translation = C.Vector3D.create(25.5, y / 10, 2.65); MS.occurrences.addExistingComponent(M['SHCS ISO 4762 M5x12'], m)
    m = C.Matrix3D.create(); m.translation = C.Vector3D.create(25.5, y / 10, 1.82); MS.occurrences.addExistingComponent(M['T-nut 2020 drop-in M5'], m)
log.append('AG-01 bolts moved (%d old removed)' % len(ag))
# --- WS-01 saddle bolts into the counterbores (seat Z26.5) ---
n = 0
for o in root.allOccurrences:
    if o.component.name == 'SHCS ISO 4762 M5x12':
        t = o.transform2.translation
        if abs(t.y * 10 - 508.5) < 0.6 and (abs(t.x * 10 - 410) < 0.6 or abs(t.x * 10 - 465) < 0.6) and abs(t.z * 10 - 28) < 0.6:
            m = o.transform2; tt = m.translation; tt.z = 2.65; m.translation = tt; o.transform2 = m; n += 1
log.append('WS-01 bolts seated in counterbores: %d' % n)
# --- deck screws M3x10 -> M3x12 (lengthen the shank of the deck copy) ---
dk = [o for o in root.allOccurrences if o.component.name.startswith('SHCS ISO 4762 M3x10 (deck)')]
if dk:
    c = dk[0].component; ch = 0
    for f in c.features.extrudeFeatures:
        try:
            ex = f.extentOne
            if abs(abs(ex.distance.value) - 1.0) < 1e-4:
                ex.distance.expression = ('-' if ex.distance.value < 0 else '') + '12 mm'; ch += 1
        except Exception: pass
    c.name = 'SHCS ISO 4762 M3x12 (deck)'; log.append('deck screws lengthened (%d features), %d instances' % (ch, len(dk)))
try: design.snapshots.add()
except Exception: pass
# --- materials (CDR-22) ---
lm = app.materialLibraries.itemByName('Fusion Material Library')
def mat(name, libname):
    m = design.materials.itemByName(name)
    if m: return m
    src = lm.materials.itemByName(libname)
    return design.materials.addByCopy(src, name) if src else None
glass = design.materials.itemByName('Glass'); ptfe = mat('Polytetrafluoroethylene', 'Polytetrafluoroethylene'); pla = design.materials.itemByName('PLA (FDM)')
fixes = {'REF-ROD': glass, 'REF-GLIDE-1': ptfe, 'REF-GLIDE-2': ptfe, 'REF-GLIDE-3': ptfe, 'REF-GLIDE-4': ptfe}
for o in root.allOccurrences:
    m = fixes.get(o.component.name)
    if m:
        for b in o.component.bRepBodies: b.material = m
log.append('REF-ROD -> %s, glides -> %s' % (glass.name if glass else None, ptfe.name if ptfe else None))
print('\n'.join(log))
