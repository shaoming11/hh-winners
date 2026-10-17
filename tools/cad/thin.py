exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(r'C:/Users/User/fusion_bridge/' + f).read())
out = []; PLA = design.materials.itemByName('PLA (FDM)')
def one(n): return [o for o in root.occurrences if o.component.name == n]
tt = one('TT-05 turntable tie plate (Y-right)')[0]; p = Part.__new__(Part); p.c = tt.component; p.o = (790, 512, 0); p.body = p.c.bRepBodies.item(0)
p.box(691.01, 404, 1.2, 901, 621, 2.1, CUT); out.append('TT-05 %.1f cm3' % p.c.bRepBodies.item(0).volume)
# lighter jigs: same contact faces, 8 wide x 10 tall
def rm(n):
    for o in one(n):
        for j in joints_of(o): j.deleteMe()
        o.deleteMe()
def fin(p, label):
    p.body = p.c.bRepBodies.item(0); p.body.name = label
    process4(p.c, [], r_out=0.8, r_in=0.8, ch=0.3, r_top=0.5); p.c.bRepBodies.item(0).material = PLA
for n in ('JG-01 gap block E6-Xfront 122 (L)', 'JG-01 gap block E6-Xfront 122 (R)', 'JG-02 gap block Xfront-Xback 50 (L)', 'JG-02 gap block Xfront-Xback 50 (R)', 'JG-03 E6 + S1 locator', 'JG-07 turntable plate gauge', 'JG-10 S2 locator'): rm(n)
for i, x in enumerate((300, 520)):
    q = Part('JG-01 gap block E6-Xfront 122 (%s)' % 'LR'[i], (x, 511, 0)); q.box(x - 4, 450.15, 0, x + 4, 571.85, 10); fin(q, 'JG-01')
for i, x in enumerate((300, 505)):
    q = Part('JG-02 gap block Xfront-Xback 50 (%s)' % 'LR'[i], (x, 617, 0)); q.box(x - 4, 592.4, 0, x + 4, 641.6, 10); fin(q, 'JG-02')
q = Part('JG-03 E6 + S1 locator', (273, 360, 0)); q.box(268, 290.0, 0, 276, 429.85, 10); q.box(255.2, 284.0, 0, 276, 290.0, 10); q.box(275, 302, 0, 359.85, 310, 10); fin(q, 'JG-03')
q = Part('JG-07 turntable plate gauge', (695, 337, 0)); q.box(691, 270.0, 0, 699, 404.9, 10); q.box(665, 264, 0, 699, 270, 10); fin(q, 'JG-07')
q = Part('JG-10 S2 locator', (602.5, 306, 0)); q.box(540.15, 302, 0, 664.85, 310, 10); fin(q, 'JG-10')
try: design.snapshots.add()
except Exception: pass
em = design.exportManager; OUT = 'C:/Users/User/fusion_bridge/prints_v2/'
exp = {'TT-05 turntable tie plate (Y-right)': 'TT-05_turntable-tie-plate_qty1', 'JG-01 gap block E6-Xfront 122 (L)': 'JG-01L', 'JG-01 gap block E6-Xfront 122 (R)': 'JG-01R', 'JG-02 gap block Xfront-Xback 50 (L)': 'JG-02L', 'JG-02 gap block Xfront-Xback 50 (R)': 'JG-02R', 'JG-03 E6 + S1 locator': 'JG-03', 'JG-07 turntable plate gauge': 'JG-07', 'JG-10 S2 locator': 'JG-10'}
for n, s in exp.items():
    so = em.createSTLExportOptions(one(n)[0].component.bRepBodies.item(0), OUT + s + '.stl'); so.meshRefinement = F.MeshRefinementSettings.MeshRefinementHigh; em.execute(so)
print('\n'.join(out))
