"""Check that carousel indexing carries every seated beaker with the deck."""
from __future__ import annotations

import math

from bench import load_layout
from world import BenchWorld


def _wrap_degrees(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def run() -> dict:
    world = BenchWorld()
    center = tuple(value / 1000 for value in load_layout()["carousel"]["centre"])
    initial = {f"carousel_beaker_{i}": world.body_pose(f"carousel_beaker_{i}")
               for i in range(1, 5)}
    target_deg = 45.0
    reached_deg = world.move_carousel(target_deg, duration=2.0)

    results = {}
    for name, (position_before, _) in initial.items():
        position_after, rotation_after = world.body_pose(name)
        angle_before = math.degrees(math.atan2(position_before[1] - center[1],
                                               position_before[0] - center[0]))
        angle_after = math.degrees(math.atan2(position_after[1] - center[1],
                                              position_after[0] - center[0]))
        delta_deg = _wrap_degrees(angle_after - angle_before)
        radius_mm = math.hypot(position_after[0] - center[0],
                               position_after[1] - center[1]) * 1000
        tilt_deg = math.degrees(math.acos(max(-1.0, min(1.0, rotation_after[2, 2]))))
        results[name] = {
            "angular_travel_deg": delta_deg,
            "radius_mm": radius_mm,
            "bottom_z_mm": position_after[2] * 1000,
            "tilt_deg": tilt_deg,
        }
        assert abs(delta_deg - reached_deg) <= 1.0, f"{name} did not follow carousel angle"
        assert abs(radius_mm - 84.0) <= 0.5, f"{name} left its carousel pocket radius"
        assert abs(position_after[2] - position_before[2]) <= 0.001, f"{name} bounced vertically"
        assert tilt_deg <= 1.0, f"{name} tipped by {tilt_deg:.2f} degrees"

    return {"commanded_deg": target_deg, "reached_deg": reached_deg,
            "beakers": results}


if __name__ == "__main__":
    result = run()
    print(f"PASS: carousel reached {result['reached_deg']:.2f}°")
    for name, beaker in result["beakers"].items():
        print(f"PASS: {name} traveled {beaker['angular_travel_deg']:.2f}°, "
              f"radius {beaker['radius_mm']:.2f} mm, "
              f"tilt {beaker['tilt_deg']:.3f}°")
