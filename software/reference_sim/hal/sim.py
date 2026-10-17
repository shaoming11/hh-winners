"""Simulated arm buses and JSON-line Mega device for the reference scene."""
from __future__ import annotations

from collections.abc import Iterator
import math
from typing import Any

from hal.base import ArmBus
from hal.protocol import decode_line, encode_line
from world import BenchWorld


class SimArmBus:
    """SO-101-like joint interface backed by the MuJoCo position actuators."""

    def __init__(self, world: BenchWorld, arm: str):
        if arm not in ("pourer", "transfer"):
            raise ValueError(f"Unknown arm: {arm}")
        self.world = world
        self.arm = arm
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def _require_connected(self) -> None:
        if not self.connected:
            raise RuntimeError("ArmBus.connect() must be called first")

    def read_positions(self) -> dict[str, float]:
        self._require_connected()
        return self.world.arm_positions_deg(self.arm)

    def read_load(self) -> dict[str, float]:
        self._require_connected()
        return self.world.arm_load(self.arm)

    def write_goals(self, goals: dict[str, float]) -> None:
        self._require_connected()
        self.world.set_arm_goals_deg(self.arm, goals)

    def set_torque(self, on: bool) -> None:
        self._require_connected()
        self.world.set_arm_torque(self.arm, bool(on))


