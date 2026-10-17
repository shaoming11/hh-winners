"""HAL backend for the real bench: LeRobot Feetech bus for each SO-101, pyserial for the Mega.

Install on the laptop:  pip install lerobot pyserial
Calibrate both arms with LeRobot first (`lerobot-calibrate --robot.type=so101_follower ...`);
the positions this backend reads and writes are LeRobot's calibrated degrees, which is the
same convention as the sim (the MJCF "new calibration" zero).

Port identity: set WLB_POURER_PORT / WLB_TRANSFER_PORT / WLB_MEGA_PORT, or edit PORTS below.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from typing import Iterator

from bench.config import Config, load
from bench.hal import protocol
from bench.hal.base import ARM_JOINTS, Bench, BenchFault

PORTS = {
    "pourer": os.environ.get("WLB_POURER_PORT", "/dev/tty.usbmodem_pourer"),
    "transfer": os.environ.get("WLB_TRANSFER_PORT", "/dev/tty.usbmodem_transfer"),
    "mega": os.environ.get("WLB_MEGA_PORT", "/dev/tty.usbserial-mega"),
}
# LeRobot's gripper is 0 (closed) .. 100 (open) "linear"; the sim/firmware use the joint angle.
# Map our CLOSE/OPEN_WIDE degrees onto that range - re-measure on the real gripper.
GRIPPER_DEG_TO_PCT = (16.0, 62.0)      # (deg at 0 %, deg at 100 %)


class RealClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class LeRobotArmBus:
    """One SO-101 follower through LeRobot's FeetechMotorsBus."""

    def __init__(self, role: str, port: str, cfg: Config | None = None):
        self.role = role
        self.port = port
        self.cfg = cfg or load()
        self.robot = None
        self.max_step = 5.0            # deg per write, ArmDriver clamp (architecture 2.6)
        self._last: dict[str, float] = {}

    def connect(self) -> None:
        try:
            from lerobot.robots.so101_follower import SO101Follower, SO101FollowerConfig
        except ImportError as e:  # pragma: no cover
            raise BenchFault("lerobot is not installed: pip install lerobot") from e
        self.robot = SO101Follower(SO101FollowerConfig(port=self.port, id=f"wlb_{self.role}",
                                                      max_relative_target=self.max_step))
        self.robot.connect(calibrate=False)
        self._last = self.read_positions()

    def disconnect(self) -> None:
        # never drops torque mid-run (architecture 2.7): only on explicit RESET
        pass

    def read_positions(self) -> dict[str, float]:
        obs = self.robot.get_observation()
        out = {}
        for j in ARM_JOINTS:
            v = float(obs[f"{j}.pos"])
            if j == "gripper":
                lo, hi = GRIPPER_DEG_TO_PCT
                v = lo + (hi - lo) * v / 100.0
            out[j] = v
        self._last = out
        return out

    def read_load(self) -> dict[str, float]:
        bus = self.robot.bus
        try:
            loads = bus.sync_read("Present_Load", normalize=False)
            return {j: float(loads[j]) for j in ARM_JOINTS}
        except Exception:  # noqa: BLE001
            return {j: 0.0 for j in ARM_JOINTS}

    def write_goals(self, goals: dict[str, float]) -> None:
        action = {}
        for j, v in goals.items():
            if j == "gripper":
                lo, hi = GRIPPER_DEG_TO_PCT
                v = (v - lo) / (hi - lo) * 100.0
            action[f"{j}.pos"] = float(v)
        self.robot.send_action(action)

    def set_torque(self, on: bool) -> None:
        bus = self.robot.bus
        (bus.enable_torque if on else bus.disable_torque)()


class SerialMegaLink:
    """JSON-line protocol over pyserial, with a reader thread so weight samples are never lost."""

    def __init__(self, port: str, baud: int = 250000):
        self.port, self.baud = port, baud
        self.ser = None
        self.q: deque = deque(maxlen=20000)
        self.replies: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._thread = None
        self._hb_thread = None
        self._alive = False

    def connect(self) -> None:
        import serial
        self.ser = serial.Serial()
        self.ser.port, self.ser.baudrate, self.ser.timeout = self.port, self.baud, 0.05
        self.ser.dtr = False; self.ser.rts = False          # don't reset the Mega on open
        self.ser.open()
        self._alive = True
        self._thread = threading.Thread(target=self._reader, daemon=True); self._thread.start()
        self._hb_thread = threading.Thread(target=self._heartbeat, daemon=True); self._hb_thread.start()
        rep = self.command({"cmd": "ver"})
        if not rep.get("ok"):
            raise BenchFault(f"Mega did not answer VER on {self.port}: {rep}")

    def _reader(self) -> None:
        buf = b""
        while self._alive:
            chunk = self.ser.read(256)
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                obj = protocol.decode(line)
                if obj is None or "junk" in obj:
                    continue
                if "id" in obj and ("ok" in obj):
                    with self._lock:
                        self.replies[int(obj["id"])] = obj
                else:
                    self.q.append(obj)

    def _heartbeat(self) -> None:
        while self._alive:
            try:
                self.ser.write(protocol.encode({"id": 0, "cmd": "hb"}))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.1)

    def command(self, obj: dict, timeout: float = 1.0) -> dict:
        cid = obj.get("id") or protocol.next_id()
        obj = dict(obj, id=cid)
        self.ser.write(protocol.encode(obj))
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            with self._lock:
                if cid in self.replies:
                    return self.replies.pop(cid)
            time.sleep(0.002)
        return {"id": cid, "ok": False, "err": "TIMEOUT"}

    def samples(self) -> Iterator[dict]:
        self.command({"cmd": "stream", "on": True})
        while True:
            if self.q:
                yield self.q.popleft()
            else:
                time.sleep(0.002)

    def drain(self) -> list[dict]:
        out = list(self.q); self.q.clear()
        return out

    def flush(self) -> None:
        keep = [m for m in self.q if "w" not in m]
        self.q.clear(); self.q.extend(keep)


def make_real_bench(cfg: Config | None = None) -> Bench:
    cfg = cfg or load()
    arms = {r: LeRobotArmBus(r, PORTS[r], cfg) for r in ("pourer", "transfer")}
    return Bench(arms=arms, mega=SerialMegaLink(PORTS["mega"], int(cfg.at("link.baud"))),
                 clock=RealClock(), backend="real", sim=None)
