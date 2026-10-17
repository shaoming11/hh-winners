"""Drives the benchsim bench for the backend.

One bench, one thread.  Everything that steps the world - the run, direct hardware commands, the idle nudge -
happens on a single "bench" thread, because benchsim renders the camera from a world frame hook and MuJoCo's GL
context deadlocks (blocks forever in make_current, no exception) the moment a second thread renders.  HTTP
threads never touch the world: they queue a job and wait for its result, or raise a flag.

The run is `benchsim.process.sequencer.Sequencer`, the steps are `benchsim.process.steps`, and the live view is
`benchsim.dashboard.feed.Feed` - the same feed the dashboard has always rendered.  Every feed snapshot is also
projected into `ExperimentState` (backend/project.py) and written to the Store, so the dashboard and the agents
read the same poll of the same bench.

PAUSE blocks inside the frame hook; SAFE_STOP goes through `ctx.request_stop`, the sequencer's own path, which
holds torque and never opens a gripper on a held beaker.
"""
from __future__ import annotations

import io
import json
import queue
import sys
import threading
import time
import traceback
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
if str(SOFTWARE / "benchsim") not in sys.path:
    sys.path.insert(0, str(SOFTWARE / "benchsim"))     # before `software/`, or the namespace dir shadows it

from backend import project
from backend.schemas import (HardwareCommand, HardwareReply, Plan as PlanSchema, PlanStep, Recipe,
                             RunPlanCmd, RunState, StepState, Validation, now_iso)
from backend.store import Store
from backend.watchdog import Watchdog

BUILD_TIMEOUT_S = 300.0
JOB_TIMEOUT_S = 180.0


class _Job:
    """work for the bench thread; the caller waits on `done`"""

    def __init__(self, fn, name=""):
        self.fn = fn
        self.name = name
        self.done = threading.Event()
        self.result = None
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self.result = self.fn()
        except BaseException as e:  # noqa: BLE001 - carried to the caller, never kills the loop
            self.error = e
        finally:
            self.done.set()


