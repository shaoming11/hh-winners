exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
P = [(192.3, 394.6), (134.6, 477.1), (108.5, 574.4)]
st = [o for o in root.occurrences if o.component.name.startswith('RK-03 reagent stand v2')]
print('stand occurrences:', len(st), set(o.component.name for o in st))
for o, (x, y) in zip(st, P): place(o, T(x, y, 0))
try: design.snapshots.add()
except Exception: pass
for o in st: t = o.transform2.translation; b = o.boundingBox; print('stand t=(%.1f,%.1f) bbox x%.0f..%.0f y%.0f..%.0f' % (t.x*10, t.y*10, b.minPoint.x*10, b.maxPoint.x*10, b.minPoint.y*10, b.maxPoint.y*10))
em = design.exportManager
so = em.createSTLExportOptions(st[0].component.bRepBodies.item(0), 'C:/Users/User/fusion_bridge/prints_v2/RK-03v2_reagent-stand_qty3.stl'); so.meshRefinement = F.MeshRefinementSettings.MeshRefinementHigh; em.execute(so); print('exported stand')
