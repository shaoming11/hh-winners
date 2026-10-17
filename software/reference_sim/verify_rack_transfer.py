"""Check an empty beaker transfer from the rack to the scale."""
from __future__ import annotations

from motion.pick_place import transfer_beaker
from world import BenchWorld


def run() -> dict:
    world = BenchWorld()
    result = transfer_beaker(world, "pourer", "rack_beaker_1",
                             (0.620, 0.407, 0.0957))
    assert result["reach_error_mm"] <= 5.0
    assert result["endpoint_plan"]["upright_axis_match_deg"] <= 0.25
    assert result["final_site_error_mm"] <= 8.0
    assert result["upright_error_deg"] <= 5.0
    assert min(segment["min_joint_margin_deg"]
               for segment in result["segments"]) >= 5.0
    return result


if __name__ == "__main__":
    result = run()
    print(f"PASS: rack beaker grasped at {result['reach_error_mm']:.2f} mm")
    print(f"PASS: pourer arm released it {result['final_site_error_mm']:.2f} mm from the scale target, "
          f"tilt {result['upright_error_deg']:.2f}°")
    print(f"PASS: minimum waypoint joint margin "
          f"{min(segment['min_joint_margin_deg'] for segment in result['segments']):.1f}°")
