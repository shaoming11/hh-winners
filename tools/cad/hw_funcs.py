import adsk.core as C, adsk.fusion as F, math
root = design.rootComponent
VI = lambda mm: C.ValueInput.createByReal(mm / 10)
def P(x, y, z=0): return C.Point3D.create(x / 10, y / 10, z / 10)

LIB=[o for o in root.occurrences if o.component.name=='HW-LIB (masters, hidden)'][0]
lib = LIB.component

def thread(comp, face, internal, force=None):
    tf = comp.features.threadFeatures; q = tf.threadDataQuery
    dia = face.geometry.radius * 2
    ok, des, cls = q.recommendThreadData(dia, internal, 'ISO Metric profile')
    if force: des, cls = force, '6H'
    info = tf.createThreadInfo(internal, 'ISO Metric profile', des, cls)
    fc = C.ObjectCollection.create(); fc.add(face)
    ti = tf.createInput(fc, info); ti.isFullLength = True
    try:
        ti.isModeled = True; tf.add(ti); return des + ' modeled'
    except Exception:
        ti = tf.createInput(fc, info); ti.isFullLength = True; ti.isModeled = False; tf.add(ti); return des + ' cosmetic'

def circ(sk, x, y, r): return sk.sketchCurves.sketchCircles.addByCenterRadius(P(x, y), r / 10)
def ext(comp, prof, dist_mm, op=F.FeatureOperations.NewBodyFeatureOperation, start=0.0):
    ei = comp.features.extrudeFeatures.createInput(prof, op)
    if start: ei.startExtent = F.OffsetStartDefinition.create(VI(start))
    ei.setDistanceExtent(False, VI(dist_mm))
    return comp.features.extrudeFeatures.add(ei)
def plane_at(comp, z):
    pi = comp.constructionPlanes.createInput(); pi.setByOffset(comp.xYConstructionPlane, VI(z))
    pl = comp.constructionPlanes.add(pi); pl.isLightBulbOn = False; return pl
def poly(sk, pts):
    pp = [P(x, y) for x, y in pts]
    for i in range(len(pp)): sk.sketchCurves.sketchLines.addByTwoPoints(pp[i], pp[(i + 1) % len(pp)])
def hexagon(sk, s):
    R = s / math.sqrt(3); poly(sk, [(R * math.cos(math.radians(60 * i)), R * math.sin(math.radians(60 * i))) for i in range(6)])
def smallest(sk): return min(sk.profiles, key=lambda p: p.areaProperties().area)
def largest(sk): return max(sk.profiles, key=lambda p: p.areaProperties().area)
def newc(name):
    o = lib.occurrences.addNewComponent(C.Matrix3D.create()); o.component.name = name; return o.component
def appear(comp, name):
    try:
        al = app.materialLibraries.itemByName('Fusion Appearance Library'); a = al.appearances.itemByName(name)
        da = design.appearances.itemByName(name) or design.appearances.addByCopy(a, name)
        for b in comp.bRepBodies: b.appearance = da
    except Exception:
        pass
def chamfer_edges(comp, edges, d):
    try:
        col = C.ObjectCollection.create()
        for e in edges: col.add(e)
        ci = comp.features.chamferFeatures.createInput2(); ci.chamferEdgeSets.addEqualDistanceChamferEdgeSet(col, VI(d), False)
        comp.features.chamferFeatures.add(ci)
    except Exception:
        pass

SH = {3: (5.5, 3, 2.5), 4: (7.0, 4, 3), 5: (8.5, 5, 4)}
def shcs(d, L):
    c = newc('SHCS ISO 4762 M%dx%d' % (d, L)); dk, k, s = SH[d]
    sk = c.sketches.add(c.xYConstructionPlane); circ(sk, 0, 0, dk / 2); ext(c, sk.profiles.item(0), k)
    sk = c.sketches.add(c.xYConstructionPlane); circ(sk, 0, 0, d / 2); ext(c, sk.profiles.item(0), -L, F.FeatureOperations.JoinFeatureOperation)
    sk = c.sketches.add(plane_at(c, k)); hexagon(sk, s); ext(c, sk.profiles.item(0), -0.6 * d, F.FeatureOperations.CutFeatureOperation)
    b = c.bRepBodies.item(0)
    chamfer_edges(c, [e for e in b.edges if isinstance(e.geometry, C.Circle3D) and abs(e.geometry.radius * 10 - dk / 2) < 0.01 and e.boundingBox.minPoint.z * 10 > k - 0.01], 0.3)
    b = c.bRepBodies.item(0)
    face = [f for f in b.faces if isinstance(f.geometry, C.Cylinder) and abs(f.geometry.radius * 10 - d / 2) < 0.01][0]
    r = thread(c, face, False); b = c.bRepBodies.item(0); b.name = c.name
    appear(c, 'Steel - Satin'); return c, r

def tnut(d):
    c = newc('T-nut 2020 drop-in M%d' % d)
    sk = c.sketches.add(c.xZConstructionPlane)
    pts = [(-5.0, -4.0), (5.0, -4.0), (5.0, -1.5), (3.0, 0.0), (-3.0, 0.0), (-5.0, -1.5)]
    pp = [sk.modelToSketchSpace(P(x, 0, z)) for x, z in pts]
    for i in range(len(pp)): sk.sketchCurves.sketchLines.addByTwoPoints(pp[i], pp[(i + 1) % len(pp)])
    e = c.features.extrudeFeatures.createInput(sk.profiles.item(0), F.FeatureOperations.NewBodyFeatureOperation)
    e.setSymmetricExtent(VI(5.5), True); c.features.extrudeFeatures.add(e)
    sk = c.sketches.add(c.xYConstructionPlane); circ(sk, 0, 0, {4: 3.3, 5: 4.2}[d] / 2)
    ext(c, smallest(sk), -4.0, F.FeatureOperations.CutFeatureOperation)
    b = c.bRepBodies.item(0); face = [f for f in b.faces if isinstance(f.geometry, C.Cylinder)][0]
    r = thread(c, face, True, {4: 'M4x0.7', 5: 'M5x0.8'}[d]); appear(c, 'Steel - Satin'); return c, r

