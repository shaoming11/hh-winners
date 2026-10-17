exec(open(r'C:/Users/User/fusion_bridge/fixlib.py').read())
def one(n): return [o for o in root.occurrences if o.component.name == n][0]
def W(o):
    """world matrix of an occurrence proxy by composing native transforms along its path"""
    chain = []; cur = o
    while cur is not None:
        nat = cur.nativeObject if cur.nativeObject else cur
        chain.append(nat.transform2.copy()); cur = cur.assemblyContext
    m = C.Matrix3D.create()
    for t in chain:            # child first: m = parent * ... * child  -> apply child then parents
        m.transformBy(t)
    return m
def inv(m): m = m.copy(); m.invert(); return m
def link(X, prefix):
    a = one('REF-SO101-STOCK-' + X).childOccurrences.item(0)
    return [c for c in a.childOccurrences if c.component.name.startswith(prefix)][0]
fA, fB = W(link('A', 'Wrist_Roll_Follower')), W(link('B', 'Wrist_Roll_Follower'))
jA, jB = W(link('A', 'Moving_Jaw')), W(link('B', 'Moving_Jaw'))
d = fA.copy(); d.transformBy(inv(fB)) if False else None
rel = inv(fB); rel.transformBy(fA)          # fA * inv(fB)
print('follower A vs B (should be pure X shift if same pose):', [round(v, 4) for v in rel.asArray()])
relj = inv(jB); relj.transformBy(jA)
print('moving jaw A vs B:', [round(v, 4) for v in relj.asArray()])
out = []
for n, R_ in (('GR-01 gripper body (%s)', rel), ('GR-03 fin-ray finger TPU (%s fixed)', rel), ('GR-02 moving jaw (%s)', relj), ('GR-03 fin-ray finger TPU (%s moving)', relj)):
    a, b = one(n % 'A'), one(n % 'B')
    for j in joints_of(a): j.deleteMe()
    new = b.transform2.copy(); new.transformBy(R_)
    place(a, new); out.append(n % 'A')
try: design.snapshots.add()
except Exception: pass
st = one('REF-SO101-STOCK-A').childOccurrences.item(0)
fol = link('A', 'Wrist_Roll_Follower'); mj = link('A', 'Moving_Jaw')
for a, b, nm in ((one('GR-01 gripper body (A)'), fol, 'FIX-GR01A-wristroll'), (one('GR-02 moving jaw (A)'), mj, 'FIX-GR02A-gripperjaw'),
                 (one('GR-03 fin-ray finger TPU (A fixed)'), one('GR-01 gripper body (A)'), 'FIX-GR03A-fixed'), (one('GR-03 fin-ray finger TPU (A moving)'), one('GR-02 moving jaw (A)'), 'FIX-GR03A-moving')):
    ji = root.asBuiltJoints.createInput(a, b, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = nm
print('re-posed', out)
