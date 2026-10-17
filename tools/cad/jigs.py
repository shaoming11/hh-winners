"""Alignment jigs (printed, no purchase): spacer/locator blocks that set every frame and station position in the verified layout."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []; PLA = design.materials.itemByName('PLA (FDM)')
def fin(p, label):
    p.body.name = label.split()[0]
    out.append('%-8s %s' % (label.split()[0], process4(p.c, [], r_out=1.0, r_in=1.0, ch=0.4, r_top=0.6)))
    b = p.c.bRepBodies.item(0); b.material = PLA
    bb = b.boundingBox; out.append('         %.1f cm3, bodies %d, %.1f x %.1f x %.1f' % (b.volume, p.c.bRepBodies.count, (bb.maxPoint.x-bb.minPoint.x)*10, (bb.maxPoint.y-bb.minPoint.y)*10, (bb.maxPoint.z-bb.minPoint.z)*10))
# JG-01 x2: E6 north face (Y450) -> X-front south face (Y572): 122 mm gap, on the table at X300 (left) / X610 (right, clear of the scale saddle Y<=455)
for i, x in enumerate((300, 600)):
    p = Part('JG-01 gap block E6-Xfront 122 (%s)' % ('L', 'R')[i], (x, 511, 0))
    p.box(x - 6, 450.15, 0, x + 6, 571.85, 14); fin(p, 'JG-01 E6->Xfront')
# JG-02 x2: X-front north (Y592) -> X-back south (Y642): 50 mm gap; left X300 (west of arm A base X342), right X675 is the Y-right rail, so use X520 between the arm bases
for i, x in enumerate((300, 505)):
    p = Part('JG-02 gap block Xfront-Xback 50 (%s)' % ('L', 'R')[i], (x, 617, 0))
    p.box(x - 6, 592.15, 0, x + 6, 641.85, 14); fin(p, 'JG-02 Xfront->Xback')
# JG-03: E6 position: lip hooks the Y-left south end face (Y290), bar on the table inside Y-left (X266-280) up to E6's south face (Y430)
p = Part('JG-03 E6 locator (Y-left end -> E6)', (273, 360, 0))
p.box(266, 290.0, 0, 280, 429.85, 14); p.box(245, 284.0, 0, 280, 290.0, 14); fin(p, 'JG-03 E6-locator')
# JG-04: pouring arm base X: lip on Y-left's west face (X245), bar on the X-front rail top up to the base's west edge (X342.02)
p = Part('JG-04 pourer base locator', (290, 582, 20))
p.box(245, 576, 20, 341.9, 588, 26); p.box(239, 576, 4, 245, 588, 26); fin(p, 'JG-04 pourer-base')
# JG-05: transfer arm base X: bar on the X-front top from the base's east edge (X660.38) to Y-right's east face (X685) + lip
p = Part('JG-05 transfer base locator', (675, 582, 20))
p.box(660.5, 576, 20, 685, 588, 26); p.box(685, 576, 4, 691, 588, 26); fin(p, 'JG-05 transfer-base')
# JG-06: scale saddle X: 6.9 mm gauge between S2's east face (X540) and WS-01's west face (X547)
p = Part('JG-06 scale gauge 7 mm', (543.5, 405, 0))
p.box(540.05, 392, 0, 546.95, 425, 15); fin(p, 'JG-06 scale-gauge')
try: design.snapshots.add()
except Exception: pass
print('\n'.join(out + FLOG))
