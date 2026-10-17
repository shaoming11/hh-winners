import adsk.core as C, adsk.fusion as F
root = design.rootComponent
rk = [o for o in root.occurrences if o.component.name == 'RK-04 rack tie plate (Y-left)'][0]; c = rk.component
bs = list(c.bRepBodies); tgt = max(bs, key=lambda b: b.volume)
col = C.ObjectCollection.create()
for b in bs:
    if b != tgt: col.add(b)
ci = c.features.combineFeatures.createInput(tgt, col); ci.operation = F.FeatureOperations.JoinFeatureOperation; c.features.combineFeatures.add(ci)
print('bodies', c.bRepBodies.count, 'vol %.1f' % c.bRepBodies.item(0).volume)
em = design.exportManager
so = em.createSTLExportOptions(c.bRepBodies.item(0), 'C:/Users/User/fusion_bridge/prints_v2/RK-04_rack-tie-plate_qty1.stl'); so.meshRefinement = F.MeshRefinementSettings.MeshRefinementHigh; em.execute(so)
