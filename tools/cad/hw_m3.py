"""Masters: SHCS M3x16, M3x25, hex nut ISO 4032 M3, nylon-insert nut DIN 985 M3 (modeled internal threads)."""
import os
exec(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'hw_funcs.py')).read())
for o in list(lib.occurrences):
    if o.component.name in ('Hex nut ISO 4032 M3', 'Nyloc nut DIN 985 M3'): o.deleteMe()
names = [o.component.name for o in lib.occurrences]
LIB.isLightBulbOn = True
out = []
for L in (16, 25):
    if 'SHCS ISO 4762 M3x%d' % L not in names:
        c, r = shcs(3, L); c.bRepBodies.item(0).material = design.materials.itemByName('Steel'); out.append('M3x%d %s' % (L, r))
def nut(name, h):
    c = newc(name)
    sk = c.sketches.add(c.xYConstructionPlane); hexagon(sk, 5.5); ext(c, sk.profiles.item(0), h)
    sk = c.sketches.add(c.xYConstructionPlane); circ(sk, 0, 0, 1.25); ext(c, smallest(sk), h, F.FeatureOperations.CutFeatureOperation)
    b = c.bRepBodies.item(0)
    face = [f for f in b.faces if isinstance(f.geometry, C.Cylinder) and abs(f.geometry.radius * 10 - 1.25) < 0.01][0]
    r = thread(c, face, True, force='M3x0.5'); c.bRepBodies.item(0).material = design.materials.itemByName('Steel'); appear(c, 'Steel - Satin'); return r
if 'Hex nut ISO 4032 M3' not in names: out.append('hex nut %s' % nut('Hex nut ISO 4032 M3', 2.4))
if 'Nyloc nut DIN 985 M3' not in names: out.append('nyloc %s' % nut('Nyloc nut DIN 985 M3', 4.0))
LIB.isLightBulbOn = False
print(out or 'all present')