class SimMegaLink:
    """80 Hz scale stream and asynchronous mechanism commands for the sim.

    Supported commands are carousel, stage, auger, tare, estop and clear_estop.
    Commands return BUSY first. The sample stream emits periodic weight records and
    one done or fault record when an operation reaches its requested duration.
    """

    def __init__(self, world: BenchWorld, *, sample_hz: float = 80.0,
                 grams_per_auger_rev: float = 0.50):
        self.world = world
        self.period = 1.0 / sample_hz
        self.grams_per_auger_rev = grams_per_auger_rev
        self._pending: dict[str, Any] | None = None
        self._fault: str | None = None
        self._last_fault_emitted = False
        self._serial: list[dict] = []
        self._yeast_g = 0.0
        self._step_fraction = 0.0

    def command(self, obj: dict) -> dict:
        if self._fault and obj.get("cmd") not in ("clear_estop",):
            return {"ok": False, "error": self._fault}
        if self._pending is not None:
            return {"ok": False, "error": "BUSY"}
        name = obj.get("cmd")
        if name == "tare":
            self.world.tare_scale()
            return {"ok": True, "state": "DONE", "cmd": name}
        if name == "estop":
            self._fault = "ESTOP"
            self._pending = None
            return {"ok": True, "state": "FAULT", "fault": self._fault}
        if name == "clear_estop":
            self._fault = None
            self._last_fault_emitted = False
            return {"ok": True, "state": "DONE", "cmd": name}
        if name == "carousel":
            degrees = float(obj.get("deg", 0.0))
            duration = self._duration(obj, 2000)
            self.world.set_actuator_goal_rad("carousel_position", math.radians(degrees))
            self._pending = {"cmd": name, "duration": duration,
                             "result": {"deg": degrees}}
        elif name == "stage":
            degrees = float(obj.get("deg", 150.0))
            if not 0.0 <= degrees <= 150.0:
                return {"ok": False, "error": "RANGE"}
            duration = self._duration(obj, 2500)
            travel = self.world.stage_travel_mm(degrees)
            start_travel = self.world.status()["stage_travel_mm"]
            self._pending = {"cmd": name, "duration": duration, "elapsed": 0.0,
                             "settle_elapsed": 0.0,
                             "start_travel_mm": start_travel,
                             "target_travel_mm": travel,
                             "result": {"deg": degrees, "travel_mm": travel}}
        elif name == "auger":
            revs = float(obj.get("revs", 0.0))
            if not 0.0 <= revs <= 100.0:
                return {"ok": False, "error": "RANGE"}
            duration = self._duration(obj, max(100, round(revs * 500)))
            self._pending = {"cmd": name, "duration": duration,
                             "result": {"revs": revs,
                                        "grams": revs * self.grams_per_auger_rev}}
        else:
            return {"ok": False, "error": "UNKNOWN_COMMAND"}
        return {"ok": True, "state": "BUSY", "cmd": name}

    @staticmethod
    def _duration(obj: dict, fallback_ms: int) -> float:
        value = int(obj.get("ms", fallback_ms))
        if value < 1 or value > 120000:
            raise ValueError("ms must be between 1 and 120000")
        return value / 1000.0

    def samples(self) -> Iterator[dict]:
        """Advance at 80 Hz and yield weight plus operation-completion records."""
        while True:
            steps_exact = self.period / self.world.model.opt.timestep + self._step_fraction
            steps = max(1, math.floor(steps_exact))
            self._step_fraction = steps_exact - steps
            elapsed = steps * self.world.model.opt.timestep
            if self._pending is not None and self._pending["cmd"] == "stage":
                command = self._pending
                command["elapsed"] = min(command["duration"], command["elapsed"] + elapsed)
                u = command["elapsed"] / command["duration"]
                smooth = u * u * (3.0 - 2.0 * u)
                travel = (command["start_travel_mm"] +
                          (command["target_travel_mm"] - command["start_travel_mm"]) * smooth)
                self.world.set_actuator_goal_rad("stage_position", -travel / 1000)
            self.world.step(elapsed)
            if self._fault:
                if not self._last_fault_emitted:
                    self._last_fault_emitted = True
                    yield {"f": self._fault}
                continue
            now_ms = round(self.world.data.time * 1000)
            yield {"w": [now_ms, round(self.world.scale_grams(), 3)]}
            if self._pending is not None:
                pending = self._pending
                if pending["cmd"] == "stage":
                    profile_finished = pending["elapsed"] >= pending["duration"]
                    actual = self.world.status()["stage_travel_mm"]
                    finished = profile_finished and abs(actual - pending["target_travel_mm"]) <= 0.25
                    if profile_finished and not finished:
                        pending["settle_elapsed"] += elapsed
                        if pending["settle_elapsed"] > 2.0:
                            self._pending = None
                            self._fault = "STAGE_TIMEOUT"
                            self._last_fault_emitted = True
                            yield {"f": self._fault}
                            continue
                else:
                    pending["duration"] -= elapsed
                    finished = pending["duration"] <= 0
                if finished:
                    done = self._pending
                    self._pending = None
                    if done["cmd"] == "auger":
                        self._yeast_g += float(done["result"]["grams"])
                        self.world.set_scale_payload_g(
                            self.world.scale_payload_g + float(done["result"]["grams"]))
                    if done["cmd"] == "stage":
                        done["result"]["actual_travel_mm"] = self.world.status()["stage_travel_mm"]
                    self._serial.append({"done": done["cmd"], **done["result"]})
                    yield self._serial.pop(0)

    def wait_until_idle(self) -> dict:
        """Simulator helper: consume samples through the next completion record."""
        if self._pending is None:
            return {"ok": True, "state": "IDLE"}
        for event in self.samples():
            if "f" in event:
                return {"ok": False, "state": "FAULT", "fault": event["f"]}
            if "done" in event:
                return {"ok": True, "state": "DONE", **event}
        raise RuntimeError("unreachable sample stream exit")

    def handle_line(self, line: str | bytes) -> str:
        """Exercise the same newline-delimited codec used by the serial backend."""
        command = decode_line(line)
        return encode_line(self.command(command))


def make_sim_bench(world: BenchWorld | None = None) -> tuple[BenchWorld, SimArmBus, SimArmBus, SimMegaLink]:
    world = world or BenchWorld()
    pourer, transfer = SimArmBus(world, "pourer"), SimArmBus(world, "transfer")
    pourer.connect()
    transfer.connect()
    return world, pourer, transfer, SimMegaLink(world)
