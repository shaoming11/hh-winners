"""Fin-ray gripper control and grasp/miss classification (software_architecture.md 3.5).

The jaw is a position servo commanded PAST contact by SQUEEZE degrees; the load it ends up
holding tells us if something is in the jaws:
  grasp  - load above the grip threshold (the finger stalls on, or deflects against, the beaker)
  miss   - within 0.5 deg of the goal and load below 8 %
anything else is retried once, then reported as uncertain.
"""
from __future__ import annotations

from dataclasses import dataclass

from bench.config import Config, load
from bench.hal.base import Bench

# Jaw angles in the LeRobot/MJCF gripper-joint convention.  JAW_CONTACT in sim/build_scene.py
# fixes the contact angle on a Phi56 beaker; the 14 deg travel is gripper_design.json's
# q_open - q_contact; the wide opening is for top-down picks past the 67 mm pocket pitch.
CONTACT_DEG = 20.05
OPEN_DEG = 34.1
OPEN_WIDE_DEG = 62.0
CLOSE_DEG = 16.05        # contact + SQUEEZE(4) on hardware, the direction that closes
# The sim's fingers are rigid boxes (a real fin-ray finger deflects under the squeeze), so the
# sim squeezes 3 deg: enough to stall the jaw at its torque limit on the beaker.
SIM_CLOSE_DEG = CONTACT_DEG - 3.0


@dataclass
class GraspResult:
    ok: bool
    kind: str            # "grasp" | "miss" | "uncertain"
    jaw_deg: float
    load: float
    short_deg: float

    def __str__(self) -> str:
        return f"{self.kind} (jaw {self.jaw_deg:.1f} deg, {self.short_deg:.1f} deg short, load {self.load:.0f})"


class Gripper:
    def __init__(self, bench: Bench, role: str, cfg: Config | None = None):
        self.b = bench
        self.role = role
        self.cfg = cfg or load()
        c = self.cfg.at("control.gripper")
        self.classify_delay = float(c["classify_delay_s"])
        self.stall_short = float(c["stall_short_deg"])
        self.miss_near = float(c["miss_near_goal_deg"])
        self.miss_load = float(c["miss_load_frac"]) * 1000.0
        self.grip_load = 90.0                   # Present_Load units (9 %); tune on hardware Friday
        self.close_deg = SIM_CLOSE_DEG if getattr(bench, "backend", "") == "sim" else CLOSE_DEG
        self.last: GraspResult | None = None

    @property
    def arm(self):
        return self.b.arms[self.role]

    def open(self, wide: bool = False, wait: float = 0.35) -> None:
        self.arm.write_goals({"gripper": OPEN_WIDE_DEG if wide else OPEN_DEG})
        self.b.clock.sleep(wait)

    def close(self, retries: int = 1) -> GraspResult:
        for attempt in range(retries + 1):
            self.arm.write_goals({"gripper": self.close_deg})
            self.b.clock.sleep(self.classify_delay + 0.25)
            q = self.arm.read_positions()["gripper"]
            load = abs(self.arm.read_load()["gripper"])
            short = abs(q - self.close_deg)
            # Load first: a fin-ray finger deflects under the squeeze, so a firm grasp can show
            # as "goal reached, high load" as well as "stalled short, high load".
            if load >= self.grip_load:
                self.last = GraspResult(True, "grasp", q, load, short)
                return self.last
            if short <= self.miss_near and load < self.miss_load:
                self.last = GraspResult(False, "miss", q, load, short)
                return self.last
            if attempt < retries:
                self.open(wait=0.3)
        self.last = GraspResult(False, "uncertain", q, load, short)
        return self.last

    def is_closed(self) -> bool:
        return abs(self.arm.read_positions()["gripper"] - self.close_deg) < 6.0
