"""CDR-16: 1.5x45 slot-mouth chamfer on every GR-03 (clears the R1.5 tongue-root fillet); ST-09 centred on the real posts."""
import os, json, math
import adsk.core as C, adsk.fusion as F
root = design.rootComponent
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
exec(open(os.path.join(B, 'fillet_lib.py')).read())
D = json.load(open(os.path.join(B, 'gripper_design.json'))); FR = json.load(open(os.path.join(B, 'grip_frames.json')))
PHI = math.radians(D['PHI']); BF = D['B_F']; W = D['W']; BLK = D['BLK']; TZ0, TZ1 = D['TZ']; SL = 0.25
BETA43, QC43 = 12.5, -60.0
d = (math.cos(PHI), math.sin(PHI)); nb = (math.sin(PHI), -math.cos(PHI))
def mirror(p, beta):
    a = math.radians(2 * beta); return (p[0] * math.cos(a) + p[1] * math.sin(a), p[0] * math.sin(a) - p[1] * math.cos(a))
def rot(p, a): a = math.radians(a); return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a))
def uv_fixed(x, y): q = (x - BF[0], y - BF[1]); return (q[0] * d[0] + q[1] * d[1], q[0] * nb[0] + q[1] * nb[1])
def uv_moving(x, y): return uv_fixed(*mirror(rot((x, y), QC43), BETA43))
for tag in 'AB':
    a = [o for o in root.occurrences if o.component.name == 'REF-SO101-STOCK-' + tag][0]
    for j in a.childOccurrences.item(0).component.asBuiltJoints:
        if j.name.startswith('ARM'): j.jointMotion.rotationValue = 0
def local(tag, P, inv):
    fr = FR[tag]; gp, e1, e2 = fr['gp'], fr['e1'], fr['e2']
    z = gp[0] - P[0]; dy, dz = P[1] - gp[1], P[2] - gp[2]
    det = e1[1] * e2[2] - e1[2] * e2[1]; x = (dy * e2[2] - dz * e2[1]) / det; y = (e1[1] * dz - e1[2] * dy) / det
    u, v = inv(x, y); return u, v, z
log = []
for tag in 'AB':
    for side, inv in (('fixed', uv_fixed), ('moving', uv_moving)):
        fo = [o for o in root.occurrences if o.component.name == 'GR-03 fin-ray finger TPU (%s %s)' % (tag, side)][0]
        body = fo.bRepBodies.item(0); sel = []
        for e in body.edges:
            pts = []
            ok, p0, p1 = e.evaluator.getParameterExtents()
            for t in (p0, (p0 + p1) / 2, p1):
                ok, p = e.evaluator.getPointAtParameter(t); pts.append(local(tag, (p.x * 10, p.y * 10, p.z * 10), inv))
            if all(abs(u + BLK) < 0.05 and 2 - SL - 0.1 <= v <= W - 2 + SL + 0.1 and TZ0 - SL - 0.1 <= z <= TZ1 + SL + 0.1 for u, v, z in pts):
                sel.append(e.nativeObject if e.nativeObject else e)
        done = 0
        for s in (1.5, 1.2, 1.0):
            if sel and guarded_add(fo.component, 'chamfer', sel, s): log.append('GR-03 %s %s slot-mouth chamfer %.1f on %d edges' % (tag, side, s, len(sel))); done = 1; break
        if not done: log.append('GR-03 %s %s slot-mouth chamfer FAILED (%d edges)' % (tag, side, len(sel)))
# ST-09 sleeves onto the real post axes
posts = []
st = [o for o in root.allOccurrences if o.component.name == 'ST-01'][0]
for f in st.bRepBodies.item(0).faces:
    g = f.geometry
    if isinstance(g, C.Cylinder) and abs(g.radius * 10 - 9.0) < 0.05: posts.append((g.origin.x, g.origin.y))
s9 = [o for o in root.allOccurrences if o.component.name == 'ST-09 stop-post TPU sleeve']
for o in s9:
    t = o.transform2.translation; px, py = min(posts, key=lambda p: (p[0] - t.x) ** 2 + (p[1] - t.y) ** 2)
    m = o.transform2; tt = m.translation; tt.x = px; tt.y = py; m.translation = tt; o.transform2 = m
    log.append('ST-09 moved to (%.2f, %.2f)' % (px * 10, py * 10))
try: design.snapshots.add()
except Exception: pass
print('\n'.join(log))
