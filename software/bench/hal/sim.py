"""HAL backend over the MuJoCo world.  Same interfaces as bench.hal.real, different plumbing.

Time: the sim only advances when something waits on it - `clock.sleep()` or pulling the next
weight sample from `mega.samples()` - so control loops written against these interfaces run
identically on hardware, where those calls block on real time and real serial lines.
"""
from __future__ import annotations

import math
from typing import Iterator

from bench.config import Config, load
from bench.hal import protocol
from bench.hal.base import ARM_JOINTS, Bench, BenchFault
from sim.world import World


class SimClock:
    def __init__(self, world: World):
        self.w = world

    def now(self) -> float:
        return self.w.t

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.w.step_time(seconds)


class SimArmBus:
    """Six STS3215s on one bus, as the sim sees them.

    The grasp weld latches when the jaw is commanded closed and has travelled to within a few
    degrees of contact with a beaker inside the finger capture region; a close onto nothing
    simply reaches its goal with no load - the same signature the real classifier looks for.
    """

    def __init__(self, world: World, role: str):
        self.w = world
        self.role = role
        self.goals: dict[str, float] = world.arm_qpos_deg(role)
        self.torque = True
        self._close_cmd_t: float | None = None
        world.hooks.append(self._tick)

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def read_positions(self) -> dict[str, float]:
        return self.w.arm_qpos_deg(self.role)

    def read_load(self) -> dict[str, float]:
        return self.w.arm_load(self.role)

    JAW_RATE_DPS = 150.0          # an STS3215 jaw takes ~0.3 s for 45 deg; the raw MJCF servo
                                  # would snap it in 50 ms and punt the beaker out of the jaws

    def write_goals(self, goals: dict[str, float]) -> None:
        if not self.torque:
            return
        self.goals.update(goals)
        arm_goals = {k: v for k, v in goals.items() if k != "gripper"}
        if arm_goals:
            self.w.set_arm_goals_deg(self.role, arm_goals)
        if "gripper" in goals:
            closing = self._is_closing(goals["gripper"])
            if closing and self.w.held[self.role] is None:
                # latch when the finger reaches the contact angle (see _tick)
                self._close_cmd_t = self.w.t
            elif not closing:
                self._close_cmd_t = None
                if self.w.held[self.role] is not None:
                    self._pending_release = True

    _pending_release = False

    def set_torque(self, on: bool) -> None:
        self.torque = on

    # --- internals
    def _is_closing(self, goal_deg: float) -> bool:
        contact = self.w.jaw_contact_deg()
        opn = self.w.jaw_open_deg()
        return abs(goal_deg - contact) < abs(goal_deg - opn)

    def _tick(self) -> None:
        # rate-limited jaw servo
        a = self.w.aid[f"{self.role}_gripper"]
        goal = math.radians(self.goals.get("gripper", math.degrees(self.w.d.ctrl[a])))
        step = math.radians(self.JAW_RATE_DPS) * self.w.dt
        cur = float(self.w.d.ctrl[a])
        self.w.d.ctrl[a] = cur + max(-step, min(step, goal - cur))
        if self._close_cmd_t is not None and self.w.held[self.role] is None:
            q_deg = math.degrees(self.w.d.qpos[self.w.qadr[f"{self.role}_gripper"]])
            at_contact = q_deg <= self.w.jaw_contact_deg() + 0.8      # closing = decreasing q
            if at_contact or self.w.t - self._close_cmd_t >= 0.6:
                # the finger has reached the beaker surface: the fin-ray grasp forms here.
                # grasp() latches the weld + jaw lock if a beaker is between the fingers;
                # otherwise the jaw simply carries on to its goal (a miss)
                self.w.grasp(self.role)
                self._close_cmd_t = None
        if self._pending_release:
            self.w.release(self.role)
            self._pending_release = False


