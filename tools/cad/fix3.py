exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
out = []
def snap():
    try: design.snapshots.add()
    except Exception: pass
def grp(name): return [o for o in root.allOccurrences if o.component.name == name][0]
# frame brackets: front +74; rear flipped to the south side of the rear rail, then +74
n = [0, 0]
for c in list(grp('Frame brackets').childOccurrences):
    y = ctr(c)[1]
    if y < 540: moveby(c, T(0, 74)); n[0] += 1
    elif y < 620:
        M = Rx(180, 578, 10); M.transformBy(T(0, 74)); moveby(c, M); n[1] += 1
snap(); out.append('frame brackets: %d front +74, %d rear flipped south +74' % tuple(n))
# crank screws: heads on the crank top (Z54), shanks down into the horn
cr = [o for o in root.occurrences if o.component.name == 'ST-13 crank'][0]
for c in cr.childOccurrences:
    if c.component.name == 'SHCS ISO 4762 M3x8':
        t = c.transform2.translation; place(c, T(t.x * 10, t.y * 10, 54.0))
snap(); out.append('crank M3x8 screws -> Z54')
# TT-04 dowels: 4 x M4 at r88, deck-local 67.5+90k, heads on the web top (Z61.7), world = rot 220.6 about the carousel centre
tt = [o for o in root.occurrences if o.component.name == 'TT-04 beaker locator ring'][0]
k = 0
for c in tt.childOccurrences:
    a = math.radians(67.5 + 90 * k + 220.6); k += 1
    place(c, T(807.9 + 88 * math.cos(a), 523.5 + 88 * math.sin(a), 61.7))
snap()
bb = tt.boundingBox; out.append('TT-04 bbox now x %.0f..%.0f y %.0f..%.0f z %.0f..%.0f' % (bb.minPoint.x*10, bb.maxPoint.x*10, bb.minPoint.y*10, bb.maxPoint.y*10, bb.minPoint.z*10, bb.maxPoint.z*10))
bb = cr.boundingBox; out.append('crank bbox z %.0f..%.0f' % (bb.minPoint.z*10, bb.maxPoint.z*10))
bb = grp('Frame brackets').boundingBox; out.append('frame brackets y %.0f..%.0f' % (bb.minPoint.y*10, bb.maxPoint.y*10))
print('\n'.join(out))
