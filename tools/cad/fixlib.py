import adsk.core as C, adsk.fusion as F, math
root = design.rootComponent
def V(x, y, z=0): return C.Vector3D.create(x / 10, y / 10, z / 10)
def T(dx, dy, dz=0):
    m = C.Matrix3D.create(); m.translation = V(dx, dy, dz); return m
def Rz(deg, cx, cy):
    m = C.Matrix3D.create(); m.setToRotation(math.radians(deg), C.Vector3D.create(0, 0, 1), C.Point3D.create(cx / 10, cy / 10, 0)); return m
def Rx(deg, cy, cz):
    m = C.Matrix3D.create(); m.setToRotation(math.radians(deg), C.Vector3D.create(1, 0, 0), C.Point3D.create(0, cy / 10, cz / 10)); return m
def ctr(o):
    bb = o.boundingBox; return ((bb.minPoint.x + bb.maxPoint.x) * 5, (bb.minPoint.y + bb.maxPoint.y) * 5, (bb.minPoint.z + bb.maxPoint.z) * 5)
def joints_of(o):
    t = o.entityToken; r = []
    for j in list(root.asBuiltJoints) + list(root.joints):
        try:
            a, b = j.occurrenceOne, j.occurrenceTwo
            if (a and a.entityToken == t) or (b and b.entityToken == t): r.append(j)
        except Exception: pass
    return r
def place(o, M_world_new):
    """Move occurrence o (root or nested) to the new transform (relative to its parent). Returns the (possibly new) occurrence."""
    for j in joints_of(o): j.deleteMe()
    nat = o
    try: g = nat.isGrounded
    except Exception: g = False
    if g: nat.isGrounded = False
    before = ctr(o)
    nat.transform2 = M_world_new
    try: design.snapshots.add()
    except Exception: pass
    after = ctr(o)
    if math.dist(before, after) > 0.01 or M_world_new.isEqualTo(nat.transform2):
        if g:
            try: nat.isGrounded = True
            except Exception: pass
        return o, 'set'
    # fallback: re-add the component in the same parent and delete the old occurrence
    parent = nat.assemblyContext.component if nat.assemblyContext else root
    pcomp = o.assemblyContext.component if o.assemblyContext else root
    newo = pcomp.occurrences.addExistingComponent(o.component, M_world_new)
    o.deleteMe()
    if g:
        try: newo.isGrounded = True
        except Exception: pass
    return newo, 'readded'
def moveby(o, M):
    m = o.transform2.copy(); m.transformBy(M)
    return place(o, m)
