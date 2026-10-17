exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(r'C:/Users/User/fusion_bridge/' + f).read())
out = []
def one(n): return [o for o in root.occurrences if o.component.name == n][0]
# TT-05: plate 3 -> 2 mm (cut Z2-3.1 everywhere except the flange), flange height 20 -> 16 (bolt still at Z10 with 6 mm above)
tt = one('TT-05 turntable tie plate (Y-right)'); p = Part.__new__(Part); p.c = tt.component; p.o = (790, 512, 0); p.body = p.c.bRepBodies.item(0)
p.box(691.01, 404, 2.0, 901, 621, 3.2, CUT); p.box(684, 404, 16, 692, 621, 21, CUT)
out.append('TT-05 %.1f cm3 bodies %d' % (p.c.bRepBodies.item(0).volume, p.c.bRepBodies.count))
# RK-04: bars 3 -> 2 mm, rings 8 -> 6 tall, flange 20 -> 16
rk = one('RK-04 rack tie plate (Y-left)'); q = Part.__new__(Part); q.c = rk.component; q.o = (200, 480, 0); q.body = q.c.bRepBodies.item(0)
q.box(60, 350, 6, 238.99, 620, 9, CUT); q.box(60, 350, 2, 238.99, 620, 3.2, CUT)
P = [(192.3, 394.6), (134.6, 477.1), (108.5, 574.4)]
for x, y in P: q.cyl(x, y, 1.9, 6.0, 35.0, JOIN, 31.1)        # restore the rings between Z2 and Z6
q.box(238, 350, 16, 246, 620, 21, CUT)
out.append('RK-04 %.1f cm3 bodies %d' % (q.c.bRepBodies.item(0).volume, q.c.bRepBodies.count))
try: design.snapshots.add()
except Exception: pass
em = design.exportManager
for o, stem in ((tt, 'TT-05_turntable-tie-plate_qty1'), (rk, 'RK-04_rack-tie-plate_qty1')):
    so = em.createSTLExportOptions(o.component.bRepBodies.item(0), 'C:/Users/User/fusion_bridge/prints_v2/%s.stl' % stem); so.meshRefinement = F.MeshRefinementSettings.MeshRefinementHigh; em.execute(so)
print('\n'.join(out))
