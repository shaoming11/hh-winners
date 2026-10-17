"""Stands v2 (light, no foot) + RK-04 rack tie plate (Y-left) + TT-05 turntable tie plate (Y-right) + JG-07/JG-08 end-hook gauges."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []; PLA = design.materials.itemByName('PLA (FDM)'); ZF = 60.2
P = [(192.3, 394.6), (134.6, 477.1), (108.5, 574.4)]
def rm(prefix):
    for o in list(root.occurrences):
        if o.component.name.startswith(prefix):
            for j in list(root.asBuiltJoints):
                try:
                    if j.occurrenceOne == o or j.occurrenceTwo == o: j.deleteMe()
                except Exception: pass
            o.deleteMe()
for p_ in ('RK-03', 'RK-04', 'TT-05', 'JG-07', 'JG-08'): rm(p_)
def fin(p, label, keep=None):
    p.body = p.c.bRepBodies.item(0); p.body.name = label
    out.append('%-6s %s' % (label, process4(p.c, keep or [], r_out=1.0, r_in=1.0, ch=0.4, r_top=0.6)))
    b = p.c.bRepBodies.item(0); b.material = PLA; bb = b.boundingBox
    out.append('       %.1f cm3 bodies %d  %.0f x %.0f x %.0f' % (b.volume, p.c.bRepBodies.count, (bb.maxPoint.x-bb.minPoint.x)*10, (bb.maxPoint.y-bb.minPoint.y)*10, (bb.maxPoint.z-bb.minPoint.z)*10))
def bar(p, x0, y0, x1, y1, w, z0, z1):
    L = math.hypot(x1 - x0, y1 - y0); nx, ny = -(y1 - y0) / L * w / 2, (x1 - x0) / L * w / 2
    poly_xy(p, [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], z0, z1)
def xcyl(p, y, z, x0, x1, r, op):
    sgn = p.c.yZConstructionPlane.geometry.normal.x
    pi = p.c.constructionPlanes.createInput(); pi.setByOffset(p.c.yZConstructionPlane, VI((x0 - p.o[0]) * sgn)); pl = p.c.constructionPlanes.add(pi); pl.isLightBulbOn = False
    sk = p.c.sketches.add(pl); sk.sketchCurves.sketchCircles.addByCenterRadius(sk.modelToSketchSpace(C.Point3D.create((x0 - p.o[0]) / 10, (y - p.o[1]) / 10, (z - p.o[2]) / 10)), r / 10)
    col = C.ObjectCollection.create(); col.add(sk.profiles.item(0))
    ei = p.c.features.extrudeFeatures.createInput(col, op); ei.setDistanceExtent(False, VI((x1 - x0) * sgn)); ei.participantBodies = [p.c.bRepBodies.item(0)]; p.c.features.extrudeFeatures.add(ei)
# ---- stand v2: column r30.8 wall 1.2, ribs 1.0, floor 2.4, cup ring 12 tall; no foot ----
st = Part('RK-03 reagent stand v2 (x3)', (P[0][0], P[0][1], 0)); x, y = P[0]
st.cyl(x, y, 0, ZF, 30.8); st.cyl(x, y, ZF, ZF + 12.0, 30.8, JOIN, 28.3)
st.cyl(x, y, -0.1, 57.8, 29.6, CUT)
for a in (0, 90):
    ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a)); h = 29.8; w = 0.5
    poly_xy(st, [(x - h*ca - w*sa, y - h*sa + w*ca), (x + h*ca - w*sa, y + h*sa + w*ca), (x + h*ca + w*sa, y + h*sa - w*ca), (x - h*ca + w*sa, y - h*sa - w*ca)], 0, 57.8)
fin(st, 'RK-03v2')
stc = st.c
for (x, y) in P[1:]: root.occurrences.addExistingComponent(stc, C.Matrix3D.create()).transform2 = (lambda m: (setattr(m, 'translation', C.Vector3D.create((x - P[0][0]) / 10 + P[0][0] / 10, (y - P[0][1]) / 10 + P[0][1] / 10, 0)), m)[1])(C.Matrix3D.create())
# ---- RK-04 rack tie plate: rings (ID 62.2) round each column, bars, flange on Y-left west face (X239-245) with 2 x M4 ----
rk = Part('RK-04 rack tie plate (Y-left)', (200, 480, 0))
rk.box(239, 356, 0, 245, 612, 20)                                  # flange
for i, (x, y) in enumerate(P):
    bar(rk, x, y, 242, y, 10, 0, 3)                               # tie to flange (built first so all joins)
    rk.cyl(x, y, 0, 8, 35.0, JOIN, 31.1)                          # capture ring
    if i < 2: bar(rk, x, y, P[i + 1][0], P[i + 1][1], 10, 0, 3)
for x, y in P: rk.cyl(x, y, -0.1, 8.1, 31.1, CUT)                  # keep the ring bore clear of the bars
for y in (380, 590):
    xcyl(rk, y, 10, 238.9, 245.1, 2.25, CUT); xcyl(rk, y, 10, 238.9, 241.0, 4.0, CUT)
fin(rk, 'RK-04')
# ---- JG-08: Y-left south end (Y290) -> RK-04 south edge (Y356), on the table against Y-left's west face ----
j8 = Part('JG-08 rack tie plate gauge', (236, 323, 0))
j8.box(229, 290.0, 0, 239, 355.9, 14); j8.box(229, 284, 0, 265, 290, 14); fin(j8, 'JG-08')
# ---- TT-05 turntable tie plate: 3 mm plate X685-900 Y405-620 with TT-01 + E5 + PS-01 cut-outs (projected, +0.3), flange on Y-right east face ----
tt = Part('TT-05 turntable tie plate (Y-right)', (790, 512, 0))
tt.box(685, 405, 0, 900, 620, 3)
tt.box(685, 405, 0, 691, 620, 20)                                  # flange against Y-right's east face (X685)
tp = tt.c.constructionPlanes.createInput(); tp.setByOffset(tt.c.xYConstructionPlane, VI(-0.05)); pl = tt.c.constructionPlanes.add(tp); pl.isLightBulbOn = False
sk = tt.c.sketches.add(pl); n0 = 0
for nm in ('TT-01', 'FRAME-2020 aux rail E5', 'PS-01 auger post'):
    o = [x for x in root.allOccurrences if x.component.name == nm][0]
    b = o.bRepBodies.item(0)
    zmin = b.boundingBox.minPoint.z
    f = max([f for f in b.faces if isinstance(f.geometry, C.Plane) and abs(f.geometry.normal.z) > 0.99 and abs(f.boundingBox.maxPoint.z - zmin) < 0.005], key=lambda f: f.area)
    cc = sk.project(f)
    for i in range(cc.count): cc.item(i).isConstruction = False
    n0 += cc.count
loops = [p for p in sk.profiles]
col = C.ObjectCollection.create()
for p in sk.profiles: col.add(p)
ei = tt.c.features.extrudeFeatures.createInput(col, CUT); ei.setDistanceExtent(False, VI(25)); ei.participantBodies = [tt.c.bRepBodies.item(0)]
tt.c.features.extrudeFeatures.add(ei)
out.append('TT-05 projected %d curves, %d profiles cut' % (n0, len(loops)))
for y in (430, 600):
    xcyl(tt, y, 10, 684.9, 691.1, 2.25, CUT); xcyl(tt, y, 10, 689.0, 691.1, 4.0, CUT)
fin(tt, 'TT-05')
# ---- JG-07: Y-right south end (Y270) -> TT-05 south edge (Y405), on the table against Y-right's east face ----
j7 = Part('JG-07 turntable plate gauge', (695, 337, 0))
j7.box(691, 270.0, 0, 701, 404.9, 14); j7.box(665, 264, 0, 701, 270, 14); fin(j7, 'JG-07')
try: design.snapshots.add()
except Exception: pass
print('\n'.join(out + FLOG))
