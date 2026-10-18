"""The physical bench behind the backend, with the sim as its mirror and its tape recorder.

Modes (WLB_BACKEND):

    sim       the sim bench only (the default).  A hardware replay runs replay_plan.py's real driver code on
              emulated USB devices that ARE the displayed world (backends/emu.py).
    usb       the real bench: both SO-101 buses and the Mega over USB (ports WLB_MEGA / WLB_POURER / WLB_TRANSFER,
              replay_plan.py's defaults otherwise).  The displayed sim world becomes a MIRROR: its arms follow the
              servos' measured angles, its carousel and sled follow the Mega, and the scale shown is the real one.
    usb-fake  usb with the hardware replaced by a second, hidden sim world behind emulated USB - the whole usb path
              (read-only link, going live, mirror, recorder) without a bench.  For testing.

The link opens READ-ONLY (dry run: every servo goal, torque write and TT/ST/AUG line is refused), so starting the
backend never moves or drops an arm - LeRobotArm.connect in live mode would switch torque off.  It goes live only
for the duration of an approved replay, and back to read-only afterwards.

Every replay is recorded: runs/<run_id>/telemetry.jsonl (one line per sample: measured joint angles, commanded
goals, carousel/sled angles, scale grams, the subgoal being played) and runs/<run_id>/run.json (the RunState with
its steps, subgoals and checks).  ``Playback`` plays a recording back into the sim world, timeline and checks
included, so a real run can be watched again in the sim.
"""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import numpy as np

USB_MODES = ("usb", "usb-fake")
SAMPLE_S = 0.05                  # mirror / recorder sample period (hardware seconds): 20 Hz


def smoothstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def follow_q(measured, commanded):
    """what a sim arm should be driven to so it does what the hardware arm did: the five arm joints where the
    encoders say they are, the gripper where it was COMMANDED.  A gripper closed on a beaker stops at the beaker, so
    its measured angle says 'holding still', while the sim only latches a beaker in the jaws when the jaw is being
    driven closed (SimArm.post_step) - the command is what carries the grasp across"""
    q = np.array(measured, float)
    if commanded is not None:
        q[5] = float(commanded[5])
    return q


def _raw(arm):
    """the backend arm under the dashboard's TappedArm (mirror goals are not bus writes, so not wire lines)"""
    return getattr(arm, "_arm", arm)


# ====================================================================== clocks
class WallClock:
    def now(self): return time.monotonic()

    def sleep(self, dt):
        if dt > 0: time.sleep(dt)


class PacedSimClock:
    """usb-fake: the hidden plant's time, held to the wall clock so it behaves like hardware"""

    def __init__(self, sim_clock):
        self.c = sim_clock; self.t0 = sim_clock.now(); self.w0 = time.monotonic()

    def now(self): return self.c.now()

    def sleep(self, dt):
        if dt <= 0: return
        self.c.sleep(dt)
        ahead = (self.c.now() - self.t0) - (time.monotonic() - self.w0)
        if ahead > 0: time.sleep(ahead)
        elif ahead < -1.0: self.t0, self.w0 = self.c.now(), time.monotonic()   # fell behind: do not try to catch up


class TickClock:
    """the clock replay_plan and the MegaClient wait on during a replay: the hardware's time, and every wait is cut
    into <= SAMPLE_S slices with ``tick`` (mirror + recorder) run between them"""

    TICK_EVERY_S = 0.5                    # a mirror tick costs >= 0.25 s on the real bench (world step + render): at most
                                          # twice a second, so the replay's waits stay waits and the arms are never held up

    def __init__(self, inner, tick):
        self.inner = inner; self.tick = tick; self.t_tick = -1e9

    def now(self): return self.inner.now()

    def sleep(self, dt):
        t_end = self.inner.now() + dt
        while True:
            left = t_end - self.inner.now()
            if left <= 0: return              # exactly 0, not "close enough": replay_plan.nap loops until left <= 0
            self.inner.sleep(min(left, SAMPLE_S))
            if self.inner.now() - self.t_tick >= self.TICK_EVERY_S and t_end - self.inner.now() > 0.3:
                self.t_tick = self.inner.now(); self.tick()   # only when the wait has room for it


