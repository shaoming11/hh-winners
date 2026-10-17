import adsk.core as C, adsk.fusion as F
root = design.rootComponent
out = []
def occ(n): return [o for o in root.occurrences if o.component.name == n][0]
s1, slo, bro, cro = occ('FRAME-2020 stage rail S1'), occ('ST-11 stage sled'), occ('ST-12 servo bridge'), occ('ST-13 crank')
for j in list(root.asBuiltJoints):
    if j.name in ('ST-SLIDE', 'ST-CRANK'): j.deleteMe()
# slider: geometry = the sled plate's bottom face, motion along world Y
bot = min([f for f in slo.bRepBodies.item(0).faces if isinstance(f.geometry, C.Plane) and abs(f.geometry.normal.z) > 0.99], key=lambda f: f.boundingBox.minPoint.z if f.area > 50 else 1e9)
ji = root.asBuiltJoints.createInput(slo, s1, F.JointGeometry.createByPlanarFace(bot, None, F.JointKeyPointTypes.CenterKeyPoint))
ji.setAsSliderJointMotion(F.JointDirections.CustomJointDirection, root.yConstructionAxis)
j = root.asBuiltJoints.add(ji); j.name = 'ST-SLIDE'
j.jointMotion.slideValue = -10.0; v = j.jointMotion.slideValue; j.jointMotion.slideValue = 0
out.append('ST-SLIDE ok, test move %.1f mm' % (v * 10))
hub = [f for f in cro.bRepBodies.item(0).faces if isinstance(f.geometry, C.Cylinder) and abs(f.geometry.radius * 10 - 12.0) < 0.05][0]
ji = root.asBuiltJoints.createInput(cro, bro, F.JointGeometry.createByNonPlanarFace(hub, F.JointKeyPointTypes.MiddleKeyPoint))
ji.setAsRevoluteJointMotion(F.JointDirections.CustomJointDirection, hub)
j = root.asBuiltJoints.add(ji); j.name = 'ST-CRANK'
out.append('ST-CRANK ok')
try: design.snapshots.add(); out.append('snapshot')
except Exception as e: out.append('snapshot: %s' % e)
for n in ('ST-11 stage sled', 'ST-12 servo bridge', 'ST-13 crank', 'ST-14 connecting rod', 'ST-15 pivot spacer'):
    b = occ(n).component.bRepBodies; out.append('%s bodies %d vol %.1f' % (n, b.count, b.item(0).volume if b.count else 0))
sv = [o for o in root.allOccurrences if o.component.name.startswith('FlashHobby M45CHW') and 'Servos' in o.fullPathName]
out.append('servos at ' + str([[round(v * 10) for v in o.transform2.translation.asArray()] for o in sv]))
print('\n'.join(out))
