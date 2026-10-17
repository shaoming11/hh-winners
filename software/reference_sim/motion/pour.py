"""Arm-driven beaker tilting with an analytical liquid and scale model."""
from __future__ import annotations

from collections import deque
import math
import random

import mujoco
import numpy as np

from chemistry import PourPlant
from hal.sim import SimArmBus
from motion.kinematics import ARM_JOINTS, ArmKinematics, IKError
from world import BenchWorld


def _skew(vector: np.ndarray) -> np.ndarray:
    x, y, z = vector
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def _solve_axis_position(kin: ArmKinematics, target_xyz: np.ndarray,
                         object_axis_in_tool: np.ndarray, target_axis: np.ndarray,
                         q0: np.ndarray, *, min_margin_deg: float = 5.0) -> np.ndarray:
    """Solve gripper position and held-object up axis, leaving roll unconstrained."""
    target_xyz = np.asarray(target_xyz, float)
    target_axis = np.asarray(target_axis, float)
    target_axis /= np.linalg.norm(target_axis)
    q = np.clip(np.asarray(q0, float), kin.limits[:, 0], kin.limits[:, 1])
    axis_weight = 0.08
    for _ in range(220):
        pos, rotation = kin._forward(q)
        axis = rotation @ object_axis_in_tool
        pos_error = target_xyz - pos
        axis_error = target_axis - axis
        pos_error_mm = float(np.linalg.norm(pos_error) * 1000)
        axis_error_deg = math.degrees(math.acos(float(np.clip(axis @ target_axis, -1, 1))))
        if pos_error_mm <= 1.5 and axis_error_deg <= 0.5:
            margin = float(kin.joint_margins_deg(q).min())
            if margin < min_margin_deg:
                raise IKError(f"Tilt path reaches only {margin:.1f} degrees from a joint limit")
            return q

        mujoco.mj_jacSite(kin.model, kin.data, kin.jacp, kin.jacr, kin.site_id)
        jpos = kin.jacp[:, kin.dof_ids]
        jaxis = -_skew(axis) @ kin.jacr[:, kin.dof_ids]
        jacobian = np.vstack((jpos, axis_weight * jaxis))
        error = np.concatenate((pos_error, axis_weight * axis_error))
        delta = jacobian.T @ np.linalg.solve(
            jacobian @ jacobian.T + 1e-5 * np.eye(6), error)
        q = np.clip(q + np.clip(delta, -0.06, 0.06),
                    kin.limits[:, 0], kin.limits[:, 1])

    pos, rotation = kin.forward(q)
    position_error_mm = float(np.linalg.norm(target_xyz - pos) * 1000)
    axis_error_deg = math.degrees(math.acos(float(np.clip(
        (rotation @ object_axis_in_tool) @ target_axis, -1, 1))))
    raise IKError(f"Tilt IK missed by {position_error_mm:.1f} mm, "
                  f"held axis by {axis_error_deg:.1f} degrees")


def _tilt_axis(base_axis: np.ndarray, pour_direction: np.ndarray,
               angle_deg: float) -> np.ndarray:
    angle = math.radians(angle_deg)
    axis = math.cos(angle) * base_axis + math.sin(angle) * pour_direction
    return axis / np.linalg.norm(axis)


def _plan_manifold(kin: ArmKinematics, start_q: np.ndarray, *,
                   start_rotation: np.ndarray, object_rotation: np.ndarray,
                   tool_position: np.ndarray, pour_direction: np.ndarray,
                   maximum_deg: int = 105, step_deg: float = 0.5
                   ) -> tuple[list[float], list[np.ndarray], dict]:
    base_axis = object_rotation[:, 2].copy()
    base_axis /= np.linalg.norm(base_axis)
    object_axis_in_tool = start_rotation.T @ base_axis
    count = int(round(maximum_deg / step_deg))
    angles = [float(index * step_deg) for index in range(count + 1)]
    q_path = [np.asarray(start_q, float).copy()]
    q = q_path[0]
    for angle in angles[1:]:
        try:
            q = _solve_axis_position(
                kin, tool_position, object_axis_in_tool,
                _tilt_axis(base_axis, pour_direction, angle), q)
        except IKError as exc:
            raise IKError(f"Tilt manifold failed at {angle} degrees: {exc}") from exc
        q_path.append(q.copy())
    margins = [float(kin.joint_margins_deg(value).min()) for value in q_path]
    max_joint_step = max(float(np.max(np.abs(np.degrees(b - a))) / step_deg)
                         for a, b in zip(q_path, q_path[1:]))
    return angles, q_path, {
        "minimum_joint_margin_deg": min(margins),
        "maximum_joint_step_deg_per_tilt_degree": max_joint_step,
        "maximum_tilt_deg": float(maximum_deg),
    }


def _interpolate_joint_path(angles: list[float], q_path: list[np.ndarray],
                            target_deg: float) -> np.ndarray:
    value = float(np.clip(target_deg, angles[0], angles[-1]))
    lower = min(len(angles) - 2, int(np.searchsorted(angles, value, side="right") - 1))
    interval = angles[lower + 1] - angles[lower]
    fraction = (value - angles[lower]) / interval
    return q_path[lower] * (1 - fraction) + q_path[lower + 1] * fraction


