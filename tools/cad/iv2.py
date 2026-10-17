"""Interference check of every v2 part against all bodies whose bounding box it overlaps (current pose)."""
import adsk.core as C, adsk.fusion as F
root = design.rootComponent
V2 = ONLY if 'ONLY' in globals() else ['AG-01 auger stand', 'DH-01 yeast auger head', 'DH-02 auger screw', 'WS-01 scale base', 'WS-02 scale pan',
      'TT-04 beaker locator ring', 'RK-02 reagent rack', 'ST-01', 'ST-09 stop-post TPU sleeve', 'EL-02 electronics box (bought ABS)',
      'GR-01 gripper body (A)', 'GR-02 moving jaw (A)', 'GR-03 fin-ray finger TPU (A fixed)', 'GR-03 fin-ray finger TPU (A moving)',
      'GR-01 gripper body (B)', 'GR-02 moving jaw (B)', 'GR-03 fin-ray finger TPU (B fixed)', 'GR-03 fin-ray finger TPU (B moving)']
SKIPP = ('HW-LIB', 'REF-TABLE', 'ANIM-')
allb = []
for o in root.allOccurrences:
    if not o.isVisible or any(k in o.fullPathName for k in SKIPP): continue
    for b in o.bRepBodies:
        if b.isVisible and b.isSolid: allb.append((o, b))
def ov(a, b, pad=0.05):
    A, B = a.boundingBox, b.boundingBox
    return all(A.maxPoint.asArray()[i] + pad >= B.minPoint.asArray()[i] and A.minPoint.asArray()[i] - pad <= B.maxPoint.asArray()[i] for i in range(3))
def nm(e):
    c = e.assemblyContext; return (c.component.name if c else e.parentComponent.name)[:40].encode('ascii', 'replace').decode()
for name in V2:
    mine = [(o, b) for o, b in allb if o.component.name == name]
    if not mine: print('-- %s: not found / hidden' % name); continue
    for o, b in mine[:1]:
        near = [x for oo, x in allb if x is not b and oo.component.name != name and ov(b, x)]
        if not near: print('-- %s: 0 neighbours, CLEAN' % name); continue
        col = C.ObjectCollection.create(); col.add(b)
        for x in near: col.add(x)
        ii = design.createInterferenceInput(col); ii.areCoincidentFacesIncluded = False
        try: res = design.analyzeInterference(ii)
        except Exception as e: print('-- %s: analyze failed %s' % (name, e)); continue
        agg = {}
        for r in (res or []):
            a1, a2 = nm(r.entityOne), nm(r.entityTwo)
            if name[:40] not in (a1, a2): continue
            other = a2 if a1 == name[:40] else a1
            agg[other] = agg.get(other, 0) + r.interferenceBody.volume * 1000
        print('-- %s: %d neighbours, %s' % (name, len(near), 'CLEAN' if not agg else ', '.join('%s %.1f mm3' % kv for kv in sorted(agg.items(), key=lambda q: -q[1]))))
