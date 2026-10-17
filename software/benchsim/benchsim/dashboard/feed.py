"""Live feed of a sequencer run for the dashboard (shared contract ``benchsim.feed/1``).

``Feed(bench).attach(seq)`` hooks into ``seq.ctx.on_tick_hooks`` (every backend) and, in simulation, into
``world.frame_hooks`` as well, so the feed keeps moving during Mega motions that do not tick. Polls are throttled to
``rate_hz`` on ``timebase`` (wall clock by default). Nothing in the run is changed, except that the arms are wrapped in
``TappedArm`` so the commanded goals can be seen. A poll never raises into the run. A snapshot is JSON-able:

    {"schema", "t", "mode", "seq_state", "stop_reason",
     "steps":   [{"index", "label", "type", "status": pending|running|passed|failed|skipped, "reason"}],
     "current": {"index", "of", "type", "label", "params", "elapsed_s", "remaining_s", "scale_start_g", "narration"} | null,
     "scale":   {"g", "rate_hz"},
     "arms":    {name: {"q_deg", "goal_deg", "load_pm", "moving", "torque", "holding", "twin"?}},
     "vessels": {vessel: {species: g}} | null, "spilled_g", "probes": {...},
     "wire":    [{"id", "t", "dev", "dir": tx|rx|fault|bad, "text", "note"?}]   last WIRE_TAIL lines, ids increase
     "events":  [{"id", "t", "kind", ...}]                                     last EVENT_TAIL ctx events
     "faults":  [...], "errors": [str]}

Topology shown on the wire: the Mega lines are the exact JSON-lines protocol (benchsim.protocol, CRC included); arm
lines are what the laptop writes to each SO-101 servo bus (goals at most every ARM_LINE_S, torque changes always).
"""
import collections
import math
import time

import numpy as np

from .. import protocol
from ..process.steps import Step
from . import narration

SCHEMA = 'benchsim.feed/1'
WIRE_TAIL = 80
EVENT_TAIL = 40
ARM_LINE_S = 0.5
SAMPLE_LINE_S = 1.0


def deg(q):
    return None if q is None else [round(math.degrees(float(v)), 2) for v in q]


class TappedArm:
    """forwards everything to the backend arm (so ``hasattr(arm, 'goal')`` still reflects the backend) and records the
    last commanded goal plus the bus writes for the wire panel"""

    def __init__(self, arm, on_write):
        self._arm = arm; self._on_write = on_write; self.last_goal = None

    def __getattr__(self, k):
        return getattr(self._arm, k)

    def set_goal(self, q, speed_scale=1.0):
        self._arm.set_goal(q, speed_scale); self.last_goal = np.array(q, float)
        self._on_write(self._arm.name, 'goal', self.last_goal)

    def set_torque(self, enabled):
        self._arm.set_torque(enabled); self._on_write(self._arm.name, 'torque', bool(enabled))


