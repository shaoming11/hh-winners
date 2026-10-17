root = design.rootComponent
lib = app.materialLibraries.itemByName('Fusion Appearance Library')
def app_(name):
    a = design.appearances.itemByName(name)
    return a if a else design.appearances.addByCopy(lib.appearances.itemByName(name), name)
GLASS, PP = app_('Glass (Clear)'), app_('Plastic - Translucent Glossy (White)')
from collections import Counter
done = Counter(); seen = set()
for o in root.allOccurrences:
    c = o.component
    if c.name in seen: continue
    seen.add(c.name)
    for b in c.bRepBodies:
        mat = b.material.name if b.material else ''
        if c.name.startswith('ANIM-'):
            if b.name in ('wall', 'floor'): b.appearance = PP; done['ANIM wall/floor'] += 1
            continue
        if mat == 'Glass':
            b.appearance = GLASS; done['glass: ' + c.name] += 1
        elif mat == 'Polypropylene' and c.name != 'REF-BIN':
            b.appearance = PP; done['PP: ' + c.name] += 1
for k, v in sorted(done.items()): print('%-60s %d bodies' % (k.encode('ascii', 'replace').decode(), v))
