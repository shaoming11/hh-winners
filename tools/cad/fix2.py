exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
out = []
def snap():
    try: design.snapshots.add()
    except Exception: pass
def grp(name): return [o for o in root.allOccurrences if o.component.name == name][0]
def rootocc(name): return [o for o in root.occurrences if o.component.name == name]
def to_center(o, tx, ty, label):
    c = ctr(o); d = (tx - c[0], ty - c[1])
    if math.hypot(*d) < 0.5: out.append('%-30s ok' % label); return o
    o2, how = moveby(o, T(d[0], d[1])); snap(); c2 = ctr(o2)
    out.append('%-30s %s (%.0f,%.0f)->(%.0f,%.0f)' % (label, how, c[0], c[1], c2[0], c2[1])); return o2
# arms A (absolute)
to_center(rootocc('REF-SO101-STOCK-A')[0], 330.5 + 67.4, 501 + 74, 'STOCK-A')
for nm, (cx, cy) in {'GR-03 fin-ray finger TPU (A fixed)': (337, 324.5), 'GR-03 fin-ray finger TPU (A moving)': (337, 369.5), 'GR-01 gripper body (A)': (335, 381.5), 'GR-02 moving jaw (A)': (336.5, 394.5)}.items():
    to_center(rootocc(nm)[0], cx + 67.4, cy + 74, nm[:30])
# scale group
to_center(rootocc('WS-01 scale base')[0], 453.5 + 152, 489 - 68, 'WS-01')
to_center(rootocc('WS-02 scale pan')[0], 620, 407, 'WS-02')
meas = grp('Measuring + auger station')
for c in list(meas.childOccurrences):
    x, y, z = ctr(c)
    if 395 < x < 485 and 460 < y < 520: to_center(c, x + 152, y - 68, 'scale hw ' + c.component.name[:18])
for o in rootocc('ANIM-beaker100'):
    x, y, z = ctr(o)
    if 430 < x < 510 and 430 < y < 520: to_center(o, 620, 407, 'beaker on scale')
# stands (absolute)
P = [(192.3, 394.6), (134.6, 477.1), (108.5, 574.4)]
for o, (x, y) in zip(rootocc('RK-03 reagent stand (x3, free-standing)'), P): to_center(o, x, y, 'RK-03 stand')
bk = [o for o in rootocc('ANIM-beaker100') if o.isLightBulbOn or True]
# carousel-unit leftovers (still at the old place)
M = Rz(220.6, 175, 370); M.transformBy(T(807.9 - 175, 523.5 - 370))
MA = T(4, 0); MA.transformBy(M)
tt1 = [o for o in root.allOccurrences if o.component.name == 'TT-01'][0]
if ctr(tt1)[0] < 300: o2, h = moveby(tt1, M); snap(); out.append('TT-01 %s -> (%.0f,%.0f)' % (h, ctr(o2)[0], ctr(o2)[1]))
for c in list(grp('Servos').childOccurrences):
    x, y, z = ctr(c)
    if x < 300 and y > 300: moveby(c, M); out.append('carousel servo item %s moved' % c.component.name[:24])
for c in list(meas.childOccurrences):
    x, y, z = ctr(c)
    if x < 140 and 240 < y < 400: moveby(c, MA); out.append('auger item %s moved' % c.component.name[:24])
snap()
# deletions
dl = []
for c in list(meas.childOccurrences):
    x, y, z = ctr(c)
    if (200 < x < 262 and 290 < y < 336) or (abs(x - 675) < 8 and 440 < y < 560): dl.append(c)
for o in root.occurrences:
    x, y, z = ctr(o)
    if o.component.name == 'SHCS ISO 4762 M3x12' and 640 < x < 670 and 125 < y < 155: dl.append(o)
    if o.component.name == 'SHCS ISO 4762 M5x20' and 525 < x < 545: dl.append(o)
for o in root.allOccurrences:
    if o.component.name in ('REF-BEARING-G1', 'REF-BEARING-G2', 'TL-01'): dl.append(o)
for o in dl:
    n = o.component.name
    try: o.deleteMe(); out.append('deleted %s' % n)
    except Exception as e: out.append('delete FAILED %s %s' % (n, e))
for o in root.occurrences:
    if o.component.name in ('ANIM-beaker50', 'ANIM-foam'): o.isLightBulbOn = False
snap()
print('\n'.join(out))
