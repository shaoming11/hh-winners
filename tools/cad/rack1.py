"""RK-03 one-piece reagent rack: 3 cups at the verified pocket positions (beaker bottom Z60.2), webs between them, and a spine that
bolts into the Y-left rail's WEST-face slot (2 x M4x10 + T-nuts) with a hook on the rail's south end face (Y290) as the Y datum."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []; PLA = design.materials.itemByName('PLA (FDM)'); ZF = 60.2
P = [(192.3, 394.6), (134.6, 477.1), (108.5, 574.4)]
for o in list(root.occurrences):
    if o.component.name.startswith('RK-03 reagent stand'):
        for j in list(root.asBuiltJoints):
            try:
                if j.occurrenceOne == o or j.occurrenceTwo == o: j.deleteMe()
            except Exception: pass
        o.deleteMe()
rk = Part('RK-03 reagent rack (one-piece, rail-mounted)', (192.3, 394.6, 0))
def bar(x0, y0, x1, y1, w, z0, z1):
    L = math.hypot(x1 - x0, y1 - y0); nx, ny = -(y1 - y0) / L * w / 2, (x1 - x0) / L * w / 2
    poly_xy(rk, [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], z0, z1)
# spine against Y-left's west face (X245): X239-245, Y290-600, Z0-20, plus the hook round the south end (Y284-290, X239-265)
rk.box(239, 290, 0, 245, 600, 20)
rk.box(239, 284, 0, 265, 290, 20)
for i, (x, y) in enumerate(P):
    bar(x, y, 242, y, 6, 0, 24)                       # tie to the spine first, so everything joins one body
    rk.cyl(x, y, 0, 3.0, 36.0)                        # foot
    rk.cyl(x, y, 0, ZF, 30.8)                         # column
    rk.cyl(x, y, ZF, ZF + 12.0, 30.8, JOIN, 28.3)     # cup wall, ID 56.6
    if i < 2: bar(x, y, P[i + 1][0], P[i + 1][1], 6, 0, 24)
rk.body.name = 'RK-03'
for x, y in P:                                         # hollow columns (thin wall + 2 ribs so the cup floor bridges <= 29 mm)
    rk.cyl(x, y, 3.0, 57.0, 29.2, CUT)
    for a in (0, 90):
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a)); h = 29.5; w = 0.8
        poly_xy(rk, [(x - h*ca - w*sa, y - h*sa + w*ca), (x + h*ca - w*sa, y + h*sa + w*ca), (x + h*ca + w*sa, y + h*sa - w*ca), (x - h*ca + w*sa, y - h*sa - w*ca)], 3.0, 57.0)
    rk.holes([(x + 15, y + 15)], 3.1, -0.1, 6.0)
# M4 through the spine into the west-face slot (slot centre Z10): counterbored from the outer (west) face
def xcyl(p, y, z, x0, x1, r, op):
    sgn = p.c.yZConstructionPlane.geometry.normal.x
    pi = p.c.constructionPlanes.createInput(); pi.setByOffset(p.c.yZConstructionPlane, VI((x0 - p.o[0]) * sgn))
    pl = p.c.constructionPlanes.add(pi); pl.isLightBulbOn = False
    sk = p.c.sketches.add(pl)
    cp = sk.modelToSketchSpace(C.Point3D.create((x0 - p.o[0]) / 10, (y - p.o[1]) / 10, (z - p.o[2]) / 10))
    sk.sketchCurves.sketchCircles.addByCenterRadius(cp, r / 10)
    col = C.ObjectCollection.create(); col.add(sk.profiles.item(0))
    ei = p.c.features.extrudeFeatures.createInput(col, op); ei.setDistanceExtent(False, VI((x1 - x0) * sgn)); ei.participantBodies = [p.c.bRepBodies.item(0)]
    p.c.features.extrudeFeatures.add(ei)
for y in (330, 560):
    xcyl(rk, y, 10, 238.9, 245.1, 2.25, CUT)          # M4 clearance
    xcyl(rk, y, 10, 238.9, 241.0, 4.0, CUT)           # head counterbore dia 8 x 2
rk.body = rk.c.bRepBodies.item(0)
out.append('RK-03 ' + process4(rk.c, [], r_out=1.5, r_in=1.5, ch=0.4, r_top=0.8))
b = rk.c.bRepBodies.item(0); b.material = PLA; bb = b.boundingBox
out.append('RK-03 one-piece %.1f cm3 bodies %d, %.0f x %.0f x %.0f mm' % (b.volume, rk.c.bRepBodies.count, (bb.maxPoint.x-bb.minPoint.x)*10, (bb.maxPoint.y-bb.minPoint.y)*10, (bb.maxPoint.z-bb.minPoint.z)*10))
print('\n'.join(out + FLOG))
