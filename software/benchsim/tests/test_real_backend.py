"""Hardware backend without hardware: lazy imports, the serial framing over a loopback to the simulated Mega,
the dry-run guards, the calibration schema and joint mapping, and the LeRobot arm on a fake Feetech bus."""
import json
import math
import subprocess
import sys
import types

import numpy as np
import pytest

from benchsim import paths, protocol
from benchsim.backends import real
from benchsim.bench import HardwareNotAllowed, make_bench
from benchsim.interfaces import MegaClient, MegaError

JOINTS = real.JOINTS


# ------------------------------------------------------------------ fakes
class FakeBus:
    """the LeRobotArm bus interface (connect, disconnect, read(reg) -> {joint: int}, write(reg, {joint: int}))"""

    def __init__(self, port, ids, torque=0, fingerprint=None):
        self.port = port; self.ids = ids; self.writes = []; self.connected = False
        fp = fingerprint or {n: [0, 0, 4095] for n in JOINTS}
        self.regs = {'Present_Position': {n: 2047 for n in JOINTS}, 'Present_Load': {n: 0 for n in JOINTS},
                     'Torque_Enable': {n: torque for n in JOINTS}, 'Moving': {n: 0 for n in JOINTS},
                     'Homing_Offset': {n: fp[n][0] for n in JOINTS}, 'Min_Position_Limit': {n: fp[n][1] for n in JOINTS},
                     'Max_Position_Limit': {n: fp[n][2] for n in JOINTS}}

    def connect(self): self.connected = True

    def disconnect(self): self.connected = False

    def read(self, reg): return dict(self.regs[reg])

    def write(self, reg, values):
        self.writes.append((reg, dict(values))); self.regs.setdefault(reg, {}).update(values)


def fake_bus_factory(store, **kw):
    def f(port, ids):
        b = FakeBus(port, ids, **kw); store[port] = b; return b
    return f


@pytest.fixture(scope='module')
def cal():
    return real.load_calibration()


@pytest.fixture
def sim_bench(built):
    from benchsim.backends import sim
    model, b = built
    return make_bench('sim', world=sim.SimWorld(model=model, builder=b))


def loop_factory(device, store=None, **kw):
    def f(**open_kw):
        s = real.LoopbackSerial(device, **open_kw, **kw)
        if store is not None: store['serial'] = s; store['open_kw'] = open_kw
        return s
    return f


# ------------------------------------------------------------------ imports
def test_import_needs_neither_pyserial_nor_lerobot_nor_mujoco():
    code = ("import sys; import benchsim.backends.real as r; "
            "bad = [m for m in ('serial', 'lerobot', 'mujoco') if m in sys.modules]; assert not bad, bad")
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, cwd=paths.SIM_ROOT)
    assert r.returncode == 0, r.stderr


def test_missing_pyserial_and_lerobot_give_clear_errors(monkeypatch):
    monkeypatch.setitem(sys.modules, 'serial', None)
    with pytest.raises(ImportError, match='pyserial'): real.SerialTransport('/dev/ttyUSB9', baud=250000).open()
    for m in ('lerobot', 'lerobot.motors', 'lerobot.common', 'lerobot.common.motors'): monkeypatch.setitem(sys.modules, m, None)
    with pytest.raises(ImportError, match='lerobot'): real.LeRobotBus('/dev/ttyACM9', {n: i + 1 for i, n in enumerate(JOINTS)})


def test_pyserial_port_is_configured_before_open_so_the_mega_does_not_reset(monkeypatch):
    log = []

    class Serial:
        def __init__(self): object.__setattr__(self, 'is_open', False)

        def __setattr__(self, k, v):
            log.append((k, v)); object.__setattr__(self, k, v)

        def open(self): log.append(('open', None)); object.__setattr__(self, 'is_open', True)

        def close(self): pass

    fake = types.SimpleNamespace(Serial=Serial, EIGHTBITS=8, PARITY_NONE='N', STOPBITS_ONE=1)
    monkeypatch.setitem(sys.modules, 'serial', fake)
    t = real.SerialTransport('/dev/ttyUSB0').open()
    keys = [k for k, _ in log]
    assert dict(log)['dtr'] is False and dict(log)['rts'] is False
    assert keys.index('dtr') < keys.index('open') and keys.index('rts') < keys.index('open')
    assert dict(log)['baudrate'] == 250000 and dict(log)['timeout'] == 0 and t.ser.is_open


