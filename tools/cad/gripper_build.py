import adsk.core as C, adsk.fusion as F, json, os, math
root = design.rootComponent
OPS = json.load(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'gripper_ops.json')))
VI = C.ValueInput.createByReal
NEW, JOIN, CUT = F.FeatureOperations.NewBodyFeatureOperation, F.FeatureOperations.JoinFeatureOperation, F.FeatureOperations.CutFeatureOperation
log = []
# rest pose
arms = {}
for tag in 'AB':
    a = [o for o in root.occurrences if o.component.name == 'REF-SO101-STOCK-' + tag][0]; arms[tag] = a
    asmc = a.childOccurrences.item(0).component
    for j in asmc.asBuiltJoints:
        if j.name.startswith('ARM'): j.jointMotion.rotationValue = 0
# old gripper parts from a previous run
for o in list(root.occurrences):
    if o.component.name.startswith(('GR-01', 'GR-02', 'GR-03')): o.deleteMe()
for j in list(root.asBuiltJoints):
    if j.name.startswith('FIX-GR'): j.deleteMe()
mats = design.materials; lib = app.materialLibraries.itemByName('Fusion Material Library')
def material(name):
    m = mats.itemByName('TPU 95A (FDM)' if name == 'TPU' else name)
    if m: return m
    if name == 'TPU':
        base = mats.itemByName('Plastic') or lib.materials.itemByName('Plastic')
        m = mats.addByCopy(base, 'TPU 95A (FDM)') if base else None
        return m
    return None
def plane_at(comp, x):
    sg = comp.yZConstructionPlane.geometry.normal.x
    pi = comp.constructionPlanes.createInput(); pi.setByOffset(comp.yZConstructionPlane, VI(x / 10 * sg)); pl = comp.constructionPlanes.add(pi); pl.isLightBulbOn = False
    return pl, sg
def extrude(comp, o, body):
    pl, sg = plane_at(comp, o['x0'])
    sk = comp.sketches.add(pl); sk.isVisible = False
    def P(y, z): return sk.modelToSketchSpace(C.Point3D.create(o['x0'] / 10, y / 10, z / 10))
    if o['op'] == 'cutring':
        y, z = o['c']; r = o['r']
        sk.sketchCurves.sketchCircles.addByCenterRadius(P(y, z), r / 10)
        sk.sketchCurves.sketchLines.addTwoPointRectangle(P(y - 200, z - 200), P(y + 200, z + 200))
        prof = max(list(sk.profiles), key=lambda p: p.areaProperties().area)
        kind = CUT
    else:
        pts = [P(y, z) for y, z in o['poly']]
        L = sk.sketchCurves.sketchLines
        for i in range(len(pts)): L.addByTwoPoints(pts[i], pts[(i + 1) % len(pts)])
        prof = max(list(sk.profiles), key=lambda p: p.areaProperties().area)
        kind = {'new': NEW, 'join': JOIN, 'cut': CUT}[o['op']]
    ei = comp.features.extrudeFeatures.createInput(prof, kind if (body or kind == NEW) else NEW)
    ei.setDistanceExtent(False, VI((o['x1'] - o['x0']) / 10 * sg))
    if body and kind != NEW: ei.participantBodies = [body]
    f = comp.features.extrudeFeatures.add(ei)
    return f.bodies.item(0) if kind == NEW else body
for tag in 'AB':
    asm = arms[tag].childOccurrences.item(0)
    src = {k: [o for o in asm.childOccurrences if o.name.startswith(k)][0] for k in ('Wrist_Roll_Follower', 'Moving_Jaw')}
    for part in OPS[tag]:
        occ = root.occurrences.addNewComponent(C.Matrix3D.create()); comp = occ.component; comp.name = part['name']
        body = None
        if part['copy']:
            s = src[part['copy']]; sb = s.bRepBodies.item(0)
            tb = C.Application.get() and F.TemporaryBRepManager.get().copy(sb)
            bf = comp.features.baseFeatures.add(); bf.startEdit(); body = comp.bRepBodies.add(tb, bf); bf.finishEdit(); body = comp.bRepBodies.item(0)
            for b in s.bRepBodies: b.isLightBulbOn = False
        for o in part['ops']:
            try: body = extrude(comp, o, body)
            except Exception as e: log.append('%s op %s failed: %s' % (part['name'], o['op'], e))
        body = comp.bRepBodies.item(0); body.name = part['name'].split(' (')[0][:5]
        m = material(part['mat'])
        if m:
            for b in comp.bRepBodies: b.material = m
        # rigidly attach to the arm link that carried the stock part
        target = src[part['copy'] or ('Wrist_Roll_Follower' if 'fixed' in part['name'] else 'Moving_Jaw')]
        try:
            ji = root.asBuiltJoints.createInput(occ, target, None); ji.setAsRigidJointMotion(); j = root.asBuiltJoints.add(ji); j.name = 'FIX-GR-%s-%s' % (tag, part['name'][:5])
        except Exception as e: log.append('joint %s: %s' % (part['name'], e))
        bb = body.boundingBox
        log.append('%-36s bodies %d vol %.1f cm3 (%.0f,%.0f,%.0f)-(%.0f,%.0f,%.0f)' % (part['name'], comp.bRepBodies.count, body.volume, *[v * 10 for v in bb.minPoint.asArray()], *[v * 10 for v in bb.maxPoint.asArray()]))
print('\n'.join(log))
