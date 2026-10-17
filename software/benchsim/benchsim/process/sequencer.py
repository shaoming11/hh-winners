"""Process sequencer: runs a validated list of Steps (benchsim.process.steps) on any backend.

Explicit states: IDLE -> PRECHECK -> RUNNING -> DONE, or -> SAFE_STOP / FAILED. Every step has a timeout. A stop
request (operator, e-stop fault, timeout, failed check) is honoured at the next safe point and runs the safe-stop
path: the Mega is told to STOP (auger off, servos hold), a tilted pouring arm is brought back upright over its
receiver when it can be, arm torque stays ON, and a gripper that holds a beaker is never opened. Remaining steps
are reported as skipped with the reason.

Skills (the step implementations) are injected, so the same sequencer drives the simulator and the hardware.
A skill is a callable skill(step, ctx) -> dict(measured=..., target=..., detail=...) that raises StepFailed or
StopRequested. ``ctx`` gives access to the backends, the clock, the stop flag and the logger.
"""
import time
import traceback

import numpy as np

from .steps import validate


class StepFailed(RuntimeError):
    def __init__(self, code, detail='', measured=None):
        super().__init__('%s: %s' % (code, detail)); self.code = code; self.detail = detail; self.measured = measured or {}


class StopRequested(RuntimeError):
    pass


TIMEOUT_S = dict(TRANSFER=120.0, POUR_TO_SCALE=150.0, POUR_TO_FUNNEL=120.0, CAROUSEL=30.0, DOSE_YEAST=150.0, VERIFY_MASS=150.0,
                 WAIT=None, STAGE=20.0)


class Context:
    """what a skill sees: backends, clock, stop flag, logging, shared process state (beaker locations, masses)"""

    def __init__(self, bench, runlog, trace_dt=0.1):
        self.bench = bench; self.clock = bench.clock; self.mega = bench.mega; self.arms = bench.arms
        self.runlog = runlog; self.stop_reason = None
        self.state = dict(beakers={}, masses={}, active_arm=None, pouring=None, contents_g={}, tare_g={}, stage='WORK')
        self.deadline = None; self.trace = []; self.trace_dt = trace_dt; self._next_trace = 0.0; self.events = []
        self.on_tick_hooks = []

    def log(self, kind, **kw):
        self.events.append(dict(t=round(self.clock.now(), 3), kind=kind, **kw))

    def request_stop(self, reason):
        if self.stop_reason is None: self.stop_reason = reason; self.log('stop_requested', reason=reason)

    def tick(self):
        """called by skills at safe points and from motion loops: traces, faults, deadline, stop requests"""
        now = self.clock.now()
        if now >= self._next_trace:
            self._next_trace = now + self.trace_dt
            row = dict(t=round(now, 3))
            for a, arm in self.arms.items(): row[a] = np.round(np.degrees(arm.read_positions()), 2).tolist()
            s = self.mega.last_sample; row['scale_g'] = None if s is None else s['w']
            self.trace.append(row)
        for h in self.on_tick_hooks: h()
        self.mega._pump()
        if self.mega.faults: self.request_stop('mega fault %s' % self.mega.faults[-1].get('fault'))
        if self.deadline is not None and now > self.deadline: self.request_stop('step timeout')
        if self.stop_reason is not None: raise StopRequested(self.stop_reason)


class Sequencer:
    def __init__(self, bench, skills, runlog, safe_stop=None, precheck=None):
        self.bench = bench; self.skills = skills; self.runlog = runlog; self.safe_stop_fn = safe_stop; self.precheck_fn = precheck
        self.state = 'IDLE'; self.ctx = Context(bench, runlog)

    def run(self, steps, source='preset', text=None, approved_by='operator (sim)'):
        ok, problems = validate(steps)
        self.runlog.set_protocol(source, steps, dict(ok=ok, problems=problems), text=text, approved_by=approved_by if ok else None)
        rows = []
        if not ok:
            self.state = 'FAILED'
            for i, st in enumerate(steps): rows.append(self._row(i, st, 'skipped', 'protocol failed validation: %s' % '; '.join(problems)))
            return self._finish(rows)
        self.state = 'PRECHECK'
        try:
            if self.precheck_fn: self.precheck_fn(self.ctx)
        except Exception as e:
            self.state = 'FAILED'
            for i, st in enumerate(steps): rows.append(self._row(i, st, 'skipped', 'precheck failed: %s' % e))
            return self._finish(rows)
        self.state = 'RUNNING'; failed = None
        for i, st in enumerate(steps):
            if failed is not None:
                rows.append(self._row(i, st, 'skipped', 'not run: %s' % failed)); continue
            t0 = self.ctx.clock.now(); to = TIMEOUT_S.get(st.type)
            if st.type == 'WAIT': to = st.params.get('seconds', 0) + 30.0
            self.ctx.deadline = t0 + to if to else None
            self.ctx.log('step_start', index=i + 1, type=st.type, label=st.label)
            try:
                res = self.skills[st.type](st, self.ctx) or {}
                rows.append(self._row(i, st, 'passed', res.get('detail', ''), t0, res))
                self.ctx.log('step_done', index=i + 1, status='passed')
            except StopRequested as e:
                failed = 'safe stop: %s' % e; rows.append(self._row(i, st, 'failed', failed, t0)); self.state = 'SAFE_STOP'
                self._safe_stop(str(e))
            except StepFailed as e:
                failed = '%s: %s' % (e.code, e.detail); rows.append(self._row(i, st, 'failed', failed, t0, dict(measured=e.measured)))
                self.state = 'SAFE_STOP'; self._safe_stop(failed)
            except Exception as e:
                failed = 'error: %r' % e; rows.append(self._row(i, st, 'failed', failed + '\n' + traceback.format_exc(limit=3), t0))
                self.state = 'SAFE_STOP'; self._safe_stop(failed)
            finally:
                self.ctx.deadline = None
        if failed is None: self.state = 'DONE'
        return self._finish(rows)

    def _safe_stop(self, reason):
        self.ctx.log('safe_stop', reason=reason)
        stop = self.ctx.stop_reason; self.ctx.stop_reason = None            # allow the recovery motions to tick
        try:
            try: self.ctx.mega.command('STOP')
            except Exception as e: self.ctx.log('safe_stop_mega_error', error=str(e))
            if self.safe_stop_fn: self.safe_stop_fn(self.ctx, reason)
        except Exception as e:
            self.ctx.log('safe_stop_error', error=repr(e))
        finally:
            self.ctx.stop_reason = stop or reason

    def _row(self, i, st, status, reason, t0=None, res=None):
        res = res or {}
        r = dict(index=i + 1, type=st.type, label=st.label, params=st.params, status=status, reason=reason,
                 t_start=None if t0 is None else round(t0, 3), t_end=round(self.ctx.clock.now(), 3) if t0 is not None else None,
                 target=res.get('target', {}), measured=res.get('measured', {}), faults=[f for f in self.ctx.mega.faults])
        self.runlog.step(**r); return r

    def _finish(self, rows):
        return dict(state=self.state, steps=rows, passed=sum(r['status'] == 'passed' for r in rows),
                    failed=sum(r['status'] == 'failed' for r in rows), skipped=sum(r['status'] == 'skipped' for r in rows))
