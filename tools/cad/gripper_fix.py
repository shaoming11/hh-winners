"""CDR-16 gripper fit features, found by predicted world position:
slot-roof/floor long edges 2x45 (TPU, concave fill), tongue long edges 2x45 (PLA), tongue tip 1x45 lead-in,
tongue roots R1.5 at the bridge face."""
import os, json, math
import adsk.core as C, adsk.fusion as F
root = design.rootComponent
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
exec(open(os.path.join(B, 'fillet_lib.py')).read())
D = json.load(open(os.path.join(B, 'gripper_design.json'))); FR = json.load(open(os.path.join(B, 'grip_frames.json')))
PHI = math.radians(D['PHI']); BF = D['B_F']; W = D['W']; BLK = D['BLK']; TZ0, TZ1 = D['TZ']; SL = 0.25
BETA43, QC43 = 12.5, -60.0
d = (math.cos(PHI), math.sin(PHI)); nb = (math.sin(PHI), -math.cos(PHI))
def to_fixed(u, v): return (BF[0] + u * d[0] + v * nb[0], BF[1] + u * d[1] + v * nb[1])
def mirror(p, beta):
    a = math.radians(2 * beta); return (p[0] * math.cos(a) + p[1] * math.sin(a), p[0] * math.sin(a) - p[1] * math.cos(a))
def rot(p, a): a = math.radians(a); return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a))
def to_moving(u, v): return rot(mirror(to_fixed(u, v), BETA43), -QC43)
# arms at rest
for tag in 'AB':
    a = [o for o in root.occurrences if o.component.name == 'REF-SO101-STOCK-' + tag][0]
    for j in a.childOccurrences.item(0).component.asBuiltJoints:
        if j.name.startswith('ARM'): j.jointMotion.rotationValue = 0
def world(tag, place, u, v, z):
    fr = FR[tag]; gp, e1, e2 = fr['gp'], fr['e1'], fr['e2']; x, y = place(u, v)
    return (gp[0] - z, gp[1] + x * e1[1] + y * e2[1], gp[2] + x * e1[2] + y * e2[2])
def mid(e):
    ev = e.evaluator; ok, p0, p1 = ev.getParameterExtents(); ok, p = ev.getPointAtParameter((p0 + p1) / 2); return (p.x * 10, p.y * 10, p.z * 10)
def find(occ, pts, tol=0.6):
    """edges (as proxies of the occurrence's native body) whose midpoint is within tol of any target"""
    body = occ.bRepBodies.item(0); out = []
    for e in body.edges:
        m = mid(e)
        if any(math.dist(m, p) < tol for p in pts): out.append(e)
    return out
def apply(occ, kind, edges, sizes, label, log):
    comp = occ.component; nat = [e.nativeObject if e.nativeObject else e for e in edges]
    for s in sizes:
        if nat and guarded_add(comp, kind, nat, s):
            log.append('%s %s: %s %.1f on %d/%d edges%s' % (comp.name, label, kind, s, len(nat), len(nat), '' if s == sizes[0] else ' ** FALLBACK')); return
    n = 0
    for e in nat:
        if e.isValid and guarded_add(comp, kind, [e], sizes[-1]): n += 1
    log.append('%s %s: %s %.1f individually on %d/%d edges ** FALLBACK' % (comp.name, label, kind, sizes[-1], n, len(nat)))
log = []
umid_slot = (-BLK + (-1.5 + SL)) / 2          # slot runs u -BLK .. -1.5+SL
umid_tng = (-12.0 + (-1.5)) / 2               # exposed tongue between the bridge face and its tip
for tag in 'AB':
    for side, place in (('fixed', to_fixed), ('moving', to_moving)):
        fo = [o for o in root.occurrences if o.component.name == 'GR-03 fin-ray finger TPU (%s %s)' % (tag, side)][0]
        pts = [world(tag, place, umid_slot, v, z) for v in (2 - SL, W - 2 + SL) for z in (TZ0 - SL, TZ1 + SL)]
        apply(fo, 'chamfer', find(fo, pts), (2.0, 1.5), 'slot roof/floor lead edges', log)
        body_name = 'GR-01 gripper body (%s)' % tag if side == 'fixed' else 'GR-02 moving jaw (%s)' % tag
        go = [o for o in root.occurrences if o.component.name == body_name][0]
        pts = [world(tag, place, umid_tng, v, z) for v in (2.0, W - 2.0) for z in (TZ0, TZ1)]
        apply(go, 'chamfer', find(go, pts), (2.0, 1.5), 'tongue long edges', log)
        tip = [world(tag, place, -1.5, (2 + W - 2) / 2, z) for z in (TZ0, TZ1)] + [world(tag, place, -1.5, v, (TZ0 + TZ1) / 2) for v in (2.0, W - 2.0)]
        apply(go, 'chamfer', find(go, tip, 1.0), (1.0, 0.6), 'tongue tip lead-in', log)
        root_pts = [world(tag, place, -12.0, (2 + W - 2) / 2, z) for z in (TZ0, TZ1)] + [world(tag, place, -12.0, v, (TZ0 + TZ1) / 2) for v in (2.0, W - 2.0)]
        apply(go, 'fillet', find(go, root_pts, 1.5), (1.5, 1.0), 'tongue roots', log)
print('\n'.join(log))
