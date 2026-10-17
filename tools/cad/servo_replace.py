import adsk.core as C
root = design.rootComponent
LIBO = [x for x in root.occurrences if x.component.name == 'HW-LIB (masters, hidden)'][0]
Mm = {x.component.name: x.component for x in LIBO.component.occurrences}
SG = [o for o in root.allOccurrences if o.component.name == 'Servos'][0].component
old = [o for o in SG.occurrences if o.component.name.startswith('FlashHobby M45CHW') and abs(o.transform2.translation.x * 10 - 175) > 1]
for o in old: o.deleteMe()
m = C.Matrix3D.create(); m.setWithCoordinateSystem(C.Point3D.create(45.0, 7.7, 0), C.Vector3D.create(0, 1, 0), C.Vector3D.create(-1, 0, 0), C.Vector3D.create(0, 0, 1))
n = SG.occurrences.addExistingComponent(Mm['FlashHobby M45CHW + 25T disc horn'], m)
print('replaced', len(old), '-> new stage servo at', [round(v * 10, 1) for v in n.transform2.translation.asArray()])
sv = [o for o in root.allOccurrences if o.component.name.startswith('FlashHobby M45CHW') and 'Servos' in o.fullPathName]
print('servos at', [[round(v * 10) for v in o.transform2.translation.asArray()] for o in sv])