# ------------------------------------------------------------------ serial framing against the simulated Mega
def test_megaclient_over_serialtransport_matches_the_in_process_transport(built):
    """the same command sequence through SimTransport and through SerialTransport + LoopbackSerial (reads split in
    random 1-200 byte pieces, so lines split across reads) gives the same replies"""
    from benchsim.backends import sim
    model, b = built

    def session(serial):
        w = sim.SimWorld(model=model, builder=b); dev = sim.SimMega(w); clock = sim.SimClock(w)
        t = real.SerialTransport('loop', baud=250000, serial_factory=loop_factory(dev, chunk=200)).open() if serial else sim.SimTransport(dev)
        mc = MegaClient(t, clock); out = [mc.command('PING')['ok'], mc.command('STREAM', on=True)['ok'], mc.command('TARE')['ok']]
        out.append(round(mc.read_mass(16), 1))
        out.append(mc.motion('TT', done_timeout=8, deg=45.0, ms=2000)['deg'] >= 45.0 - sim.SimMega.MOVE_TOL_DEG - 1e-9)   # done = inside the firmware tolerance
        out.append(mc.motion('AUG', done_timeout=8, rev=1.0, dir=1)['rev'])
        for cmd, kw in (('TT', dict(deg=400.0, ms=9000)), ('FLY', {})):
            try: mc.command(cmd, **kw); out.append('no error')
            except MegaError as e: out.append(e.code)
        return out, mc

    a, _ = session(False)
    b_, mc = session(True)
    assert a == b_ == [True, True, True, 0.0, True, 1.0, 'RANGE', 'BADCMD']
    assert not [x for x in mc.log if x[0] == 'bad-line']


def test_serialtransport_reassembles_lines_drops_noise_and_strips_crlf():
    class Dev:
        def __init__(self): self.out = []; self.got = []

        def receive(self, line): self.got.append(line)

        def drain(self): o, self.out = self.out, []; return o

    dev = Dev(); store = {}
    t = real.SerialTransport('loop', baud=250000, serial_factory=loop_factory(dev, store, chunk=3, seed=1)).open()
    assert store['open_kw']['dtr'] is False and store['open_kw']['rts'] is False and store['open_kw']['baudrate'] == 250000
    lines = [protocol.encode(dict(w=1.25 * i, raw=1000 + i, t=i)) for i in range(40)]
    dev.out = list(lines); store['serial'].inject(b'\x00\xffgarbage-before-reset\n')
    got = []
    for _ in range(2000): got += t.read_lines()
    assert got[0] == '��garbage-before-reset' or got[0].endswith('garbage-before-reset')
    assert got[1:] == [l.rstrip('\n') for l in lines]
    store['serial'].inject(protocol.encode(dict(ok=True, seq=3)).rstrip('\n').encode() + b'\r\n')
    got = []
    for _ in range(200): got += t.read_lines()
    assert protocol.decode(got[0]) == dict(ok=True, seq=3)
    store['serial'].inject(b'x' * (real.SerialTransport.MAX_PARTIAL + 10))
    for _ in range(2000): t.read_lines()
    assert t.dropped_bytes > real.SerialTransport.MAX_PARTIAL
    t.write_line('{"cmd":"PING","seq":1}')
    assert dev.got == ['{"cmd":"PING","seq":1}\n']


