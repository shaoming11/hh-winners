import os
exec(open(os.path.join(os.path.expanduser('~'), 'fusion_bridge', 'hw_funcs.py')).read())
names = [o.component.name for o in lib.occurrences]
if 'SHCS ISO 4762 M3x8' not in names:
    LIB.isLightBulbOn = True
    c, r = shcs(3, 8); c.bRepBodies.item(0).material = design.materials.itemByName('Steel')
    LIB.isLightBulbOn = False
    print('built M3x8', r)
else: print('M3x8 exists')