# ====================================================================== the link
class HardwareLink:
    """the bench's devices, opened read-only; ``live(True)`` for an approved replay"""

    def __init__(self, mode: str, calibration_path, params):
        self.mode = mode; self.cal = calibration_path; self.P = params
        self.hw = None; self.clock = None; self.plant = None; self.is_live = False; self._raw_t = None; self._dry_t = None

    def open(self):
        from benchsim.bench import make_bench
        if self.mode == "usb":
            ports = dict(port_mega=os.environ.get("WLB_MEGA", "/dev/cu.usbserial-1130"),
                         port_pourer=os.environ.get("WLB_POURER", "/dev/cu.usbmodem58760435221"),
                         port_transfer=os.environ.get("WLB_TRANSFER", "/dev/cu.usbmodem58CD1767761"))
            self.hw = make_bench("real", allow_hardware=True, calibration_path=self.cal, dry_run=True, **ports)
            self.clock = WallClock()
            time.sleep(2.5)                         # opening the CH340 port resets the Mega: let it boot
            try: self.hw.transport.read_lines()
            except Exception: pass                  # noqa: E701
        elif self.mode == "usb-fake":
            from benchsim.backends.emu import make_emulated_bench
            self.plant = make_bench("sim")
            self.hw = make_emulated_bench(self.plant, self.cal, dry_run=True, share_mega_log=False)
            self.clock = PacedSimClock(self.plant.clock)
        else:
            raise ValueError(f"not a hardware mode: {self.mode}")
        self.hw.mega.clock = self.clock
        self._dry_t = self.hw.mega.t
        self._raw_t = getattr(self._dry_t, "inner", self._dry_t)
        return self

    def live(self, on: bool):
        """dry run off (on=True) or back on; the arms keep whatever torque state the replay left them in"""
        for a in self.hw.arms.values():
            a.dry_run = not on
            # replay_plan closes the buses when it ends (right for the script, which opened them); the backend keeps
            # its link open between replays, so that close is a no-op while it holds the link
            if on: a.disconnect = lambda: None
            else: a.__dict__.pop("disconnect", None)
        self.hw.mega.t = self._raw_t if on else self._dry_t
        self.is_live = on

    def describe(self) -> str:
        return {"usb": "the real bench over USB", "usb-fake": "a hidden simulated bench behind emulated USB"}[self.mode]


# ====================================================================== the mirror
class Mirror:
    """the displayed sim world follows the hardware.  Arm goals = measured joint angles (the sim's grasp physics then
    carries the beakers the way the real gripper did); carousel and sled = the Mega's reported angles, animated
    along each TT/ST move the host sent; the scale shown = the real scale's last sample."""

    def __init__(self, sim_bb, link: HardwareLink):
        self.link = link; self.hw = link.hw; self.recorder = None
        self.q = {}; self.axis = {"TT": None, "ST": None}; self.moves = {}
        self.t_last = -1e9; self.t_world = None
        self.bind(sim_bb)
        self._watch_mega()
        try:
            r = self.hw.mega.command("PING")
            self.axis = {"TT": r.get("tt"), "ST": r.get("st")}
        except Exception:  # noqa: BLE001 - no Mega: the axes simply are not mirrored
            pass

    def bind(self, sim_bb):
        """(re)attach to the displayed world - after every rebuild"""
        self.sim = sim_bb; self.w = sim_bb.world; self.dev = sim_bb.mega_device; self.t_world = None
        for a in sim_bb.arms.values():
            if not _raw(a).torque_enabled(): _raw(a).set_torque(True)

    def _watch_mega(self):
        mega = self.hw.mega; send = mega.send

        def watched(cmd, **args):
            seq = send(cmd, **args)
            if cmd in ("TT", "ST") and "deg" in args:
                frm = self.axis.get(cmd)
                self.moves[cmd] = dict(t0=self.link.clock.now(), frm=frm if frm is not None else float(args["deg"]),
                                       to=float(args["deg"]), dur=max(float(args.get("ms", 1000)) / 1000.0, 1e-3), seq=seq)
            return seq
        mega.send = watched

    def _axis_deg(self, ax, now):
        mv = self.moves.get(ax)
        if mv is None: return self.axis.get(ax)
        for r in self.hw.mega.replies.get(mv["seq"], []):
            if r.get("done") and r.get("deg") is not None:
                self.axis[ax] = float(r["deg"]); self.moves.pop(ax, None); return self.axis[ax]
            if "err" in r:
                self.moves.pop(ax, None); return self.axis.get(ax)
        s = smoothstep((now - mv["t0"]) / mv["dur"])
        return mv["frm"] + (mv["to"] - mv["frm"]) * s

    def tick(self, force=False):
        now = self.link.clock.now()
        if not force and now - self.t_last < SAMPLE_S:
            return
        self.t_last = now
        for name, a in self.hw.arms.items():
            try:
                self.q[name] = np.asarray(a.read_positions(), float)
            except Exception:  # noqa: BLE001 - a dropped status packet: keep the last angles
                pass
        try:
            self.hw.mega._pump()
        except Exception:  # noqa: BLE001
            pass
        m = self.w.m
        for name, q in self.q.items():
            ha = self.hw.arms[name]; g = getattr(ha, "_goal", None)
            q = follow_q(q, ha.map.ticks_to_q(g) if g is not None and hasattr(ha, "map") and ha.torque_enabled() else None)
            sa = _raw(self.sim.arms[name])
            lo, hi = m.actuator_ctrlrange[sa.aid, 0], m.actuator_ctrlrange[sa.aid, 1]
            if not sa.torque_enabled(): sa.set_torque(True)
            sa.set_goal(np.clip(q, lo, hi), speed_scale=1.0)
        for ax, act in (("TT", self.dev.tt_act), ("ST", self.dev.st_act)):
            d = self._axis_deg(ax, now)
            if d is not None and self.dev.motion is None:
                self.w.d.ctrl[act] = math.radians(d)
        if self.hw.mega.last_sample is not None:
            self.sim.mega.last_sample = self.hw.mega.last_sample
        # the displayed world keeps pace with the hardware (never more than 0.25 s per tick)
        if self.t_world is None:
            self.t_world = now
        dt = min(now - self.t_world, 0.25)
        self.t_world = now
        if dt > 0:
            self.w.advance(dt)
        if self.recorder is not None:
            self.recorder.sample(q=self.q)

    def faults(self):
        return list(self.hw.mega.faults)