# ------------------------------------------------------------------ dry run
def test_dry_run_mega_refuses_motion_and_passes_everything_else(sim_bench):
    dev = sim_bench.mega_device; store = {}
    bb = make_bench('real', allow_hardware=True, port_mega='loop', serial_factory=loop_factory(dev, store))
    assert bb.dry_run and isinstance(bb.transport, real.DryRunTransport) and bb.arms == {}
    mega = MegaClient(bb.transport, sim_bench.clock)
    assert mega.command('PING')['ok'] and mega.command('STREAM', on=True)['ok'] and mega.command('STOP')['ok']
    for cmd, kw in (('TT', dict(deg=10.0, ms=4000)), ('ST', dict(deg=150.0, ms=2500)), ('AUG', dict(rev=1.0, dir=1))):
        with pytest.raises(real.HardwareOutputDisabled): mega.send(cmd, **kw)
    with pytest.raises(real.HardwareOutputDisabled): bb.transport.write_line('not json')
    sent = [protocol.decode(l)['cmd'] for l in store['serial'].tx_lines]
    assert not set(sent) & set(protocol.MOTION) and len(bb.transport.refused) == 4
    bb.close()


def test_dry_run_arms_read_but_never_write(cal):
    buses = {}
    bb = real.make_real_bench(port_pourer='/dev/A', port_transfer='/dev/B', calibration_path=real.EXAMPLE_CALIBRATION,
                              bus_factory=fake_bus_factory(buses))
    assert bb.dry_run and set(bb.arms) == {'pourer', 'transfer'} and bb.mega is None
    for name, a in bb.arms.items():
        assert np.allclose(a.read_positions(), 0.0) and a.read_loads().shape == (6,) and not a.torque_enabled()
        with pytest.raises(RuntimeError): a.set_goal(np.zeros(6))                   # torque off
        with pytest.raises(real.HardwareOutputDisabled): a.set_torque(True)
        with pytest.raises(real.HardwareOutputDisabled): a.set_torque(False)
    assert all(b.writes == [] for b in buses.values())
    assert any('no fingerprint' in w for w in bb.warnings)
    bb.close()
    assert not any(b.connected for b in buses.values())


def test_dry_run_with_servos_already_torqued_still_refuses_goals(cal):
    buses = {}
    a = real.LeRobotArm('pourer', '/dev/A', cal['arms']['pourer'], bus_factory=fake_bus_factory(buses, torque=1), dry_run=True)
    a.connect()
    assert a.torque_enabled() and a.warnings
    with pytest.raises(real.HardwareOutputDisabled): a.set_goal(np.zeros(6))
    assert buses['/dev/A'].writes == []


def test_arms_need_a_calibration_file():
    with pytest.raises(real.CalibrationError): real.make_real_bench(port_pourer='/dev/A')


# ------------------------------------------------------------------ live mode on the fake bus
def test_live_arm_connect_limp_enable_without_snap_and_synchronised_goal(cal):
    buses = {}
    a = real.LeRobotArm('pourer', '/dev/A', cal['arms']['pourer'], bus_factory=fake_bus_factory(buses), dry_run=False,
                        max_speed_deg_s=180.0)
    a.connect(); bus = buses['/dev/A']
    assert bus.writes == [('Torque_Enable', {n: 0 for n in JOINTS})] and not a.torque_enabled()
    bus.regs['Present_Position'] = {n: 2047 + 10 * i for i, n in enumerate(JOINTS)}
    a.set_torque(True)
    regs = [r for r, _ in bus.writes[1:]]
    assert regs == ['Goal_Position', 'Acceleration', 'Goal_Velocity', 'Torque_Enable']
    assert bus.writes[1][1] == bus.regs['Present_Position']                         # goal = present before enable
    assert bus.writes[2][1]['shoulder_pan'] == round(300.0 * 4096 / 360 / 100)       # 300 deg/s^2 in 100 step/s^2
    assert bus.writes[3][1]['shoulder_pan'] == round(60.0 * 4096 / 360)              # min(calibration 60, [arm] 180)
    n0 = len(bus.writes)
    q = np.radians([30.0, -15.0, 10.0, 0.0, 5.0, 20.0])
    a.set_goal(q, speed_scale=0.5)
    (r1, vel), (r2, goal) = bus.writes[n0:]
    assert (r1, r2) == ('Goal_Velocity', 'Goal_Position')
    assert goal == a.map.q_to_ticks(q)
    dq = {n: abs(goal[n] - bus.regs['Present_Position'][n]) for n in JOINTS}
    t = [dq[n] / vel[n] for n in JOINTS if dq[n] > 50]
    assert max(vel.values()) == round(30.0 * 4096 / 360) and max(t) - min(t) < 0.05      # all joints arrive together
    with pytest.raises(ValueError): a.set_goal(np.radians([150.0, 0, 0, 0, 0, 0]))      # outside the calibrated range
    with pytest.raises(ValueError): a.set_goal(q, speed_scale=1.5)
    assert len(bus.writes) == n0 + 2
    bus.regs['Moving']['elbow_flex'] = 1
    assert a.is_moving()
    a.disconnect()
    assert ('Torque_Enable', {n: 0 for n in JOINTS}) not in bus.writes[1:]               # disconnect leaves torque on


