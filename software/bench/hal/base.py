"""The hardware abstraction seam.

Everything above this file (motion, process, agent, sequencer) talks only to these three
interfaces.  Two implementations exist:

  * bench.hal.sim   - backed by the MuJoCo world in software/sim
  * bench.hal.real  - LeRobot FeetechMotorsBus for the arms, pyserial for the Mega

Angles are degrees in the LeRobot "new calibration" convention (= the MJCF joint zero), which
is what a calibrated SO-101 reports.  Gripper angle likewise (the sim and the firmware both
treat it as a joint angle; LeRobot's 0-100 linear gripper mapping is applied in hal.real).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Protocol, runtime_checkable

ARM_JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]


@runtime_checkable
class ArmBus(Protocol):
    role: str

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def read_positions(self) -> dict[str, float]: ...
    def read_load(self) -> dict[str, float]: ...
    def write_goals(self, goals: dict[str, float]) -> None: ...
    def set_torque(self, on: bool) -> None: ...


@runtime_checkable
class MegaLink(Protocol):
    def connect(self) -> None: ...
    def command(self, obj: dict) -> dict: ...
    def samples(self) -> Iterator[dict]: ...
    def drain(self) -> list[dict]: ...
    def flush(self) -> None: ...          # discard queued WEIGHT samples (keep done/fault notices)


@runtime_checkable
class Clock(Protocol):
    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


@dataclass
class Bench:
    """Everything the sequencer needs, with no knowledge of what is behind it."""
    arms: dict[str, ArmBus]
    mega: MegaLink
    clock: Clock
    backend: str
    sim: object | None = None          # the World when backend == "sim", for recording/checks
    cameras: dict[str, object] = field(default_factory=dict)

    def connect(self) -> None:
        for a in self.arms.values():
            a.connect()
        self.mega.connect()


class BenchFault(RuntimeError):
    """A latched fault from the Mega or a safety rule; the sequencer goes to SAFE_STOP."""