def insert_m5():
    c = newc('Heat-set insert M5 ruthex RX-M5x9.5')
    sk = c.sketches.add(c.xYConstructionPlane); circ(sk, 0, 0, 3.55); ext(c, sk.profiles.item(0), -9.5)
    sk = c.sketches.add(c.xYConstructionPlane); circ(sk, 0, 0, 2.1); ext(c, smallest(sk), -9.5, F.FeatureOperations.CutFeatureOperation)
    b = c.bRepBodies.item(0); face = [f for f in b.faces if isinstance(f.geometry, C.Cylinder) and f.geometry.radius * 10 < 2.5][0]
    r = thread(c, face, True, 'M5x0.8'); appear(c, 'Brass - Polished'); return c, r

def spacer():
    c = newc('ST-08 bearing race spacer')
    sk = c.sketches.add(c.xYConstructionPlane); circ(sk, 0, 0, 4.0); circ(sk, 0, 0, 2.65)
    ext(c, largest(sk), 1.0); c.bRepBodies.item(0).name = 'ST-08'; return c

def bracket():
    c = newc('2020 inside corner bracket')
    sk = c.sketches.add(c.xYConstructionPlane); poly(sk, [(0, 0), (20, 0), (20, -3), (3, -3), (3, -20), (0, -20)])
    ext(c, sk.profiles.item(0), 18, start=1)
    sk = c.sketches.add(c.xYConstructionPlane); poly(sk, [(3, -3), (16, -3), (3, -16)])
    ext(c, sk.profiles.item(0), 3, F.FeatureOperations.JoinFeatureOperation, start=8.5)
    for pl, org in [(c.xZConstructionPlane, (12, 0, 10)), (c.yZConstructionPlane, (0, -12, 10))]:
        sk = c.sketches.add(pl); sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(P(*org)), 0.275)
        e = c.features.extrudeFeatures.createInput(smallest(sk), F.FeatureOperations.CutFeatureOperation)
        e.setSymmetricExtent(VI(10), True); c.features.extrudeFeatures.add(e)
    appear(c, 'Aluminum - Anodized Glossy (Black)'); return c

def servo():
    c = newc('FlashHobby M45CHW + 25T disc horn')
    sk = c.sketches.add(c.xYConstructionPlane); sk.sketchCurves.sketchLines.addTwoPointRectangle(P(-30, -10), P(10, 10)); ext(c, sk.profiles.item(0), 40.5)
    sk = c.sketches.add(plane_at(c, 27.3)); sk.sketchCurves.sketchLines.addTwoPointRectangle(P(-37.5, -9.35), P(17.5, 9.35))
    for x in (-34.3, 14.3):
        for y in (-4.95, 4.95): circ(sk, x, y, 2.25)
    ext(c, largest(sk), 4.0, F.FeatureOperations.JoinFeatureOperation)
    sk = c.sketches.add(plane_at(c, 40.5)); circ(sk, 0, 0, 6); ext(c, sk.profiles.item(0), 1.0, F.FeatureOperations.JoinFeatureOperation)
    sk = c.sketches.add(plane_at(c, 41.5)); circ(sk, 0, 0, 3); ext(c, sk.profiles.item(0), 4.5, F.FeatureOperations.JoinFeatureOperation)
    appear(c, 'Plastic - Matte (Black)')
    hb = c.occurrences.addNewComponent(C.Matrix3D.create()).component; hb.name = '25T Al disc horn (Treedix)'
    sk = hb.sketches.add(hb.xYConstructionPlane); circ(sk, 0, 0, 10)
    for sx in (1, -1):
        for sy in (1, -1): circ(sk, sx * 4.95, sy * 4.95, 1.25)
    circ(sk, 0, 0, 1.6)
    ext(hb, largest(sk), 2.0, start=46.0)
    sk = hb.sketches.add(hb.xYConstructionPlane); circ(sk, 0, 0, 4.5); circ(sk, 0, 0, 1.6); ext(hb, largest(sk), 2.5, start=43.5)
    appear(hb, 'Aluminum - Anodized Glossy (Red)')
    return c

def clamp():
    c = newc('BESSEY CM34DR C-clamp')
    def box(x0, y0, z0, x1, y1, z1):
        sk = c.sketches.add(plane_at(c, z0)); sk.sketchCurves.sketchLines.addTwoPointRectangle(P(x0, y0), P(x1, y1))
        ext(c, sk.profiles.item(0), z1 - z0, F.FeatureOperations.JoinFeatureOperation if c.bRepBodies.count else F.FeatureOperations.NewBodyFeatureOperation)
    box(-6, -52, 20, 6, 48, 30); box(-6, 36, -80, 6, 48, 30); box(-6, -52, -80, 6, 48, -70)
    sk = c.sketches.add(plane_at(c, -70)); circ(sk, 0, -40, 5); ext(c, sk.profiles.item(0), 22)
    sk = c.sketches.add(plane_at(c, -48)); circ(sk, 0, -40, 9); ext(c, sk.profiles.item(0), 3)
    appear(c, 'Paint - Enamel Glossy (Blue)'); return c