# ====================================================================== the recorder
class Recorder:
    """runs/<run_id>/telemetry.jsonl while a replay plays; run.json when it ends"""

    def __init__(self, run_dir: Path, hw, sim_bb, now, store, mode: str):
        self.dir = Path(run_dir); self.dir.mkdir(parents=True, exist_ok=True)
        self.f = open(self.dir / "telemetry.jsonl", "w")
        self.hw, self.sim, self.now, self.store, self.mode = hw, sim_bb, now, store, mode
        self.t_last = -1e9; self.n = 0
        self.f.write(json.dumps(dict(schema="wlb.telemetry/1", mode=mode, started=time.strftime("%Y-%m-%dT%H:%M:%S"))) + "\n")

    def sample(self, q=None, force=False):
        t = self.now()
        if not force and t - self.t_last < SAMPLE_S:
            return
        self.t_last = t
        rec = dict(t=round(t, 3), q={}, goal={})
        for name, a in self.hw.arms.items():
            try:
                qq = q[name] if q and name in q else np.asarray(a.read_positions(), float)
                rec["q"][name] = [round(math.degrees(v), 2) for v in qq]
            except Exception:  # noqa: BLE001
                pass
            g = getattr(a, "_goal", None)
            if g is not None and hasattr(a, "map"):
                rec["goal"][name] = [round(math.degrees(v), 2) for v in a.map.ticks_to_q(g)]
        dev = getattr(self.sim, "mega_device", None)
        if dev is not None:
            rec["tt"] = round(dev.tt_deg(), 2); rec["st"] = round(dev.st_deg(), 2)
        s = getattr(self.hw.mega, "last_sample", None) if getattr(self.hw, "mega", None) is not None else None
        if s is not None:
            rec["w"] = round(float(s["w"]), 2)
        run = self.store.state.run
        if run is not None and run.current_subgoal:
            rec["sub"] = run.current_subgoal
        self.f.write(json.dumps(rec) + "\n"); self.n += 1
        if self.n % 40 == 0:
            self.f.flush()

    def close(self, run_state):
        try:
            self.sample(force=True)
        finally:
            self.f.close()
        (self.dir / "run.json").write_text(run_state.model_dump_json(indent=1) if run_state is not None else "{}")


