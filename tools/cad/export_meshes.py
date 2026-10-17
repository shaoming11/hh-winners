import adsk.core as C, adsk.fusion as F, math, json, os
root = design.rootComponent
OUT = os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'meshes.json')
def tris(body, tol=0.08):
    calc = body.meshManager.createMeshCalculator(); calc.surfaceTolerance = tol   # cm
    m = calc.calculate()
    pts = m.nodeCoordinatesAsDouble; idx = m.nodeIndices
    P = [(pts[i] * 10, pts[i + 1] * 10, pts[i + 2] * 10) for i in range(0, len(pts), 3)]
    return [[P[idx[k]], P[idx[k + 1]], P[idx[k + 2]]] for k in range(0, len(idx), 3)]
data = {'arms': {}, 'scene': [], 'carousel': []}
for tag in 'AB':
    for j in [o for o in root.occurrences if o.component.name == 'REF-SO101-STOCK-' + tag][0].childOccurrences.item(0).component.asBuiltJoints:
        if j.name.startswith('ARM'): j.jointMotion.rotationValue = 0
# arms: link groups
for tag in 'AB':
    a = [o for o in root.occurrences if o.component.name == 'REF-SO101-STOCK-' + tag][0]
    asmo = a.childOccurrences.item(0); asmc = asmo.component
    member = {}
    for g in asmc.rigidGroups:
        lk = g.name.split('-')[-1]
        for o in g.occurrences: member[o.name] = lk
    links = {}
    for o in asmo.childOccurrences:
        if not o.isVisible: continue
        lk = member.get(o.name)
        if lk is None: lk = 'L6' if o.name.startswith('Moving_Jaw') else None
        if lk is None: continue
        def walk(oo):
            r = list(oo.bRepBodies)
            for ch in oo.childOccurrences: r += walk(ch)
            return r
        for b in walk(o):
            if b.isVisible:
                links.setdefault(lk, []).extend(tris(b, 0.1))
        if o.name.startswith('Wrist_Roll_Follower'):
            data.setdefault('fixed_jaw', {})[tag] = sum([tris(b, 0.03) for b in walk(o)], [])
        if o.name.startswith('Moving_Jaw'):
            data.setdefault('moving_jaw', {})[tag] = sum([tris(b, 0.03) for b in walk(o)], [])
    # fin-ray gripper parts live at the root, rigidly jointed to the wrist-roll follower (L5) and moving jaw (L6)
    fj, mj = [], []
    for o in root.occurrences:
        n = o.component.name
        if not o.isVisible or not n.startswith(('GR-01', 'GR-02', 'GR-03')) or '(%s' % tag not in n: continue
        lk = 'L6' if (n.startswith('GR-02') or 'moving' in n) else 'L5'
        for b in o.bRepBodies:
            if b.isVisible:
                links.setdefault(lk, []).extend(tris(b, 0.1)); (mj if lk == 'L6' else fj).extend(tris(b, 0.03))
    if fj:
        data.setdefault('fixed_jaw', {})[tag] = fj; data.setdefault('moving_jaw', {})[tag] = mj; data['finray'] = True
    data['arms'][tag] = links
# scene (static, carousel exported separately at the pick angle)
carousel_names = ('TT-02-deck', 'TT-04 beaker locator ring', 'REF-BEAKER', 'TT-03 horn spacer', 'SHCS ISO 4762 M3x10 (deck)')
for o in root.allOccurrences:
    p = o.fullPathName
    if not o.isVisible or any(k in p for k in ('HW-LIB', 'REF-TABLE', 'REF-LAYOUT', 'ANIM-', 'REF-SO101-STOCK')) or o.component.name.startswith(('GR-01', 'GR-02', 'GR-03')): continue
    if o.component.name in carousel_names: continue
    for b in o.bRepBodies:
        if b.isVisible and b.isSolid:
            data['scene'].append({'name': o.component.name, 'path': p, 'tris': tris(b, 0.1)})
tj = [j for j in root.joints if j.name == 'TT-INDEX'][0]
tj.jointMotion.rotationValue = math.radians(22.5)
for o in root.allOccurrences:
    if o.isVisible and o.component.name in carousel_names:
        for b in o.bRepBodies:
            if b.isVisible: data['carousel'].append({'name': o.component.name, 'path': o.fullPathName, 'tris': tris(b, 0.1)})
tj.jointMotion.rotationValue = 0
json.dump(data, open(OUT, 'w'))
print('arms', {t: {k: len(v) for k, v in l.items()} for t, l in data['arms'].items()}, 'scene objs', len(data['scene']), 'carousel', len(data['carousel']), 'MB %.1f' % (os.path.getsize(OUT) / 1e6))
