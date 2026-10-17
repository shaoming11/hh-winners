import adsk.core as C
root = design.rootComponent
G = [o for o in root.allOccurrences if o.component.name.startswith('Measuring')][0].component
lib = [o for o in root.occurrences if o.component.name == 'HW-LIB (masters, hidden)'][0].component
Mm = {o.component.name: o.component for o in lib.occurrences}
for o in list(G.occurrences):
    t = o.transform2.translation
    if abs(t.x * 10 - 675) < 0.5 and (o.component.name.startswith('SHCS ISO 4762 M5') or o.component.name.startswith('T-nut')): o.deleteMe()
for y in (455, 545):
    m = C.Matrix3D.create(); m.translation = C.Vector3D.create(67.5, y / 10, 2.62); G.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M5x12'], m)
    m = C.Matrix3D.create(); m.translation = C.Vector3D.create(67.5, y / 10, 1.82); G.occurrences.addExistingComponent(Mm['T-nut 2020 drop-in M5'], m)
frame = [o for o in root.occurrences if o.component.name.startswith('FRAME-2020')][0]
rko = [o for o in root.occurrences if o.component.name == 'RK-02 reagent rack'][0]
for j in list(root.asBuiltJoints):
    if j.name == 'FIX-RK02-frame': j.deleteMe()
ji = root.asBuiltJoints.createInput(rko, frame, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-RK02-frame'
try: design.snapshots.add()
except Exception: pass
print('rack bolts + joint ok')