def list_recordings(runs_dir: Path) -> list[dict]:
    out = []
    for d in sorted(Path(runs_dir).glob("*/telemetry.jsonl"), reverse=True):
        run = {}
        try:
            run = json.loads((d.parent / "run.json").read_text())
        except (OSError, ValueError):
            pass
        try:
            head = json.loads(d.open().readline())
        except (OSError, ValueError):
            head = {}
        out.append(dict(run_id=d.parent.name, mode=head.get("mode"), started=head.get("started"),
                        outcome=run.get("outcome"), steps=[s.get("name") for s in run.get("steps", [])],
                        failed_checks=len(run.get("faults", [])), bench_seconds=run.get("bench_seconds"),
                        telemetry=f"/runs/{d.parent.name}/telemetry.jsonl"))
    return out


# ====================================================================== playback
class Playback:
    """a recording played back into the sim world: the arms follow the recorded angles (so the sim's grasp physics
    and liquids redo what the recording implies), the carousel and sled follow the recorded axes, and the run's
    steps, subgoals and checks change status at the times they did in the recording"""

    def __init__(self, run_dir: Path):
        self.dir = Path(run_dir)
        lines = (self.dir / "telemetry.jsonl").read_text().splitlines()
        self.head = json.loads(lines[0]) if lines else {}
        self.samples = [json.loads(x) for x in lines[1:] if x.strip()]
        if not self.samples:
            raise ValueError(f"{self.dir.name}: no samples recorded")
        self.run = json.loads((self.dir / "run.json").read_text()) if (self.dir / "run.json").exists() else {}
        self.t0 = self.samples[0]["t"]; self.t1 = self.samples[-1]["t"]

    def status_at(self, T: float) -> dict:
        """the recorded run as it stood T seconds into the recording (absolute recording time)"""
        r = json.loads(json.dumps(self.run))
        cur = None
        faults = []
        for i, st in enumerate(r.get("steps", [])):
            t0, t1 = st.get("t0"), st.get("t1")
            final = st.get("status")
            if t1 is not None and T >= t1:
                st["status"] = final
            elif t0 is not None and T >= t0:
                st["status"] = "running"; cur = i
            else:
                st["status"] = "pending"
            for sg in st.get("subgoals", []):
                s0, s1 = sg.get("t0"), sg.get("t1")
                if s1 is not None and T >= s1:
                    if sg.get("status") in ("failed",) or sg.get("code") in ("DOSE_ERROR", "SCALE_DISTURBED"):
                        faults.append(f"{st['name']}: {sg['name']}: {sg.get('result', '')}")
                elif s0 is not None and T >= s0:
                    sg["status"] = "running"; sg["result"] = ""
                else:
                    sg["status"] = "pending"; sg["result"] = ""
        r["current_step"] = cur
        r["faults"] = faults
        r["bench_seconds"] = round(min(T, self.t1) - self.t0, 2)
        done = sum(1 for st in r.get("steps", []) if st["status"] in ("ok", "fault"))
        r["progress"] = round(done / max(1, len(r.get("steps", []))), 3)
        if cur is not None:
            sub = next((sg for sg in reversed(r["steps"][cur].get("subgoals", [])) if sg["status"] == "running"), None)
            r["current_subgoal"] = f"{r['steps'][cur]['name']} / {sub['name']}" if sub else None
        else:
            r["current_subgoal"] = None
        return r

    def play(self, sim_bb, on_status, gate=None):
        """on the bench thread; ``on_status(T)`` every ~0.2 s of recording time"""
        w = sim_bb.world; m = w.m; dev = sim_bb.mega_device
        arms = {n: _raw(a) for n, a in sim_bb.arms.items()}
        for a in arms.values():
            if not a.torque_enabled(): a.set_torque(True)
        w0 = w.time; next_status = -1e9
        for s in self.samples:
            target = w0 + (s["t"] - self.t0)
            while w.time < target - 1e-9:
                w.advance(min(SAMPLE_S, target - w.time))
            for name, qd in (s.get("q") or {}).items():
                a = arms.get(name)
                if a is None: continue
                gd = (s.get("goal") or {}).get(name)
                q = follow_q(np.radians(qd), np.radians(gd) if gd is not None else None)
                lo, hi = m.actuator_ctrlrange[a.aid, 0], m.actuator_ctrlrange[a.aid, 1]
                a.set_goal(np.clip(q, lo, hi), speed_scale=1.0)
            if s.get("tt") is not None and dev.motion is None: w.d.ctrl[dev.tt_act] = math.radians(s["tt"])
            if s.get("st") is not None and dev.motion is None: w.d.ctrl[dev.st_act] = math.radians(s["st"])
            if s["t"] >= next_status:
                next_status = s["t"] + 0.2
                on_status(s["t"])
        on_status(self.t1 + 1e6)
