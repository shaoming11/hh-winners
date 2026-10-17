"""CDR v2: WS-01 (CDR-06), WS-02 (CDR-17), TT-04 (CDR-14/15/12), ST-08 (CDR-26)."""
import os, math
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
PLA = design.materials.itemByName('PLA (FDM)')
def occ(name): return [o for o in root.occurrences if o.component.name == name][0]
def wrap(o, origin):
    p = Part.__new__(Part); p.c = o.component; p.o = origin; p.body = o.component.bRepBodies.item(0); return p
def circ_edges(body, r, zlo, zhi, origin_z):
    return [e for e in body.edges if isinstance(e.geometry, (C.Circle3D, C.Arc3D)) and abs(e.geometry.radius * 10 - r) < 0.05
            and zlo <= e.geometry.center.z * 10 + origin_z <= zhi]
def try_edges(comp, kind, edges, sizes, label):
    for s in sizes:
        if edges and guarded_add(comp, kind, edges, s):
            out.append('%s: %s %.1f on %d edges%s' % (label, kind, s, len(edges), '' if s == sizes[0] else '  ** FALLBACK from %.1f' % sizes[0])); return s
    out.append('%s: %s FAILED (%d edges)' % (label, kind, len(edges))); return 0
# ---------------- WS-01 v2 ----------------
ws1o = occ('WS-01 scale base'); ws1 = wrap(ws1o, (395, 455, 0)); clear(ws1.c)
ws1.box(493, 468, 0, 507, 496, 45)                    # overload-stop tower under the pan rim (CDR-06)
ws1.holes([(500, 475)], 45, 35, 2.5)                  # M3x12 set-screw pilot
ws1.holes([(410, 508.5), (465, 508.5)], 28, 26.5, 10.0)   # dia 10 x 1.5 counterbores
spec_fillet(ws1, (393, 493, 27, 429, 497, 29.5), 4.0, 'pedestal-to-saddle root (along X)')
spec_fillet(ws1, (425.5, 493, -0.5, 428.5, 496, 28.5), 4.0, 'pedestal-to-saddle root (vertical)')
spec_fillet(ws1, (491, 493, -0.5, 509, 497, 46), 3.0, 'stop tower to saddle')
out.append('WS-01 ' + process4(ws1.c, [(-2, 43, -1, 119, 64, 21.2)], r_out=2.0, r_in=2.0, ch=0.6, r_top=1.2))
ws1.c.bRepBodies.item(0).material = PLA
# ---------------- WS-02 v2 ----------------
ws2 = Part('WS-02 scale pan', (468, 475, 57.7))
ws2.cyl(468, 475, 57.7, 63.7, 40.0)                   # dia 80 pan (capped by arm-B base clearance)
ws2.cyl(468, 475, 63.7, 71.7, 40.0, JOIN, 38.0)       # 8 mm spill lip, ID 76 (~24 mL)
ws2.cyl(468, 475, 63.7, 71.7, 25.5, JOIN, 23.0)       # beaker locating ring ID 46
ws2.box(430, 467.5, 57.7, 458, 482.5, 59.2, CUT)      # relief over the load-cell flexure
ws2.holes([(463, 475), (473, 475)], 63.7, 59.7, 8.0)
ws2.holes([(463, 475), (473, 475)], 59.7, 57.7, 4.4)
ws2.body.name = 'WS-02'
try_edges(ws2.c, 'chamfer', circ_edges(ws2.body, 23.0, 71.6, 71.8, 57.7), [2.0, 1.5, 1.0], 'WS-02 locator lead-in')
try_edges(ws2.c, 'fillet', circ_edges(ws2.c.bRepBodies.item(0), 23.0, 63.6, 63.8, 57.7) + circ_edges(ws2.c.bRepBodies.item(0), 25.5, 63.6, 63.8, 57.7), [1.5, 1.0], 'WS-02 ring roots')
try_edges(ws2.c, 'fillet', circ_edges(ws2.c.bRepBodies.item(0), 38.0, 63.6, 63.8, 57.7), [1.5, 1.0], 'WS-02 lip root')
try_edges(ws2.c, 'fillet', circ_edges(ws2.c.bRepBodies.item(0), 40.0, 71.6, 71.8, 57.7) + circ_edges(ws2.c.bRepBodies.item(0), 38.0, 71.6, 71.8, 57.7), [0.8, 0.5], 'WS-02 lip top')
try_edges(ws2.c, 'chamfer', circ_edges(ws2.c.bRepBodies.item(0), 40.0, 57.6, 57.8, 57.7), [0.5], 'WS-02 bed chamfer')
ws2.c.bRepBodies.item(0).material = PLA
ji = root.asBuiltJoints.createInput(occ('WS-02 scale pan'), ws1o, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-WS02-WS01'
# ---------------- TT-04 (unprinted): walls 16 -> 12, lead-ins, R1.5 pocket roots ----------------
tto = occ('TT-04 beaker locator ring'); tt = wrap(tto, (175, 370, 58.6)); clear(tt.c)
tt.box(40, 235, 58.6 + 12, 310, 505, 58.6 + 20, CUT)
b = tt.c.bRepBodies.item(0)
zfloor = None
cands = sorted(set(round(e.geometry.center.z * 10, 2) for e in b.edges if isinstance(e.geometry, (C.Circle3D, C.Arc3D)) and abs(e.geometry.radius * 10 - 23.0) < 0.05))
out.append('TT-04 r23 circle z levels %s' % cands)
try_edges(tt.c, 'chamfer', circ_edges(b, 23.0, 58.6 + 11.9, 58.6 + 12.1, 58.6), [1.8, 1.4, 1.0], 'TT-04 pocket lead-in (2.4 wall)')
lo = [z for z in cands if z < 11.5]
if lo:
    zf = max(lo)
    try_edges(tt.c, 'fillet', circ_edges(tt.c.bRepBodies.item(0), 23.0, 58.6 + zf - 0.1, 58.6 + zf + 0.1, 58.6), [1.5, 1.0], 'TT-04 pocket inner roots')
    try_edges(tt.c, 'fillet', circ_edges(tt.c.bRepBodies.item(0), 25.4, 58.6 + zf - 0.1, 58.6 + zf + 0.1, 58.6), [1.5, 1.0], 'TT-04 pocket outer roots')
out.append('TT-04 ' + process4(tt.c, [], r_out=1.5, r_in=1.5, ch=0.4, r_top=0.8))
tt.c.bRepBodies.item(0).material = PLA
# ---------------- ST-08 dia 7.2 (CDR-26) ----------------
st8 = [o for o in root.allOccurrences if o.component.name == 'ST-08 bearing race spacer'][0].component
n = 0
for sk in st8.sketches:
    for cc in sk.sketchCurves.sketchCircles:
        if abs(cc.radius - 0.4) < 1e-4: cc.radius = 0.36; n += 1
out.append('ST-08 OD 8 -> 7.2 (%d circles), vol %.3f cm3' % (n, st8.bRepBodies.item(0).volume))
for nm in ('WS-01 scale base', 'WS-02 scale pan', 'TT-04 beaker locator ring'):
    bb = occ(nm).component.bRepBodies.item(0)
    out.append('%s %.1f cm3' % (nm, bb.volume))
print('\n'.join(out + FLOG))
