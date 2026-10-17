import adsk.core as C, adsk.fusion as F
app = C.Application.get(); root = design.rootComponent
NAME = 'Paint - Metallic (Black)'
src = [l for l in app.materialLibraries if l.name == 'Fusion Appearance Library'][0].appearances.itemByName(NAME)
ap = design.appearances.itemByName(NAME) or design.appearances.addByCopy(src, NAME)
n = 0; seen = set()
for o in root.allOccurrences:
    c = o.component
    if c.name.startswith('FRAME-2020') and c.entityToken not in seen:
        seen.add(c.entityToken)
        for b in c.bRepBodies: b.appearance = ap; n += 1
print('black on', n, 'extrusion bodies in', len(seen), 'components')
ok = app.activeDocument.save('Extrusions black anodised look; DH-01 v5 / DH-02 v4 / PS-01 v2 (+25 mm); TT-04 v4 4x100 mL; WS-02 v3; CAL-02 v2; 100 mL ref beakers')
print('saved:', ok)