class Feed:
    def __init__(self, bench, publish=None, rate_hz=10.0, timebase=time.monotonic, ledger=None, twin=None, probes=None):
        self.bench = bench; self.clock = bench.clock; self.mega = bench.mega; self.world = getattr(bench, 'world', None)
        self.publish = publish or (lambda snap: None); self.period = 1.0 / rate_hz; self.timebase = timebase
        self.ledger = ledger; self.twin = twin; self.probes = dict(probes or {})
        self.seq = None; self.planned = []; self.last = None; self._next = -1e18
        self.wire = collections.deque(maxlen=WIRE_TAIL); self._wire_id = 0; self._mega_cur = 0
        self._arm_line_t = {}; self._sample_line_t = -1e9; self._cur_index = None; self._scale_start = None
        self.errors = []
        for name, a in list(bench.arms.items()):
            if not isinstance(a, TappedArm): bench.arms[name] = TappedArm(a, self._arm_write)

    # ------------------------------------------------------------------ wiring into a run
    def plan(self, steps):
        """show the protocol before the run starts (Step objects or dicts)"""
        self.planned = [s.to_dict() if isinstance(s, Step) else dict(s) for s in steps]

    def attach(self, seq):
        self.detach(); self.seq = seq; self._mega_cur = len(self.mega.log)
        seq.ctx.on_tick_hooks.append(self.poll)
        if self.world is not None: self.world.frame_hooks.append(self._frame)
        return self

    def detach(self):
        if self.seq is not None and self.poll in self.seq.ctx.on_tick_hooks: self.seq.ctx.on_tick_hooks.remove(self.poll)
        if self.world is not None and self._frame in self.world.frame_hooks: self.world.frame_hooks.remove(self._frame)

    def _frame(self, w):
        self.poll()

    def poll(self):
        now = self.timebase()
        if now < self._next: return
        self._next = now + self.period; self.flush()

    def flush(self):
        """build and publish a snapshot now; never raises"""
        try:
            snap = self.snapshot()
        except Exception as e:
            self._error('feed: %r' % e); return self.last
        self.last = snap; self.publish(snap); return snap

    # ------------------------------------------------------------------ wire panel
    def _add_wire(self, dev, d, text, note=None):
        self._wire_id += 1; row = dict(id=self._wire_id, t=round(self.clock.now(), 3), dev=dev, dir=d, text=text)
        if note: row['note'] = note
        self.wire.append(row)

    def _arm_write(self, arm, kind, value):
        now = self.clock.now()
        if kind == 'torque': self._add_wire(arm, 'tx', 'torque %s' % ('ON' if value else 'OFF')); return
        if now - self._arm_line_t.get(arm, -1e9) < ARM_LINE_S: return
        self._arm_line_t[arm] = now
        self._add_wire(arm, 'tx', 'goal %s deg' % deg(value), note='streamed at 50 Hz, 1 line per %.1f s shown' % ARM_LINE_S)

    def _pump_mega(self):
        log = self.mega.log
        for entry in log[self._mega_cur:]:
            kind, msg = entry[0], entry[1]
            if kind == 'send': self._add_wire('mega', 'tx', protocol.encode(msg).strip())
            elif kind == 'reply': self._add_wire('mega', 'rx', protocol.encode(msg).strip())
            elif kind == 'fault': self._add_wire('mega', 'fault', protocol.encode(msg).strip())
            else: self._add_wire('mega', 'bad', str(msg), note=str(entry[2]) if len(entry) > 2 else None)
        self._mega_cur = len(log)
        s = self.mega.last_sample
        if s is not None and self.clock.now() - self._sample_line_t >= SAMPLE_LINE_S:
            self._sample_line_t = self.clock.now(); self._add_wire('mega', 'rx', protocol.encode(s).strip(), note='scale stream, 1 of 80 lines/s shown')

    # ------------------------------------------------------------------ snapshot
    def _protocol(self):
        p = self.seq.runlog.d.get('protocol') if self.seq is not None else None
        return (p or {}).get('steps') or self.planned

    def _steps(self, proto):
        rows = {r['index']: r for r in self.seq.runlog.d['steps']} if self.seq is not None else {}
        running = None
        if self.seq is not None:
            for e in reversed(self.seq.ctx.events):
                if e['kind'] == 'step_start':
                    running = e if e['index'] not in rows else None; break
        out = []
        for i, st in enumerate(proto, 1):
            r = rows.get(i)
            status = r['status'] if r else ('running' if running and running['index'] == i else 'pending')
            out.append(dict(index=i, label=st.get('label', ''), type=st['type'], status=status, reason=(r or {}).get('reason', '')))
        return out, running

    def _current(self, proto, running):
        if running is None: self._cur_index = None; return None
        i = running['index']; st = proto[i - 1]; now = self.clock.now(); s = self.mega.last_sample
        if self._cur_index != i: self._cur_index = i; self._scale_start = None if s is None else s['w']
        dl = self.seq.ctx.deadline
        return dict(index=i, of=len(proto), type=st['type'], label=st.get('label', ''), params=st.get('params', {}),
                    elapsed_s=round(now - running['t'], 2), remaining_s=None if dl is None else round(dl - now, 2),
                    scale_start_g=self._scale_start, narration=narration.describe(st))

    def _scale(self):
        s = self.mega.last_sample; rate = None; log = getattr(self.mega, 'sample_log', None)
        if log and log[-1][0] is not None:                  # samples in the last second of Mega time (t in ms)
            t_last = log[-1][0]; n = 0
            for row in reversed(log):
                if row[0] is None or t_last - row[0] > 1000: break
                n += 1
            rate = n
        return dict(g=None if s is None else round(float(s['w']), 2), rate_hz=rate)

    def _arms(self):
        held = getattr(self.world, 'held', {}) if self.world is not None else {}
        out = {}
        for name, a in self.bench.arms.items():
            q = a.read_positions(); goal = getattr(a, 'last_goal', None)
            row = dict(q_deg=deg(q), goal_deg=deg(goal), load_pm=[float(v) for v in a.read_loads()], moving=bool(a.is_moving()),
                       torque=bool(a.torque_enabled()), holding=held.get(name))
            if self.twin is not None: row['twin'] = self.twin.arm(name, q, goal, moving=row['moving'])
            out[name] = row
        return out

    def _error(self, msg):
        if msg not in self.errors: self.errors.append(msg)

    def _probe(self, k, f):
        """an optional extra (foam height, ...); a broken probe blanks only itself"""
        try: return f()
        except Exception as e: self._error('probe %s: %r' % (k, e)); return None

    def snapshot(self):
        self._pump_mega(); proto = self._protocol(); steps, running = self._steps(proto); ctx = self.seq.ctx if self.seq else None
        snap = dict(schema=SCHEMA, t=round(self.clock.now(), 3), mode=self.bench.mode,
                    seq_state=self.seq.state if self.seq else 'IDLE', stop_reason=ctx.stop_reason if ctx else None,
                    steps=steps, current=self._current(proto, running), scale=self._scale(), arms=self._arms(),
                    vessels=None, spilled_g=None, probes={k: self._probe(k, f) for k, f in self.probes.items()},
                    wire=list(self.wire), events=[], faults=list(self.mega.faults), errors=list(self.errors))
        if self.ledger is not None:
            ls = self.ledger.snapshot(); snap['vessels'] = ls['vessels']; snap['spilled_g'] = ls['spilled_g']
        if ctx is not None:
            n0 = max(0, len(ctx.events) - EVENT_TAIL)
            snap['events'] = [dict(id=n0 + k, **e) for k, e in enumerate(ctx.events[n0:])]
            snap['errors'] += [r['reason'].split('\n')[0] for r in self.seq.runlog.d['steps'] if r['status'] == 'failed']
        return snap
