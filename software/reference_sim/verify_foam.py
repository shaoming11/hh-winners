"""Check peroxide and yeast scaling plus the MuJoCo foam visual update."""
from __future__ import annotations

from chemistry import FoamReaction
from world import BenchWorld


def run() -> dict:
    reaction = FoamReaction()
    before_induction = reaction.sample(0.1, h2o2_g=4.68, yeast_g=7.0)
    midpoint = reaction.sample(2.25, h2o2_g=4.68, yeast_g=7.0)
    peak = reaction.sample(4.25, h2o2_g=4.68, yeast_g=7.0)
    half_dose = reaction.sample(4.25, h2o2_g=4.68, yeast_g=3.5)
    assert before_induction.height_mm == 0
    assert 0 < midpoint.height_mm < peak.height_mm
    assert abs(peak.height_mm - 140.0) < 1e-6
    assert abs(peak.oxygen_l - 1.7) < 1e-6
    assert abs(half_dose.height_mm - 70.0) < 1e-6

    world = BenchWorld()
    world.set_foam_height_mm(peak.height_mm)
    gid = world.foam_geom_id
    assert abs(world.model.geom_size[gid, 0] - 0.048) < 1e-6
    assert abs(world.model.geom_size[gid, 1] - 0.070) < 1e-6
    assert abs(world.status()["foam_height_mm"] - 140.0) < 1e-6
    world.set_foam_height_mm(0)
    assert world.model.geom_rgba[gid, 3] == 0
    return {"oxygen_estimate_l": peak.oxygen_l,
            "peak_height_mm": peak.height_mm,
            "midpoint_height_mm": midpoint.height_mm,
            "half_yeast_height_mm": half_dose.height_mm}


if __name__ == "__main__":
    result = run()
    print(f"PASS: 4.68 g H2O2 gives {result['oxygen_estimate_l']:.2f} L oxygen estimate")
    print(f"PASS: foam rises from {result['midpoint_height_mm']:.1f} to "
          f"{result['peak_height_mm']:.1f} mm over the configured growth interval")
    print(f"PASS: halving yeast halves the modeled peak to "
          f"{result['half_yeast_height_mm']:.1f} mm")
