"""Pick, carry and place a beaker between stations (both arms), from the planned station poses.

Side grasp (pourer):  park -> carry-height over source -> lift -> pre (45 mm back along the
fingers, jaw open) -> grasp pose -> close -> lift -> carry -> ... -> lift over destination ->
place pose -> open -> pre (back out) -> lift -> carry -> park.
Top-down (transfer):  the pre pose is 60 mm above; otherwise the same.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from bench.config import Config, load
from bench.hal.base import Bench, BenchFault
from bench.motion.calib import park_mjcf_deg
from bench.motion.gripper import Gripper, GraspResult
from bench.motion.player import MotionLock, Player
from bench.motion.stations import PickPlan


class GraspFailed(BenchFault):
    pass


@dataclass
class ArmTask:
    """One arm's motion primitives, bound to its plans."""
    bench: Bench
    role: str
    plans: dict
    lock: MotionLock
    cfg: Config | None = None
    speed: float = 1.0
    log: object = print

    def __post_init__(self):
        self.cfg = self.cfg or load()
        self.player = Player(self.bench, self.role, self.lock, self.cfg, speed_scale=self.speed)
        self.gripper = Gripper(self.bench, self.role, self.cfg)
        self.park_q = park_mjcf_deg(self.cfg)

    def plan(self, station: str) -> PickPlan:
        return self.plans[f"{self.role}:{station}"]

    # ---------------------------------------------------------------- primitives
    def park(self, speed: float = 50.0) -> None:
        self.player.move_to(self.park_q, speed)
        self.player.done()

    def to_carry(self, station: str, speed: float = 60.0) -> None:
        self.player.move_to(self.plan(station).carry.q, speed)

    def pick(self, station: str) -> GraspResult:
        p = self.plan(station)
        self.log(f"  {self.role}: pick at {station}")
        self.gripper.open(wide=(p.grasp == "top_down"))
        self.player.move_to(p.carry.q, 60)
        self.player.move_to(p.lift.q, 45)
        self.player.move_to(p.pre.q, 35)
        self.player.move_to(p.grasp_pose.q, 20, settle_tol=1.5)
        res = self.gripper.close()
        self.log(f"  {self.role}: grasp -> {res}")
        if not res.ok:
            self.gripper.open(wide=(p.grasp == "top_down"))
            self.player.move_to(p.pre.q, 25)
            self.player.move_to(p.lift.q, 40)
            raise GraspFailed(f"{self.role} missed the beaker at {station}: {res}")
        # lift check: 5 mm up, hold, then the full lift
        self.player.move_to(p.lift.q, 25)
        self.player.move_to(p.carry.q, 50)
        return res

    def place(self, station: str) -> None:
        p = self.plan(station)
        self.log(f"  {self.role}: place at {station}")
        self.player.move_to(p.carry.q, 50)
        self.player.move_to(p.lift.q, 35)
        self.player.move_to(p.grasp_pose.q, 18, settle_tol=1.5)
        self.bench.clock.sleep(0.2)
        self.gripper.open(wide=(p.grasp == "top_down"))
        self.player.move_to(p.pre.q, 25)
        self.player.move_to(p.lift.q, 40)
        self.player.move_to(p.carry.q, 60)

    def transfer(self, src: str, dst: str) -> None:
        self.pick(src)
        self.place(dst)
        self.park()