def test_fingerprint_mismatch_refuses_the_arm(cal):
    arm = json.loads(json.dumps(cal['arms']['transfer']))
    arm['fingerprint'] = {n: [7, 0, 4095] for n in JOINTS}
    with pytest.raises(real.ArmIdentityError):
        real.LeRobotArm('transfer', '/dev/B', arm, bus_factory=fake_bus_factory({}), dry_run=False).connect()
    buses = {}
    a = real.LeRobotArm('transfer', '/dev/B', arm, bus_factory=fake_bus_factory(buses, fingerprint=arm['fingerprint']), dry_run=False)
    a.connect()
    assert a.read_fingerprint() == arm['fingerprint'] and not a.warnings


def test_joint_order_matches_the_simulator():
    from benchsim import state
    assert list(JOINTS) == state.ARM_JOINTS


def test_present_load_sign_bit_is_decoded():
    assert [real.decode_load(v) for v in (0, 300, 0x400 | 300, 0x400 | 1000, -42)] == [0, 300, -300, -1000, -42]


# ------------------------------------------------------------------ calibration
def test_example_calibration_is_valid_and_inside_the_mjcf_ranges(cal):
    ranges = real.mjcf_joint_ranges_deg()
    if ranges is None: pytest.skip('SO-101 model not fetched (python -m benchsim fetch)')
    assert real.validate_calibration(cal, ranges) == []
    assert 'example' in cal['status']


def test_calibration_schema_errors_are_reported(cal):
    bad = json.loads(json.dumps(cal))
    j = bad['arms']['pourer']['joints']
    j['shoulder_pan']['sign'] = 2; j['elbow_flex']['id'] = j['shoulder_lift']['id']; j['wrist_flex']['tick_at_zero'] = 5000
    j['wrist_roll']['min_deg'] = 200.0; j['gripper']['tick_open'] = j['gripper']['tick_closed']
    bad['arms']['transfer']['max_speed_deg_s'] = 0
    errs = real.validate_calibration(bad, {'shoulder_pan': (-100.0, 100.0)})
    text = '\n'.join(errs)
    for frag in ('shoulder_pan.sign', 'servo ids must be unique', 'wrist_flex: ticks', 'wrist_roll: min_deg', 'closed and open',
                 'transfer.max_speed_deg_s', 'exceeds the MJCF range'):
        assert frag in text, (frag, errs)
    assert real.validate_calibration({'schema': 'x'}) and real.validate_calibration([])


def test_joint_map_round_trip_sign_and_gripper(cal):
    arm = json.loads(json.dumps(cal['arms']['pourer']))
    arm['joints']['elbow_flex'].update(tick_at_zero=1900, sign=-1)
    m = real.JointMap(arm, 4096)
    rng = np.random.default_rng(0)
    for _ in range(50):
        q = rng.uniform(m.lo, m.hi); q2 = m.ticks_to_q(m.q_to_ticks(q))
        assert np.all(np.abs(q2 - q) <= math.pi / 4096 + 1e-12)                       # half a tick
    t = m.q_to_ticks(np.zeros(6))
    assert t['shoulder_pan'] == 2047 and t['elbow_flex'] == 1900
    assert m.q_to_ticks(np.radians([0, 0, 10.0, 0, 0, 0]))['elbow_flex'] < 1900          # sign -1
    g = arm['joints']['gripper']
    assert m.q_to_ticks(np.radians([0, 0, 0, 0, 0, g['deg_open']]))['gripper'] == g['tick_open']
    assert m.q_to_ticks(np.radians([0, 0, 0, 0, 0, g['deg_closed']]))['gripper'] == g['tick_closed']


