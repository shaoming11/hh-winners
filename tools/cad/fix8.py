exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
out = []
def one(n): return [o for o in root.occurrences if o.component.name == n][0]
def snap():
    try: design.snapshots.add()
    except Exception: pass
def bbmin(o): b = o.boundingBox; return (b.minPoint.x * 10, b.minPoint.y * 10, b.minPoint.z * 10)
dx = 397.4 - 604.8
for n in ('GR-01 gripper body (%s)', 'GR-02 moving jaw (%s)', 'GR-03 fin-ray finger TPU (%s fixed)', 'GR-03 fin-ray finger TPU (%s moving)'):
    a, b = one(n % 'A'), one(n % 'B')
    for j in joints_of(a): j.deleteMe()
    ma, mb = bbmin(a), bbmin(b)
    d = (mb[0] + dx - ma[0], mb[1] - ma[1], mb[2] - ma[2])
    moveby(a, T(*d)); out.append('%s shifted (%.1f, %.1f, %.1f)' % (n % 'A', *d))
snap()
st = one('REF-SO101-STOCK-A').childOccurrences.item(0)
fol = [c for c in st.childOccurrences if c.component.name.startswith('Wrist_Roll_Follower')][0]
mj = [c for c in st.childOccurrences if c.component.name.startswith('Moving_Jaw')][0]
for a, b, nm in ((one('GR-01 gripper body (A)'), fol, 'FIX-GR01A-wristroll'), (one('GR-02 moving jaw (A)'), mj, 'FIX-GR02A-gripperjaw'),
                 (one('GR-03 fin-ray finger TPU (A fixed)'), one('GR-01 gripper body (A)'), 'FIX-GR03A-fixed'), (one('GR-03 fin-ray finger TPU (A moving)'), one('GR-02 moving jaw (A)'), 'FIX-GR03A-moving')):
    ji = root.asBuiltJoints.createInput(a, b, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = nm
# scale seat: -0.6 (undo the +0.3, then the needed -0.3)
for n in ('WS-01 scale base', 'WS-02 scale pan'):
    for j in joints_of(one(n)): j.deleteMe()
for o in [one('WS-01 scale base'), one('WS-02 scale pan')] + [o for o in root.allOccurrences if o.component.name.startswith('Load cell') or (o.component.name == 'ANIM-beaker100' and abs(o.transform2.translation.x * 10 - 620) < 1)]:
    for j in joints_of(o): j.deleteMe()
    moveby(o, T(0, -0.6))
snap()
e6 = one('FRAME-2020 crossbar E6'); ws1 = one('WS-01 scale base'); ws2 = one('WS-02 scale pan')
for a, b, nm in ((ws1, e6, 'FIX-WS01-E6'), (ws2, ws1, 'FIX-WS02-WS01')):
    ji = root.asBuiltJoints.createInput(a, b, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = nm
for o in root.allOccurrences:
    if o.component.name.startswith('Load cell') or (o.component.name == 'ANIM-beaker100' and abs(o.transform2.translation.x * 10 - 620) < 1):
        try:
            ji = root.asBuiltJoints.createInput(o, ws1 if o.component.name.startswith('Load') else ws2, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji)
        except Exception: pass
for X in 'AB':
    b = one('GR-01 gripper body (%s)' % X).boundingBox; out.append('GR-01 %s x%.1f..%.1f' % (X, b.minPoint.x*10, b.maxPoint.x*10))
print('\n'.join(out))