def _flow_rate(plant: PourPlant, mass_g: float, tilt_deg: float) -> float:
    return plant.flow_g_s(mass_g, tilt_deg)


def pour_with_arm(world: BenchWorld, arm: str, beaker: str, receiver: str, *,
                  donor_mass_g: float = 80.0, target_g: float = 39.0,
                  pour_direction_xy: tuple[float, float] = (1.0, 0.0),
                  receiver_radius_mm: float = 20.0,
                  maximum_tilt_deg: float = 70.0,
                  plant: PourPlant | None = None, seed: int = 2026) -> dict:
    """Tilt a held beaker while flow and landing are evaluated from actual MuJoCo pose.

    Arm motion is MuJoCo joint control. Liquid remains an analytical model. The
    simulated scale payload is updated by landed liquid at each 80 Hz controller
    sample, so the pour loop observes a changing scale rather than a precomputed dose.
    """
    maximum_tilt_deg = int(maximum_tilt_deg)
    if maximum_tilt_deg < 55:
        raise ValueError("maximum_tilt_deg must reach the weir at 55 degrees or more")
    if world.held_object(arm) != beaker:
        raise RuntimeError(f"{arm} must be holding {beaker} before pouring")
    bus = SimArmBus(world, arm)
    bus.connect()
    kin = ArmKinematics(world, arm)
    tool_position, tool_rotation = world.site_pose(f"{arm}_gripperframe")
    object_position, object_rotation = world.body_pose(beaker)
    receiver_position, receiver_rotation = world.body_pose(receiver)

    direction = np.array([*pour_direction_xy, 0.0], dtype=float)
    base_axis = object_rotation[:, 2].copy()
    base_axis /= np.linalg.norm(base_axis)
    direction -= base_axis * float(direction @ base_axis)
    direction /= np.linalg.norm(direction)

    angles, q_path, path_report = _plan_manifold(
        kin, kin.current_q(), start_rotation=tool_rotation,
        object_rotation=object_rotation, tool_position=tool_position,
        pour_direction=direction, maximum_deg=int(maximum_tilt_deg))
    if path_report["maximum_joint_step_deg_per_tilt_degree"] > 8.0:
        raise IKError("Tilt manifold contains a joint branch jump above 8 degrees")

    plant = plant or PourPlant(seed=seed)
    world.tare_scale()
    dt_nominal = 1.0 / 80.0
    step_fraction = 0.0

    def step_control() -> float:
        nonlocal step_fraction
        exact = dt_nominal / world.model.opt.timestep + step_fraction
        n = max(1, math.floor(exact))
        step_fraction = exact - n
        world.step(n * world.model.opt.timestep)
        return n * world.model.opt.timestep

    def set_tilt(target_deg: float) -> None:
        q = _interpolate_joint_path(angles, q_path, target_deg)
        bus.write_goals({name: math.degrees(float(value))
                         for name, value in zip(ARM_JOINTS, q)})

    # Move from upright to the analytical controller's initial 40 degree posture.
    for angle in range(1, 41):
        set_tilt(float(angle))
        elapsed = 0.0
        while elapsed < 0.04:
            elapsed += step_control()

    delay_steps = max(1, round(plant.fall_delay_s / dt_nominal))
    in_flight: deque[float] = deque([0.0] * delay_steps)
    readings: deque[tuple[float, float]] = deque(maxlen=40)
    rng = random.Random(seed)
    remaining_g = float(donor_mass_g)
    landed_g = spilled_g = 0.0
    sensor_payload_g = 0.0
    integral = 0.0
    target_tilt_deg = 40.0
    peak_flow = sum_flow = 0.0
    flow_samples = 0
    peak_tilt = 0.0
    time_s = 0.0
    cut = False
    samples: list[dict] = []
    receiver_rim_z = float((receiver_position + receiver_rotation @
                            np.array([0.0, 0.0, plant.height]))[2])
    receiver_xy = receiver_position[:2].copy()
    max_actual_tilt = 0.0
    max_position_error_mm = 0.0
    sensor_mass = 0.0
    contacts: dict[tuple[str, str, str, str], int] = {}

    while time_s < 30.0:
        dt = step_control()
        time_s += dt
        set_tilt(target_tilt_deg)
        actual_tool_pos, _ = world.site_pose(f"{arm}_gripperframe")
        max_position_error_mm = max(max_position_error_mm,
            float(np.linalg.norm(actual_tool_pos - tool_position) * 1000))
        body_pos, body_rot = world.body_pose(beaker)
        object_up = body_rot[:, 2]
        actual_tilt = math.degrees(math.atan2(float(object_up @ direction),
                                              float(object_up @ base_axis)))
        actual_tilt = float(np.clip(actual_tilt, 0.0, 120.0))
        max_actual_tilt = max(max_actual_tilt, actual_tilt)

        sensor_mass = world.scale_grams() + rng.gauss(0.0, 0.05)
        readings.append((time_s, sensor_mass))
        qhat = 0.0
        if len(readings) >= 8:
            t0 = readings[0][0]
            ts = [t - t0 for t, _ in readings]
            ms = [m - readings[0][1] for _, m in readings]
            mean_t = sum(ts) / len(ts)
            mean_m = sum(ms) / len(ms)
            denominator = sum((t - mean_t) ** 2 for t in ts)
            if denominator > 0:
                qhat = sum((t - mean_t) * (m - mean_m)
                           for t, m in zip(ts, ms)) / denominator

        if not cut:
            error = 5.0 - qhat
            integral = max(-10.0, min(10.0, integral + error * dt))
            target_tilt_deg += max(-0.75, min(0.75, 0.10 * error + 0.035 * integral))
            target_tilt_deg = max(40.0, min(maximum_tilt_deg, target_tilt_deg))
        else:
            target_tilt_deg = max(0.0, target_tilt_deg - 60.0 * dt)

        rate = _flow_rate(plant, remaining_g, actual_tilt)
        amount = min(remaining_g, rate * dt)
        remaining_g -= amount

        # Select the lowest point on the donor rim, then add the modeled ballistic
        # displacement along the pour direction to determine whether it reaches P1.
        rim_angles = np.linspace(0, 2 * math.pi, 48, endpoint=False)
        local_rim = np.column_stack((plant.radius * np.cos(rim_angles),
                                     plant.radius * np.sin(rim_angles),
                                     np.full_like(rim_angles, plant.height)))
        world_rim = body_pos + local_rim @ body_rot.T
        lip = world_rim[int(np.argmin(world_rim[:, 2]))]
        fall_mm = max(0.0, (float(lip[2]) - receiver_rim_z) * 1000)
        offset_mm = plant.landing_offset_mm(fall_mm)
        landing_xy = lip[:2] + direction[:2] * offset_mm / 1000
        landing_error_mm = float(np.linalg.norm(landing_xy - receiver_xy) * 1000)

        in_flight.append(amount)
        landed_now = in_flight.popleft()
        if landing_error_mm <= receiver_radius_mm:
            landed_g += landed_now
            sensor_payload_g += landed_now
        else:
            spilled_g += landed_now
        world.set_scale_payload_g(sensor_payload_g)
        peak_flow = max(peak_flow, rate)
        sum_flow += rate
        flow_samples += 1
        peak_tilt = max(peak_tilt, actual_tilt)
        for contact in world.arm_contact_pairs(arm):
            key = (contact["arm_body"], contact["other_body"],
                   contact["arm_geom"], contact["other_geom"])
            contacts[key] = contacts.get(key, 0) + 1

        if len(samples) < 4 or round(time_s * 10) != round((time_s - dt) * 10):
            samples.append({"time_s": round(time_s, 3),
                            "command_tilt_deg": round(target_tilt_deg, 2),
                            "actual_tilt_deg": round(actual_tilt, 2),
                            "flow_g_s": round(rate, 3),
                            "scale_g": round(sensor_mass, 3),
                            "landing_error_mm": round(landing_error_mm, 2)})

        if not cut and sensor_mass >= target_g - (0.3 + 0.15 * max(0.0, qhat)):
            cut = True
        if cut and target_tilt_deg <= 0.0 and actual_tilt <= 3.0 and not any(in_flight):
            break
        if remaining_g <= 0.0 and not any(in_flight):
            break

    if not cut:
        raise RuntimeError(
            f"Pour did not reach the scale cut point: scale {sensor_mass:.2f} g, "
            f"landed {landed_g:.2f} g, spilled {spilled_g:.2f} g, "
            f"peak flow {peak_flow:.2f} g/s, max tilt {max_actual_tilt:.1f} degrees, "
            f"last sample {samples[-1] if samples else 'none'}")
    if max_actual_tilt < 55.0:
        raise RuntimeError(f"Arm never reached the weir: max tilt {max_actual_tilt:.1f} degrees")
    if target_tilt_deg > 0.0 or actual_tilt > 3.0:
        raise RuntimeError("Arm failed to return the held beaker to an upright pose")

    return {
        "target_g": float(target_g),
        "landed_g": landed_g,
        "spilled_g": spilled_g,
        "remaining_g": remaining_g,
        "peak_flow_g_s": peak_flow,
        "mean_flow_g_s": sum_flow / max(1, flow_samples),
        "peak_tilt_deg": peak_tilt,
        "duration_s": time_s,
        "minimum_joint_margin_deg": path_report["minimum_joint_margin_deg"],
        "maximum_joint_step_deg_per_tilt_degree": path_report[
            "maximum_joint_step_deg_per_tilt_degree"],
        "maximum_gripper_drift_mm": max_position_error_mm,
        "scale_g": world.scale_grams(),
        "arm_contacts": [{"arm_body": a, "other_body": b,
                          "arm_geom": ag, "other_geom": og, "samples": count}
                         for (a, b, ag, og), count in sorted(contacts.items())],
        "samples": samples,
        "tilt_path": path_report,
    }
