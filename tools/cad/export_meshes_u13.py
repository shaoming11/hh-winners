import adsk.core as C, adsk.fusion as F, math, json, os
root = design.rootComponent
OUT = os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'meshes_u13.json')
def tris(body, tol=0.1):
    calc = body.meshManager.createMeshCalculator(); calc.surfaceTolerance = tol
    m = calc.calculate(); pts = m.nodeCoordinatesAsDouble; idx = m.nodeIndices
    P = [(pts[i] * 10, pts[i + 1] * 10, pts[i + 2] * 10) for i in range(0, len(pts), 3)]
    return [[P[idx[k]], P[idx[k + 1]], P[idx[k + 2]]] for k in range(0, len(idx), 3)]
data = {'scene': []}
for o in root.allOccurrences:
    p = o.fullPathName
    if not o.isVisible or any(k in p for k in ('HW-LIB', 'REF-TABLE', 'REF-LAYOUT', 'ANIM-', 'REF-SO101-STOCK')) or o.component.name.startswith(('GR-01', 'GR-02', 'GR-03')): continue
    for b in o.bRepBodies:
        if b.isVisible and b.isSolid:
            data['scene'].append({'name': o.component.name, 'path': p, 'tris': tris(b, 0.1)})
json.dump(data, open(OUT, 'w'))
print('scene objs', len(data['scene']), 'MB %.1f' % (os.path.getsize(OUT) / 1e6))
