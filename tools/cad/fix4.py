exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
out = []
P = [(192.3, 394.6), (134.6, 477.1), (108.5, 574.4)]
bs = [o for o in root.occurrences if o.component.name == 'ANIM-beaker100']
stray = [o for o in bs if o.transform2.translation.z * 10 > 100]
for o, (x, y) in zip(sorted(stray, key=lambda o: o.transform2.translation.y), P):
    place(o, T(x, y, 60.2))
try: design.snapshots.add()
except Exception: pass
stands = [o for o in root.occurrences if o.component.name.startswith('RK-03 reagent stand')]
for o in bs:
    t = o.transform2.translation
    if t.z * 10 < 1 and abs(t.x) < 1e-6: continue          # the animation master at the origin stays hidden
    o.isLightBulbOn = True
    for i, s in enumerate(stands):
        ts = s.transform2.translation
        if abs(ts.x - t.x) < 0.1 and abs(ts.y - t.y) < 0.1:
            ji = root.asBuiltJoints.createInput(o, s, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-BEAKER-RK03-%d' % (i + 1); out.append('beaker on stand %d' % (i + 1))
comp = bs[0].component
for b in comp.bRepBodies:
    if b.name.startswith('liq'): b.isLightBulbOn = False
out.append('beakers visible (glass only); liquid level bodies hidden')
for o in bs:
    t = o.transform2.translation; out.append('beaker t=(%.1f,%.1f,%.1f) vis=%d' % (t.x*10, t.y*10, t.z*10, o.isLightBulbOn))
print('\n'.join(out))
