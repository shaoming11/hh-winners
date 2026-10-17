exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'):
    exec(open(r'C:/Users/User/fusion_bridge/' + f).read())
out = []
def one(n): return [o for o in root.occurrences if o.component.name == n][0]
def snap():
    try: design.snapshots.add()
    except Exception: pass
# 1) arm A gripper parts = arm B's parts shifted by the arm-base offset (-207.4 in X); joints re-made
dx = 397.4 - 604.8
for n in ('GR-01 gripper body (%s)', 'GR-02 moving jaw (%s)', 'GR-03 fin-ray finger TPU (%s fixed)', 'GR-03 fin-ray finger TPU (%s moving)'):
    a, b = one(n % 'A'), one(n % 'B')
    for j in joints_of(a): j.deleteMe()
    m = b.transform2.copy(); t = m.translation; t.x += dx / 10; m.translation = t
    place(a, m); out.append('%s -> arm B pose shifted %.1f' % (n % 'A', dx))
snap()
st = one('REF-SO101-STOCK-A').childOccurrences.item(0)
fol = [c for c in st.childOccurrences if c.component.name.startswith('Wrist_Roll_Follower')][0]
mj = [c for c in st.childOccurrences if c.component.name.startswith('Moving_Jaw')][0]
for a, b, nm in ((one('GR-01 gripper body (A)'), fol, 'FIX-GR01A-wristroll'), (one('GR-02 moving jaw (A)'), mj, 'FIX-GR02A-gripperjaw'),
                 (one('GR-03 fin-ray finger TPU (A fixed)'), one('GR-01 gripper body (A)'), 'FIX-GR03A-fixed'), (one('GR-03 fin-ray finger TPU (A moving)'), one('GR-02 moving jaw (A)'), 'FIX-GR03A-moving')):
    ji = root.asBuiltJoints.createInput(a, b, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = nm
# 2) WS-01: 0.3 mm seat offset + notch for the E6/Y-right north corner bracket (component-local = original frame, origin (395,455,0))
ws1 = one('WS-01 scale base')
p = Part.__new__(Part); p.c = ws1.component; p.o = (395, 455, 0); p.body = ws1.component.bRepBodies.item(0)
p.box(491, 517.9, -0.1, 514, 539, 20.6, CUT)          # world X643-666, Y449.9-471 after the +152/-68 move
out.append('WS-01 notch cut; bodies %d vol %.1f cm3' % (ws1.component.bRepBodies.count, ws1.component.bRepBodies.item(0).volume))
for n in ('WS-01 scale base', 'WS-02 scale pan'):
    o = one(n)
    for j in joints_of(o): j.deleteMe()
    moveby(o, T(0, 0.3))
for o in root.allOccurrences:
    if o.component.name.startswith('Load cell') or (o.component.name == 'ANIM-beaker100' and abs(o.transform2.translation.x * 10 - 620) < 1):
        moveby(o, T(0, 0.3))
snap()
e6 = one('FRAME-2020 crossbar E6')
for a, b, nm in ((one('WS-01 scale base'), e6, 'FIX-WS01-E6'), (one('WS-02 scale pan'), one('WS-01 scale base'), 'FIX-WS02-WS01')):
    ji = root.asBuiltJoints.createInput(a, b, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = nm
print('\n'.join(out + FLOG))
