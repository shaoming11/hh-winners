"""benchsim.hwtest: the guided hardware ladder against a fake Mega (LoopbackSerial) and fake arm buses.
No ports, no MuJoCo world: everything here runs without hardware."""

import json

import pytest

from benchsim import hwtest, protocol
from benchsim.backends import real

JOINTS = real.JOINTS


class FakeMega:
    """speaks the Mega protocol lines: receive(line) / drain() -> [line]"""

    def __init__(self, estop=False, faults=0, hx_flat=False, motion_ok=True):
        self.out = []; self.streaming = False; self.t = 0; self.estop = estop; self.faults = faults
        self.hx_flat = hx_flat; self.motion_ok = motion_ok; self.cmds = []

    def emit(self, d): self.out.append(protocol.encode(d))

    def receive(self, line):
        m = protocol.decode(line); c = m['cmd']; s = m.get('seq'); self.cmds.append(c)
        if c == 'PING': self.emit(dict(seq=s, ok=True, fw='wlb-mega 0.1', sim=False, estop=self.estop, faults=self.faults, pos='known', tt=0.0, st=0.0, hx_ms=79.0, adc=128, t=self.t))
        elif c == 'STREAM': self.streaming = m['on']; self.emit(dict(seq=s, ok=True, t=self.t))
        elif c == 'CLR': self.emit(dict(seq=s, ok=True, t=self.t))
        elif c in ('TT', 'ST', 'AUG'):
            self.emit(dict(seq=s, ack=True, t=self.t))
            if self.motion_ok: self.emit(dict(seq=s, done=True, cmd=c, t=self.t))

    def drain(self):
        if self.streaming:
            self.t += 80
            self.emit(dict(w=0.0, raw=227000 if self.hx_flat else 227000 + self.t % 7, t=self.t))
        out, self.out = self.out, []
        return out


class FakeBus:
    """LeRobotArm bus: positions start at 2047 (= MJCF 0 with the example calibration); goals land at once"""

    def __init__(self, port, ids, ticks=None, loads=None, stuck=None):
        self.port = port; self.ids = ids; self.stuck = stuck
        self.regs = {'Present_Position': dict(ticks or {n: 2047 for n in JOINTS}), 'Present_Load': dict(loads or {n: 0 for n in JOINTS}),
                     'Torque_Enable': {n: 0 for n in JOINTS}, 'Moving': {n: 0 for n in JOINTS},
                     'Homing_Offset': {n: 0 for n in JOINTS}, 'Min_Position_Limit': {n: 0 for n in JOINTS}, 'Max_Position_Limit': {n: 4095 for n in JOINTS}}
        self.writes = []

    def connect(self): pass
    def disconnect(self): pass
    def read(self, reg): return dict(self.regs[reg])

    def write(self, reg, values):
        self.writes.append((reg, dict(values))); self.regs.setdefault(reg, {}).update(values)
        if reg == 'Goal_Position':
            for n, v in values.items():
                if n != self.stuck: self.regs['Present_Position'][n] = v


class FakeClock:
    def __init__(self): self.t = 0.0
    def now(self): return self.t
    def sleep(self, dt): self.t += dt


def run(tmp_path, argv, answers=(), mega=None, buses=None, bus_kw=None):
    a = hwtest.parse(argv + ['--no-report'])
    store = buses if buses is not None else {}

    def bus_factory(port, ids):
        b = FakeBus(port, ids, **(bus_kw or {}).get(port, {})); store[port] = b; return b

    replies = list(answers); out = []
    lad = hwtest.Ladder(a, input_fn=lambda prompt: replies.pop(0) if replies else '', out=out.append,
                        serial_factory=(lambda **kw: real.LoopbackSerial(mega or FakeMega(), **kw)), bus_factory=bus_factory, clock=FakeClock())
    return lad.run(), lad.rows, out


def cal_file(tmp_path):
    cal = real.load_calibration(); p = tmp_path / 'cal.json'; p.write_text(json.dumps(cal)); return str(p)


def test_l1_reads_everything_and_writes_nothing(tmp_path):
    buses = {}; mega = FakeMega()
    st, rows, _ = run(tmp_path, ['--mega', 'M', '--pourer', 'A', '--transfer', 'B', '--calibration', cal_file(tmp_path), '--upto', 'L1'], mega=mega, buses=buses)
    assert st == 'PASS', rows
    assert not any(b.writes for b in buses.values())                       # dry run: no register written
    assert not any(c in ('TT', 'ST', 'AUG') for c in mega.cmds)             # dry run: no motion line sent
    assert {r['check'] for r in rows if r['rung'] == 'L1'} >= {'Mega PING', 'scale stream', 'pourer joints inside calibrated limits'}


def test_flat_scale_stops_the_ladder(tmp_path):
    st, rows, _ = run(tmp_path, ['--mega', 'M', '--upto', 'L3'], mega=FakeMega(hx_flat=True))
    assert st == 'STOPPED' and rows[-1]['check'] == 'scale stream' and rows[-1]['status'] == 'FAIL'
    assert not any(r['rung'] == 'L3' for r in rows)


