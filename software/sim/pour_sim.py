#!/usr/bin/env python3
"""Software-in-the-loop model for a scale-controlled beaker pour.

This is an exploratory model, not a validated robot controller or CFD simulation. It uses a
cylindrical beaker, a quasi-static liquid surface, a rectangular-weir flow approximation, a
delayed stream, an HX711-like scale signal, and the proposed feed-forward plus PI pour logic.
Parameters should be fitted from water-pour data before using results to predict bench accuracy.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import deque
from dataclasses import dataclass
from pathlib import Path


G = 9.80665


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class Config:
    target_g: float = 39.0
    fill_ml: float = 65.0
    fill_estimate_error_ml: float = 0.0
    diameter_mm: float = 56.0
    height_mm: float = 74.0
    density_kg_m3: float = 997.0
    weir_cd: float = 0.60
    actual_weir_scale: float = 1.0
    scale_sigma_g: float = 0.05
    scale_lag_s: float = 0.025
    sensor_delay_s: float = 0.020
    stream_fall_delay_s: float = 0.120
    flow_response_s: float = 0.060
    command_delay_s: float = 0.020
    dt_s: float = 1.0 / 80.0
    estimator_window_s: float = 0.5
    initial_tilt_deg: float = 40.0
    max_tilt_deg: float = 85.0
    approach_rate_deg_s: float = 3.0
    tilt_rate_deg_s: float = 10.0
    fast_untilt_rate_deg_s: float = 270.0
    untilt_rate_deg_s: float = 60.0
    flow_ceiling_g_s: float = 8.0
    kp_deg_per_g_s: float = 0.15
    ki_deg_per_g: float = 0.30
    cut_a_g: float = 0.30
    cut_b_s: float = 0.15
    drip_hold_s: float = 1.5
    max_time_s: float = 90.0
    seed: int = 7

    @property
    def density_g_ml(self) -> float:
        return self.density_kg_m3 / 1000.0


def vessel_volume_below_level_ml(level_mm: float, tilt_deg: float, diameter_mm: float, height_mm: float) -> float:
    """Volume below a horizontal world-space water plane in a tilted cylindrical beaker."""
    radius = diameter_mm / 2.0
    phi = math.radians(clamp(tilt_deg, 0.0, 89.0))
    sin_phi = math.sin(phi)
    cos_phi = math.cos(phi)
    slices = 96
    dx = 2.0 * radius / slices
    volume_mm3 = 0.0
    for i in range(slices):
        x = -radius + (i + 0.5) * dx
        chord = 2.0 * math.sqrt(max(0.0, radius * radius - x * x))
        local_z = (level_mm + x * sin_phi) / cos_phi
        depth = clamp(local_z, 0.0, height_mm)
        volume_mm3 += chord * depth * dx
    return volume_mm3 / 1000.0


def waterline_for_volume_mm(volume_ml: float, tilt_deg: float, diameter_mm: float, height_mm: float) -> float:
    """Find the world-space water level for a given volume by bisection."""
    radius = diameter_mm / 2.0
    phi = math.radians(clamp(tilt_deg, 0.0, 89.0))
    low = -radius * math.sin(phi) - 1.0
    high = height_mm * math.cos(phi) + radius * math.sin(phi) + 1.0
    capacity_ml = math.pi * radius * radius * height_mm / 1000.0
    volume_ml = clamp(volume_ml, 0.0, capacity_ml)
    for _ in range(28):
        mid = (low + high) / 2.0
        if vessel_volume_below_level_ml(mid, tilt_deg, diameter_mm, height_mm) < volume_ml:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def weir_flow_g_s(volume_ml: float, tilt_deg: float, cfg: Config, cd_scale: float = 1.0) -> float:
    """Approximate flow over the low rim using q=(2/3)Cd*w*sqrt(2g)*h^(3/2)."""
    if volume_ml <= 0.0 or tilt_deg <= 0.0:
        return 0.0
    radius_m = cfg.diameter_mm / 2000.0
    height_m = cfg.height_mm / 1000.0
    phi = math.radians(clamp(tilt_deg, 0.0, 89.0))
    level_mm = waterline_for_volume_mm(volume_ml, tilt_deg, cfg.diameter_mm, cfg.height_mm)
    # The pouring lip is at x=+R, z=H in the tilted vessel frame.
    lip_world_mm = cfg.height_mm * math.cos(phi) - (cfg.diameter_mm / 2.0) * math.sin(phi)
    head_m = max(0.0, (level_mm - lip_world_mm) / 1000.0)
    if head_m <= 0.0:
        return 0.0
    width_m = 2.0 * radius_m
    cd = cfg.weir_cd * cd_scale
    flow_m3_s = (2.0 / 3.0) * cd * width_m * math.sqrt(2.0 * G) * (head_m ** 1.5)
    return flow_m3_s * cfg.density_kg_m3 * 1000.0


def angle_for_flow_g_s(target_flow_g_s: float, volume_ml: float, cfg: Config) -> float:
    """Invert the nominal weir model to get a feed-forward tilt angle.

    For each angle, calculate the volume that would produce the requested head.
    This avoids repeatedly solving for the waterline inside the angle search.
    """
    if target_flow_g_s <= 0.0:
        return 0.0
    radius_m = cfg.diameter_mm / 2000.0
    width_m = 2.0 * radius_m
    mass_flow_coefficient = (
        (2.0 / 3.0) * cfg.weir_cd * width_m * math.sqrt(2.0 * G)
        * cfg.density_kg_m3 * 1000.0
    )
    target_head_m = (target_flow_g_s / mass_flow_coefficient) ** (2.0 / 3.0)
    target_head_mm = target_head_m * 1000.0

    def volume_at_target_head(angle_deg: float) -> float:
        phi = math.radians(angle_deg)
        lip_world_mm = cfg.height_mm * math.cos(phi) - (cfg.diameter_mm / 2.0) * math.sin(phi)
        return vessel_volume_below_level_ml(
            lip_world_mm + target_head_mm,
            angle_deg,
            cfg.diameter_mm,
            cfg.height_mm,
        )

    if volume_at_target_head(0.0) <= volume_ml:
        return 0.0
    low = 0.0
    high = cfg.max_tilt_deg
    if volume_at_target_head(high) > volume_ml:
        return high
    for _ in range(24):
        mid = (low + high) / 2.0
        if volume_at_target_head(mid) > volume_ml:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


class RollingLSQ:
    """Estimate current scale mass and flow from a rolling linear fit."""

    def __init__(self, window_s: float) -> None:
        self.window_s = window_s
        self.samples: deque[tuple[float, float]] = deque()

    def add(self, time_s: float, mass_g: float) -> tuple[float, float]:
        self.samples.append((time_s, mass_g))
        while len(self.samples) > 2 and time_s - self.samples[0][0] > self.window_s:
            self.samples.popleft()
        if len(self.samples) < 2:
            return max(0.0, mass_g), 0.0
        n = len(self.samples)
        mean_t = sum(t for t, _ in self.samples) / n
        mean_m = sum(m for _, m in self.samples) / n
        denom = sum((t - mean_t) ** 2 for t, _ in self.samples)
        if denom <= 1e-12:
            return max(0.0, mass_g), 0.0
        slope = sum((t - mean_t) * (m - mean_m) for t, m in self.samples) / denom
        mass_now = mean_m + slope * (time_s - mean_t)
        return max(0.0, mass_now), max(0.0, slope)


class PourSimulation:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.time_s = 0.0
        self.phase = "approach"
        self.phase_time_s = 0.0
        self.angle_deg = cfg.initial_tilt_deg
        self.angle_command_deg = cfg.initial_tilt_deg
        self.command_rate_deg_s = cfg.approach_rate_deg_s
        self.command_delay_steps = max(0, round(cfg.command_delay_s / cfg.dt_s))
        self.command_buffer: deque[float] = deque(
            [self.angle_command_deg] * (self.command_delay_steps + 1),
            maxlen=self.command_delay_steps + 1,
        )
        self.source_volume_ml = cfg.fill_ml
        self.source_estimate_ml = max(0.0, cfg.fill_ml + cfg.fill_estimate_error_ml)
        self.receiver_mass_g = 0.0
        self.flow_g_s = 0.0
        self.flow_delay_steps = max(0, round(cfg.stream_fall_delay_s / cfg.dt_s))
        self.flow_buffer: deque[float] = deque([0.0] * (self.flow_delay_steps + 1), maxlen=self.flow_delay_steps + 1)
        self.scale_signal_g = 0.0
        self.scale_delay_steps = max(0, round(cfg.sensor_delay_s / cfg.dt_s))
        self.scale_buffer: deque[float] = deque([0.0] * (self.scale_delay_steps + 1), maxlen=self.scale_delay_steps + 1)
        self.estimator = RollingLSQ(cfg.estimator_window_s)
        self.mass_est_g = 0.0
        self.flow_est_g_s = 0.0
        self.flow_setpoint_g_s = 0.0
        self.integral_deg = 0.0
        self.first_drop_count = 0
        self.cut_mass_est_g: float | None = None
        self.cut_flow_est_g_s: float | None = None
        self.cut_angle_deg: float | None = None
        self.fast_untilt_angle_deg: float | None = None
        self.slow_untilt_angle_deg: float | None = None
        self.quiet_time_s = 0.0
        self.dry_time_s = 0.0
        self.fault: str | None = None
        self.rows: list[dict[str, float | str]] = []
        self.estimator.add(0.0, 0.0)

    def set_phase(self, phase: str) -> None:
        if phase != self.phase:
            self.phase = phase
            self.phase_time_s = 0.0

    def control_step(self) -> None:
        cfg = self.cfg
        dt = cfg.dt_s
        if self.phase == "approach":
            if self.flow_est_g_s > 0.5 and self.mass_est_g > 0.3:
                self.first_drop_count += 1
            else:
                self.first_drop_count = 0
            if self.first_drop_count >= 3:
                self.integral_deg = 0.0
                self.set_phase("pour")
            elif self.angle_deg >= cfg.max_tilt_deg - 0.2 and self.phase_time_s > 2.0:
                self.fault = "no flow detected before maximum tilt"
                self.set_phase("fault")
            else:
                self.angle_command_deg = min(
                    cfg.max_tilt_deg,
                    self.angle_command_deg + cfg.approach_rate_deg_s * dt,
                )
                self.command_rate_deg_s = cfg.approach_rate_deg_s

        if self.phase == "pour":
            remaining_g = cfg.target_g - self.mass_est_g
            cut_threshold_g = cfg.target_g - (cfg.cut_a_g + cfg.cut_b_s * self.flow_est_g_s)
            if self.mass_est_g >= cut_threshold_g:
                self.cut_mass_est_g = self.mass_est_g
                self.cut_flow_est_g_s = self.flow_est_g_s
                self.cut_angle_deg = self.angle_deg
                self.fast_untilt_angle_deg = max(0.0, self.angle_deg - 5.0)
                self.slow_untilt_angle_deg = max(0.0, self.angle_deg - 15.0)
                self.set_phase("untilt_fast")
            else:
                self.flow_setpoint_g_s = clamp(0.6 * remaining_g, 1.0, cfg.flow_ceiling_g_s)
                volume_for_ff = max(0.0, self.source_estimate_ml - self.mass_est_g / cfg.density_g_ml)
                theta_ff = angle_for_flow_g_s(self.flow_setpoint_g_s, volume_for_ff, cfg)
                error = self.flow_setpoint_g_s - self.flow_est_g_s
                integral_candidate = clamp(
                    self.integral_deg + cfg.ki_deg_per_g * error * dt,
                    -15.0,
                    15.0,
                )
                theta_candidate = theta_ff + cfg.kp_deg_per_g_s * error + integral_candidate
                theta_limited = clamp(theta_candidate, 0.0, cfg.max_tilt_deg)
                if theta_limited == theta_candidate or (theta_limited == cfg.max_tilt_deg and error < 0.0) or (theta_limited == 0.0 and error > 0.0):
                    self.integral_deg = integral_candidate
                self.angle_command_deg = theta_limited
                self.command_rate_deg_s = cfg.tilt_rate_deg_s

        if self.phase == "untilt_fast":
            self.angle_command_deg = self.fast_untilt_angle_deg or 0.0
            self.command_rate_deg_s = cfg.fast_untilt_rate_deg_s
            if self.angle_deg <= self.angle_command_deg + 0.3:
                self.set_phase("untilt_slow")

        if self.phase == "untilt_slow":
            self.angle_command_deg = self.slow_untilt_angle_deg or 0.0
            self.command_rate_deg_s = cfg.untilt_rate_deg_s
            if self.angle_deg <= self.angle_command_deg + 0.3:
                self.set_phase("drip_hold")

        if self.phase == "drip_hold":
            self.angle_command_deg = self.slow_untilt_angle_deg or 0.0
            self.command_rate_deg_s = cfg.untilt_rate_deg_s
            if self.phase_time_s >= cfg.drip_hold_s:
                self.set_phase("settle")

        if self.phase in ("settle", "done", "fault"):
            self.angle_command_deg = 0.0
            self.command_rate_deg_s = cfg.untilt_rate_deg_s

        if self.phase == "pour" and self.source_volume_ml <= 0.1 and self.flow_est_g_s < 0.2:
            self.dry_time_s += dt
            if self.dry_time_s >= 1.0:
                self.fault = "source beaker emptied before reaching target"
                self.set_phase("fault")
        else:
            self.dry_time_s = 0.0

    def plant_step(self) -> None:
        cfg = self.cfg
        dt = cfg.dt_s

        self.command_buffer.append(self.angle_command_deg)
        delayed_command = self.command_buffer[0]
        max_angle_step = self.command_rate_deg_s * dt
        self.angle_deg += clamp(delayed_command - self.angle_deg, -max_angle_step, max_angle_step)
        self.angle_deg = clamp(self.angle_deg, 0.0, cfg.max_tilt_deg)

        q_equilibrium = weir_flow_g_s(
            self.source_volume_ml,
            self.angle_deg,
            cfg,
            cd_scale=cfg.actual_weir_scale,
        )
        flow_alpha = clamp(dt / max(cfg.flow_response_s, dt), 0.0, 1.0)
        self.flow_g_s += flow_alpha * (q_equilibrium - self.flow_g_s)
        self.flow_g_s = max(0.0, self.flow_g_s)

        outgoing_g = min(self.flow_g_s * dt, self.source_volume_ml * cfg.density_g_ml)
        self.source_volume_ml = max(0.0, self.source_volume_ml - outgoing_g / cfg.density_g_ml)
        self.flow_buffer.append(outgoing_g / dt)
        landing_flow_g_s = self.flow_buffer[0]
        landed_g = landing_flow_g_s * dt
        self.receiver_mass_g += landed_g

        # Impact force adds apparent weight while the stream is landing: q * v / g = q * fall_time.
        stream_momentum_g = landing_flow_g_s * cfg.stream_fall_delay_s
        apparent_mass_g = self.receiver_mass_g + stream_momentum_g
        scale_alpha = clamp(dt / max(cfg.scale_lag_s, dt), 0.0, 1.0)
        self.scale_signal_g += scale_alpha * (apparent_mass_g - self.scale_signal_g)
        self.scale_buffer.append(self.scale_signal_g)
        scale_value_g = self.scale_buffer[0] + self.rng.gauss(0.0, cfg.scale_sigma_g)
        self.mass_est_g, self.flow_est_g_s = self.estimator.add(self.time_s, scale_value_g)

        self.rows.append(
            {
                "time_s": self.time_s,
                "phase": self.phase,
                "tilt_deg": self.angle_deg,
                "tilt_command_deg": self.angle_command_deg,
                "source_volume_ml": self.source_volume_ml,
                "flow_out_g_s": self.flow_g_s,
                "flow_landing_g_s": landing_flow_g_s,
                "flow_setpoint_g_s": self.flow_setpoint_g_s,
                "scale_reading_g": scale_value_g,
                "mass_estimate_g": self.mass_est_g,
                "flow_estimate_g_s": self.flow_est_g_s,
                "receiver_mass_g": self.receiver_mass_g,
            }
        )

    def run(self) -> dict[str, float | str | None]:
        cfg = self.cfg
        while self.time_s < cfg.max_time_s and self.phase not in ("done", "fault"):
            self.control_step()
            self.plant_step()
            self.time_s += cfg.dt_s
            self.phase_time_s += cfg.dt_s

            if self.phase == "settle":
                pending_stream = max(self.flow_buffer, default=0.0)
                if self.angle_deg <= 0.3 and self.flow_g_s < 0.02 and pending_stream < 0.02:
                    self.quiet_time_s += cfg.dt_s
                    if self.quiet_time_s >= 1.0:
                        self.set_phase("done")
                else:
                    self.quiet_time_s = 0.0

        final_error_g = self.receiver_mass_g - cfg.target_g
        status = self.fault or ("cut and settled" if self.phase == "done" else "time limit reached")
        return {
            "status": status,
            "target_g": cfg.target_g,
            "delivered_g": self.receiver_mass_g,
            "error_g": final_error_g,
            "cut_mass_estimate_g": self.cut_mass_est_g,
            "cut_flow_estimate_g_s": self.cut_flow_est_g_s,
            "elapsed_s": self.time_s,
            "final_tilt_deg": self.angle_deg,
            "source_remaining_ml": self.source_volume_ml,
        }


def parse_scale_list(value: str) -> list[float]:
    try:
        values = [float(piece.strip()) for piece in value.split(",") if piece.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated numbers") from exc
    if not values or any(v <= 0.0 for v in values):
        raise argparse.ArgumentTypeError("scale factors must be positive")
    return values


def print_result(label: str, result: dict[str, float | str | None]) -> None:
    print(f"{label}: {result['status']}")
    print(
        f"  target {result['target_g']:.2f} g, delivered {result['delivered_g']:.2f} g, "
        f"settled error {result['error_g']:+.2f} g"
    )
    cut_mass = result["cut_mass_estimate_g"]
    cut_flow = result["cut_flow_estimate_g_s"]
    if cut_mass is not None and cut_flow is not None:
        print(f"  cut estimate {cut_mass:.2f} g at {cut_flow:.2f} g/s")
    print(
        f"  elapsed {result['elapsed_s']:.2f} s, source remaining "
        f"{result['source_remaining_ml']:.2f} mL"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-g", type=float, default=39.0)
    parser.add_argument("--fill-ml", type=float, default=65.0, help="starting liquid volume in the source beaker")
    parser.add_argument("--fill-estimate-error-ml", type=float, default=0.0, help="error in the controller's fill estimate")
    parser.add_argument("--weir-scale", type=float, default=1.0, help="actual weir coefficient multiplier relative to the controller model")
    parser.add_argument("--scale-noise-g", type=float, default=0.05)
    parser.add_argument("--scale-lag-ms", type=float, default=25.0)
    parser.add_argument("--sensor-delay-ms", type=float, default=20.0)
    parser.add_argument("--fall-delay-ms", type=float, default=120.0)
    parser.add_argument("--csv", type=Path, help="write the time series to this CSV path")
    parser.add_argument("--sweep-weir-scales", type=parse_scale_list, help="run comma-separated flow-model mismatch cases")
    args = parser.parse_args()
    if args.target_g <= 0.0 or args.fill_ml <= 0.0:
        parser.error("target and starting fill must be positive")
    if args.weir_scale <= 0.0 or args.scale_noise_g < 0.0:
        parser.error("weir scale must be positive and scale noise cannot be negative")

    scales = args.sweep_weir_scales or [args.weir_scale]
    runs: list[tuple[str, PourSimulation, dict[str, float | str | None]]] = []
    for scale in scales:
        cfg = Config(
            target_g=args.target_g,
            fill_ml=args.fill_ml,
            fill_estimate_error_ml=args.fill_estimate_error_ml,
            actual_weir_scale=scale,
            scale_sigma_g=args.scale_noise_g,
            scale_lag_s=args.scale_lag_ms / 1000.0,
            sensor_delay_s=args.sensor_delay_ms / 1000.0,
            stream_fall_delay_s=args.fall_delay_ms / 1000.0,
        )
        sim = PourSimulation(cfg)
        result = sim.run()
        runs.append((f"weir_scale={scale:.2f}", sim, result))
        print_result(f"weir_scale={scale:.2f}", result)

    if args.csv:
        fieldnames = ["case"] + list(runs[0][1].rows[0].keys())
        with args.csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for label, sim, _ in runs:
                for row in sim.rows:
                    writer.writerow({"case": label, **row})
        print(f"CSV written to {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
