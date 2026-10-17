# shared helpers for CDR v2 parts (exec'd after parts_lib + fillet_lib)
FLOG = []
def _sketch_poly(part, pl, pts3):
    sk = part.c.sketches.add(pl)
    pp = [sk.modelToSketchSpace(C.Point3D.create((p[0] - part.o[0]) / 10, (p[1] - part.o[1]) / 10, (p[2] - part.o[2]) / 10)) for p in pts3]
    for i in range(len(pp)): sk.sketchCurves.sketchLines.addByTwoPoints(pp[i], pp[(i + 1) % len(pp)])
    col = C.ObjectCollection.create(); col.add(max(list(sk.profiles), key=lambda p: p.areaProperties().area))
    return col
def _extrude(part, col, dist, op):
    c = part.c
    ei = c.features.extrudeFeatures.createInput(col, NEW if part.body is None else op); ei.setDistanceExtent(False, VI(dist))
    if part.body is not None and op != NEW: ei.participantBodies = [part.body]
    f = c.features.extrudeFeatures.add(ei)
    if part.body is None: part.body = f.bodies.item(0)
    return f
def vpoly_xz(part, pts_xz, y0, y1, op=JOIN):
    """polygon in the XZ plane (world x,z), extruded along +Y from y0 to y1"""
    c = part.c; sgn = c.xZConstructionPlane.geometry.normal.y
    pi = c.constructionPlanes.createInput(); pi.setByOffset(c.xZConstructionPlane, VI((y0 - part.o[1]) * sgn)); pl = c.constructionPlanes.add(pi); pl.isLightBulbOn = False
    return _extrude(part, _sketch_poly(part, pl, [(x, y0, z) for x, z in pts_xz]), (y1 - y0) * sgn, op)
def vpoly_yz(part, pts_yz, x0, x1, op=JOIN):
    """polygon in the YZ plane (world y,z), extruded along +X from x0 to x1"""
    c = part.c; sgn = c.yZConstructionPlane.geometry.normal.x
    pi = c.constructionPlanes.createInput(); pi.setByOffset(c.yZConstructionPlane, VI((x0 - part.o[0]) * sgn)); pl = c.constructionPlanes.add(pi); pl.isLightBulbOn = False
    return _extrude(part, _sketch_poly(part, pl, [(x0, y, z) for y, z in pts_yz]), (x1 - x0) * sgn, op)
def poly_xy(part, pts, z0, z1, op=JOIN):
    return _extrude(part, _sketch_poly(part, part.plane(z0), [(x, y, z0) for x, y in pts]), z1 - z0, op)
def in_world_box(e, origin, box):
    bb = e.boundingBox
    lo = [bb.minPoint.x * 10 + origin[0], bb.minPoint.y * 10 + origin[1], bb.minPoint.z * 10 + origin[2]]
    hi = [bb.maxPoint.x * 10 + origin[0], bb.maxPoint.y * 10 + origin[1], bb.maxPoint.z * 10 + origin[2]]
    return all(lo[i] >= box[i] - 0.05 and hi[i] <= box[i + 3] + 0.05 for i in range(3))
def spec_fillet(part, box, r, label, kind='concave', min_len=2.0):
    """explicit load-path fillet: all edges of `kind` inside a world box, radius r, fallbacks logged"""
    edges = []
    for rr in (r, 0.75 * r, 0.5 * r):
        body = part.c.bRepBodies.item(0)
        edges = [e for e in body.edges if in_world_box(e, part.o, box) and classify(body, e) == kind and e.length * 10 >= min_len]
        if not edges:
            FLOG.append('%s | %s: no %s edges in box' % (part.c.name, label, kind)); return 0
        if guarded_add(part.c, 'fillet', edges, rr):
            FLOG.append('%s | %s: R%.1f on %d edges%s' % (part.c.name, label, rr, len(edges), '' if rr == r else '  ** FALLBACK from R%.1f' % r)); return rr
    n = 0
    for e in edges:
        if e.isValid and guarded_add(part.c, 'fillet', [e], 0.5 * r): n += 1
    FLOG.append('%s | %s: R%.1f individually on %d/%d edges  ** FALLBACK' % (part.c.name, label, 0.5 * r, n, len(edges))); return 0.5 * r
def spec_chamfer(part, box, d, label, kind='convex', min_len=2.0):
    body = part.c.bRepBodies.item(0)
    edges = [e for e in body.edges if in_world_box(e, part.o, box) and classify(body, e) == kind and e.length * 10 >= min_len]
    for dd in (d, 0.75 * d, 0.5 * d):
        if edges and guarded_add(part.c, 'chamfer', edges, dd):
            FLOG.append('%s | %s: chamfer %.1f on %d edges%s' % (part.c.name, label, dd, len(edges), '' if dd == d else '  ** FALLBACK from %.1f' % d)); return dd
        body = part.c.bRepBodies.item(0)
        edges = [e for e in body.edges if in_world_box(e, part.o, box) and classify(body, e) == kind and e.length * 10 >= min_len]
    FLOG.append('%s | %s: chamfer FAILED (%d edges)' % (part.c.name, label, len(edges))); return 0
