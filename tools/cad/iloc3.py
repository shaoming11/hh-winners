import adsk.core as C
root = design.rootComponent
def bodies(names): return [(o.component.name, b) for o in root.allOccurrences if o.isVisible and o.component.name in names for b in o.bRepBodies]
def check(a_names, b_names):
    A = bodies(a_names); Bs = bodies(b_names)
    for an, a in A:
        eb = a.boundingBox
        cand = [(bn, b) for bn, b in Bs if all(b.boundingBox.maxPoint.asArray()[i] >= eb.minPoint.asArray()[i] and b.boundingBox.minPoint.asArray()[i] <= eb.maxPoint.asArray()[i] for i in range(3))]
        if not cand: continue
        col = C.ObjectCollection.create(); col.add(a)
        for _, b in cand: col.add(b)
        ii = design.createInterferenceInput(col); ii.areCoincidentFacesIncluded = False
        for r in design.analyzeInterference(ii) or []:
            bb = r.interferenceBody.boundingBox
            print('%-12s %6.1f mm3 %s %s' % (an[:12], r.interferenceBody.volume * 1000, [round(v * 10, 1) for v in bb.minPoint.asArray()], [round(v * 10, 1) for v in bb.maxPoint.asArray()]))
check(['FRAME-2020 aux rail E5'], ['T-nut 2020 drop-in M5', 'PS-01 auger post'])
check(['DH-01 yeast auger head'], ['SHCS ISO 4762 M3x16'])
