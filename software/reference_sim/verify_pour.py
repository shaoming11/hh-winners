"""Execute an arm-driven analytical pour into a beaker on the simulated scale."""
from __future__ import annotations

from motion.pick_place import transfer_beaker
from motion.pour import pour_with_arm
from world import BenchWorld


def run() -> dict:
    world = BenchWorld()
    receiver_transfer = transfer_beaker(
        world, "transfer", "carousel_beaker_1", (0.620, 0.407, 0.0957))
    donor_transfer = transfer_beaker(
        world, "pourer", "rack_beaker_1", (0.620, 0.340, 0.180),
        release_after=False)
    assert world.held_object("pourer") == "rack_beaker_1"
    result = pour_with_arm(world, "pourer", "rack_beaker_1", "carousel_beaker_1",
                           donor_mass_g=80.0, target_g=39.0,
                           pour_direction_xy=(0.0, 1.0),
                           receiver_radius_mm=20.0, maximum_tilt_deg=70.0)
    assert 37.0 <= result["landed_g"] <= 41.0, \
        f"arm-driven pour delivered {result['landed_g']:.2f} g"
    assert result["spilled_g"] <= 0.1, \
        f"arm-driven pour spilled {result['spilled_g']:.2f} g"
    assert result["peak_tilt_deg"] >= 55.0
    assert result["minimum_joint_margin_deg"] >= 5.0
    assert result["maximum_gripper_drift_mm"] <= 8.0
    assert result["scale_g"] >= 37.0
    result["receiver_transfer"] = {
        "placement_error_mm": receiver_transfer["final_site_error_mm"],
        "upright_error_deg": receiver_transfer["upright_error_deg"],
    }
    result["donor_transfer"] = {
        "placement_error_mm": donor_transfer["final_site_error_mm"],
        "held_after_transfer": world.held_object("pourer") == "rack_beaker_1",
    }
    return result


if __name__ == "__main__":
    data = run()
    print(f"PASS: SO-101 tilted the held beaker to {data['peak_tilt_deg']:.1f} degrees")
    print(f"PASS: analytical stream delivered {data['landed_g']:.2f} g; "
          f"spill {data['spilled_g']:.2f} g; scale {data['scale_g']:.2f} g")
    print(f"PASS: tilt path retained {data['minimum_joint_margin_deg']:.1f} degrees "
          f"of joint margin and {data['maximum_gripper_drift_mm']:.1f} mm max position drift")
    if data["arm_contacts"]:
        print(f"REVIEW: {len(data['arm_contacts'])} arm-to-scene contacts occurred during tilt")
    else:
        print("PASS: no arm-to-scene contacts occurred during tilt")