class SimMegaLink:
    """The Arduino Mega, as a JSON-line peer, over the world's scale and hobby servos."""

    def __init__(self, world: World, cfg: Config | None = None):
        self.w = world
        self.cfg = cfg or load()
        self.streaming = False
        self.fault: str | None = None
        self._done: list[dict] = []
        self._pending: dict[str, int] = {}     # mechanism -> command id awaiting "done"
        self._auger_rev_reported = 0.0
        self._consumed = 0
        self._stall_sim: float = 0.0           # for fault-injection tests
        world.hooks.append(self._tick)

    def connect(self) -> None:
        pass

    # ---- host -> mega
    def command(self, obj: dict) -> dict:
        cid = obj.get("id", protocol.next_id())
        err = protocol.validate(obj)
        if err:
            return {"id": cid, "ok": False, "err": err}
        c = obj["cmd"]
        if self.fault and c not in ("clr", "status", "ver", "stop", "weight", "stream", "hb", "estop_test"):
            return {"id": cid, "ok": False, "err": "ESTOP" if self.fault == "ESTOP" else "STATE"}
        if c == "ver":
            return {"id": cid, "ok": True, "fw": "WLB-MEGA v1 (sim)", "hx_hz": self.w.scale_rate}
        if c == "weight":
            ms, g = self.w.samples[-1] if self.w.samples else (int(self.w.t * 1000), self.w.scale_grams_raw())
            return {"id": cid, "ok": True, "g": round(g, 3), "ms": ms}
        if c == "stream":
            self.streaming = bool(obj.get("on", True))
            self._consumed = self.w.n_samples
            return {"id": cid, "ok": True}
        if c == "hb":
            return {"id": cid, "ok": True}
        if c == "status":
            return {"id": cid, "ok": True, "estop": self.w.estop_pressed, "fault": self.fault,
                    "carousel_deg": round(self.w.carousel_deg(), 2),
                    "stage_deg": round(self.w.stage_deg(), 2),
                    "auger_rev": round(self.w.auger_pos_rev(), 3),
                    "busy": [k for k in ("carousel", "stage") if self.w.servo_busy(k)]
                            + (["auger"] if self.w.auger_busy() else [])}
        if c == "stop":
            self.w.moves.clear(); self.w.auger_active = False
            self.w.d.ctrl[self.w.aid["auger"]] = 0.0
            return {"id": cid, "ok": True}
        if c == "clr":
            if self.w.estop_pressed:
                return {"id": cid, "ok": False, "err": "ESTOP"}
            self.fault = None
            return {"id": cid, "ok": True}
        if c == "estop_test":
            self.w.estop_pressed = bool(obj.get("pressed", True))
            if self.w.estop_pressed:
                self._raise("ESTOP")
            return {"id": cid, "ok": True}
        if c in ("carousel", "stage"):
            if self.w.servo_busy(c) or self.w.auger_busy():
                return {"id": cid, "ok": False, "err": "BUSY"}
            # absolute angles, exactly like the hobby servos (an M45CHW has a 270 deg window;
            # the run only uses 0 / +90 / -90)
            tgt = math.radians(float(obj["deg"]))
            self.w.servo_move(c, tgt, obj["ms"] / 1000.0)
            self._pending[c] = cid
            return {"id": cid, "ok": True}
        if c == "auger":
            if self.w.servo_busy("carousel") or self.w.servo_busy("stage") or self.w.auger_busy():
                return {"id": cid, "ok": False, "err": "BUSY"}
            rev = float(obj["rev"]); d = int(obj.get("dir", 1 if rev >= 0 else -1))
            self.w.auger_start(abs(rev), d)
            self._auger_rev_reported = self.w.auger_pos_rev()
            self._pending["auger"] = cid
            return {"id": cid, "ok": True}
        return {"id": cid, "ok": False, "err": "UNKNOWN"}

    # ---- mega -> host
    def samples(self) -> Iterator[dict]:
        """Yield the next weight sample, advancing the sim to produce it.  Fault lines and
        completion notices are interleaved, exactly as they arrive on the serial port."""
        if not self.streaming:
            self.command({"cmd": "stream", "on": True})
        period = 1.0 / self.w.scale_rate
        while True:
            while self._done:
                yield self._done.pop(0)
            while self.w.n_samples <= self._consumed:
                self.w.step_time(period)
            behind = self.w.n_samples - self._consumed
            if behind > len(self.w.samples):          # fell off the ring: skip forward
                self._consumed = self.w.n_samples - len(self.w.samples)
                behind = len(self.w.samples)
            ms, g = self.w.samples[len(self.w.samples) - behind]
            self._consumed += 1
            yield {"w": [ms, round(float(g), 3)]}

    def drain(self) -> list[dict]:
        out, self._done = self._done, []
        return out

    def flush(self) -> None:
        """A host that stopped listening (an arm move) must not read a backlog of old weight
        samples when it resumes: skip to the newest.  Completion/fault notices are kept."""
        self._consumed = self.w.n_samples

    # ---- internals
    def _raise(self, code: str) -> None:
        if self.fault is None:
            self.fault = code
            self._done.append({"f": code})
            self.w.events.append((self.w.t, f"FAULT {code}"))

    def _tick(self) -> None:
        for mech in ("carousel", "stage"):
            if mech in self._pending and not self.w.servo_busy(mech):
                self._done.append({"done": self._pending.pop(mech)})
        if "auger" in self._pending:
            # deliver yeast as the screw turns (forward only), then report completion
            now = self.w.auger_pos_rev()
            d = now - self._auger_rev_reported
            if d > 0.05:
                self.w.auger_deliver(d)
                self._auger_rev_reported = now
            elif d < -0.05:
                self._auger_rev_reported = now
            if not self.w.auger_busy():
                self._done.append({"done": self._pending.pop("auger"),
                                   "rev": round(self.w.auger_rev_done, 3)})
        if self.w.estop_pressed:
            self._raise("ESTOP")


def make_sim_bench(cfg: Config | None = None, seed: int = 0, **world_kw) -> Bench:
    cfg = cfg or load()
    world = World(cfg, seed=seed, **world_kw)
    arms = {r: SimArmBus(world, r) for r in ("pourer", "transfer")}
    return Bench(arms=arms, mega=SimMegaLink(world, cfg), clock=SimClock(world),
                 backend="sim", sim=world)
