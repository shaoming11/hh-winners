exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(r'C:/Users/User/fusion_bridge/' + f).read())
out = []; PLA = design.materials.itemByName('PLA (FDM)')
def one(n): return [o for o in root.occurrences if o.component.name == n]
def fin(p, label):
    p.body = p.c.bRepBodies.item(0); p.body.name = label
    out.append('%-6s %s' % (label, process4(p.c, [], r_out=1.0, r_in=1.0, ch=0.4, r_top=0.6))); p.c.bRepBodies.item(0).material = PLA
for o in one('JG-03 E6 locator (Y-left end -> E6)'): o.deleteMe()
# JG-03: sets E6 (Y, from the Y-left south end) AND stage rail S1 (X, from Y-left's inner face X265 to S1's west face X360)
p = Part('JG-03 E6 + S1 locator', (273, 360, 0))
p.box(266, 290.0, 0, 280, 429.85, 14); p.box(255.2, 284.0, 0, 280, 290.0, 14)
p.box(279, 300, 0, 359.85, 312, 14); fin(p, 'JG-03')
# JG-10: stage rail S2 (X): S2 east face X540 -> Y-right inner face X665
p = Part('JG-10 S2 locator', (602.5, 306, 0)); p.box(540.15, 300, 0, 664.85, 312, 14); fin(p, 'JG-10')
P = [(192.3, 394.6), (134.6, 477.1), (108.5, 574.4)]
for o, (x, y) in zip(one('RK-03 reagent stand v2 (x3)'), P):
    t = o.transform2.translation
    if abs(t.x * 10 - x) > 0.5 or abs(t.y * 10 - y) > 0.5: place(o, T(x, y, 0))
    t = o.transform2.translation; out.append('stand at (%.1f, %.1f)' % (t.x * 10, t.y * 10))
try: design.snapshots.add()
except Exception: pass
em = design.exportManager; OUT = 'C:/Users/User/fusion_bridge/prints_v2'
names = {'RK-03 reagent stand v2 (x3)': 'RK-03v2_reagent-stand_qty3', 'RK-04 rack tie plate (Y-left)': 'RK-04_rack-tie-plate_qty1', 'TT-05 turntable tie plate (Y-right)': 'TT-05_turntable-tie-plate_qty1'}
seen = set()
for o in root.occurrences:
    n = o.component.name
    if n in seen: continue
    if n in names or n.startswith('JG-'):
        seen.add(n); stem = names.get(n) or n.split(' ')[0] + '_' + '-'.join(n.split(' ')[1:]).replace('(', '').replace(')', '').replace('>', '').replace('/', '')
        so = em.createSTLExportOptions(o.component.bRepBodies.item(0), OUT + '/' + stem + '.stl'); so.meshRefinement = F.MeshRefinementSettings.MeshRefinementHigh; em.execute(so); out.append('exported ' + stem)
print('\n'.join(out + FLOG))
