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


def _match_endpoint_orientations(kinematics: ArmKinematics, source: np.ndarray,
                                 destination: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Find reachable endpoint configurations that leave a beaker upright."""
    rng = np.random.default_rng(606)
    source_solutions = _position_candidates(kinematics, source, rng)
    destination_solutions = _position_candidates(kinematics, destination, rng)
    pairs = []
    for source_q in source_solutions:
        _, source_rot = kinematics.forward(source_q)
        source_margin = float(kinematics.joint_margins_deg(source_q).min())
        if source_margin < 5.0:
            continue
        for destination_q in destination_solutions:
            destination_margin = float(kinematics.joint_margins_deg(destination_q).min())
            if destination_margin < 5.0:
                continue
            _, destination_rot = kinematics.forward(destination_q)
            axis_error = _upright_error_deg(source_rot, destination_rot)
            pairs.append((axis_error, min(source_margin, destination_margin),
                          source_q, destination_q))
    if not pairs:
        raise IKError("No source and destination IK pair has a 5 degree joint margin")
    pairs.sort(key=lambda item: (item[0], -item[1]))
    _, _, source_q, destination_q = pairs[0]

    weight = 0.1
    for _ in range(150):
        source_pos, source_rot = kinematics._forward(source_q)
        mujoco.mj_jacSite(kinematics.model, kinematics.data, kinematics.jacp,
                          kinematics.jacr, kinematics.site_id)
        source_jacp = kinematics.jacp[:, kinematics.dof_ids].copy()
        source_jacr = kinematics.jacr[:, kinematics.dof_ids].copy()

        destination_pos, destination_rot = kinematics._forward(destination_q)
        mujoco.mj_jacSite(kinematics.model, kinematics.data, kinematics.jacp,
                          kinematics.jacr, kinematics.site_id)
        destination_jacp = kinematics.jacp[:, kinematics.dof_ids].copy()
        destination_jacr = kinematics.jacr[:, kinematics.dof_ids].copy()

        world_up = np.array([0.0, 0.0, 1.0])
        relative = destination_rot @ source_rot.T
        relative_up = relative @ world_up
        upright_error = world_up - relative_up
        if (max(np.linalg.norm(source_pos - source),
                np.linalg.norm(destination_pos - destination)) < 0.0002
                and _upright_error_deg(source_rot, destination_rot) < 0.1):
            break

        source_up_jac = relative @ _skew(world_up) @ source_jacr
        destination_up_jac = -_skew(relative_up) @ destination_jacr
        jacobian = np.block([
            [source_jacp, np.zeros((3, 5))],
            [np.zeros((3, 5)), destination_jacp],
            [weight * source_up_jac, weight * destination_up_jac],
        ])
        error = np.concatenate((source - source_pos,
                                destination - destination_pos,
                                weight * upright_error))
        delta = jacobian.T @ np.linalg.solve(
            jacobian @ jacobian.T + 1e-6 * np.eye(9), error)
        source_q = np.clip(source_q + np.clip(delta[:5], -0.005, 0.005),
                           kinematics.limits[:, 0], kinematics.limits[:, 1])
        destination_q = np.clip(destination_q + np.clip(delta[5:], -0.005, 0.005),
                                kinematics.limits[:, 0], kinematics.limits[:, 1])

    source_pos, source_rot = kinematics.forward(source_q)
    destination_pos, destination_rot = kinematics.forward(destination_q)
    axis_error_deg = _upright_error_deg(source_rot, destination_rot)
    source_margin = float(kinematics.joint_margins_deg(source_q).min())
    destination_margin = float(kinematics.joint_margins_deg(destination_q).min())
    if (np.linalg.norm(source_pos - source) > 0.002
            or np.linalg.norm(destination_pos - destination) > 0.002
            or axis_error_deg > 0.25
            or min(source_margin, destination_margin) < 5.0):
        raise IKError("Endpoint orientation match failed: "
                      f"{axis_error_deg:.2f} deg axis mismatch, "
                      f"margins {source_margin:.1f}/{destination_margin:.1f} deg")
    return source_q, destination_q, {
        "upright_axis_match_deg": axis_error_deg,
        "source_position_error_mm": float(np.linalg.norm(source_pos - source) * 1000),
        "destination_position_error_mm": float(np.linalg.norm(destination_pos - destination) * 1000),
        "source_min_joint_margin_deg": source_margin,
        "destination_min_joint_margin_deg": destination_margin,
    }


def _safe_position_ik(kinematics: ArmKinematics, target: np.ndarray,
                      seed: np.ndarray, rng: np.random.Generator, *,
                      samples: int = 50) -> np.ndarray:
    """Choose a nearby IK branch that remains at least 5 degrees from limits."""
    candidates = []
    for _ in range(samples):
        random_seed = rng.uniform(kinematics.limits[:, 0], kinematics.limits[:, 1])
        try:
            q = kinematics.solve_position(target, random_seed,
                                          max_iterations=160).q_rad
        except IKError:
            continue
        margin = float(kinematics.joint_margins_deg(q).min())
        if margin >= 5.0:
            candidates.append((float(np.linalg.norm(np.degrees(q - seed))), -margin, q))
    if not candidates:
        raise IKError("No collision waypoint IK solution has a 5 degree joint margin")
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _play_to(world: BenchWorld, bus: SimArmBus, arm: str,
             target_q: np.ndarray, speed_deg_s: float) -> dict:
    current = np.radians([bus.read_positions()[name] for name in ARM_JOINTS])
    return play_joint_path(world, bus, arm,
                          _joint_interpolation(current, target_q),
                          speed_deg_s=speed_deg_s)


def transfer_beaker(world: BenchWorld, arm: str, beaker: str,
                    destination_site_xyz_m: tuple[float, float, float], *,
                    clearance_mm: float = 60.0,
                    speed_deg_s: float = 55.0) -> dict:
    """Transfer one empty beaker and verify that it lands upright on the receiver.

    Endpoint IK solutions are paired so the held beaker stays upright at pickup
    and placement while allowing gripper yaw to differ. An outward escape waypoint clears the
    carousel before the higher carry path. Grasping remains the proximity plus weld
    abstraction documented in the reference simulator README.
    """
    if arm not in ("pourer", "transfer"):
        raise ValueError(f"Unknown arm: {arm}")
    bus = SimArmBus(world, arm)
    bus.connect()
    kinematics = ArmKinematics(world, arm)
    object_site = f"{beaker}_grasp"
    pick_xyz, _ = world.site_pose(object_site)
    destination = np.asarray(destination_site_xyz_m, dtype=float)
    pick_q, place_q, endpoint_plan = _match_endpoint_orientations(
        kinematics, pick_xyz, destination)

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
    escape_xyz = pick_xyz.copy()
    escape_xyz[:2] += escape_direction / norm * 0.045
    escape_xyz[2] += 0.060

    waypoint_rng = np.random.default_rng(99)
    escape_q = _safe_position_ik(kinematics, escape_xyz, pick_q, waypoint_rng)
    high_source_xyz = pick_xyz + np.array([0.0, 0.0, clearance_mm / 1000])
    high_destination_xyz = destination + np.array([0.0, 0.0, clearance_mm / 1000])
    high_source_q = _safe_position_ik(kinematics, high_source_xyz,
                                      escape_q, waypoint_rng)
    high_destination_q = _safe_position_ik(kinematics, high_destination_xyz,
                                           place_q, waypoint_rng)

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
    for label, target_q, speed in (
        ("escape", escape_q, min(speed_deg_s, 15.0)),
        ("lift", high_source_q, min(speed_deg_s, 20.0)),
        ("carry", high_destination_q, min(speed_deg_s, 30.0)),
        ("lower", place_q, min(speed_deg_s, 15.0)),
    ):
        motion = _play_to(world, bus, arm, target_q, speed)
        segments.append({"name": label, **motion,
                         "min_joint_margin_deg": float(
                             kinematics.joint_margins_deg(target_q).min())})

    # Give the soft grasp constraint time to correct small contact deflections at the pan.
    world.step(2.0)
    pre_release_error_mm = float(np.linalg.norm(
        world.site_pose(object_site)[0] - destination) * 1000)
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
        "released": beaker,
        "source_site_xyz_m": pick_xyz.tolist(),
        "destination_site_xyz_m": destination.tolist(),
        "reach_error_mm": reach_error_mm,
        "approach_motion": approach,
        "endpoint_plan": endpoint_plan,
        "segments": segments,
        "pre_release_error_mm": pre_release_error_mm,
        "final_site_error_mm": final_error_mm,
        "upright_error_deg": upright_error_deg,
        "final_body_xyz_m": final_body_pos.tolist(),
    }
