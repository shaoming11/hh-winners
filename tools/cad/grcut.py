import adsk.core as C, adsk.fusion as F
root=design.rootComponent
out=[]
for tag in 'AB':
    g=[o for o in root.occurrences if o.component.name=='GR-01 gripper body (%s)'%tag][0]
    tb=g.bRepBodies.item(0)
    lo=[v-0.3 for v in tb.boundingBox.minPoint.asArray()]; hi=[v+0.3 for v in tb.boundingBox.maxPoint.asArray()]
    arm=[o for o in root.occurrences if o.component.name=='REF-SO101-STOCK-'+tag][0]
    tools=C.ObjectCollection.create(); names=[]
    for o in arm.allOccurrences if hasattr(arm,'allOccurrences') else []:
        pass
    def walk(o):
        for c in o.childOccurrences:
            if c.component.name.startswith(('ZK_122','XG-ZIJI','SG-ZIJI')):
                for b in c.bRepBodies:
                    bb=b.boundingBox
                    if all(bb.maxPoint.asArray()[i]>=lo[i] and bb.minPoint.asArray()[i]<=hi[i] for i in range(3)): tools.add(b); names.append(c.component.name)
            walk(c)
    walk(arm)
    v0=tb.volume
    ci=root.features.combineFeatures.createInput(tb,tools); ci.operation=F.FeatureOperations.CutFeatureOperation; ci.isKeepToolBodies=True
    try:
        root.features.combineFeatures.add(ci); out.append('%s: cut %d servo bodies %s, vol %.2f -> %.2f'%(tag,tools.count,sorted(set(names)),v0,g.bRepBodies.item(0).volume))
    except Exception as e: out.append('%s combine failed: %s'%(tag,e))
print('\n'.join(out))
