"""PS-01 v2: post +25 mm (Z0-160) so DH-01 clears 74 mm tall 100 mL beakers; everything else as ps01.py."""
import os
B = os.path.join(os.path.expanduser('~'), 'fusion_bridge')
for f in ('parts_lib.py', 'fillet_lib.py', 'cad_helpers.py'): exec(open(os.path.join(B, f)).read())
out = []
DZ = 25.0
frame = [x for x in root.occurrences if x.component.name.startswith('FRAME-2020')][0]
ps = Part('PS-01 auger post', (35, 258, 0))
ps.box(35, 258, 0, 75, 290, 135 + DZ)
ps.box(35, 290, 20, 75, 310, 28)
for x in (43, 67):
    ps.ycyl(x, 10, 280, 290.01, 2.75, CUT)
    ps.ycyl(x, 10, 257.9, 280, 5.0, CUT)
ps.holes([(55, 300)], 28, 19.9, 5.5)
ps.holes([(55, 300)], 28, 26.5, 10.0)
ps.holes([(45, 270), (65, 270)], 135 + DZ, 117 + DZ, 3.4)
ps.box(34.9, 267.1, 123.5 + DZ, 68.6, 272.9, 126.2 + DZ, CUT)
ps.body.name = 'PS-01'
spec_fillet(ps, (34, 289, 27, 76, 291.5, 29.5), 5.0, 'post-to-flange root')
ps.box(34, 289.4, 17.5, 76, 292.5, 20.0, CUT)
out.append('PS-01 ' + process4(ps.c, [(-1, 8.5, 122.5 + DZ, 35, 15.5, 127.5 + DZ), (-1, 30.5, 17, 41, 34, 21.5)], r_out=2.0, r_in=2.0, ch=0.6, r_top=1.2))
b = ps.c.bRepBodies.item(0); b.material = design.materials.itemByName('PLA (FDM)')
out.append('PS-01 v2 %.1f cm3, bodies %d' % (b.volume, ps.c.bRepBodies.count))
pso = [x for x in root.occurrences if x.component.name == 'PS-01 auger post'][0]
ji = root.asBuiltJoints.createInput(pso, frame, None); ji.setAsRigidJointMotion(); root.asBuiltJoints.add(ji).name = 'FIX-PS01-frame'
print('\n'.join(out + FLOG))
