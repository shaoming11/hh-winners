import adsk.core as C, adsk.fusion as F, os
OUT = "C:/Users/User/fusion_bridge/prints_v2"
root = design.rootComponent
PARTS = [
    ('AG-01 auger stand', 'AG-01_auger-stand-v2_qty1'),
    ('DH-01 yeast auger head', 'DH-01_yeast-auger-head-v2_qty1_SUPPORTS'),
    ('DH-02 auger screw', 'DH-02_auger-screw-v2_qty1_SUPPORTS'),
    ('WS-01 scale base', 'WS-01_scale-base-v2_qty1'),
    ('WS-02 scale pan', 'WS-02_scale-pan-v2_qty1'),
    ('TT-04 beaker locator ring', 'TT-04_beaker-locator-ring-v2_qty1'),
    ('RK-02 reagent rack', 'RK-02_reagent-rack-v2_qty1'),
    ('ST-08 bearing race spacer', 'ST-08_bearing-race-spacer-v2_qty6'),
    ('ST-01', 'ST-01_stage-base-v2_qty1'),
    ('ST-09 stop-post TPU sleeve', 'ST-09_stop-post-sleeve_qty2_TPU'),
    ('CAL-01 arm calibration block', 'CAL-01_arm-calibration-block_qty2'),
    ('CAL-02 calibration probe', 'CAL-02_calibration-probe_qty1'),
    ('GA-01 stage angle gauge', 'GA-01_stage-angle-gauge_qty1'),
    ('GR-01 gripper body (A)', 'GR-01_gripper-body_qty2_SUPPORTS'),
    ('GR-02 moving jaw (A)', 'GR-02_moving-jaw_qty2_SUPPORTS'),
    ('GR-03 fin-ray finger TPU (A fixed)', 'GR-03_fin-ray-finger_qty4_TPU'),
]
em = design.exportManager
for name, stem in PARTS:
    occs = [o for o in root.allOccurrences if o.component.name == name]
    if not occs: print('MISSING', name); continue
    c = occs[0].component; b = c.bRepBodies.item(0)
    so = em.createSTLExportOptions(b, os.path.join(OUT, stem + '.stl')); so.meshRefinement = F.MeshRefinementSettings.MeshRefinementHigh; so.isBinaryFormat = True; em.execute(so)
    em.execute(em.createSTEPExportOptions(os.path.join(OUT, stem + '.step'), c))
    bb = b.boundingBox
    print('%-44s %6.1f cm3  %.1f x %.1f x %.1f  %s' % (stem, b.volume, (bb.maxPoint.x - bb.minPoint.x) * 10, (bb.maxPoint.y - bb.minPoint.y) * 10, (bb.maxPoint.z - bb.minPoint.z) * 10, b.material.name))
