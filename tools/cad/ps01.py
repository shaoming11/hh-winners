"""E5 auxiliary 2020 rail + PS-01 auger post (replaces AG-01): nothing threads into plastic."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
LIBO = [x for x in root.occurrences if x.component.name == 'HW-LIB (masters, hidden)'][0]
Mm = {x.component.name: x.component for x in LIBO.component.occurrences}
MS = [x for x in root.allOccurrences if x.component.name.startswith('Measuring')][0].component
frame = [x for x in root.occurrences if x.component.name.startswith('FRAME-2020')][0]
def T(o): return o.transform2.copy()
def place(comp_name, M, parent=MS):
    return parent.occurrences.addExistingComponent(Mm[comp_name], M)
# ---- templates: relative transforms screw->T-nut for a side-slot bracket bolt and for a vertical saddle bolt ----
allo = list(root.allOccurrences)
def near(o, names, r_mm):
    p = o.transform2.translation
    return [x for x in allo if x.component.name in names and x is not o and math.dist([v * 10 for v in x.transform2.translation.asArray()], [v * 10 for v in p.asArray()]) < r_mm]
br0 = [x for x in allo if x.component.name == '2020 inside corner bracket' and 'Frame brackets' in x.fullPathName and abs(x.transform2.translation.x * 10 - 265) < 0.5 and abs(x.transform2.translation.y * 10 - 498.5) < 0.5][0]
inv0 = br0.transform2.copy(); inv0.invert()
br_rel = []
for x in near(br0, ('SHCS ISO 4762 M5x8', 'T-nut 2020 drop-in M5'), 30):
    m = x.transform2.copy(); m2 = inv0.copy(); m2.transformBy(m)  # placeholder, replaced below
    rel = inv0.copy(); rel.transformBy(C.Matrix3D.create()); rel = x.transform2.copy(); rel.transformBy(inv0)
    br_rel.append((x.component.name, rel))
out.append('bracket template parts: %s' % [n for n, _ in br_rel])
sad = [x for x in allo if x.component.name == 'SHCS ISO 4762 M5x12' and abs(x.transform2.translation.x * 10 - 255) < 0.6 and abs(x.transform2.translation.y * 10 - 355) < 0.6][0]
tn = min([x for x in allo if x.component.name == 'T-nut 2020 drop-in M5'], key=lambda x: math.dist(x.transform2.translation.asArray(), sad.transform2.translation.asArray()))
inv_s = sad.transform2.copy(); inv_s.invert(); rel_vt = tn.transform2.copy(); rel_vt.transformBy(inv_s)
# ---- remove AG-01 and its hardware ----
for o in list(root.occurrences):
    if o.component.name in ('AG-01 auger stand', 'PS-01 auger post', 'FRAME-2020 aux rail E5'): o.deleteMe()
n = 0
for o in list(MS.occurrences):
    t = o.transform2.translation; x, y, z = t.x * 10, t.y * 10, t.z * 10
    if (abs(x - 255) < 0.6 and 280 < y < 340 and z < 30) or (o.component.name == 'SHCS ISO 4762 M3x20' and z > 140) or (z < 40 and x < 90 and 255 < y < 320 and o.component.name in ('SHCS ISO 4762 M5x12', 'T-nut 2020 drop-in M5', 'SHCS ISO 4762 M5x8', '2020 inside corner bracket')) or (o.component.name in ('SHCS ISO 4762 M3x25', 'Hex nut ISO 4032 M3') and x < 90):
        o.deleteMe(); n += 1
for o in list(MS.occurrences):
    t = o.transform2.translation
    if o.component.name in ('2020 inside corner bracket', 'SHCS ISO 4762 M5x8', 'T-nut 2020 drop-in M5') and 215 < t.x * 10 < 256 and 295 < t.y * 10 < 335 and t.z * 10 < 25: o.deleteMe(); n += 1
out.append('removed %d old AG-01/E5 hardware occurrences' % n)
# ---- E5: copy of RAIL-X-FRONT moved to X-155..245, Y290-310 ----
rf = [b for b in frame.component.bRepBodies if b.name == 'RAIL-X-FRONT'][0]
tb = F.TemporaryBRepManager.get().copy(rf)
mv = C.Matrix3D.create(); mv.translation = C.Vector3D.create(-42.0, -20.85, 0); F.TemporaryBRepManager.get().transform(tb, mv)
eo = root.occurrences.addNewComponent(C.Matrix3D.create()); ec = eo.component; ec.name = 'FRAME-2020 aux rail E5'
bf = ec.features.baseFeatures.add(); bf.startEdit(); ec.bRepBodies.add(tb, bf); bf.finishEdit()
eb = ec.bRepBodies.item(0); eb.name = 'RAIL-E5 (spare 400 mm)'; eb.material = design.materials.itemByName('Aluminum 6061')
bb = eb.boundingBox; out.append('E5 %s - %s' % ([round(v * 10, 1) for v in bb.minPoint.asArray()], [round(v * 10, 1) for v in bb.maxPoint.asArray()]))
ji = root.asBuiltJoints.createInput(eo, frame, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-E5-frame'
# ---- corner bracket E5 north face / Y-left rail west face, corner (245, 310) ----
Bm = C.Matrix3D.create(); Bm.setWithCoordinateSystem(C.Point3D.create(24.5, 31.0, 0), C.Vector3D.create(-1, 0, 0), C.Vector3D.create(0, -1, 0), C.Vector3D.create(0, 0, 1))
place('2020 inside corner bracket', Bm)
for nm, rel in br_rel:
    m = rel.copy(); m.transformBy(Bm); place(nm, m)
# ---- PS-01 post ----
ps = Part('PS-01 auger post', (35, 258, 0))
ps.box(35, 258, 0, 75, 290, 135)                       # post 40 x 32, stands on the table against E5's south face
ps.box(35, 290, 20, 75, 310, 28)                        # flange over the E5 top
for x in (43, 67):
    ps.ycyl(x, 10, 280, 290.01, 2.75, CUT)              # M5 into E5 south-face slot (10 mm wall)
    ps.ycyl(x, 10, 257.9, 280, 5.0, CUT)                # dia-10 pocket for the head
ps.holes([(55, 300)], 28, 19.9, 5.5)                      # M5 into E5 top slot (centred so its T-nut clears the side-slot nuts)
ps.holes([(55, 300)], 28, 26.5, 10.0)
ps.holes([(45, 270), (65, 270)], 135, 117, 3.4)          # DH-01 through-bolts
ps.box(34.9, 267.1, 123.5, 68.6, 272.9, 126.2, CUT)      # hex-nut slot from the west face (2 x M3 nuts)
ps.body.name = 'PS-01'
spec_fillet(ps, (34, 289, 27, 76, 291.5, 29.5), 5.0, 'post-to-flange root')
ps.box(34, 289.4, 17.5, 76, 292.5, 20.0, CUT)           # relief along E5's top-south edge (no fillet sliver into the rail)
out.append('PS-01 ' + process4(ps.c, [(-1, 8.5, 122.5, 35, 15.5, 127.5), (-1, 30.5, 17, 41, 34, 21.5)], r_out=2.0, r_in=2.0, ch=0.6, r_top=1.2))
ps.c.bRepBodies.item(0).material = design.materials.itemByName('PLA (FDM)')
b = ps.c.bRepBodies.item(0); out.append('PS-01 %.1f cm3, bodies %d' % (b.volume, ps.c.bRepBodies.count))
pso = [x for x in root.occurrences if x.component.name == 'PS-01 auger post'][0]
ji = root.asBuiltJoints.createInput(pso, frame, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-PS01-frame'
# ---- PS-01 hardware ----
for x in (43, 67):    # side bolts: head on the pocket floor (Y280) facing -Y, shank +Y into the slot
    m = C.Matrix3D.create(); m.setWithCoordinateSystem(C.Point3D.create(x / 10, 28.0, 1.0), C.Vector3D.create(1, 0, 0), C.Vector3D.create(0, 0, 1), C.Vector3D.create(0, -1, 0))
    place('SHCS ISO 4762 M5x12', m)
    # T-nut in the side slot: reuse the bracket template's screw->nut relation
    scr = [(n_, r_) for n_, r_ in br_rel if n_ == 'SHCS ISO 4762 M5x8']; nut = [(n_, r_) for n_, r_ in br_rel if n_.startswith('T-nut')]
    if scr and nut:
        s_inv = scr[0][1].copy(); s_inv.invert(); rel = nut[0][1].copy(); rel.transformBy(s_inv)   # nut relative to its screw
        # M5x8 head sits 3 mm (bracket) above the slot face; our M5x12 head sits 10 mm above -> shift 7 mm along the screw axis
        mm = rel.copy(); sh = C.Matrix3D.create(); sh.translation = C.Vector3D.create(0, 0, -0.7); mm.transformBy(sh); mm.transformBy(m); place('T-nut 2020 drop-in M5', mm)
for x in (55,):    # top bolt like the saddle bolts
    m = C.Matrix3D.create(); m.translation = C.Vector3D.create(x / 10, 30.0, 2.65); place('SHCS ISO 4762 M5x12', m)
    rz = C.Matrix3D.create(); rz.setToRotation(math.pi / 2, C.Vector3D.create(0, 0, 1), C.Point3D.create(0, 0, 0))   # E5 runs along X: turn the T-nut 90 deg
    up = C.Matrix3D.create(); up.translation = C.Vector3D.create(0, 0, 0.15)   # counterbored head sits 1.5 lower than the template; nut stays against the slot lip
    mm = rel_vt.copy(); mm.transformBy(rz); mm.transformBy(up); mm.transformBy(m); place('T-nut 2020 drop-in M5', mm)
print('\n'.join(out + FLOG))
