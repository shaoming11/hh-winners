root = design.rootComponent
lib = app.materialLibraries.itemByName('Fusion Appearance Library')
def app_(name):
    a = design.appearances.itemByName(name)
    return a if a else design.appearances.addByCopy(lib.appearances.itemByName(name), name)
CLEAR = app_('Polycarbonate (Clear)')
n_op = n_app = 0; err = None; seen = set()
for o in root.allOccurrences:
    c = o.component
    if c.name in seen: continue
    seen.add(c.name)
    for b in c.bRepBodies:
        pp = (b.material and b.material.name == 'Polypropylene' and c.name != 'REF-BIN' and not c.name.startswith('ANIM-')) or (c.name.startswith('ANIM-') and b.name in ('wall', 'floor'))
        if not pp: continue
        try: b.opacity = 0.4; n_op += 1
        except Exception as e: err = str(e); b.appearance = CLEAR; n_app += 1
print('opacity 0.4 on', n_op, 'bodies; clear-PC appearance on', n_app, err or '')
