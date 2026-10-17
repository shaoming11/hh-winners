exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(r'C:/Users/User/fusion_bridge/' + f).read())
out = []; PLA = design.materials.itemByName('PLA (FDM)')
def one(n): return [o for o in root.occurrences if o.component.name == n]
# 1) stands at their three positions (component origin = P1)
P = [(192.3, 394.6), (134.6, 477.1), (108.5, 574.4)]
st = one('RK-03 reagent stand v2 (x3)')
for o, (x, y) in zip(st, P): place(o, T(x, y, 0))
# 2) TT-05 cut-outs from the real bodies (+~0.3 mm by scaling about each footprint centre)
tt = one('TT-05 turntable tie plate (Y-right)')[0]; tc = tt.component; tgt = tc.bRepBodies.item(0)
TB = F.TemporaryBRepManager.get(); tools = []
inv = tt.transform2.copy(); inv.invert()
for nm, grow in (('TT-01', 0.3), ('FRAME-2020 aux rail E5', 0.3), ('PS-01 auger post', 0.3)):
    o = [x for x in root.allOccurrences if x.component.name == nm][0]
    b = TB.copy(o.bRepBodies.item(0)); TB.transform(b, inv)
    bb = b.boundingBox; cx, cy, cz = [(bb.minPoint.asArray()[i] + bb.maxPoint.asArray()[i]) / 2 for i in range(3)]
    half = min(bb.maxPoint.x - bb.minPoint.x, bb.maxPoint.y - bb.minPoint.y) / 2
    s = 1 + (grow / 10) / half
    m = C.Matrix3D.create(); m.setCell(0, 0, s); m.setCell(1, 1, s); m.setCell(2, 2, 1.0)
    m.setCell(0, 3, cx * (1 - s)); m.setCell(1, 3, cy * (1 - s)); TB.transform(b, m)
    tools.append(b)
bf = tc.features.baseFeatures.add(); bf.startEdit()
tb_bodies = [tc.bRepBodies.add(b, bf) for b in tools]
bf.finishEdit()
col = C.ObjectCollection.create()
for b in list(tc.bRepBodies):
    if b != tgt: col.add(b)
ci = tc.features.combineFeatures.createInput(tgt, col); ci.operation = F.FeatureOperations.CutFeatureOperation; ci.isKeepToolBodies = False
tc.features.combineFeatures.add(ci)
out.append('TT-05 cut by TT-01/E5/PS-01 bodies (+0.3): bodies %d vol %.1f' % (tc.bRepBodies.count, tc.bRepBodies.item(0).volume))
# 3) jigs: rebuild the conflicting ones
def rm(n):
    for o in one(n):
        for j in joints_of(o): j.deleteMe()
        o.deleteMe()
def fin(p, label):
    p.body = p.c.bRepBodies.item(0); p.body.name = label
    out.append('%-6s %s' % (label, process4(p.c, [], r_out=1.0, r_in=1.0, ch=0.4, r_top=0.6))); p.c.bRepBodies.item(0).material = PLA
for n in ('JG-04 pourer base locator', 'JG-05 transfer base locator', 'JG-08 rack tie plate gauge', 'JG-03 E6 locator (Y-left end -> E6)', 'JG-01 gap block E6-Xfront 122 (R)', 'JG-02 gap block Xfront-Xback 50 (L)', 'JG-02 gap block Xfront-Xback 50 (R)'): rm(n)
p = Part('JG-04 pourer base locator', (290, 582, 20)); p.box(233, 576, 20, 341.9, 588, 26); p.box(233, 576, 4, 239, 588, 26); fin(p, 'JG-04')      # references RK-04's flange face (X239)
p = Part('JG-05 transfer base locator', (675, 582, 20)); p.box(660.5, 576, 20, 697, 588, 26); p.box(691, 576, 4, 697, 588, 26); fin(p, 'JG-05')   # references TT-05's flange face (X691)
p = Part('JG-03 E6 locator (Y-left end -> E6)', (273, 360, 0)); p.box(266, 290.0, 0, 280, 429.85, 14); p.box(255.2, 284.0, 0, 280, 290.0, 14); fin(p, 'JG-03')
p = Part('JG-08 rack tie plate gauge', (236, 323, 0)); p.box(229, 290.0, 0, 239, 355.9, 14); p.box(229, 284, 0, 254.8, 290, 14); fin(p, 'JG-08')
p = Part('JG-01 gap block E6-Xfront 122 (R)', (520, 511, 0)); p.box(514, 450.15, 0, 526, 571.85, 14); fin(p, 'JG-01R')
for i, x in enumerate((300, 505)):
    p = Part('JG-02 gap block Xfront-Xback 50 (%s)' % ('L', 'R')[i], (x, 617, 0)); p.box(x - 6, 592.4, 0, x + 6, 641.6, 14); fin(p, 'JG-02')
try: design.snapshots.add()
except Exception: pass
print('\n'.join(out + FLOG))
