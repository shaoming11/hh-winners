"""Rate-limited playback of MuJoCo-native joint paths through the ArmBus interface."""
from __future__ import annotations

import math

import numpy as np

from hal.base import ArmBus
from motion.kinematics import ARM_JOINTS
from world import BenchWorld


def play_joint_path(world: BenchWorld, bus: ArmBus, arm: str, path_rad: list[np.ndarray], *,
                    speed_deg_s: float = 55.0, control_period_s: float = 0.02) -> dict:
    """Play a sequence at bounded joint speed and report servo tracking and contacts."""
    if not path_rad:
        return {"samples": 0, "duration_s": 0.0, "max_tracking_error_deg": 0.0,
                "arm_contacts": []}
    previous = np.radians([bus.read_positions()[name] for name in ARM_JOINTS])
    max_error_deg = 0.0
    sample_count = 0
    duration = 0.0
    contacts: dict[tuple[str, str, str, str], int] = {}
    for target in path_rad:
        target = np.asarray(target, float)
        segment = target - previous
        segment_duration = max(float(np.max(np.abs(np.degrees(segment)))) / speed_deg_s,
                               control_period_s)
        steps = max(1, math.ceil(segment_duration / control_period_s))
        for step in range(1, steps + 1):
            ratio = step / steps
            goal = previous + segment * ratio
            bus.write_goals({name: math.degrees(float(value))
                             for name, value in zip(ARM_JOINTS, goal)})
            world.step(segment_duration / steps)
            actual = np.radians([bus.read_positions()[name] for name in ARM_JOINTS])
            max_error_deg = max(max_error_deg,
                                float(np.max(np.abs(np.degrees(goal - actual)))))
            sample_count += 1
            duration += segment_duration / steps
            for contact in world.arm_contact_pairs(arm):
                key = (contact["arm_body"], contact["other_body"],
                       contact["arm_geom"], contact["other_geom"])
                contacts[key] = contacts.get(key, 0) + 1
        previous = target
    world.step(0.20)
    return {"samples": sample_count, "duration_s": duration,
            "max_tracking_error_deg": max_error_deg,
            "arm_contacts": [{"arm_body": a, "other_body": b,
                              "arm_geom": ag, "other_geom": og, "samples": n}
                             for (a, b, ag, og), n in sorted(contacts.items())]}
