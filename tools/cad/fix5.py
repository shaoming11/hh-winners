exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
out = []
def snap():
    try: design.snapshots.add()
    except Exception: pass
def one(n): return [o for o in root.occurrences if o.component.name == n][0]
def nested(n): return [o for o in root.allOccurrences if o.component.name == n]
# a) joints to drop (re-created below)
targets = ['GR-01 gripper body (A)', 'GR-02 moving jaw (A)', 'GR-03 fin-ray finger TPU (A fixed)', 'GR-03 fin-ray finger TPU (A moving)', 'FRAME-2020 aux rail E5', 'PS-01 auger post', 'DH-01 yeast auger head', 'DH-02 auger screw', 'TT-02-deck']
for n in targets:
    for j in joints_of(one(n)): j.deleteMe()
for j in list(root.asBuiltJoints):
    if j.name in ('FIX-AUGERSERVO-DH01', 'FIX-TT04-TT02', 'FIX-BEAKERS-TT04', 'FIX-TT03-TT02'): j.deleteMe()
snap()
# b) arm A gripper parts: same pose relative to arm A's stock links as arm B's parts have to arm B's
def link(X, prefix):
    a = one('REF-SO101-STOCK-' + X).childOccurrences.item(0)
    return [c for c in a.childOccurrences if c.component.name.startswith(prefix)][0]
def inv(m): m = m.copy(); m.invert(); return m
for gname, parent in (('GR-01 gripper body (%s)', 'Wrist_Roll_Follower'), ('GR-02 moving jaw (%s)', 'Moving_Jaw')):
    pA, pB = link('A', parent), link('B', parent)
    rel = one(gname % 'B').transform2.copy(); rel.transformBy(inv(pB.transform2))       # B-part in B-link frame
    new = rel.copy(); new.transformBy(pA.transform2)
    place(one(gname % 'A'), new); out.append('%s re-posed from arm B relation' % (gname % 'A'))
for fname, pname in (('GR-03 fin-ray finger TPU (%s fixed)', 'GR-01 gripper body (%s)'), ('GR-03 fin-ray finger TPU (%s moving)', 'GR-02 moving jaw (%s)')):
    rel = one(fname % 'B').transform2.copy(); rel.transformBy(inv(one(pname % 'B').transform2))
    new = rel.copy(); new.transformBy(one(pname % 'A').transform2)
    place(one(fname % 'A'), new); out.append('%s re-posed' % (fname % 'A'))
snap()
# c) auger body parts get the missing +4 mm (rotated with the unit)
a = math.radians(220.6); d = (4 * math.cos(a), 4 * math.sin(a))
for n in ('FRAME-2020 aux rail E5', 'PS-01 auger post', 'DH-01 yeast auger head', 'DH-02 auger screw'):
    moveby(one(n), T(d[0], d[1]))
out.append('auger post/head/E5/screw shifted (%.2f, %.2f)' % d)
# d) carousel deck back to Z54.6
tt2 = one('TT-02-deck'); m = tt2.transform2.copy(); t = m.translation; t.z = 5.46; m.translation = t; place(tt2, m)
out.append('TT-02 deck Z -> 54.6')
snap()
# e) E6 corner brackets that block the scale saddle: S2-east (X540-560) and Y-right south (X645-665), both on E6's south side
g = nested('Stage + crossbar brackets')[0]; dl = []
for c in list(g.childOccurrences):
    x, y, z = ctr(c)
    if 405 < y < 437 and (538 < x < 562 or 643 < x < 672) and z < 20: dl.append(c)
for c in dl: c.deleteMe()
out.append('removed %d bracket items (2 brackets + screws/T-nuts)' % len(dl))
snap()
print('\n'.join(out))
