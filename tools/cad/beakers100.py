import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge'); exec(open(os.path.join(B, 'parts_lib.py')).read())
b100 = [o for o in root.allOccurrences if o.component.name == 'ANIM-beaker100'][0].component
n = 0
for o in list(root.allOccurrences):
    if o.component.name in ('REF-BEAKER', 'EISCO 50 mL beaker on scale'):
        try: o.deleteMe(); n += 1
        except Exception: pass
grp = [o for o in root.occurrences if o.component.name == 'REF-BEAKERS-TT']
parent = grp[0].component if grp else root
if grp: grp[0].component.name = 'REF-BEAKERS-TT (100 mL x4)'
for k in range(4):
    a = math.radians(22.5 + 90 * k); x, y = 175 + 84 * math.cos(a), 370 + 84 * math.sin(a)
    m = C.Matrix3D.create(); m.translation = C.Vector3D.create(x / 10, y / 10, 6.17); parent.occurrences.addExistingComponent(b100, m)
m = C.Matrix3D.create(); m.translation = C.Vector3D.create(46.8, 47.5, 6.37); oc = root.occurrences.addExistingComponent(b100, m)
print('deleted', n, 'old beakers; placed 4 on carousel + 1 on scale')
try: design.snapshots.add()
except Exception: pass
