"""Execute the carousel-to-scale beaker transfer acceptance check."""
from __future__ import annotations

from motion.pick_place import transfer_beaker
from world import BenchWorld


def run() -> dict:
    world = BenchWorld()
    result = transfer_beaker(world, "transfer", "carousel_beaker_1",
                             (0.620, 0.407, 0.0637 + 0.032))
    assert result["reach_error_mm"] <= 5.0
    assert result["endpoint_plan"]["upright_axis_match_deg"] <= 0.25
    assert result["final_site_error_mm"] <= 8.0
    assert result["upright_error_deg"] <= 5.0
    assert min(segment["min_joint_margin_deg"] for segment in result["segments"]) >= 5.0
    return result


if __name__ == "__main__":
    result = run()
    print(f"PASS: grasped P1 at {result['reach_error_mm']:.2f} mm")
    print(f"PASS: held beaker axes match within "
          f"{result['endpoint_plan']['upright_axis_match_deg']:.3f}°")
    print(f"PASS: P1 released {result['final_site_error_mm']:.2f} mm from scale target, "
          f"tilt {result['upright_error_deg']:.2f}°")
    if result["arm_contacts"]:
        print(f"CONTACT AUDIT: {len(result['arm_contacts'])} stock-gripper contacts during transfer")
        for contact in result["arm_contacts"]:
            print(f"  {contact['phase']}: {contact['arm_geom']} with {contact['other_geom']} "
                  f"({contact['samples']} control samples)")
    else:
        print("PASS: no arm-to-scene contacts along the transfer")
