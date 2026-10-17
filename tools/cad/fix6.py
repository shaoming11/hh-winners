root = design.rootComponent
bs = [o for o in root.occurrences if o.component.name == 'ANIM-beaker100']
stands = [o for o in root.occurrences if o.component.name.startswith('RK-03 reagent stand')]
n = 0
for o in bs:
    t = o.transform2.translation
    for i, s in enumerate(stands):
        ts = s.transform2.translation
        if abs(ts.x - t.x) < 0.1 and abs(ts.y - t.y) < 0.1:
            ji = root.asBuiltJoints.createInput(o, s, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-BEAKER-RK03-%d' % (i + 1); n += 1
print('beaker joints', n, 'total joints', root.asBuiltJoints.count)
