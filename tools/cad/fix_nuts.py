"""Stage servo pose (captured), TT-01 v2 through-bolt nut pockets, WS-01 v3 captive set-screw nut, hardware swaps."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
LIBO = [x for x in root.occurrences if x.component.name == 'HW-LIB (masters, hidden)'][0]
Mm = {x.component.name: x.component for x in LIBO.component.occurrences}
# ---- stage servo to (450,77), body along +Y, upright ----
sv = [o for o in root.allOccurrences if o.component.name.startswith('FlashHobby M45CHW') and 'Servos' in o.fullPathName and abs(o.transform2.translation.x * 10 - 175) > 1][0]
m = C.Matrix3D.create(); m.setWithCoordinateSystem(C.Point3D.create(45.0, 7.7, 0), C.Vector3D.create(0, 1, 0), C.Vector3D.create(-1, 0, 0), C.Vector3D.create(0, 0, 1))
sv.transform2 = m
n = 0
for o in list(root.allOccurrences):
    if o.component.name.startswith('SHCS ISO 4762 M3x12') and 'Servos' in o.fullPathName and o.transform2.translation.x * 10 > 600: o.deleteMe(); n += 1
out.append('old stage ear screws removed: %d' % n)
# ---- TT-01 v2: carousel servo ears through-bolted (M3x20 down into hex nuts held in pockets from the underside) ----
tto = [o for o in root.allOccurrences if o.component.name == 'TT-01'][0]
org = tto.transform2.translation; org = (org.x * 10, org.y * 10, org.z * 10)
tt = Part.__new__(Part); tt.c = tto.component; tt.o = org; tt.body = tt.c.bRepBodies.item(0)
EARS_TT = [(140.65, 365.05), (140.65, 374.95), (189.35, 365.05), (189.35, 374.95)]
tt.holes(EARS_TT, 29.4, 15.9, 3.4)
for (x, y) in EARS_TT: poly_xy(tt, hexagon((x, y), 5.8) if False else [(x + 5.8 / math.sqrt(3) * math.cos(math.radians(30 + 60 * i)), y + 5.8 / math.sqrt(3) * math.sin(math.radians(30 + 60 * i))) for i in range(6)], -0.1, 16.0, CUT)
out.append('TT-01 v2 vol %.1f cm3 bodies %d (origin %s)' % (tt.c.bRepBodies.item(0).volume, tt.c.bRepBodies.count, [round(v, 1) for v in org]))
SV = [o for o in root.allOccurrences if o.component.name.startswith('FlashHobby M45CHW') and 'Servos' in o.fullPathName][0]
SG = SV.assemblyContext.component if SV.assemblyContext else root
for o in list(root.allOccurrences):
    if o.component.name.startswith('SHCS ISO 4762 M3x12') and 'Servos' in o.fullPathName: o.deleteMe()
SGc = [o for o in root.allOccurrences if o.component.name == 'Servos'][0].component
for (x, y) in EARS_TT:
    mm = C.Matrix3D.create(); mm.translation = C.Vector3D.create(x / 10, y / 10, 3.33); SGc.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M3x20'], mm)
    mm = C.Matrix3D.create(); mm.translation = C.Vector3D.create(x / 10, y / 10, 1.36); SGc.occurrences.addExistingComponent(Mm['Hex nut ISO 4032 M3'], mm)
# ---- WS-01 v3: set screw through a captive M3 nut + jam nut on top ----
wso = [o for o in root.allOccurrences if o.component.name == 'WS-01 scale base'][0]
ws = Part.__new__(Part); ws.c = wso.component; ws.o = (395, 455, 0); ws.body = ws.c.bRepBodies.item(0)
ws.holes([(500, 475)], 45.1, 29.9, 3.4)
ws.box(497.1, 475 - 2.9, 38.0, 507.2, 475 + 2.9, 40.7, CUT)      # hex-nut slot from the tower's +X face
out.append('WS-01 v3 vol %.1f cm3 bodies %d' % (ws.c.bRepBodies.item(0).volume, ws.c.bRepBodies.count))
MS = [x for x in root.allOccurrences if x.component.name.startswith('Measuring')][0].component
for o in list(MS.occurrences):
    t = o.transform2.translation
    if abs(t.x * 10 - 500) < 0.6 and abs(t.y * 10 - 475) < 0.6 and o.component.name in ('SHCS ISO 4762 M3x12', 'SHCS ISO 4762 M3x16', 'Hex nut ISO 4032 M3'): o.deleteMe()
mm = C.Matrix3D.create(); mm.setWithCoordinateSystem(C.Point3D.create(50.0, 47.5, 5.6), C.Vector3D.create(1, 0, 0), C.Vector3D.create(0, -1, 0), C.Vector3D.create(0, 0, -1))
MS.occurrences.addExistingComponent(Mm['SHCS ISO 4762 M3x16'], mm)      # set screw tip up at Z56 (gap to the pan set at assembly)
for z in (3.82, 4.51):
    mm = C.Matrix3D.create(); mm.translation = C.Vector3D.create(50.0, 47.5, z); MS.occurrences.addExistingComponent(Mm['Hex nut ISO 4032 M3'], mm)
try: design.snapshots.add(); out.append('snapshot captured')
except Exception as e: out.append('snapshot: %s' % e)
sv = [o for o in root.allOccurrences if o.component.name.startswith('FlashHobby M45CHW') and 'Servos' in o.fullPathName]
out.append('servos at ' + str([[round(v * 10) for v in o.transform2.translation.asArray()] for o in sv]))
print('\n'.join(out + FLOG))
