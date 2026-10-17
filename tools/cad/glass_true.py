"""Material-true labware appearance: glass -> Glass (Clear); polypropylene labware -> Polycarbonate (Clear) (physically clear plastic);
opacity reset to 1. Adds the 100 mL glass graduated cylinder (BOM GLS-03) as a reference body off the bench."""
import adsk.core as C, adsk.fusion as F
root = design.rootComponent
lib = app.materialLibraries.itemByName('Fusion Appearance Library')
def app_(name):
    a = design.appearances.itemByName(name)
    return a if a else design.appearances.addByCopy(lib.appearances.itemByName(name), name)
GLASS, CLEAR = app_('Glass (Clear)'), app_('Polycarbonate (Clear)')
# reference graduated cylinder
for o in list(root.occurrences):
    if o.component.name == 'REF-GRAD-CYL-100 (glass)': o.deleteMe()
m = C.Matrix3D.create(); m.translation = C.Vector3D.create(-25.0, 55.0, 0)
o = root.occurrences.addNewComponent(m); c = o.component; c.name = 'REF-GRAD-CYL-100 (glass)'
VI = lambda mm: C.ValueInput.createByReal(mm / 10)
sk = c.sketches.add(c.xYConstructionPlane); sk.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(0, 0, 0), 3.5)
ei = c.features.extrudeFeatures.createInput(sk.profiles.item(0), F.FeatureOperations.NewBodyFeatureOperation); ei.setDistanceExtent(False, VI(6)); base = c.features.extrudeFeatures.add(ei).bodies.item(0)
pi = c.constructionPlanes.createInput(); pi.setByOffset(c.xYConstructionPlane, VI(6)); pl = c.constructionPlanes.add(pi); pl.isLightBulbOn = False
sk = c.sketches.add(pl); sk.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(0, 0, 0), 1.6); sk.sketchCurves.sketchCircles.addByCenterRadius(C.Point3D.create(0, 0, 0), 1.45)
prof = [p for p in sk.profiles if p.profileLoops.count == 2][0]
ei = c.features.extrudeFeatures.createInput(prof, F.FeatureOperations.JoinFeatureOperation); ei.setDistanceExtent(False, VI(244)); ei.participantBodies = [base]; c.features.extrudeFeatures.add(ei)
c.bRepBodies.item(0).material = design.materials.itemByName('Glass'); c.bRepBodies.item(0).name = 'graduated cylinder 100 mL'
from collections import Counter
done = Counter(); seen = set()
for oc in root.allOccurrences:
    cc = oc.component
    if cc.name in seen: continue
    seen.add(cc.name)
    for b in cc.bRepBodies:
        mat = b.material.name if b.material else ''
        anim = cc.name.startswith('ANIM-')
        if anim and b.name not in ('wall', 'floor'): continue
        if mat == 'Glass':
            b.appearance = GLASS; done['glass: ' + cc.name] += 1
        elif (mat == 'Polypropylene' and cc.name != 'REF-BIN') or anim:
            b.appearance = CLEAR; done['clear PP: ' + cc.name] += 1
        else: continue
        try: b.opacity = 1.0
        except Exception: pass
for k, v in sorted(done.items()): print('%-62s %d' % (k.encode('ascii', 'replace').decode(), v))