# ------------------------------------------------------------------ LeRobot adapter on a stub lerobot package
def test_lerobot_adapter_uses_raw_registers_and_keeps_torque_on_disconnect(monkeypatch, cal):
    calls = []

    class Motor:
        def __init__(self, id, model, norm): self.id = id; self.model = model; self.norm = norm

    class FeetechMotorsBus:
        def __init__(self, port, motors): calls.append(('init', port, {k: (m.id, m.model) for k, m in motors.items()}))

        def connect(self): calls.append(('connect',))

        def disconnect(self, disable_torque=True): calls.append(('disconnect', disable_torque))

        def sync_read(self, reg, normalize=True): calls.append(('read', reg, normalize)); return {n: 2047 for n in JOINTS}

        def sync_write(self, reg, values, normalize=True): calls.append(('write', reg, normalize))

    motors = types.ModuleType('lerobot.motors'); motors.Motor = Motor
    motors.MotorNormMode = types.SimpleNamespace(RANGE_0_100='r0', RANGE_M100_100='rm')
    feetech = types.ModuleType('lerobot.motors.feetech'); feetech.FeetechMotorsBus = FeetechMotorsBus
    for name, mod in (('lerobot', types.ModuleType('lerobot')), ('lerobot.motors', motors), ('lerobot.motors.feetech', feetech)):
        monkeypatch.setitem(sys.modules, name, mod)
    a = real.LeRobotArm('pourer', '/dev/ttyACM0', cal['arms']['pourer'], dry_run=True)
    a.connect(); q = a.read_positions(); a.disconnect()
    assert calls[0] == ('init', '/dev/ttyACM0', {n: (i + 1, 'sts3215') for i, n in enumerate(JOINTS)})
    assert ('connect',) in calls and ('disconnect', False) in calls
    assert all(c[2] is False for c in calls if c[0] in ('read', 'write')) and not any(c[0] == 'write' for c in calls)
    assert np.allclose(q, 0.0)


# ------------------------------------------------------------------ opt-in
def test_cli_opt_in(monkeypatch, built):
    import argparse
    p = argparse.ArgumentParser(); real.add_cli_arguments(p)
    from benchsim.backends import sim
    model, b = built
    assert real.bench_from_args(p.parse_args([]), world=sim.SimWorld(model=model, builder=b)).mode == 'sim'
    with pytest.raises(HardwareNotAllowed): real.bench_from_args(p.parse_args(['--real']))
    opened = []

    class Serial:
        def open(self): opened.append((self.port, self.dtr, self.rts))

    monkeypatch.setitem(sys.modules, 'serial', types.SimpleNamespace(Serial=Serial, EIGHTBITS=8, PARITY_NONE='N', STOPBITS_ONE=1))
    bb = real.bench_from_args(p.parse_args(['--real', '--dry-run', '--mega-port', '/dev/ttyUSB0']))
    assert bb.mode == 'real' and bb.dry_run and opened == [('/dev/ttyUSB0', False, False)]
    bb = real.bench_from_args(p.parse_args(['--real', real.CONFIRM_FLAG, '--mega-port', '/dev/ttyUSB0']))
    assert not bb.dry_run and isinstance(bb.transport, real.SerialTransport)


def test_hw_check_cli_runs_offline():
    r = subprocess.run([sys.executable, '-m', 'benchsim', 'hw-check'], capture_output=True, text=True, cwd=paths.SIM_ROOT, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert 'hw-check: PASS' in r.stdout and 'no port opened' in r.stdout
