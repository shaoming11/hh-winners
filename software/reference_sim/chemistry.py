"""Analytical pour model: no liquid-particle simulation is implied."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import math
import random


@dataclass
class PourResult:
    target_g: float
    landed_g: float
    spilled_g: float
    peak_flow_g_s: float
    mean_flow_g_s: float
    peak_tilt_deg: float
    duration_s: float
    landing_offset_mm: float
    samples: list[dict] = field(default_factory=list)


class PourPlant:
    """Tilted cylindrical vessel + rectangular-weir approximation + scale stream."""
    def __init__(self, radius_m: float = 0.028, height_m: float = 0.074,
                 wall_width_m: float = 0.012, weir_c: float = 0.42,
                 fall_delay_s: float = 0.12, seed: int = 17):
        self.radius = radius_m
        self.height = height_m
        self.width = wall_width_m
        self.weir_c = weir_c
        self.fall_delay_s = fall_delay_s
        self.rng = random.Random(seed)

    def _area_below(self, threshold: float) -> float:
        r = self.radius
        if threshold <= -r:
            return math.pi * r * r
        if threshold >= r:
            return 0.0
        area_left = threshold * math.sqrt(max(0.0, r * r - threshold * threshold)) + \
                    r * r * (math.asin(threshold / r) + math.pi / 2)
        return math.pi * r * r - area_left

    def volume_below_plane(self, tilt_deg: float, plane_z_m: float) -> float:
        theta = math.radians(max(0.0, min(120.0, tilt_deg)))
        area0 = math.pi * self.radius * self.radius
        if theta < 1e-5:
            return area0 * max(0.0, min(self.height, plane_z_m))
        n = 120
        ds = self.height / n
        total = 0.0
        for i in range(n + 1):
            s = i * ds
            threshold = (s * math.cos(theta) - plane_z_m) / math.sin(theta)
            area = self._area_below(threshold)
            weight = 1 if i in (0, n) else (4 if i % 2 else 2)
            total += weight * area
        return total * ds / 3

    def surface_height_m(self, mass_g: float, tilt_deg: float) -> float:
        volume = max(0.0, mass_g) / 1_000_000.0  # 1 g water = 1 cm^3 = 1e-6 m^3.
        max_volume = math.pi * self.radius * self.radius * self.height
        volume = min(volume, max_volume)
        lo, hi = -self.radius - 0.01, self.height + self.radius + 0.01
        for _ in range(40):
            mid = (lo + hi) / 2
            if self.volume_below_plane(tilt_deg, mid) < volume:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def flow_g_s(self, remaining_g: float, tilt_deg: float) -> float:
        theta = math.radians(max(0.0, min(120.0, tilt_deg)))
        surface = self.surface_height_m(remaining_g, tilt_deg)
        lowest_lip = self.height * math.cos(theta) - self.radius * math.sin(theta)
        head = max(0.0, surface - lowest_lip)
        # C*w*h^1.5 in m^3/s, converted to grams/s for a water-like liquid.
        return min(18.0, self.weir_c * self.width * head ** 1.5 * 1_000_000)

    @staticmethod
    def landing_offset_mm(fall_height_mm: float, exit_speed_mm_s: float = 250.0) -> float:
        return exit_speed_mm_s * math.sqrt(2 * max(0.0, fall_height_mm) / 9810.0)

    def pour(self, donor_g: float, target_g: float, *, receiver_radius_mm: float = 20.0,
             receiver_drop_mm: float = 20.0, flow_target_g_s: float = 5.0,
             dt: float = 0.0125, max_seconds: float = 30.0) -> PourResult:
        """Pour to a target using 80 Hz scale readings and flow-based early cut-off."""
        donor = donor_g
        landed = spilled = 0.0
        theta = 40.0
        integral = 0.0
        sensor_mass = 0.0
        delay_steps = max(1, round(self.fall_delay_s / dt))
        in_flight: deque[float] = deque([0.0] * delay_steps)
        readings: deque[tuple[float, float]] = deque(maxlen=40)
        peak_flow = sum_flow = 0.0
        peak_theta = 0.0
        traces = []
        time_s = 0.0
        cut = False
        while time_s < max_seconds:
            measured = sensor_mass + self.rng.gauss(0, 0.05)
            readings.append((time_s, measured))
            qhat = 0.0
            if len(readings) >= 8:
                t0 = readings[0][0]
                ts = [t - t0 for t, _ in readings]
                ms = [m - readings[0][1] for _, m in readings]
                mean_t = sum(ts) / len(ts)
                mean_m = sum(ms) / len(ms)
                denom = sum((t - mean_t) ** 2 for t in ts)
                if denom > 0:
                    qhat = sum((t - mean_t) * (m - mean_m) for t, m in zip(ts, ms)) / denom
            if not cut:
                error = flow_target_g_s - qhat
                integral = max(-10.0, min(10.0, integral + error * dt))
                theta += max(-0.75, min(0.75, (0.10 * error + 0.035 * integral)))
                theta = max(40.0, min(105.0, theta))
            else:
                theta = max(0.0, theta - 60.0 * dt)

            rate = self.flow_g_s(donor, theta)
            amount = min(donor, rate * dt)
            donor -= amount
            in_flight.append(amount)
            landed_now = in_flight.popleft()
            # The offset is fixed by the outlet-to-receiver drop. If it misses, material spills.
            offset = self.landing_offset_mm(receiver_drop_mm)
            if offset <= receiver_radius_mm:
                landed += landed_now
                sensor_mass += landed_now
            else:
                spilled += landed_now
            peak_flow = max(peak_flow, rate)
            sum_flow += rate
            peak_theta = max(peak_theta, theta)
            time_s += dt
            if len(traces) < 4 or round(time_s * 10) != round((time_s - dt) * 10):
                traces.append({"time_s": round(time_s, 3), "tilt_deg": round(theta, 2),
                               "flow_g_s": round(rate, 3), "scale_g": round(sensor_mass, 3)})
            if not cut and sensor_mass >= target_g - (0.3 + 0.15 * max(0.0, qhat)):
                cut = True
            if cut and theta <= 0 and not any(in_flight):
                break
            if donor <= 0 and not any(in_flight):
                break

        return PourResult(target_g, landed, spilled, peak_flow,
                          sum_flow / max(1, round(time_s / dt)), peak_theta, time_s,
                          self.landing_offset_mm(receiver_drop_mm), traces)


@dataclass
class FoamSample:
    time_s: float
    height_mm: float
    oxygen_l: float
    activity: float


class FoamReaction:
    """Calibratable visual foam profile driven by peroxide and yeast masses.

    The 1.7 L oxygen estimate is stoichiometric for 4.68 g of hydrogen peroxide.
    Peak foam height and growth time are visual defaults, not measured chemistry.
    """

    def __init__(self, *, reference_h2o2_g: float = 4.68,
                 reference_yeast_g: float = 7.0,
                 oxygen_l_at_reference: float = 1.7,
                 peak_height_mm: float = 140.0,
                 induction_delay_s: float = 0.25,
                 growth_duration_s: float = 4.0):
        self.reference_h2o2_g = reference_h2o2_g
        self.reference_yeast_g = reference_yeast_g
        self.oxygen_l_at_reference = oxygen_l_at_reference
        self.peak_height_mm = peak_height_mm
        self.induction_delay_s = induction_delay_s
        self.growth_duration_s = growth_duration_s

    def sample(self, time_s: float, *, h2o2_g: float, yeast_g: float) -> FoamSample:
        peroxide_fraction = max(0.0, h2o2_g) / self.reference_h2o2_g
        yeast_fraction = max(0.0, yeast_g) / self.reference_yeast_g
        activity = min(1.0, peroxide_fraction, yeast_fraction)
        growth = max(0.0, min(1.0,
                              (time_s - self.induction_delay_s) /
                              max(self.growth_duration_s, 1e-9)))
        growth = growth * growth * (3 - 2 * growth)
        return FoamSample(
            time_s=float(time_s),
            height_mm=self.peak_height_mm * activity * growth,
            oxygen_l=self.oxygen_l_at_reference * peroxide_fraction,
            activity=activity,
        )
