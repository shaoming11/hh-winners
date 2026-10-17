"""Runs a protocol for the dashboard on the main thread (MuJoCo's offscreen renderer on macOS wants that thread).

A "run" object owns one bench, one Sequencer and the protocol: ``bb, seq, steps, name, ledger, probes, run(),
finish(out)``. The full demo comes from ``benchsim.demo_run`` once that module lands (see ``make_run``). Until then
``DevRun`` gives a 3-step development protocol (P1 carousel -> scale, verify empty, back), built the way
tests/test_sequencer.py builds its sequencer. Nothing here fakes a step.

HTTP threads only queue commands (start / reset) or raise the stop flag. Everything is acted on in this thread; the
stop flag becomes ``ctx.request_stop`` inside a tick or frame hook, so the sequencer's own safe-stop path runs.
"""
import queue
import time

from .. import paths, poses, runlog, state
from ..bench import make_bench
from ..layout import load_params
from ..process import sequencer, skills
from ..process import steps as S
from .feed import Feed

OUT = paths.RUNS / 'dashboard'
DEV_PROTOCOL = [S.Step('TRANSFER', dict(beaker='P1', src='carousel_pick', dst='scale_pan'), '1 P1 carousel -> scale'),
                S.Step('VERIFY_MASS', dict(beaker='P1', target_g=0.0, tol_g=0.5), '2 P1 is empty'),
                S.Step('TRANSFER', dict(beaker='P1', src='scale_pan', dst='carousel_pick'), '3 P1 -> carousel')]


class DevRun:
    name = 'development protocol (3 steps): the full demo runner is not merged yet'

    def __init__(self, out_root=OUT, seed=0):
        params = load_params(); self.bb = bb = make_bench('sim', seed=seed); planner = poses.Planner(bb.world.m, bb.world.b)

        class Plans:
            def transfer(self, b, s, d): return planner.plan_transfer(b, s, d)
        sk = skills.make_skills(bb, Plans(), params['gripper'], state.park_q(), params)

        def pre(ctx): bb.mega.command('STREAM', on=True); bb.mega.command('TARE')
        self.rl = runlog.RunLog(out_root, 'sim', seed=seed)
        self.seq = sequencer.Sequencer(bb, sk, self.rl, safe_stop=skills.safe_stop(bb, state.park_q()), precheck=pre)
        self.steps = DEV_PROTOCOL; self.ledger = None; self.probes = {}

    def run(self):
        return self.seq.run(self.steps)

    def finish(self, out):
        return self.rl.finish(dict(passed=out['passed'], failed=out['failed'], skipped=out['skipped']), events=self.seq.ctx.events)


def make_run(out_root=OUT, seed=0):
    return DevRun(out_root, seed)


class Pacer:
    """frame hook: hold sim time to wall time x speed (speed 0 = as fast as possible). ``rtf`` is the real-time factor
    since the run started, so planning pauses (no physics while IK runs) show up honestly but do not make it jump"""

    def __init__(self, clock, speed=1.0):
        self.clock = clock; self.speed = speed; self.rtf = None; self.reset()

    def reset(self):
        self.t0 = self.clock.now(); self.w0 = time.monotonic(); self._start = (self.w0, self.t0)

    def __call__(self, w=None):
        now_w = time.monotonic(); now_s = self.clock.now()
        if now_w - self._start[0] >= 1.0: self.rtf = round((now_s - self._start[1]) / (now_w - self._start[0]), 2)
        if not self.speed: return
        ahead = (now_s - self.t0) / self.speed - (now_w - self.w0)
        if ahead > 0.004: time.sleep(ahead)
        elif ahead < -0.5: self.t0 = now_s; self.w0 = now_w           # fell behind: carry on, do not sprint to catch up


class Runner:
    """phases: ready -> running -> finished (-> reset -> ready)"""

    def __init__(self, hub, make_run=make_run, speed=1.0, video=None, out_root=OUT, seed=0):
        self.hub = hub; self.make_run = make_run; self.speed = speed; self.video = video; self.out_root = out_root; self.seed = seed
        self.cmds = queue.Queue(); self.stop_flag = False; self.phase = 'building'; self.result = None; self.run_obj = None

    # ------------------------------------------------------------------ called from HTTP threads
    def control(self, cmd):
        if cmd == 'start':
            if self.phase != 'ready': return False, 'cannot start while %s (reset first)' % self.phase
            self.phase = 'starting'; self.cmds.put('start'); return True, 'starting'
        if cmd == 'stop':
            if self.phase not in ('running', 'starting'): return False, 'nothing is running'
            self.stop_flag = True; return True, 'stop requested; the sequencer stops at its next safe point'
        if cmd == 'reset':
            if self.phase in ('running', 'starting', 'building'): return False, 'cannot reset while %s' % self.phase
            self.phase = 'building'; self.cmds.put('reset'); return True, 'rebuilding the bench'
        if cmd.startswith('camera/'):
            name = cmd.split('/', 1)[1]
            if self.video is None or not self.video.set_camera(name): return False, 'unknown camera %s' % name
            return True, 'camera: %s' % name
        return False, 'unknown command %s' % cmd

    # ------------------------------------------------------------------ main thread
    def _stop_hook(self, *a):
        ctx = self.run_obj.seq.ctx
        if self.stop_flag and ctx.stop_reason is None: ctx.request_stop('operator stop (dashboard)')

    def _info(self):
        return dict(name=self.run_obj.name, phase=self.phase, speed=self.speed, rtf=self.pacer.rtf, out=str(self.run_obj.rl.dir))

    def build(self):
        self.phase = 'building'; self.stop_flag = False; self.result = None
        r = self.run_obj = self.make_run(self.out_root, self.seed); bb = r.bb
        self.pacer = Pacer(bb.clock, self.speed)
        probes = dict(r.probes, runner=self._info)
        if self.video is not None:
            self.video.snapshot = lambda: self.feed.last
            probes['video'] = lambda: dict(camera=self.video.camera, shown=self.video.shown, cameras=self.video.cameras())
        self.feed = Feed(bb, self.hub.publish, ledger=r.ledger, probes=probes).attach(r.seq)
        self.feed.plan(r.steps)
        r.seq.ctx.on_tick_hooks.append(self._stop_hook)
        if bb.world is not None:
            bb.world.frame_hooks += [self._stop_hook, self.pacer]
            if self.video is not None: self.video.attach(bb.world)
        self.phase = 'ready'; self.feed.flush()

    def _start(self):
        self.phase = 'running'; self.pacer.reset(); self.feed.flush()
        try:
            self.result = out = self.run_obj.run()
            self.run_obj.finish(out)
        finally:
            self.phase = 'finished'; self.feed.flush()

    def loop(self, max_idle_s=None):
        """serve commands until 'quit' (or max_idle_s without one, for tests)"""
        self.build(); idle_since = time.monotonic()
        while True:
            try: cmd = self.cmds.get(timeout=0.5)
            except queue.Empty:
                self.feed.flush()
                if self.video is not None: self.video.idle()
                if max_idle_s is not None and time.monotonic() - idle_since > max_idle_s: return
                continue
            if cmd == 'quit': return
            if cmd == 'start': self._start()
            elif cmd == 'reset': self.build()
            idle_since = time.monotonic()
