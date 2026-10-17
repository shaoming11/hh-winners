root = design.rootComponent
import adsk.core as C
LIBO = [x for x in root.occurrences if x.component.name == 'HW-LIB (masters, hidden)'][0]
Mm = {x.component.name: x.component for x in LIBO.component.occurrences}
MS = [x for x in root.allOccurrences if x.component.name.startswith('Measuring')][0].component
for o in list(MS.occurrences):
    t = o.transform2.translation
    if abs(t.x * 10 - 500) < 0.6 and abs(t.y * 10 - 475) < 0.6 and o.component.name in ('SHCS ISO 4762 M3x16', 'Hex nut ISO 4032 M3'): o.deleteMe()
def tr(x, y, z): m = C.Matrix3D.create(); m.translation = C.Vector3D.create(x / 10, y / 10, z / 10); return m
MS.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M3x16'], tr(500, 475, 52.0))   # stop screw, head up (top Z55, ~2.7 below the pan: set at assembly)
MS.occurrences.addExistingComponent(Mm['Hex nut ISO 4032 M3'], tr(500, 475, 38.15))  # captive nut in the side slot
MS.occurrences.addExistingComponent(Mm['Hex nut ISO 4032 M3'], tr(500, 475, 45.0))   # jam nut on the tower top
try: design.snapshots.add()
except Exception: pass
print('stop screw placed head-up with captive + jam nut')