def test_joint_outside_limits_stops_at_l1(tmp_path):
    ticks = {n: 2047 for n in JOINTS}; ticks['elbow_flex'] = 2047 + 1500     # ~132 deg: outside +-96.8
    st, rows, _ = run(tmp_path, ['--pourer', 'A', '--calibration', cal_file(tmp_path), '--upto', 'L3'], bus_kw={'A': dict(ticks=ticks)})
    assert st == 'STOPPED' and 'outside' in rows[-1]['detail'] and 'elbow_flex' in rows[-1]['detail']


def test_zero_check_records_then_catches_a_reseated_horn(tmp_path):
    cal = cal_file(tmp_path)
    st, rows, _ = run(tmp_path, ['--pourer', 'A', '--calibration', cal, '--upto', 'L2', '--record-reference'])
    assert st == 'PASS' and (tmp_path / 'cal.json.reference.json').exists()
    st, rows, _ = run(tmp_path, ['--pourer', 'A', '--calibration', cal, '--upto', 'L2'])
    assert st == 'PASS' and rows[-1]['check'].startswith('pourer zero check')
    ticks = {n: 2047 for n in JOINTS}; ticks['wrist_flex'] += 164                 # one 25T horn tooth is 14.4 deg = 164 ticks
    st, rows, _ = run(tmp_path, ['--pourer', 'A', '--calibration', cal, '--upto', 'L2'], bus_kw={'A': dict(ticks=ticks)})
    assert st == 'STOPPED' and 'wrist_flex' in rows[-1]['detail']


def test_zero_check_without_a_reference_stops(tmp_path):
    st, rows, _ = run(tmp_path, ['--pourer', 'A', '--calibration', cal_file(tmp_path), '--upto', 'L2'])
    assert st == 'STOPPED' and 'record-reference' in rows[-1]['detail']


def test_l3_moves_only_after_move_is_typed(tmp_path):
    cal = cal_file(tmp_path)
    run(tmp_path, ['--pourer', 'A', '--calibration', cal, '--upto', 'L2', '--record-reference'])
    buses = {}
    st, rows, _ = run(tmp_path, ['--pourer', 'A', '--calibration', cal, '--upto', 'L3'], answers=['', 'no'], buses=buses)
    assert st == 'STOPPED' and 'did not confirm' in rows[-1]['detail'] if rows[-1]['status'] == 'FAIL' else st == 'STOPPED'
    assert not any(reg == 'Goal_Position' and len(v) == 6 and v != {n: 2047 for n in JOINTS} for reg, v in buses['A'].writes)


def test_l3_jogs_every_joint_and_returns(tmp_path):
    cal = cal_file(tmp_path)
    run(tmp_path, ['--pourer', 'A', '--calibration', cal, '--upto', 'L2', '--record-reference'])
    buses = {}
    st, rows, _ = run(tmp_path, ['--pourer', 'A', '--calibration', cal, '--upto', 'L3'], answers=['', 'MOVE', ''], buses=buses)
    assert st == 'PASS', rows
    jogs = [r for r in rows if r['rung'] == 'L3']
    assert len(jogs) == 6 and all(r['status'] == 'PASS' for r in jogs)
    b = buses['A']
    assert b.regs['Torque_Enable'] == {n: 0 for n in JOINTS}               # torque off again at the end
    assert b.regs['Present_Position'] == {n: 2047 for n in JOINTS}         # back where it started


def test_l3_stuck_joint_fails_and_torque_still_goes_off(tmp_path):
    cal = cal_file(tmp_path)
    run(tmp_path, ['--pourer', 'A', '--calibration', cal, '--upto', 'L2', '--record-reference'])
    buses = {}
    st, rows, _ = run(tmp_path, ['--pourer', 'A', '--calibration', cal, '--upto', 'L3'], answers=['', 'MOVE', ''], buses=buses,
                      bus_kw={'A': dict(stuck='elbow_flex')})
    assert st == 'STOPPED' and 'elbow_flex' in rows[-1]['check']
    assert buses['A'].regs['Torque_Enable'] == {n: 0 for n in JOINTS}


def test_l3_mega_refuses_to_move_while_the_estop_is_latched(tmp_path):
    mega = FakeMega(estop=True, faults=1)
    st, rows, _ = run(tmp_path, ['--mega', 'M', '--upto', 'L3'], answers=['MOVE'] * 3, mega=mega)
    assert st == 'STOPPED' and not any(c in ('TT', 'ST', 'AUG') for c in mega.cmds)


def test_l3_mega_axes_one_at_a_time(tmp_path):
    mega = FakeMega()
    st, rows, _ = run(tmp_path, ['--mega', 'M', '--upto', 'L3'], answers=['MOVE'] * 3, mega=mega)
    assert st == 'PASS', rows
    assert [c for c in mega.cmds if c in ('TT', 'ST', 'AUG')] == ['TT', 'TT', 'ST', 'ST', 'AUG']
