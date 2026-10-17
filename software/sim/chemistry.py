"""Analytic liquid / powder / foam model layered on the rigid-body world.

MuJoCo moves the beakers; this module tracks what is inside them and moves mass between
vessels.  It implements the plant model specified in docs/software_architecture.md 9.3:

  * tilted-cylinder capacity V(theta): liquid above the lowest rim point overflows
  * weir discharge  q = (2/3) Cd sqrt(2g) w h^1.5  over the rim
  * a fall delay before the stream lands (0.12 s), plus stream momentum on the scale
  * stream landing from the lip:  dx = v_exit * sqrt(2 h / g)  (layout_final.md Update 8)
  * yeast delivered per auger revolution with noise and a dribble
  * elephant-toothpaste foam that grows from the measured reagent masses after an induction
    delay, for the camera to measure

Everything here is grams, mm, seconds; MuJoCo bodies are touched only through World.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

G_MM = 9810.0            # mm/s^2


@dataclass
class Vessel:
    name: str
    body: str                       # MuJoCo body name
    radius_mm: float
    height_mm: float
    accept_r_mm: float              # landing radius that counts as "in"
    contents: dict[str, float] = field(default_factory=dict)   # reagent -> grams
    empty_g: float = 15.0
    is_funnel_target: bool = False  # receives through a funnel (the flask)
    spilled_g: float = 0.0

    @property
    def liquid_g(self) -> float:
        return sum(v for k, v in self.contents.items() if k != "yeast")

    @property
    def total_g(self) -> float:
        return sum(self.contents.values())

    def add(self, reagent: str, grams: float) -> None:
        if grams <= 0:
            return
        self.contents[reagent] = self.contents.get(reagent, 0.0) + grams

    def take_liquid(self, grams: float) -> dict[str, float]:
        """Remove `grams` of liquid proportionally across liquid reagents (yeast rides along
        in the slurry in proportion to the water it is suspended in)."""
        tot = self.total_g
        if tot <= 1e-9 or grams <= 0:
            return {}
        frac = min(1.0, grams / tot)
        out = {}
        for k in list(self.contents):
            dm = self.contents[k] * frac
            self.contents[k] -= dm
            if self.contents[k] < 1e-6:
                del self.contents[k]
            out[k] = dm
        return out


@dataclass
class _InFlight:
    reagent_mix: dict[str, float]
    land_t: float
    target: str | None            # vessel name or None = spilled
    land_xy: tuple[float, float]
    fall_v_mmps: float


class Chemistry:
    def __init__(self, cfg, densities: dict[str, float], rng: np.random.Generator):
        self.cfg = cfg
        self.rho = dict(densities)
        self.rng = rng
        self.vessels: dict[str, Vessel] = {}
        self.inflight: list[_InFlight] = []
        self.weir_cd = float(cfg.at("calibration.weir_c"))
        self.exit_v = float(cfg.at("control.pour.stream_exit_mmps"))
        self.fall_delay = 0.12
        self.spilled_total_g = 0.0
        self.last_flow_gps: dict[str, float] = {}
        self.last_landing: dict[str, tuple] = {}
        # foam
        self.foam_h_mm = 0.0
        self.foam_started_t: float | None = None
        self.reaction_t: float | None = None
        self.induction_s = float(cfg.at("control.eruption.induction_s"))

    # ------------------------------------------------------------ setup
    def add_vessel(self, v: Vessel) -> Vessel:
        self.vessels[v.name] = v
        return v

    def density(self, reagent: str) -> float:
        return self.rho.get(reagent, 1.0)

    def mass_g(self, name: str) -> float:
        v = self.vessels[name]
        return v.empty_g + v.total_g

    # ------------------------------------------------------------ geometry
    @staticmethod
    def capacity_ml(r: float, h: float, tilt_rad: float) -> float:
        """Volume (mL) a cylinder of radius r, height h (mm) holds when tilted `tilt` from
        vertical - liquid level touching the lowest rim point."""
        t = abs(math.tan(tilt_rad))
        if tilt_rad >= math.pi / 2 - 1e-6:
            return 0.0
        if t * 2 * r <= h:                     # surface hits both walls
            return math.pi * r * r * (h - r * t) / 1000.0
        # The free surface through the lowest rim point (x = -r, height h) descends toward +x
        # and reaches the floor at x_dry = -r + h/t, short of the far wall: a wedge.
        x_dry = -r + h / t
        if x_dry <= -r:
            return 0.0
        xs = np.linspace(-r, x_dry, 64)
        depth = (x_dry - xs) * t                # liquid depth above the floor at x (mm)
        chord = 2 * np.sqrt(np.maximum(r * r - xs * xs, 0.0))
        return float(np.trapezoid(depth * chord, xs) / 1000.0)

    def level_above_rim_mm(self, v: Vessel, tilt_rad: float) -> float:
        """Head of liquid above the lowest rim point, from the overflow volume."""
        vol = sum(g / self.density(k) for k, g in v.contents.items())
        cap = self.capacity_ml(v.radius_mm, v.height_mm, tilt_rad)
        excess_ml = vol - cap
        if excess_ml <= 0:
            return 0.0
        # the free surface is a (tilted) ellipse of area pi r^2 / cos(tilt)
        area_mm2 = math.pi * v.radius_mm ** 2 / max(math.cos(tilt_rad), 0.15)
        return excess_ml * 1000.0 / area_mm2

    # ------------------------------------------------------------ dynamics
    def pour_step(self, src: Vessel, tilt_rad: float, lip_xyz: np.ndarray, tilt_dir_xy,
                  now: float, dt: float, receivers: dict[str, tuple[np.ndarray, float]]) -> float:
        """Advance one source vessel. `receivers` maps vessel name -> (rim centre xyz, rim z).
        Returns the instantaneous flow in g/s."""
        h = self.level_above_rim_mm(src, tilt_rad)
        if h <= 0.0 or src.total_g <= 0:
            self.last_flow_gps[src.name] = 0.0
            return 0.0
        w = 2 * src.radius_mm * 0.75 * MMs                       # effective weir width (m)
        q_m3s = (2 / 3) * self.weir_cd * math.sqrt(2 * 9.81) * w * (h * MMs) ** 1.5
        rho = max(sum(self.density(k) * g for k, g in src.contents.items()) / src.total_g, 0.5)
        q_gps = q_m3s * 1e6 * rho                                # mL/s * g/mL
        if tilt_rad > math.radians(95):                          # inverted: the rest just falls out
            q_gps = max(q_gps, 25.0)
        q_gps = min(q_gps, src.total_g / dt)                      # can't pour more than there is
        dm = q_gps * dt
        mix = src.take_liquid(dm)
        # where does it land?  fall from the lip to the receiver rim it is above
        tx, ty = tilt_dir_xy
        target, best_dz = None, None
        for name, (rim_c, rim_z) in receivers.items():
            if name == src.name or rim_z >= lip_xyz[2] - 2.0:
                continue
            fall = lip_xyz[2] - rim_z
            dx = self.exit_v * math.sqrt(2 * fall / G_MM)
            land = np.array([lip_xyz[0] + tx * dx, lip_xyz[1] + ty * dx])
            r = float(np.linalg.norm(land - rim_c[:2]))
            vv = self.vessels[name]
            if r <= vv.accept_r_mm and (best_dz is None or fall < best_dz):
                target, best_dz = name, fall
                self.last_landing[src.name] = (name, r, tuple(land))
        if target is None:
            fall = lip_xyz[2]
            self.last_landing[src.name] = (None, float("nan"), (lip_xyz[0], lip_xyz[1]))
        v_impact = math.sqrt(2 * G_MM * max(best_dz if best_dz else lip_xyz[2], 0.0))
        self.inflight.append(_InFlight(mix, now + self.fall_delay, target,
                                       (float(lip_xyz[0]), float(lip_xyz[1])), v_impact))
        self.last_flow_gps[src.name] = q_gps
        return q_gps

    def land_step(self, now: float) -> dict[str, float]:
        """Deliver in-flight liquid whose fall delay has elapsed.  Returns the momentum
        force (N) landing in each vessel this call (for the scale)."""
        impulse: dict[str, float] = {}
        keep = []
        for f in self.inflight:
            if f.land_t > now:
                keep.append(f)
                continue
            grams = sum(f.reagent_mix.values())
            if f.target is None:
                self.spilled_total_g += grams
                continue
            v = self.vessels[f.target]
            for k, g in f.reagent_mix.items():
                v.add(k, g)
            impulse[f.target] = impulse.get(f.target, 0.0) + grams * 1e-3 * f.fall_v_mmps * 1e-3 / self.fall_delay
        self.inflight = keep
        return impulse

    # ------------------------------------------------------------ yeast
    def dose_yeast(self, target: Vessel | None, revolutions: float, g_per_rev: float) -> float:
        """Auger delivery for `revolutions` turns.  Returns grams delivered (or spilled)."""
        grams = max(0.0, revolutions) * g_per_rev * float(self.rng.normal(1.0, 0.06))
        if target is None:
            self.spilled_total_g += grams
            return 0.0
        target.add("yeast", grams)
        return grams

    # ------------------------------------------------------------ foam
    def foam_step(self, flask: Vessel, now: float, dt: float) -> float:
        h2o2 = flask.contents.get("developer", 0.0)
        yeast = flask.contents.get("yeast", 0.0)
        if h2o2 > 5.0 and yeast > 0.5 and self.reaction_t is None:
            self.reaction_t = now
        if self.reaction_t is None:
            return self.foam_h_mm
        t = now - self.reaction_t - self.induction_s
        if t <= 0:
            return self.foam_h_mm
        # 39 g of 12 % developer frees ~1.7 L of O2 (demo_process.md); the foam holds a
        # fraction of it.  Height of a Phi85 column: 1 L of foam ~ 176 mm.
        final_ml = 0.6 * (h2o2 / 39.0) * 1700.0 * min(1.0, yeast / 3.0)
        final_h = final_ml * 1000.0 / (math.pi * 42.5 ** 2)
        k = 0.8                                             # 1/s growth
        self.foam_h_mm = final_h * (1 - math.exp(-k * t))
        return self.foam_h_mm


MMs = 0.001