class BenchRunner:
    PUBLISH_DT = 0.2          # bench seconds between feed snapshots (the Feed throttles on this)
    QA_DT = 0.5               # wall seconds between watchdog evaluations
    IDLE_WALL_DT = 0.25       # wall seconds between idle nudges
    IDLE_STEP_S = 0.05        # bench seconds advanced per idle nudge
    SPEEDS = (0.5, 1.0, 2.0, 4.0, 8.0)

    def __init__(self, store: Store, cfg=None, backend: str = "sim", seed: int = 0,
                 render: bool = True, realtime: float = 1.0, out_root: Path | None = None,
                 dev: bool = False, record: bool = True):
        self.store = store
        self.cfg = cfg
        self.backend = backend
        self.seed = seed
        self.render = render
        self.realtime = float(realtime)
        self.dev = dev
        self.record = record
        self.wd = Watchdog(store, cfg) if cfg is not None else None
        from benchsim.dashboard.server import Hub
        self.hub = Hub()                      # feed/1 JSON + JPEG, for the dashboard's /events and /stream.mjpg
        self.b = None                         # the benchsim bench (BenchBackends)
        self.run_obj = None                   # DemoRun / DevRun
        self.feed = None
        self.video = None
        self.pacer = None
        self.phase = "building"               # building -> ready -> running -> finished
        self.paused = False
        self._stop_request: str | None = None
        self._jobs: queue.Queue[_Job] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._closing = False
        self._next_qa_wall = 0.0
        self._current_step: str | None = None
        self._run_steps: list = []
        self._out_root = out_root
        self._mech_fallback = None

    # ================================================================== lifecycle
    def connect(self) -> None:
        """start the bench thread and wait for the first build"""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="bench", daemon=True)
            self._thread.start()
        if not self._ready.wait(BUILD_TIMEOUT_S):
            raise TimeoutError("bench did not finish building")

    def close(self) -> None:
        self._closing = True

    def running(self) -> bool:
        return self.phase == "running"

    # ------------------------------------------------------------------ the one thread
    def _loop(self) -> None:
        try:
            self._build()
        except BaseException as e:  # noqa: BLE001
            self.store.event("fault", f"bench build failed: {type(e).__name__}: {e}", level="error")
            self.store.update(lambda s: s.__setattr__("mode", "error"))
            self._ready.set()
            return
        while not self._closing:
            try:
                job = self._jobs.get(timeout=self.IDLE_WALL_DT)
            except queue.Empty:
                self._idle()
                continue
            job.run()

    def _submit(self, fn, name="", timeout=JOB_TIMEOUT_S):
        """queue work for the bench thread and wait; re-raises what it raised"""
        job = _Job(fn, name)
        self._jobs.put(job)
        if not job.done.wait(timeout):
            raise TimeoutError(f"{name or 'job'} did not finish in {timeout:.0f} s")
        if job.error is not None:
            raise job.error
        return job.result

    def _build(self) -> None:
        """construct the bench, the feed and the camera (bench thread only)"""
        from benchsim.dashboard.feed import Feed
        from benchsim.dashboard.runner import Pacer, make_run
        from benchsim.dashboard.twin import Twin
        from benchsim.dashboard.video import Video
        self.phase = "building"
        self.paused = False
        self._stop_request = None
        self._current_step = None
        out_root = self._out_root or (SOFTWARE / "out" / "backend" / "runs")
        self.run_obj = r = make_run(out_root, self.seed, dev=self.dev)
        self.b = r.bb
        w = r.bb.world
        self.pacer = Pacer(r.bb.clock, self.realtime if self.realtime > 0 else 0.0)
        probes = dict(r.probes, runner=self._info)
        if self.render:
            self.video = Video(self.hub, camera="auto", fps=15.0)
            self.video.snapshot = lambda: self.feed.last if self.feed else None
            probes["video"] = lambda: dict(camera=self.video.camera, shown=self.video.shown,
                                           cameras=self.video.cameras())
        twin = Twin(w.m) if w is not None else None
        self.feed = Feed(r.bb, self._publish_snap, ledger=r.ledger, twin=twin, probes=probes).attach(r.seq)
        self.feed.plan(r.steps)
        r.seq.ctx.on_tick_hooks.append(self._gate)
        if w is not None:
            w.frame_hooks += [self._gate, self.pacer]
            if self.video is not None:
                self.video.attach(w)
        self.store.update(lambda s: (s.__setattr__("backend", self.backend), s.__setattr__("mode", "idle"),
                                     s.media.__setattr__("live_stream_url", "/stream.mjpg")))
        self.store.event("state", f"bench connected ({self.backend}, benchsim)")
        self.phase = "ready"
        self.feed.flush()
        self._ready.set()

    def _idle(self) -> None:
        """between runs nothing steps the world, so nothing would publish, QA-check or render"""
        if self.b is None or self.phase == "running":
            return
        try:
            self.b.clock.sleep(self.IDLE_STEP_S)
            # The Mega's comm watchdog latches a WDT fault if the host goes quiet for 500 ms, and
            # faults only reach the host when the client pumps.  heartbeat() does both, which is why
            # benchsim's own idle loops call it.
            self.b.mega.heartbeat()
            if self.video is not None:
                self.video.idle()
            self.feed.flush()
        except Exception as e:  # noqa: BLE001
            self.store.event("log", f"idle tick error ({type(e).__name__}: {e})", level="warning")
            time.sleep(2.0)

    def _info(self) -> dict:
        """probes.runner - what the dashboard's header and speed buttons read"""
        return dict(name=getattr(self.run_obj, "name", "benchsim"), phase=self.phase,
                    speed=self.pacer.speed if self.pacer else self.realtime,
                    rtf=self.pacer.rtf if self.pacer else None,
                    out=str(self.run_obj.rl.dir) if self.run_obj is not None else "")

    # ------------------------------------------------------------------ hooks
    def _gate(self, *a) -> None:
        """pause / safe-stop, on the thread that is stepping the world.  Only BenchFault-equivalent
        stops may raise out of a hook, so a stop goes through the sequencer's own request_stop."""
        ctx = self.run_obj.seq.ctx if self.run_obj is not None else None
        if self._stop_request and ctx is not None and ctx.stop_reason is None:
            reason, self._stop_request = self._stop_request, None
            ctx.request_stop(reason)
        if self.paused:
            self.store.update(lambda s: s.__setattr__("mode", "paused"))
            while self.paused and not self._closing:
                time.sleep(0.05)
                if self._stop_request and ctx is not None and ctx.stop_reason is None:
                    reason, self._stop_request = self._stop_request, None
                    ctx.request_stop(reason)
                    break
            if self.running():
                self.store.update(lambda s: s.__setattr__("mode", "running"))

    def _publish_snap(self, snap: dict) -> None:
        """the Feed's publish callback: the dashboard's view and the agents' view, from one poll"""
        self.hub.publish(snap)
        try:
            self._project(snap)
        except Exception as e:  # noqa: BLE001 - never break the feed over a projection bug
            self.store.event("log", f"projection error ({type(e).__name__}: {e})", level="warning")
        now = time.monotonic()
        if self.wd is not None and now >= self._next_qa_wall:
            self._next_qa_wall = now + self.QA_DT
            try:
                self.wd.evaluate(self.store.snapshot())
            except Exception as e:  # noqa: BLE001
                self.store.event("log", f"watchdog error ({type(e).__name__}: {e})", level="warning")

    def _project(self, snap: dict) -> None:
        seq = getattr(self.run_obj, "seq", None)
        locations = (seq.ctx.state.get("beakers") if seq is not None else None) or {}
        p = project.project(snap, self.b, getattr(self.run_obj, "ledger", None), locations)
        rows = project.steps_from(snap)
        pending = any(a.status == "pending" for a in self.store.approvals.values())
        mode = project.mode_from(snap, awaiting_approval=pending, paused=self.paused,
                                 run_active=self.phase == "running")

        def upd(s):
            s.arms, s.mega, s.scale = p.arms, p.mega, p.scale
            s.vessels, s.chemistry, s.bench_t = p.vessels, p.chemistry, p.bench_t
            if s.run is None or s.run.finished_at is not None:
                if s.mode not in ("complete", "safe_stop", "error") or s.run is None:
                    s.mode = mode
                return
            s.mode = mode
            s.run.bench_seconds = p.bench_t
            cur = snap.get("current") or {}
            by_index = {r["index"]: r for r in rows}
            for st in s.run.steps:
                r = by_index.get(st.index)
                if r is None:
                    continue
                st.status, st.detail, st.type = r["status"], r["detail"], r["type"]
                if st.index == cur.get("index"):
                    s.run.current_step = st.index - 1
                    if st.t0 is None:
                        st.t0 = p.bench_t
            done = sum(1 for st in s.run.steps if st.status in ("ok", "skipped"))
            s.run.progress = round(done / max(1, len(s.run.steps)), 3)
        self.store.update(upd)

    def _publish(self) -> None:
        """force one snapshot now (tests and the direct-command path)"""
        if self.feed is not None:
            self._submit(self.feed.flush, "flush", timeout=30.0)

    # ------------------------------------------------------------------ camera
    def render_rgb(self, camera: str, timeout: float = 30.0):
        return self._submit(lambda: self.video.r.frame(self.b.world.d, camera), f"render {camera}", timeout)

    def snapshot_jpeg(self, camera: str = "overview") -> bytes | None:
        if self.video is None:
            return self.hub.jpeg
        if camera in ("", "auto", self.video.shown):
            return self.hub.jpeg

        def shoot():
            from PIL import Image
            rgb = self.video.r.frame(self.b.world.d, camera)
            buf = io.BytesIO()
            Image.fromarray(rgb).save(buf, "JPEG", quality=self.video.quality)
            return buf.getvalue()
        try:
            return self._submit(shoot, f"snapshot {camera}", timeout=30.0)
        except Exception:  # noqa: BLE001
            return self.hub.jpeg

    # app.py's MJPEG route reads these; the Hub is the real store
    @property
    def frames(self) -> dict:
        return {"overview": self.hub.jpeg} if self.hub.jpeg else {}

    @property
    def frame_version(self) -> int:
        return self.hub.jpeg_ver

    @property
    def frame_cond(self):
        return self.hub.cond

    # ================================================================== plans
    def _steps_from_plan(self, plan: PlanSchema):
        from benchsim.process import steps as S
        return [S.Step(st.type, dict(st.params), st.label) for st in plan.steps]

    @staticmethod
    def select(steps, only: list[str] | None):
        """`only` picks a subset of the plan by label token.  Tokens are resolved to whole labels first:
        a bare startswith lets "1" also match "10 ERUPT" (it did once).  The subset is validated like any
        other plan, so asking for a step whose precondition was dropped is refused, not run blind."""
        if not only:
            return list(steps), []
        wanted, unknown = [], []
        for tok in only:
            t = str(tok).strip()
            hits = [s for s in steps if s.label == t or s.label.split(" ")[0] == t or s.type == t]
            if not hits:
                hits = [s for s in steps if s.label.startswith(t)]
            if not hits:
                unknown.append(t)
            wanted += [s for s in hits if s not in wanted]
        return [s for s in steps if s in wanted], unknown

    def preset_plan(self, recipe: Recipe | None = None) -> PlanSchema:
        from benchsim.process import steps as S
        r = recipe or Recipe()
        steps = S.demo_protocol(dict(developer_g=r.developer_g, developer_tol_g=2.0, yeast_g=r.yeast_g,
                                     yeast_tol_g=0.7, water_g=r.water_g, water_tol_g=2.0,
                                     activate_wait_s=r.activate_s))
        return PlanSchema(title="elephant toothpaste (preset)", source="preset",
                          steps=[PlanStep(type=s.type, params=s.params, label=s.label) for s in steps])

    def validate_plan(self, plan: PlanSchema) -> Validation:
        """benchsim.process.steps.validate is the only gate; it is imported, never re-implemented"""
        from benchsim.process.steps import validate
        ok, problems = validate(self._steps_from_plan(plan))
        n = len(plan.steps)
        summary = f"{n} steps, all checks passed" if ok else f"{n} steps, {len(problems)} problem(s)"
        return Validation(ok=ok, problems=list(problems), summary=summary)

    # ================================================================== runs
    def start_run(self, cmd: RunPlanCmd) -> HardwareReply:
        if self.b is None:
            return HardwareReply(id=cmd.id, ok=False, err="NOT_CONNECTED", message="bench not connected")
        if self.running():
            return HardwareReply(id=cmd.id, ok=False, err="BUSY", message="a run is already active")
        if self.phase == "finished":
            return HardwareReply(id=cmd.id, ok=False, err="STATE",
                                 message="the bench has already run; reset it before starting another run")
        plan = cmd.plan or self.preset_plan(cmd.recipe)
        if cmd.only:
            picked, unknown = self.select(self._steps_from_plan(plan), cmd.only)
            if unknown:
                tokens = [s.label.split(" ")[0] for s in self._steps_from_plan(plan)]
                return HardwareReply(id=cmd.id, ok=False, err="VALIDATION",
                                     message=f"no steps match {unknown}; tokens are {tokens}")
            plan = plan.model_copy(update={"steps": [PlanStep(type=s.type, params=s.params, label=s.label)
                                                     for s in picked]})
        validation = self.validate_plan(plan)
        if not validation.ok:
            self.store.event("command", f"plan rejected by validator: {'; '.join(validation.problems)}",
                             level="warning", source=cmd.source, data={"plan": plan.model_dump()})
            return HardwareReply(id=cmd.id, ok=False, err="VALIDATION", message="; ".join(validation.problems),
                                 data={"validation": validation.model_dump()})
        if not cmd.approved:
            req = self.store.request_approval("run_plan", cmd.model_dump(),
                                              f"run '{plan.title}' - {validation.summary}", cmd.source,
                                              person=getattr(cmd, "requested_by", "") or cmd.operator or "")
            self.store.update(lambda s: s.__setattr__("mode", "awaiting_approval"))
            return HardwareReply(id=cmd.id, ok=False, err="NEEDS_APPROVAL",
                                 message="plan is valid; an operator must approve before anything moves",
                                 data={"request_id": req.id, "validation": validation.model_dump()})
        steps = self._steps_from_plan(plan)
        run_id = time.strftime("%Y%m%d_%H%M%S")
        from benchsim.dashboard import narration
        rows = [StepState(index=i + 1, name=s.label or s.type, type=s.type, params=dict(s.params),
                          narration=_narrate(narration, s))
                for i, s in enumerate(steps)]
        asker = getattr(cmd, "requested_by", "") or ""
        rs = RunState(run_id=run_id, backend=self.backend, started_at=now_iso(), operator=cmd.operator,
                      protocol_text=cmd.protocol_text, plan=plan, validation=validation,
                      recipe=cmd.recipe or Recipe(), approved_by=cmd.operator or cmd.source,
                      approved_at=now_iso(), steps=rows, outcome="running", requested_by=asker)
        if self.wd is not None:
            self.wd.reset()
        self._run_steps = steps
        self.store.update(lambda s: (s.__setattr__("run", rs), s.__setattr__("mode", "running")))
        who = cmd.operator or cmd.source
        if asker and asker != cmd.operator:
            who = f"{who} (requested by {asker})"
        self.store.event("command", f"run {run_id} started: {plan.title} ({plan.source}); operator {who}",
                         source=cmd.source, run_id=run_id, data={"requested_by": asker})
        self.feed.plan(steps)
        self._jobs.put(_Job(lambda: self._do_run(cmd, plan, rs, steps), f"run-{run_id}"))
        return HardwareReply(id=cmd.id, ok=True, message="run started", data={"run_id": run_id})

    def _do_run(self, cmd: RunPlanCmd, plan: PlanSchema, rs: RunState, steps) -> None:
        """on the bench thread"""
        self.phase = "running"
        self.paused = False
        self.pacer.reset()
        self.feed.flush()
        out = None
        try:
            approver = cmd.operator or cmd.source or "operator"
            asker = getattr(cmd, "requested_by", "") or ""
            out = self.run_obj.seq.run(steps, source=plan.source, text=cmd.protocol_text or None,
                                       approved_by=approver if not asker or asker == approver
                                       else f"{approver} (requested by {asker})")
            self.run_obj.finish(out)
        except Exception as e:  # noqa: BLE001
            self.store.event("fault", f"run thread crashed: {type(e).__name__}: {e}\n{traceback.format_exc()}",
                             level="error", run_id=rs.run_id)
            self.store.update(lambda s: (s.__setattr__("mode", "error"),
                                         s.run and s.run.__setattr__("outcome", "SAFE_STOP")))
            return
        finally:
            self.phase = "finished"
            self.feed.flush()
        self._record(rs, out)

    def _record(self, rs: RunState, out: dict) -> None:
        seq = self.run_obj.seq
        state = seq.state
        outcome = {"DONE": "complete", "SAFE_STOP": "SAFE_STOP", "FAILED": "aborted"}.get(state, state)
        reason = seq.ctx.stop_reason
        faults = [reason] if reason else []
        doses = {}
        for row in (out or {}).get("steps", []):
            m = row.get("measured") or {}
            if isinstance(m, dict) and m.get("target") is not None:
                doses[row.get("label") or row.get("type")] = {
                    "target": m.get("target"), "actual": m.get("measured") or m.get("actual")}
        snap = self.feed.last or {}
        foam = (snap.get("probes") or {}).get("foam") or {}
        if foam.get("peak_mm") is not None:
            doses["foam_peak_mm"] = foam["peak_mm"]
        run_dir = self.run_obj.rl.dir

        def upd(s):
            if s.run is None:
                return
            s.run.doses = doses
            s.run.faults = faults
            s.run.outcome = outcome
            s.run.finished_at = now_iso()
            s.run.notebook_html = f"/runs/{run_dir.name}/"
            for st in s.run.steps:
                if st.status == "running":
                    st.status = "fault" if state in ("SAFE_STOP", "FAILED") else "ok"
                    st.detail = reason or ""
            s.run.progress = round(sum(1 for st in s.run.steps if st.status in ("ok", "skipped"))
                                   / max(1, len(s.run.steps)), 3)
            s.mode = "complete" if state == "DONE" else ("safe_stop" if state == "SAFE_STOP" else "error")
        self.store.update(upd)
        self.store.event("state", f"run {rs.run_id} {outcome} after {self.b.clock.now():.0f} s bench time",
                         level="info" if outcome == "complete" else "error", run_id=rs.run_id,
                         data={"doses": doses, "faults": faults, "dir": str(run_dir)})
        if self.wd is not None:
            for f in faults:
                self.wd.on_fault(f, self._current_step)
        self.store.load_history()
        self._current_step = None

    # ================================================================== control
    def control(self, action: str, by: str = "operator") -> HardwareReply:
        rid = f"ctl-{int(time.time() * 1000)}"
        if action == "pause":
            if not self.running():
                return HardwareReply(id=rid, ok=False, err="STATE", message="no run to pause")
            self.paused = True
            self.store.event("command", f"pause requested by {by}")
            return HardwareReply(id=rid, ok=True, message="pausing at the next physics step")
        if action == "resume":
            self.paused = False
            self.store.event("command", f"resume by {by}")
            return HardwareReply(id=rid, ok=True, message="resumed")
        if action in ("safe_stop", "abort"):
            if not self.running():
                return HardwareReply(id=rid, ok=True, message="nothing running")
            self._stop_request = f"{action} requested by {by}"
            self.paused = False
            self.store.event("command", f"{action} requested by {by}", level="warning")
            return HardwareReply(id=rid, ok=True,
                                 message="safe stop will run at the next safe point (torque stays on, grippers closed)")
        if action == "reset":
            if self.running():
                return HardwareReply(id=rid, ok=False, err="BUSY", message="stop the run first")
            if self.backend != "sim":
                return HardwareReply(id=rid, ok=False, err="STATE",
                                     message="reset is sim-only; on hardware clear the fault and re-home by hand")
            run_id = self.store.state.run.run_id if self.store.state.run else None
            self.store.resolve_alerts(run_id=run_id)
            self.store.update(lambda s: (s.__setattr__("run", None), s.__setattr__("mode", "idle")))
            self._ready.clear()
            self._submit(self._build, "rebuild", timeout=BUILD_TIMEOUT_S)
            self.store.event("command", f"bench reset by {by}")
            return HardwareReply(id=rid, ok=True, message="fresh bench; reagents reloaded")
        if action == "speed":
            return HardwareReply(id=rid, ok=False, err="VALIDATION", message="use set_speed(x)")
        return HardwareReply(id=rid, ok=False, err="UNKNOWN", message=f"unknown action {action}")

    def set_speed(self, x: float, by: str = "operator") -> HardwareReply:
        rid = f"spd-{int(time.time() * 1000)}"
        if x not in self.SPEEDS:
            return HardwareReply(id=rid, ok=False, err="RANGE",
                                 message="speed must be one of " + ", ".join("%g" % v for v in self.SPEEDS))
        self.realtime = x
        if self.pacer is not None:
            self.pacer.set_speed(x)
        return HardwareReply(id=rid, ok=True, message=f"speed {x:g}x")

    def set_camera(self, name: str) -> HardwareReply:
        rid = f"cam-{int(time.time() * 1000)}"
        if self.video is None:
            return HardwareReply(id=rid, ok=False, err="STATE", message="rendering is off")
        if not self.video.set_camera(name):
            return HardwareReply(id=rid, ok=False, err="RANGE", message=f"unknown camera {name}")
        if self.phase != "running":
            self._jobs.put(_Job(lambda: (self.video.idle(), self.feed.flush()), "camera"))
        return HardwareReply(id=rid, ok=True, message=f"camera: {name}")

    # ================================================================== direct commands
    MOTION_KINDS = {"carousel", "stage", "auger", "arm_goals", "gripper", "arm_station"}

    def command(self, cmd: HardwareCommand, approved: bool = False) -> HardwareReply:
        if cmd.kind == "run_plan":
            return self.start_run(cmd)
        if cmd.kind == "run_control":
            return self.control(cmd.action, by=f"{cmd.source}:{cmd.note or '-'}")
        if cmd.kind == "approval":
            return self.decide(cmd.request_id, cmd.decision, cmd.by)
        if self.b is None:
            return HardwareReply(id=cmd.id, ok=False, err="NOT_CONNECTED", message="bench not connected")
        # Every direct command needs the world to advance - even a Mega PING, because the simulated
        # device only answers in its next pre_step.  While a run holds the bench thread (running, or
        # paused inside a frame hook mid-step) nothing else may step it, so refuse at once rather
        # than queue a job that cannot run.  run_control is handled above and is always allowed.
        if self.running() or self.paused:
            return HardwareReply(id=cmd.id, ok=False, err="BUSY",
                                 message="a run is active; stop it before commanding the bench by hand"
                                         if not self.paused else
                                         "the run is paused mid-step; resume or safe-stop it first")
        if cmd.kind in self.MOTION_KINDS:
            if cmd.source == "agent" and not approved:
                req = self.store.request_approval("hardware_command", cmd.model_dump(), _brief(cmd), cmd.source,
                                                  person=getattr(cmd, "requested_by", "") or "")
                return HardwareReply(id=cmd.id, ok=False, err="NEEDS_APPROVAL",
                                     message="a human must approve this motion",
                                     data={"request_id": req.id})
        self.store.event("command", _brief(cmd), source=cmd.source, data={"kind": cmd.kind})
        try:
            data = self._submit(lambda: (self._execute(cmd), self.feed.flush())[0], cmd.kind)
        except TimeoutError as e:
            return HardwareReply(id=cmd.id, ok=False, err="TIMEOUT", message=str(e))
        except Exception as e:  # noqa: BLE001
            self.store.event("fault", f"{cmd.kind} failed: {type(e).__name__}: {e}", level="error", source=cmd.source)
            # the bench raises plain ValueErrors; map the ones that carry a contract code onto it
            msg = str(e).upper()
            code = next((c for c in ("RANGE", "REJECTED", "ESTOP", "BUSY", "STATE", "TIMEOUT", "VALIDATION")
                         if c in msg), "INTERNAL")
            return HardwareReply(id=cmd.id, ok=False, err=code, message=f"{type(e).__name__}: {e}")
        self.store.event("reply", f"{cmd.kind} ok", source="backend", data=_jsonable(data))
        return HardwareReply(id=cmd.id, ok=True, message=f"{cmd.kind} ok", data=_jsonable(data))

    def _mech(self):
        """the run's own Mechanisms, so the deck angle and pocket bookkeeping a hand command changes
        are the ones the run will read next.  A fresh Mechanisms would assume deck 0 and the initial
        pockets, and mis-time the next move."""
        d = getattr(self.run_obj, "d", None)
        mech = getattr(d, "mech", None)
        if mech is not None:
            return mech
        from benchsim.mechanisms import Mechanisms
        if self._mech_fallback is None:
            self._mech_fallback = Mechanisms(self.b.mega)
        return self._mech_fallback

    def _execute(self, cmd) -> dict:
        """on the bench thread"""
        import numpy as np
        b = self.b
        m = self._mech()
        if cmd.kind == "carousel":
            rec = m.turn_deck(float(cmd.deg))
            return {"carousel_deg": rec.get("reported_deg", cmd.deg)}
        if cmd.kind == "stage":
            if cmd.position:
                return m.stage_to(cmd.position)
            b.mega.motion("ST", cmd.ms / 1000.0 + 5.0, deg=float(cmd.deg), ms=int(cmd.ms))
            return {"stage_deg": cmd.deg}
        if cmd.kind == "auger":
            return m.auger(float(cmd.rev))
        if cmd.kind == "mega":
            if cmd.cmd == "hb":
                b.mega.heartbeat()
                return {"hb": True}
            return dict(b.mega.command(cmd.cmd.upper()))
        if cmd.kind == "stream":
            return dict(b.mega.command("STREAM", on=bool(cmd.on)))
        if cmd.kind == "tare":
            b.mega.command("TARE")
            return {"tared": True}
        if cmd.kind == "arm_torque":
            b.arms[cmd.role].set_torque(bool(cmd.on))
            return {"torque": cmd.on}
        if cmd.kind == "arm_goals":
            from benchsim.state import ARM_JOINTS
            bad = [k for k in cmd.goals if k not in ARM_JOINTS]
            if bad:
                raise ValueError(f"REJECTED: unknown joints {bad}; joints are {list(ARM_JOINTS)}")
            arm = b.arms[cmd.role]
            q = np.array(arm.read_positions(), float)
            for k, v in cmd.goals.items():
                q[ARM_JOINTS.index(k)] = np.radians(float(v))
            # the arm's own check reports the whole vector; name the joint that is actually out of range
            lo, hi = (b.world.m.actuator_ctrlrange[arm.aid, 0], b.world.m.actuator_ctrlrange[arm.aid, 1])
            for i, j in enumerate(ARM_JOINTS):
                if not (lo[i] - 1e-9 <= q[i] <= hi[i] + 1e-9):
                    raise ValueError("RANGE: %s=%.1f deg outside [%.1f, %.1f]"
                                     % (j, np.degrees(q[i]), np.degrees(lo[i]), np.degrees(hi[i])))
            arm.set_goal(q)
            b.clock.sleep(float(cmd.duration_s))
            return {"q_deg": [round(float(np.degrees(v)), 2) for v in arm.read_positions()]}
        if cmd.kind == "gripper":
            from benchsim.layout import load_params
            from benchsim.process.motion import gripper_to
            g = load_params()["gripper"]
            deg = g["open_deg"] if cmd.action == "open" else g["contact_deg_td"]
            gripper_to(b.arms[cmd.role], float(np.radians(deg)), b.clock)
            return {"gripper_deg": deg, "holding": (b.world.held or {}).get(cmd.role) if b.world else None}
        raise ValueError(f"unsupported command {cmd.kind}")

    def simulate_estop(self, pressed: bool) -> dict:
        """Sim only: the e-stop is a world flag, as a finger on the button is - the Mega latches ESTOP in
        its next pre_step and the host sees it on its next pump.  Setting the flag is immediate even
        mid-run (that is the point of an e-stop); the step+pump is only queued when nothing else is
        driving the world, because during a run the run is already stepping it."""
        w = getattr(self.b, "world", None) if self.b is not None else None
        if w is None:
            return {"ok": False, "message": "sim only"}
        w.estop = bool(pressed)
        if self.phase != "running":
            def settle():
                self.b.clock.sleep(0.05)
                self.b.mega.heartbeat()
                self.feed.flush()
            try:
                self._submit(settle, "estop", timeout=30.0)
            except Exception as e:  # noqa: BLE001
                return {"ok": True, "estop": bool(pressed), "warning": f"{type(e).__name__}: {e}"}
        return {"ok": True, "estop": bool(pressed), "faults": sorted(getattr(self.b.mega_device, "faults", []))}

    # ================================================================== approvals
    def decide(self, request_id: str, decision: str, by: str) -> HardwareReply:
        from pydantic import TypeAdapter
        req = self.store.decide(request_id, decision, by)
        rid = f"apr-{request_id}"
        if req is None:
            return HardwareReply(id=rid, ok=False, err="STATE", message="no such pending request")
        if decision != "approve":
            if self.store.state.mode == "awaiting_approval" and not any(
                    a.status == "pending" for a in self.store.approvals.values()):
                self.store.update(lambda s: s.__setattr__("mode", "idle"))
            return HardwareReply(id=rid, ok=True, message=f"rejected by {by}")
        payload = dict(req.payload)
        if req.kind == "run_plan":
            payload["approved"] = True
            requester = payload.get("requested_by") or payload.get("operator") or payload.get("source") or "?"
            payload["requested_by"] = requester        # the asker survives the overwrite below
            payload["operator"] = by                   # the human who approved, not who asked
            payload["note"] = (f"requested by {requester}; " + (payload.get("note") or "")).strip("; ")
            rep = self.start_run(TypeAdapter(HardwareCommand).validate_python(payload))
        else:
            rep = self.command(TypeAdapter(HardwareCommand).validate_python(payload), approved=True)
        rep.message = f"approved by {by}; " + (rep.message or "ok")
        return rep

    # ================================================================== the dashboard's control verbs
    def feed_control(self, cmd: str, by: str = "operator (dashboard)") -> tuple[bool, str]:
        """POST /api/<cmd> from the dashboard page: start | stop | reset | speed/<x> | camera/<name>"""
        if cmd == "start":
            if self.phase != "ready":
                return False, f"cannot start while {self.phase} (reset first)"
            rep = self.start_run(RunPlanCmd(id=f"dash-{int(time.time() * 1000)}", source="frontend",
                                            operator=by, approved=True,
                                            note="started from the dashboard by the operator at the bench"))
            return rep.ok, rep.message
        if cmd == "stop":
            rep = self.control("safe_stop", by=by)
            return rep.ok, rep.message
        if cmd == "reset":
            if self.phase in ("running", "building"):
                return False, f"cannot reset while {self.phase}"
            rep = self.control("reset", by=by)
            return rep.ok, rep.message
        if cmd.startswith("speed/"):
            try:
                x = float(cmd.split("/", 1)[1])
            except ValueError:
                return False, "speed must be a number"
            rep = self.set_speed(x, by=by)
            return rep.ok, rep.message
        if cmd.startswith("camera/"):
            rep = self.set_camera(cmd.split("/", 1)[1])
            return rep.ok, rep.message
        return False, f"unknown command {cmd}"


def _narrate(narration, step) -> dict | None:
    """friendly prose for one step, from benchsim's own narration (pure: a Step dict in, words out).
    Reusing it keeps one source of wording for the dashboard caption and the agent's sentences."""
    try:
        return narration.describe(step.to_dict() if hasattr(step, "to_dict") else dict(step))
    except Exception:  # noqa: BLE001 - prose is never worth failing a run over
        return None


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if hasattr(o, "tolist"):
        return _jsonable(o.tolist())
    if isinstance(o, float):
        return o if o == o and o not in (float("inf"), float("-inf")) else None
    if o is None or isinstance(o, (str, int, bool)):
        return o
    return str(o)


def _brief(cmd) -> str:
    d = cmd.model_dump()
    skip = {"v", "id", "source", "note", "kind"}
    args = ", ".join(f"{k}={v}" for k, v in d.items() if k not in skip and v is not None)
    return f"{cmd.kind}({args})" + (f" - {cmd.note}" if cmd.note else "")
