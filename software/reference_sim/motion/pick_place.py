"""Joint-limited, site-weld pick-and-place motion for the reference scene."""
from __future__ import annotations

import math

import mujoco
import numpy as np

from bench import load_layout
from hal.sim import SimArmBus
from motion.kinematics import ARM_JOINTS, ArmKinematics, IKError
from motion.player import play_joint_path
from world import BenchWorld


def _joint_interpolation(start: np.ndarray, end: np.ndarray,
                         max_step_deg: float = 2.0) -> list[np.ndarray]:
    count = max(1, math.ceil(float(np.max(np.abs(np.degrees(end - start)))) / max_step_deg))
    return [start + (end - start) * (i / count) for i in range(1, count + 1)]


def _upright_error_deg(source: np.ndarray, destination: np.ndarray) -> float:
    world_up = np.array([0.0, 0.0, 1.0])
    relative_up = destination @ source.T @ world_up
    cosine = float(np.clip(relative_up @ world_up, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def _skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = vector
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def _solve_upright_position(kinematics: ArmKinematics, target_xyz: np.ndarray,
                            q0: np.ndarray, reference_rotation: np.ndarray) -> np.ndarray:
    """Solve position IK while keeping the grasped object's vertical axis upright."""
    world_up = np.array([0.0, 0.0, 1.0])
    object_axis_in_tool = reference_rotation.T @ world_up
    q = np.clip(np.asarray(q0, float), kinematics.limits[:, 0], kinematics.limits[:, 1])
    for _ in range(260):
        position, rotation = kinematics._forward(q)
        object_axis = rotation @ object_axis_in_tool
        position_error = target_xyz - position
        upright_error = world_up - object_axis
        axis_error_deg = math.degrees(math.acos(float(np.clip(
            object_axis @ world_up, -1.0, 1.0))))
        if np.linalg.norm(position_error) <= 0.0015 and axis_error_deg <= 0.5:
            margin = float(kinematics.joint_margins_deg(q).min())
            if margin < 5.0:
                raise IKError(f"Upright path reaches only {margin:.1f} degrees from a joint limit")
            return q

        mujoco.mj_jacSite(kinematics.model, kinematics.data, kinematics.jacp,
                          kinematics.jacr, kinematics.site_id)
        jpos = kinematics.jacp[:, kinematics.dof_ids]
        jaxis = -_skew(object_axis) @ kinematics.jacr[:, kinematics.dof_ids]
        weight = 0.08
        jacobian = np.vstack((jpos, weight * jaxis))
        error = np.concatenate((position_error, weight * upright_error))
        delta = jacobian.T @ np.linalg.solve(
            jacobian @ jacobian.T + 1e-5 * np.eye(6), error)
        q = np.clip(q + np.clip(delta, -0.08, 0.08),
                    kinematics.limits[:, 0], kinematics.limits[:, 1])

    position, rotation = kinematics.forward(q)
    object_axis = rotation @ object_axis_in_tool
    position_error_mm = float(np.linalg.norm(target_xyz - position) * 1000)
    axis_error_deg = math.degrees(math.acos(float(np.clip(
        object_axis @ world_up, -1.0, 1.0))))
    raise IKError(f"Upright path IK missed by {position_error_mm:.1f} mm, "
                  f"axis tilt {axis_error_deg:.1f} degrees")


def _upright_line(kinematics: ArmKinematics, start_xyz: np.ndarray,
                  end_xyz: np.ndarray, q0: np.ndarray,
                  reference_rotation: np.ndarray, *, step_mm: float = 12.0) -> list[np.ndarray]:
    start, end = np.asarray(start_xyz, float), np.asarray(end_xyz, float)
    count = max(1, math.ceil(float(np.linalg.norm(end - start) * 1000) / step_mm))
    path = []
    q = np.asarray(q0, float)
    for i in range(1, count + 1):
        target = start + (end - start) * (i / count)
        q = _solve_upright_position(kinematics, target, q, reference_rotation)
        path.append(q.copy())
    return path


def _position_candidates(kinematics: ArmKinematics, target: np.ndarray,
                         rng: np.random.Generator, *, samples: int = 40) -> list[np.ndarray]:
    candidates: list[np.ndarray] = []
    for _ in range(samples):
        seed = rng.uniform(kinematics.limits[:, 0], kinematics.limits[:, 1])
        try:
            solution = kinematics.solve_position(target, seed, max_iterations=160).q_rad
        except IKError:
            continue
        if not any(np.linalg.norm(solution - old) < 0.05 for old in candidates):
            candidates.append(solution)
    return candidates


def _plan_upright_transfer(kinematics: ArmKinematics, source: np.ndarray,
                          destination: np.ndarray, high_source: np.ndarray,
                          escape: np.ndarray, high_destination: np.ndarray
                          ) -> tuple[np.ndarray, dict, dict[str, list[np.ndarray]]]:
    """Find a source posture with a sampled, upright path inside joint limits."""
    rng = np.random.default_rng(606)
    candidates = _position_candidates(kinematics, source, rng)
    candidates.sort(key=lambda q: float(kinematics.joint_margins_deg(q).min()),
                    reverse=True)
    failures = []
    for source_q in candidates:
        source_pos, source_rotation = kinematics.forward(source_q)
        try:
            lift = _upright_line(kinematics, source_pos, high_source,
                                 source_q, source_rotation)
            escape_path = _upright_line(kinematics, high_source, escape,
                                        lift[-1], source_rotation)
            carry = _upright_line(kinematics, escape, high_destination,
                                  escape_path[-1], source_rotation, step_mm=20.0)
            lower = _upright_line(kinematics, high_destination, destination,
                                  carry[-1], source_rotation)
        except IKError as exc:
            failures.append(str(exc))
            continue

        destination_q = lower[-1]
        destination_pos, destination_rotation = kinematics.forward(destination_q)
        source_margin = float(kinematics.joint_margins_deg(source_q).min())
        destination_margin = float(kinematics.joint_margins_deg(destination_q).min())
        plan = {
            "upright_axis_match_deg": _upright_error_deg(source_rotation,
                                                          destination_rotation),
            "source_position_error_mm": float(np.linalg.norm(source_pos - source) * 1000),
            "destination_position_error_mm": float(
                np.linalg.norm(destination_pos - destination) * 1000),
            "source_min_joint_margin_deg": source_margin,
            "destination_min_joint_margin_deg": destination_margin,
        }
        paths = {"lift": lift, "escape": escape_path, "carry": carry, "lower": lower}
        return source_q, plan, paths

    detail = failures[-1] if failures else "no reachable source IK candidate"
    raise IKError(f"No joint-limited upright transfer path: {detail}")


def _play_to(world: BenchWorld, bus: SimArmBus, arm: str,
             target_q: np.ndarray, speed_deg_s: float) -> dict:
    current = np.radians([bus.read_positions()[name] for name in ARM_JOINTS])
    return play_joint_path(world, bus, arm,
                          _joint_interpolation(current, target_q),
                          speed_deg_s=speed_deg_s)


def transfer_beaker(world: BenchWorld, arm: str, beaker: str,
                    destination_site_xyz_m: tuple[float, float, float], *,
                    clearance_mm: float = 60.0,
                    speed_deg_s: float = 55.0,
                    release_after: bool = True) -> dict:
    """Transfer one beaker along a joint-limited path while keeping it upright.

    The planner samples a Cartesian path and constrains the held beaker's vertical
    axis to remain upright. It keeps at least 5 degrees of joint-limit margin. An
    outward escape waypoint clears the carousel before the higher carry path. By
    default the beaker is released at the destination; ``release_after=False``
    leaves it attached so a later motion such as pouring can continue from there.
    Grasping remains the proximity plus weld abstraction documented in the README.
    """
    if arm not in ("pourer", "transfer"):
        raise ValueError(f"Unknown arm: {arm}")
    bus = SimArmBus(world, arm)
    bus.connect()
    kinematics = ArmKinematics(world, arm)
    object_site = f"{beaker}_grasp"
    pick_xyz, _ = world.site_pose(object_site)
    destination = np.asarray(destination_site_xyz_m, dtype=float)

    layout = load_layout()
    if beaker.startswith("carousel_beaker_"):
        carousel_center = np.asarray(layout["carousel"]["centre"], dtype=float) / 1000
        escape_direction = pick_xyz[:2] - carousel_center
    else:
        arm_base, _ = world.body_pose(f"{arm}_base")
        escape_direction = arm_base[:2] - pick_xyz[:2]
    norm = float(np.linalg.norm(escape_direction))
    if norm < 1e-9:
        raise RuntimeError(f"Cannot choose an escape direction for {beaker}")
    high_source_xyz = pick_xyz + np.array([0.0, 0.0, clearance_mm / 1000])
    high_destination_xyz = destination + np.array([0.0, 0.0, clearance_mm / 1000])
    escape_xyz = high_source_xyz.copy()
    escape_xyz[:2] += escape_direction / norm * 0.045
    pick_q, endpoint_plan, motion_paths = _plan_upright_transfer(
        kinematics, pick_xyz, destination, high_source_xyz, escape_xyz,
        high_destination_xyz)

    approach = _play_to(world, bus, arm, pick_q, speed_deg_s)
    actual_pick_xyz, _ = world.site_pose(object_site)
    reach_error_mm = float(np.linalg.norm(
        world.site_pose(f"{arm}_gripperframe")[0] - actual_pick_xyz) * 1000)
    if reach_error_mm > 5.0:
        raise RuntimeError(f"{arm} missed {beaker} by {reach_error_mm:.1f} mm")
    grasp = world.grasp(arm, beaker, max_distance_m=0.008)
    if not grasp["grasped"]:
        raise RuntimeError(f"{arm} missed {beaker}: {grasp['distance_mm']:.1f} mm")

    segments = []
    for label, speed in (
        ("lift", min(speed_deg_s, 20.0)),
        ("escape", min(speed_deg_s, 15.0)),
        ("carry", min(speed_deg_s, 30.0)),
        ("lower", min(speed_deg_s, 15.0)),
    ):
        q_path = motion_paths[label]
        motion = play_joint_path(world, bus, arm, q_path, speed_deg_s=speed)
        _, held_rotation = world.body_pose(beaker)
        held_tilt_deg = math.degrees(math.acos(float(np.clip(
            held_rotation[2, 2], -1.0, 1.0))))
        if held_tilt_deg > 5.0:
            raise RuntimeError(f"{beaker} tilted {held_tilt_deg:.1f} deg during {label}")
        segments.append({"name": label, **motion,
                         "min_joint_margin_deg": float(
                             min(kinematics.joint_margins_deg(q).min()
                                 for q in q_path))})
    arm_contacts = [
        {"phase": phase, **contact}
        for phase, motion in [("approach", approach)] + [
            (segment["name"], segment) for segment in segments]
        for contact in motion["arm_contacts"]
    ]

    # Give the soft grasp constraint time to correct small contact deflections at the receiver.
    world.step(2.0 if release_after else 0.2)
    pre_release_error_mm = float(np.linalg.norm(
        world.site_pose(object_site)[0] - destination) * 1000)
    if release_after:
        world.release(arm)
        world.step(2.0)
    final_site, _ = world.site_pose(object_site)
    final_error_mm = float(np.linalg.norm(final_site - destination) * 1000)
    final_body_pos, final_body_rot = world.body_pose(beaker)
    upright_error_deg = math.degrees(math.acos(float(np.clip(
        final_body_rot[2, 2], -1, 1))))
    if final_error_mm > 8.0:
        raise RuntimeError(f"{beaker} landed {final_error_mm:.1f} mm from destination site")
    if upright_error_deg > 5.0:
        raise RuntimeError(f"{beaker} landed tilted by {upright_error_deg:.1f} deg")

    return {
        "arm": arm,
        "beaker": beaker,
        "grasp": grasp,
        "released": beaker if release_after else None,
        "source_site_xyz_m": pick_xyz.tolist(),
        "destination_site_xyz_m": destination.tolist(),
        "reach_error_mm": reach_error_mm,
        "approach_motion": approach,
        "endpoint_plan": endpoint_plan,
        "segments": segments,
        "arm_contacts": arm_contacts,
        "pre_release_error_mm": pre_release_error_mm,
        "final_site_error_mm": final_error_mm,
        "upright_error_deg": upright_error_deg,
        "final_body_xyz_m": final_body_pos.tolist(),
    }
