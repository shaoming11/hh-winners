"""Check joint-limited reach and the welded grasp abstraction in MuJoCo."""
from __future__ import annotations

import math

import numpy as np

from hal.sim import SimArmBus
from motion.kinematics import ARM_JOINTS, ArmKinematics
from motion.player import play_joint_path
from world import BenchWorld


def _path(start: np.ndarray, end: np.ndarray, max_step_deg: float = 2.0) -> list[np.ndarray]:
    count = max(1, math.ceil(float(np.max(np.abs(np.degrees(end - start)))) / max_step_deg))
    return [start + (end - start) * (i / count) for i in range(1, count + 1)]


def _rotation_error_deg(a: np.ndarray, b: np.ndarray) -> float:
    cosine = float(np.clip((np.trace(a @ b.T) - 1) / 2, -1, 1))
    return math.degrees(math.acos(cosine))


def run() -> dict:
    world = BenchWorld()
    world.step(1.0)
    bus = SimArmBus(world, "transfer")
    bus.connect()
    kinematics = ArmKinematics(world, "transfer")

    beaker = "carousel_beaker_1"
    target, _ = world.site_pose(f"{beaker}_grasp")
    ik = kinematics.solve_position(target)
    start = np.radians([bus.read_positions()[name] for name in ARM_JOINTS])
    approach = play_joint_path(world, bus, "transfer", _path(start, ik.q_rad))
    tool_pos, tool_rot = world.site_pose("transfer_gripperframe")
    source_pos, source_rot = world.site_pose(f"{beaker}_grasp")
    reach_error_mm = float(np.linalg.norm(tool_pos - source_pos) * 1000)
    if reach_error_mm > 5:
        raise AssertionError(f"SO-101 missed the carousel grasp site by {reach_error_mm:.2f} mm")
    if ik.min_joint_margin_deg < 5:
        raise AssertionError(f"IK is too close to a joint limit: {ik.min_joint_margin_deg:.2f} deg")

    grasp = world.grasp("transfer", beaker, max_distance_m=0.005)
    if not grasp["grasped"]:
        raise AssertionError(f"proximity grasp failed at {grasp['distance_mm']:.2f} mm")
    source_pos, source_rot = world.site_pose(f"{beaker}_grasp")
    latch_position_error_mm = float(np.linalg.norm(tool_pos - source_pos) * 1000)
    latch_rotation_error_deg = _rotation_error_deg(tool_rot, source_rot)
    if latch_position_error_mm > 1.0 or latch_rotation_error_deg > 1.0:
        raise AssertionError("grasp weld did not align the two grasp frames")

    current = np.radians([bus.read_positions()[name] for name in ARM_JOINTS])
    tool_pos, _ = world.site_pose("transfer_gripperframe")
    lift_ik = kinematics.solve_position(tool_pos + np.array([0.0, 0.0, 0.040]), current)
    lift = play_joint_path(world, bus, "transfer", _path(current, lift_ik.q_rad))
    tool_pos, tool_rot = world.site_pose("transfer_gripperframe")
    held_pos, held_rot = world.site_pose(f"{beaker}_grasp")
    relative_pos_before = tool_rot.T @ (held_pos - tool_pos)
    relative_rot_before = tool_rot.T @ held_rot
    current = np.radians([bus.read_positions()[name] for name in ARM_JOINTS])
    moved = current.copy()
    moved[-1] += math.radians(3.0)
    carry_motion = play_joint_path(world, bus, "transfer", _path(current, moved))
    tool_pos, tool_rot = world.site_pose("transfer_gripperframe")
    held_pos, held_rot = world.site_pose(f"{beaker}_grasp")
    relative_pos_after = tool_rot.T @ (held_pos - tool_pos)
    relative_rot_after = tool_rot.T @ held_rot
    held_position_error_mm = float(np.linalg.norm(relative_pos_after - relative_pos_before) * 1000)
    held_rotation_error_deg = _rotation_error_deg(relative_rot_before, relative_rot_after)
    if held_position_error_mm > 1.0 or held_rotation_error_deg > 1.0:
        raise AssertionError("held beaker did not follow the gripper: "
                             f"{held_position_error_mm:.2f} mm, "
                             f"{held_rotation_error_deg:.2f} deg")

    world.release("transfer")
    if world.held_object("transfer") is not None:
        raise AssertionError("release left the arm marked as holding the beaker")
    return {
        "ik_position_error_mm": ik.position_error_mm,
        "ik_min_joint_margin_deg": ik.min_joint_margin_deg,
        "approach_tracking_error_deg": approach["max_tracking_error_deg"],
        "grasp_distance_mm": grasp["distance_mm"],
        "latch_position_error_mm": latch_position_error_mm,
        "latch_rotation_error_deg": latch_rotation_error_deg,
        "lift_tracking_error_deg": lift["max_tracking_error_deg"],
        "wrist_command_deg": 3.0,
        "held_position_error_mm": held_position_error_mm,
        "held_rotation_error_deg": held_rotation_error_deg,
        "carry_tracking_error_deg": carry_motion["max_tracking_error_deg"],
    }


if __name__ == "__main__":
    result = run()
    print(f"PASS: IK reached carousel grasp target with {result['ik_min_joint_margin_deg']:.1f}° min margin")
    print(f"PASS: weld grasp latched at {result['grasp_distance_mm']:.2f} mm")
    print("PASS: beaker followed a 3° wrist command and released")
