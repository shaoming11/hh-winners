"""Hardware backend: two SO-101 followers on LeRobot's Feetech bus and the Arduino Mega over USB serial.

Nothing here touches hardware at import time: pyserial and lerobot are imported only when a port is opened, and
importing this module works without either installed (``pip install -e '.[hardware]'`` adds them). Select this
backend only through ``benchsim.bench.make_bench('real', allow_hardware=True, ...)``; the command-line opt-in is
``--real --i-understand-this-moves-hardware`` (``add_cli_arguments`` / ``bench_from_args``), and the default is
simulation.

Hardware output is disabled by default: ``make_real_bench(..., dry_run=True)`` opens the ports and reads, but
refuses every servo goal and torque write on the arms and every TT/ST/AUG line to the Mega
(``HardwareOutputDisabled``). Pass ``dry_run=False`` to move anything.

Joint convention at the ArmBackend boundary (benchsim.interfaces): radians in the upstream so101_new_calib MJCF
convention. ``JointMap`` converts with the calibration JSON (``config/hardware_calibration.example.json``):

    q_rad = sign * (ticks - tick_at_zero) * 2 pi / ticks_per_rev          (shoulder_pan .. wrist_roll)
    gripper: the same form, or a two-point map tick_closed/deg_closed -> tick_open/deg_open

The calibration is only as good as the bring-up that records it (software/benchsim/docs/bringup.md, A1-A5); the
example file holds placeholders. The LeRobot adapter is written against LeRobot's ``FeetechMotorsBus`` API
(``lerobot.motors.feetech``, or ``lerobot.common.motors.feetech`` in older releases; ``sync_read``/``sync_write`` with
``normalize=False``). It is tested against a stub of that API only; it has not been run against a real bus here.

The second half of the module holds the offline hardware checks behind ``python -m benchsim hw-check``: the
calibration schema, the firmware constants against bench_params.toml, and the firmware host test
(firmware/mega/host_test) fed with lines from ``benchsim.protocol.encode``. None of them opens a port.
"""
import importlib.util
import itertools
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from .. import paths, protocol
from ..interfaces import BenchBackends, MegaClient
from ..units import deg as to_deg, rad as to_rad

JOINTS = ('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper')   # = state.ARM_JOINTS (state imports MuJoCo)
CALIBRATION_SCHEMA = 'benchsim.hardware_calibration/1'
EXAMPLE_CALIBRATION = paths.CONFIG / 'hardware_calibration.example.json'
REAL_FLAG, CONFIRM_FLAG = '--real', '--i-understand-this-moves-hardware'


class HardwareOutputDisabled(RuntimeError):
    """a write that would move hardware was refused (dry run)"""


class CalibrationError(ValueError):
    pass


class ArmIdentityError(RuntimeError):
    """the servos on this port do not match the arm's recorded fingerprint (wrong port or arms swapped)"""


def _params():
    from ..layout import load_params
    return load_params()


# ======================================================================= clock
class RealClock:
    """wall clock for the hardware backend (time.monotonic / time.sleep)"""

    def now(self):
        return time.monotonic()

    def sleep(self, dt):
        if dt > 0: time.sleep(dt)


# ======================================================================= serial
def _import_serial():
    try:
        import serial
    except ImportError as e:
        raise ImportError("pyserial is needed for the Mega port: pip install -e '.[hardware]'") from e
    return serial


class SerialTransport:
    """MegaTransport over a serial port: 8N1 at [mega] baud (250000), non-blocking reads, line reassembly.

    The port is created unopened and DTR/RTS are set False before ``open()``, so opening it does not reset the
    Mega (electrical.md 4). Some USB-serial drivers still pulse DTR on open; bring-up test E2 checks for a
    second boot banner. ``serial_factory(port=, baudrate=, dtr=, rts=)`` replaces pyserial in tests."""

    MAX_PARTIAL = 1024                                  # bytes without a newline before the buffer is dropped

    def __init__(self, port, baud=None, serial_factory=None):
        self.port = port; self.baud = baud or _params()['mega']['baud']; self._factory = serial_factory
        self.ser = None; self._buf = b''; self.dropped_bytes = 0; self.lines_in = 0; self.lines_out = 0

    def open(self):
        if self.ser is not None: return self
        if self._factory is not None:
            self.ser = self._factory(port=self.port, baudrate=self.baud, dtr=False, rts=False)
            return self
        serial = _import_serial()
        s = serial.Serial()                             # unopened
        s.port = self.port; s.baudrate = self.baud
        s.bytesize = serial.EIGHTBITS; s.parity = serial.PARITY_NONE; s.stopbits = serial.STOPBITS_ONE
        s.timeout = 0; s.write_timeout = 1.0
        s.dtr = False; s.rts = False                    # before open(): no auto-reset
        s.open()
        self.ser = s
        return self

    def close(self):
        if self.ser is not None: self.ser.close(); self.ser = None

    def write_line(self, line):
        if self.ser is None: raise RuntimeError('serial port %s is not open' % self.port)
        if not line.endswith('\n'): line += '\n'
        self.ser.write(line.encode('ascii')); self.lines_out += 1

    def read_lines(self):
        if self.ser is None: raise RuntimeError('serial port %s is not open' % self.port)
        n = self.ser.in_waiting
        if n: self._buf += self.ser.read(n)
        out = []
        while True:
            i = self._buf.find(b'\n')
            if i < 0: break
            raw, self._buf = self._buf[:i], self._buf[i + 1:]
            out.append(raw.rstrip(b'\r').decode('ascii', errors='replace'))
        if len(self._buf) > self.MAX_PARTIAL: self.dropped_bytes += len(self._buf); self._buf = b''
        self.lines_in += len(out)
        return out


class DryRunTransport:
    """wraps a transport and refuses every TT/ST/AUG line (and anything it cannot decode); reads pass through"""

    def __init__(self, inner):
        self.inner = inner; self.refused = []

    def write_line(self, line):
        try: cmd = protocol.decode(line).get('cmd')
        except protocol.ProtocolError: cmd = '<undecodable>'
        if cmd in protocol.MOTION or cmd == '<undecodable>':
            self.refused.append(line)
            raise HardwareOutputDisabled('dry run: %s not sent to the Mega (make_real_bench(dry_run=False) to move)' % cmd)
        self.inner.write_line(line)

    def read_lines(self):
        return self.inner.read_lines()

    def close(self):
        self.inner.close()


class LoopbackSerial:
    """pyserial stand-in for tests, wired to a device that speaks the protocol lines: ``receive(line)`` and
    ``drain() -> [line]`` (benchsim.backends.sim.SimMega has both). ``chunk`` splits reads into random pieces of
    1..chunk bytes so line reassembly is exercised; ``inject(bytes)`` puts raw bytes (noise, CRLF) on the wire."""

    def __init__(self, device, port='loopback', baudrate=None, dtr=None, rts=None, chunk=None, seed=0):
        self.device = device; self.port = port; self.baudrate = baudrate; self.dtr = dtr; self.rts = rts
        self.chunk = chunk; self.rng = random.Random(seed); self.is_open = True; self._tx = b''; self._rx = b''
        self.tx_lines = []

    def write(self, data):
        self._tx += bytes(data)
        while b'\n' in self._tx:
            line, self._tx = self._tx.split(b'\n', 1)
            text = line.decode('ascii') + '\n'; self.tx_lines.append(text); self.device.receive(text)
        return len(data)

    def _fill(self):
        for line in self.device.drain(): self._rx += line.encode('ascii')

    def inject(self, data):
        self._rx += data

    @property
    def in_waiting(self):
        self._fill()
        if self.chunk and self._rx: return min(len(self._rx), self.rng.randint(1, self.chunk))
        return len(self._rx)

    def read(self, n=1):
        self._fill(); out, self._rx = self._rx[:n], self._rx[n:]; return out

    def close(self):
        self.is_open = False


# ======================================================================= calibration
def load_calibration(path=None):
    """read and validate a hardware calibration JSON; raises CalibrationError listing every problem"""
    path = Path(path or EXAMPLE_CALIBRATION)
    try: cal = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as e: raise CalibrationError('%s: %s' % (path, e))
    errs = validate_calibration(cal)
    if errs: raise CalibrationError('%s:\n  ' % path + '\n  '.join(errs))
    return cal


def _isnum(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def validate_calibration(cal, joint_ranges_deg=None):
    """schema check; returns a list of problems (empty = valid). ``joint_ranges_deg`` = {joint: (lo, hi)} from the
    MJCF, if given, bounds every joint's min_deg/max_deg."""
    e = []
    if not isinstance(cal, dict): return ['top level is not an object']
    if cal.get('schema') != CALIBRATION_SCHEMA: e.append('schema must be %r' % CALIBRATION_SCHEMA)
    tpr = cal.get('ticks_per_rev')
    if not isinstance(tpr, int) or isinstance(tpr, bool) or tpr <= 0: e.append('ticks_per_rev must be a positive integer'); tpr = 4096
    arms = cal.get('arms')
    if not isinstance(arms, dict) or set(arms) != {'pourer', 'transfer'}: return e + ['arms must hold exactly pourer and transfer']
    for an, arm in arms.items():
        p = 'arms.%s' % an
        if not isinstance(arm, dict): e.append('%s is not an object' % p); continue
        for k, lo, hi in (('max_speed_deg_s', 1.0, 360.0), ('acceleration_deg_s2', 1.0, 10000.0), ('goal_tolerance_deg', 0.05, 10.0)):
            if not _isnum(arm.get(k)) or not lo <= arm[k] <= hi: e.append('%s.%s must be a number in [%g, %g]' % (p, k, lo, hi))
        if not isinstance(arm.get('lerobot_id'), str) or not arm['lerobot_id']: e.append('%s.lerobot_id must be a non-empty string' % p)
        js = arm.get('joints')
        if not isinstance(js, dict) or set(js) != set(JOINTS): e.append('%s.joints must hold exactly %s' % (p, ', '.join(JOINTS))); continue
        ids = []
        for jn in JOINTS:
            j = js[jn]; q = '%s.joints.%s' % (p, jn)
            if not isinstance(j, dict): e.append('%s is not an object' % q); continue
            if not isinstance(j.get('id'), int) or isinstance(j.get('id'), bool) or not 1 <= j['id'] <= 253: e.append('%s.id must be a servo id 1-253' % q)
            else: ids.append(j['id'])
            two_point = jn == 'gripper' and 'tick_closed' in j
            need = ('tick_closed', 'tick_open', 'deg_closed', 'deg_open') if two_point else ('tick_at_zero', 'sign')
            for k in need + ('min_deg', 'max_deg'):
                if not _isnum(j.get(k)): e.append('%s.%s must be a number' % (q, k))
            if any(not _isnum(j.get(k)) for k in need + ('min_deg', 'max_deg')): continue
            if two_point:
                if j['tick_closed'] == j['tick_open'] or j['deg_closed'] == j['deg_open']: e.append('%s: closed and open points must differ' % q)
                ticks = (j['tick_closed'], j['tick_open'])
            else:
                if j['sign'] not in (1, -1): e.append('%s.sign must be 1 or -1' % q)
                ticks = (j['tick_at_zero'],)
            if any(not 0 <= t < tpr for t in ticks): e.append('%s: ticks must lie in [0, %d)' % (q, tpr))
            if not j['min_deg'] < j['max_deg']: e.append('%s: min_deg must be below max_deg' % q)
            if joint_ranges_deg and jn in joint_ranges_deg:
                lo, hi = joint_ranges_deg[jn]
                if j['min_deg'] < lo - 1e-6 or j['max_deg'] > hi + 1e-6:
                    e.append('%s: [%g, %g] deg exceeds the MJCF range [%.2f, %.2f]' % (q, j['min_deg'], j['max_deg'], lo, hi))
        if len(set(ids)) != len(ids): e.append('%s: servo ids must be unique' % p)
        fp = arm.get('fingerprint')
        if fp is not None:
            if not isinstance(fp, dict) or set(fp) != set(JOINTS) or any(
                    not (isinstance(v, list) and len(v) == 3 and all(isinstance(x, int) for x in v)) for v in fp.values()):
                e.append('%s.fingerprint must be null or {joint: [Homing_Offset, Min_Position_Limit, Max_Position_Limit]}' % p)
    return e


class JointMap:
    """MJCF radians <-> STS3215 ticks for one arm (see the module docstring for the formulas)"""

    def __init__(self, arm_cal, ticks_per_rev=4096):
        self.tpr = ticks_per_rev; self.j = arm_cal['joints']
        self.lo = np.array([to_rad(self.j[n]['min_deg']) for n in JOINTS]); self.hi = np.array([to_rad(self.j[n]['max_deg']) for n in JOINTS])

    def _lin(self, n):
        """(tick at 0 rad, ticks per rad) for joint n"""
        j = self.j[n]
        if 'tick_closed' in j:
            k = (j['tick_open'] - j['tick_closed']) / to_rad(j['deg_open'] - j['deg_closed'])
            return j['tick_closed'] - k * to_rad(j['deg_closed']), k
        return j['tick_at_zero'], j['sign'] * self.tpr / (2 * math.pi)

    def ticks_to_q(self, ticks):
        out = np.empty(6)
        for i, n in enumerate(JOINTS):
            t0, k = self._lin(n); out[i] = (ticks[n] - t0) / k
        return out

    def q_to_ticks(self, q):
        out = {}
        for i, n in enumerate(JOINTS):
            t0, k = self._lin(n); out[n] = int(round(t0 + k * float(q[i])))
        return out

    def ticks_per_rad(self):
        return np.array([abs(self._lin(n)[1]) for n in JOINTS])


# ======================================================================= arms
def _import_lerobot():
    for base in ('lerobot.motors', 'lerobot.common.motors'):
        try:
            motors = __import__(base, fromlist=['Motor', 'MotorNormMode'])
            feetech = __import__(base + '.feetech', fromlist=['FeetechMotorsBus'])
            return motors.Motor, motors.MotorNormMode, feetech.FeetechMotorsBus
        except ImportError:
            continue
    raise ImportError("lerobot (with its feetech extra) is needed for the arms: pip install -e '.[hardware]'")


class LeRobotBus:
    """the minimal bus used by LeRobotArm, on LeRobot's FeetechMotorsBus. Raw register values only
    (normalize=False): LeRobot's own calibration stays in the servos, our JointMap does the joint mapping."""

    def __init__(self, port, ids):
        Motor, NormMode, FeetechMotorsBus = _import_lerobot()
        motors = {n: Motor(ids[n], 'sts3215', NormMode.RANGE_0_100 if n == 'gripper' else NormMode.RANGE_M100_100) for n in JOINTS}
        self.bus = FeetechMotorsBus(port=port, motors=motors)

    def connect(self): self.bus.connect()                                         # pings and model checks only

    def disconnect(self): self.bus.disconnect(disable_torque=False)               # never drops a held beaker

    def read(self, reg): return {k: int(v) for k, v in self.bus.sync_read(reg, normalize=False).items()}

    def write(self, reg, values): self.bus.sync_write(reg, dict(values), normalize=False)


def decode_load(v):
    """STS3215 Present_Load: magnitude in bits 0-9 (0.1 % of max torque), direction in bit 10. Values that a bus
    layer has already sign-decoded (negative) pass through."""
    v = int(v)
    if v < 0: return v
    return -(v & 0x3FF) if v & 0x400 else v & 0x3FF


class LeRobotArm:
    """ArmBackend for one SO-101 follower on its Feetech bus.

    connect() pings the servos and checks the recorded fingerprint (Homing_Offset, Min/Max_Position_Limit per
    joint) so a wrong port or swapped arms is refused. In live mode it then disables torque (the arm goes limp:
    connect only with the arm resting and empty) and torque stays off until set_torque(True). In dry run it
    writes nothing and reports the torque state the servos have.

    set_torque(True) writes Goal_Position = Present_Position before Torque_Enable = 1, so enabling never snaps
    (software_architecture.md 2.2). set_goal() checks the calibrated joint limits (ValueError, never clamped),
    then writes a per-joint Goal_Velocity so every joint arrives together at <= max_speed * speed_scale, and the
    Goal_Position. The servo's own trapezoidal profile (Acceleration register) does the rate limiting.
    disconnect() leaves torque as it is."""

    def __init__(self, name, port, arm_cal, ticks_per_rev=4096, dry_run=True, bus_factory=None, max_speed_deg_s=None,
                 sts=None):
        self.name = name; self.port = port; self.cal = arm_cal; self.dry_run = dry_run
        self.map = JointMap(arm_cal, ticks_per_rev); self.tpr = ticks_per_rev
        self._bus_factory = bus_factory or LeRobotBus
        self.sts = sts or _params()['sts3215']
        self.vmax_deg_s = min(arm_cal['max_speed_deg_s'], max_speed_deg_s or math.inf)
        self.bus = None; self._torque = False; self._goal = None; self.warnings = []; self.writes = []

    # -------------------------------------------------- bus access
    def _ids(self):
        return {n: self.cal['joints'][n]['id'] for n in JOINTS}

    def _write(self, reg, values):
        if self.dry_run: raise HardwareOutputDisabled('%s dry run: %s not written' % (self.name, reg))
        self.bus.write(reg, values); self.writes.append((reg, dict(values)))

    def _read(self, reg):
        if self.bus is None: raise RuntimeError('%s is not connected' % self.name)
        return self.bus.read(reg)

    def connect(self):
        self.bus = self._bus_factory(self.port, self._ids())
        self.bus.connect()
        self.check_fingerprint()
        if self.dry_run:
            self._torque = any(self._read('Torque_Enable').values())
            if self._torque: self.warnings.append('%s: servos report torque ON (left as is in dry run)' % self.name)
        else:
            self._write('Torque_Enable', {n: 0 for n in JOINTS}); self._torque = False

    def disconnect(self):
        if self.bus is not None: self.bus.disconnect(); self.bus = None

    def read_fingerprint(self):
        regs = [self._read(r) for r in ('Homing_Offset', 'Min_Position_Limit', 'Max_Position_Limit')]
        return {n: [int(r[n]) for r in regs] for n in JOINTS}

    def check_fingerprint(self):
        want = self.cal.get('fingerprint')
        if want is None:
            self.warnings.append('%s: no fingerprint recorded; port identity not verified (bring-up A2)' % self.name); return None
        got = self.read_fingerprint()
        bad = {n: (got[n], want[n]) for n in JOINTS if list(got[n]) != list(want[n])}
        if bad: raise ArmIdentityError('%s on %s: fingerprint mismatch %s (wrong port or arms swapped?)' % (self.name, self.port, bad))
        return got

    # -------------------------------------------------- ArmBackend
    def read_ticks(self):
        return self._read('Present_Position')

    def read_positions(self):
        return self.map.ticks_to_q(self.read_ticks())

    def read_loads(self):
        raw = self._read('Present_Load')
        return np.array([decode_load(raw[n]) * self.sts['load_unit_permille'] for n in JOINTS], float)

    def _accel_reg(self):
        a = self.cal['acceleration_deg_s2'] * self.tpr / 360.0 / self.sts['acceleration_unit_ticks_s2']
        return int(min(max(round(a), 1), self.sts['acceleration_reg_max']))

    def set_torque(self, enabled):
        if enabled:
            present = self.read_ticks()
            self._write('Goal_Position', present)                                # never snap on enable
            self._write('Acceleration', {n: self._accel_reg() for n in JOINTS})
            v = max(1, int(round(self.vmax_deg_s * self.tpr / 360.0 / self.sts['goal_velocity_unit_ticks_s'])))
            self._write('Goal_Velocity', {n: v for n in JOINTS})
            self._write('Torque_Enable', {n: 1 for n in JOINTS})
            self._goal = present
        else:
            self._write('Torque_Enable', {n: 0 for n in JOINTS}); self._goal = None
        self._torque = bool(enabled)

    def torque_enabled(self):
        return self._torque

    def check_goal(self, q):
        q = np.asarray(q, float)
        if q.shape != (6,): raise ValueError('%s goal needs 6 joint values' % self.name)
        if np.any(q < self.map.lo - 1e-9) or np.any(q > self.map.hi + 1e-9):
            raise ValueError('%s goal outside calibrated joint range: %s' % (self.name, np.round(to_deg(q), 1)))
        ticks = self.map.q_to_ticks(q)
        if any(not 0 <= t < self.tpr for t in ticks.values()): raise ValueError('%s goal outside the servo tick range: %s' % (self.name, ticks))
        return q, ticks

    def set_goal(self, q, speed_scale=1.0):
        if not self._torque: raise RuntimeError('%s: torque disabled' % self.name)
        if not 0 < speed_scale <= 1.0: raise ValueError('%s: speed_scale must be in (0, 1], got %r' % (self.name, speed_scale))
        q, ticks = self.check_goal(q)
        present = self.read_ticks()
        dq = np.array([abs(ticks[n] - present[n]) for n in JOINTS], float)
        vpk = self.vmax_deg_s * speed_scale * self.tpr / 360.0                      # ticks/s for the largest move
        t_move = max(dq.max() / vpk, 1e-3)
        unit = self.sts['goal_velocity_unit_ticks_s']
        vel = {n: int(min(max(round(dq[i] / t_move / unit), 1), round(vpk / unit))) for i, n in enumerate(JOINTS)}
        self._write('Goal_Velocity', vel)
        self._write('Goal_Position', ticks)
        self._goal = ticks

    def is_moving(self):
        try: return any(self._read('Moving').values())
        except (KeyError, ValueError, NotImplementedError): pass     # a bus without the Moving register
        if self._goal is None: return False
        tol = self.cal['goal_tolerance_deg'] * self.tpr / 360.0; now = self.read_ticks()
        return any(abs(now[n] - self._goal[n]) > tol for n in JOINTS)


# ======================================================================= bench
def make_real_bench(port_mega=None, port_pourer=None, port_transfer=None, calibration_path=None, dry_run=True,
                    serial_factory=None, bus_factory=None, params=None):
    """open the Mega port and the arm buses that are given (None = leave that device out, e.g. Mega-only bring-up).
    dry_run=True (the default) opens and reads but refuses every output. Returns BenchBackends('real', ...) with
    extra attributes dry_run, transport, warnings and close()."""
    P = params or _params()
    clock = RealClock(); transport = None; mega = None; arms = {}
    want_arms = [(n, p) for n, p in (('pourer', port_pourer), ('transfer', port_transfer)) if p]
    if want_arms and calibration_path is None:
        raise CalibrationError('calibration_path is required for the arms (start from %s)' % EXAMPLE_CALIBRATION.name)
    cal = load_calibration(calibration_path) if want_arms else None
    try:
        if port_mega:
            transport = SerialTransport(port_mega, baud=P['mega']['baud'], serial_factory=serial_factory).open()
            if dry_run: transport = DryRunTransport(transport)
            mega = MegaClient(transport, clock)
        for name, port in want_arms:
            a = LeRobotArm(name, port, cal['arms'][name], ticks_per_rev=cal['ticks_per_rev'], dry_run=dry_run, bus_factory=bus_factory,
                           max_speed_deg_s=P['arm']['max_speed_deg_s'], sts=P['sts3215'])
            arms[name] = a; a.connect()
    except Exception:
        _close(arms, transport); raise
    bb = BenchBackends('real', clock, arms, mega)
    bb.dry_run = dry_run; bb.transport = transport
    bb.warnings = [w for a in arms.values() for w in a.warnings]
    bb.close = lambda: _close(arms, transport)
    return bb


def _close(arms, transport):
    for a in arms.values():
        try: a.disconnect()
        except Exception: pass
    if transport is not None: transport.close()


def add_cli_arguments(parser):
    """the hardware opt-in flags for a command that can drive the bench; the default stays simulation"""
    g = parser.add_argument_group('hardware (default: simulation)')
    g.add_argument(REAL_FLAG, dest='real', action='store_true', help='use the real bench instead of the simulator')
    g.add_argument(CONFIRM_FLAG, dest='hw_confirmed', action='store_true', help='with --real: allow motion')
    g.add_argument('--dry-run', dest='hw_dry_run', action='store_true', help='with --real: open and read only, refuse all motion')
    g.add_argument('--mega-port'); g.add_argument('--pourer-port'); g.add_argument('--transfer-port')
    g.add_argument('--calibration', help='hardware calibration JSON (schema %s)' % CALIBRATION_SCHEMA)
    return g


def bench_from_args(args, **sim_kw):
    """make_bench from parsed add_cli_arguments flags: sim unless --real; --real needs either --dry-run (read only)
    or --i-understand-this-moves-hardware (live)"""
    from ..bench import HardwareNotAllowed, make_bench
    if not getattr(args, 'real', False): return make_bench('sim', **sim_kw)
    if not (args.hw_confirmed or args.hw_dry_run):
        raise HardwareNotAllowed('%s needs %s (live) or --dry-run (read only)' % (REAL_FLAG, CONFIRM_FLAG))
    return make_bench('real', allow_hardware=True, port_mega=args.mega_port, port_pourer=args.pourer_port, port_transfer=args.transfer_port,
                      calibration_path=args.calibration, dry_run=not args.hw_confirmed)


def open_mega(port, dry_run=True, serial_factory=None):
    """bring-up helper: (MegaClient, transport) on one port, dry run unless told otherwise"""
    bb = make_real_bench(port_mega=port, dry_run=dry_run, serial_factory=serial_factory)
    return bb.mega, bb.transport


# ======================================================================= offline checks (no ports)
FIRMWARE = paths.REPO / 'firmware' / 'mega'
SKETCH = FIRMWARE / 'wlb_mega'
HOST_TEST_SRC = FIRMWARE / 'host_test' / 'test_protocol_core.cpp'
SO101_MJCF = paths.SIM_ROOT / 'third_party' / 'so101' / 'so101_new_calib.xml'


def find_cxx():
    for name in (os.environ.get('CXX'), 'c++', 'clang++', 'g++'):
        if name and shutil.which(name): return shutil.which(name)
    return None


def build_firmware_host_test(out_dir, cxx=None, sanitize=True):
    """compile firmware/mega/host_test with the system C++ compiler. Returns dict(exe, cxx, sanitizers, warnings).
    Raises FileNotFoundError when there is no compiler, RuntimeError when compilation fails."""
    cxx = cxx or find_cxx()
    if not cxx: raise FileNotFoundError('no C++ compiler (c++, clang++ or g++) on PATH')
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    exe = out_dir / ('test_protocol_core' + ('.exe' if os.name == 'nt' else ''))
    base = [cxx, '-std=c++11', '-O1', '-g', '-Wall', '-Wextra', '-o', str(exe), str(HOST_TEST_SRC), str(SKETCH / 'protocol_core.cpp')]
    attempts = ([base[:1] + ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] + base[1:]] if sanitize else []) + [base]
    err = ''
    for i, cmd in enumerate(attempts):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            return dict(exe=exe, cxx=cxx, sanitizers=sanitize and i == 0, warnings=r.stderr.strip())
        err = r.stderr
    raise RuntimeError('firmware host test does not compile:\n' + err[-4000:])


def dump_firmware_config(exe):
    r = subprocess.run([str(exe), '--dump-config'], capture_output=True, text=True, check=True)
    out = {}
    for line in r.stdout.splitlines():
        _, k, v = line.split(' ', 2); out[k] = v if k == 'fw_id' else float(v)
    return out


def firmware_config_expected(P=None):
    """the firmware defaults as they must be, from bench_params.toml and protocol.Limits"""
    P = P or _params(); lim = protocol.Limits(P); C, S, A, M = P['carousel'], P['stage'], P['auger'], P['mega']
    return {
        'tt_lo_deg': lim.tt_deg[0], 'tt_hi_deg': lim.tt_deg[1], 'tt_ms_per_45': lim.tt_ms_per_45, 'st_lo_deg': lim.st_deg[0],
        'st_hi_deg': lim.st_deg[1], 'st_ms_min': lim.st_ms_min, 'aug_rev_max': lim.aug_rev_max,
        'wdt_ms': M['wdt_ms'], 'tt_extra_ms': C['timeout_extra_s'] * 1000, 'st_extra_ms': S['timeout_extra_s'] * 1000,
        'settle_ms': M['settle_ms'], 'aug_timeout_ms': A['dose_timeout_s'] * 1000, 'progress_ms': M['progress_ms'],
        'estop_release_ms': M['estop_release_ms'], 'hx_timeout_min_ms': M['hx_timeout_min_ms'],
        'hx_timeout_intervals': M['hx_timeout_intervals'], 'tare_samples': M['tare_samples'],
        'hx_nominal_ms': 1000.0 / P['scale']['rate_hz'], 'counts_per_g': P['scale']['counts_per_g'],
        'tt.us_at_zero': M['tt_us_at_zero'], 'tt.us_per_deg': M['tt_us_per_deg'], 'st.us_at_zero': M['st_us_at_zero'],
        'st.us_per_deg': M['st_us_per_deg'], 'us_min': M['servo_us_min'], 'us_max': M['servo_us_max'],
        'home_tt_deg': M['home_tt_deg'], 'home_st_deg': S['work_deg'], 'aug_us_stop': M['aug_us_stop'],
        'aug_us_offset': M['aug_us_offset'], 'aug_dir_sign': M['aug_dir_sign'], 'aug_fb_sign': M['aug_fb_sign'],
        'aug_adc_min': M['aug_fb_adc_min'], 'aug_adc_max': M['aug_fb_adc_max'], 'stall_window_ms': A['stall_window_s'] * 1000,
        'stall_min_deg': A['stall_min_deg'], 'max_stalls': A['max_stalls'], 'reverse_deg': A['reverse_rev'] * 360.0,
        'fb_max_step_deg': M['aug_fb_max_step_deg'], 'fb_glitch_resync': M['aug_fb_glitch_resync'],
        'aug_timed': 1.0 if M['aug_timed'] else 0.0, 'tt_release': 1.0 if M['tt_release'] else 0.0, 'tt_closed': 1.0 if M['tt_closed'] else 0.0,
        **{k: float(M[k]) for k in ('tt_adc_min', 'tt_adc_max', 'tt_fb_sign', 'tt_dir_sign', 'tt_fb_zero_deg', 'tt_us_stop', 'tt_us_db', 'tt_kp', 'tt_kd', 'tt_max_off', 'tt_tol_deg', 'tt_db_deg')}, 'aug_rev_per_s': M['aug_rev_per_s'], 'aug_start_ms': M['aug_start_ms'], 'aug_coast_rev': M['aug_coast_rev'],
    }


def firmware_config_parity(dump, P=None, tol=1e-3):
    """[(name, firmware, expected)] for every mismatch (empty = the compiled-in defaults match bench_params)"""
    want = firmware_config_expected(P)
    return [(k, dump.get(k), v) for k, v in want.items() if k not in dump or abs(dump[k] - v) > tol * max(1.0, abs(v))]


# -------------------------------------------------- the host-test script (lines from protocol.encode)
def expected_reply(line, lim, current):
    """(seq the firmware echoes, first reply kind) for a fresh idle Mega, from protocol.decode/validate.
    kind: ack | ok | none | err:CODE"""
    try: msg = protocol.decode(line)
    except protocol.ProtocolError as e: return -1, 'err:' + e.code
    s = msg.get('seq')
    seq = int(s) if isinstance(s, int) and -2 ** 31 <= s < 2 ** 31 else -1
    try: name = protocol.validate(msg, lim, current)
    except protocol.ProtocolError as e: return seq, 'err:' + e.code
    return seq, 'none' if name == 'HB' else 'ack' if name in protocol.MOTION else 'ok'


def validation_vectors(lim):
    """[(line, note)] for the validation-parity check: every command at, inside and outside its limits, wrong types,
    unknown commands, seq variants, CRC/whitespace/raw-JSON variants. Current position TT 0 / ST 0."""
    seq = itertools.count(1000)
    out = []

    def m(cmd, **kw):
        d = dict(cmd=cmd, **kw); d.setdefault('seq', next(seq)); out.append((protocol.encode(d).rstrip('\n'), 'encode')); return d

    for c in ('PING', 'HB', 'STOP', 'CLR', 'TARE'): m(c)
    m('CLR', home=True); m('STREAM', on=True); m('STREAM', on=False); m('STREAM', on=1); m('STREAM', on='yes'); m('STREAM')
    for k in (420.0, 10, 10000, 9.99, 10000.5, -5, '420', None, True): m('CAL', counts_per_g=k)
    m('CAL')
    for deg in (lim.tt_deg[0], lim.tt_deg[0] - 0.1, lim.tt_deg[1], lim.tt_deg[1] + 0.1, 0, 45, 90.5, -400, 1e6):
        need = lim.tt_ms_per_45 * abs(deg) / 45.0; edge = math.ceil(need - 50)
        for ms in sorted({edge, edge - 1, int(need) + 1000, 0, -40, -60}):
            if deg == 0 and ms == 0: continue           # SimMega divides by a zero duration here (see handoff); fw-only below
            m('TT', deg=deg, ms=ms)
    for deg in (lim.st_deg[0], lim.st_deg[0] - 0.1, lim.st_deg[1], lim.st_deg[1] + 0.1, 0, 150, 170, 75.5):
        for ms in (lim.st_ms_min, lim.st_ms_min - 1, 2500, 0): m('ST', deg=deg, ms=ms)
    for rev in (0, 0.001, 1, 7.25, lim.aug_rev_max, lim.aug_rev_max + 0.01, -1, 60):
        for d in (1, -1): m('AUG', rev=rev, dir=d)
    for d in (0, 2, 1.0, -1.0, True, False, '1', None): m('AUG', rev=1, dir=d)
    m('AUG', rev=1); m('AUG', rev='1', dir=1); m('TT', deg='90', ms=4000); m('TT', deg=90); m('TT', deg=True, ms=4000); m('ST', ms=3000)
    for c in ('FLY', '', 'ping', 'Tt', 5, None): m(c)
    out.append((protocol.encode(dict(seq=next(seq))).rstrip('\n'), 'no cmd'))
    for s in (None, 1.5, '3', -4, 0, True, False, 2 ** 31 - 1):
        out.append((protocol.encode(dict(cmd='PING', seq=s)).rstrip('\n'), 'seq %r' % (s,)))
    out.append((protocol.encode(dict(cmd='PING')).rstrip('\n'), 'missing seq'))
    out.append((protocol.encode(dict(cmd='PING', seq=next(seq), extra='x')).rstrip('\n'), 'extra key'))
    # framing variants of encoded lines
    for d in (dict(cmd='TT', seq=next(seq), deg=90.0, ms=4000), dict(cmd='AUG', seq=next(seq), rev=2.5, dir=-1), dict(cmd='PING', seq=next(seq))):
        line = protocol.encode(d).rstrip('\n')
        crc = line[-4:-2]; bad = '%02x' % (int(crc, 16) ^ 0x01)
        out += [(line[:-4] + crc.upper() + line[-2:], 'upper-case CRC'), (line[:-4] + bad + line[-2:], 'wrong CRC'),
                (line.replace('"seq":', '"seq":9', 1), 'body changed after the CRC'), (json.dumps(d), 'no CRC, spaces'),
                ('  ' + line + ' \t\r', 'padded'), (line[:-1], 'truncated')]
    raw = ['', 'hello', '{"cmd":"PING","seq":7}', '{"cmd":"PING","seq":9,"seq":10}', '{"cmd":"PING","seq":01}',
           '{"cmd":"PING","seq":11,}', '[1,2]', '{"cmd":"PING","seq":12}xx', '{"cmd":"P\\u0049NG","seq":13}',
           '{"cmd":"PING","seq":14,"crc":"zz"}', '{"cmd":"PING","crc":"00","seq":15}', '{"cmd":"PING","seq":16,"x":null}',
           '{ "cmd" : "STREAM" , "on" : true , "seq" : 17 }', '{"cmd":"TT","seq":18,"deg":9e1,"ms":4.0e3}',
           '{"cmd":"TT","seq":19,"deg":-0,"ms":1E2}', '{"cmd":"PING","seq":-0}', '{"cmd":"PING","seq":1e0}']
    out += [(r, 'raw') for r in raw]
    return out


class _Script:
    def __init__(self):
        self.lines = []; self.seq = 0

    def add(self, s):
        self.lines.append(s)

    def send(self, cmd, **kw):
        self.seq += 1; self.add('send ' + protocol.encode(dict(cmd=cmd, seq=self.seq, **kw)).rstrip('\n')); return self.seq

    def run(self, ms, hb=True):
        """advance time; with hb, a heartbeat every 100 ms as MegaClient sends while waiting"""
        while ms > 0:
            step = min(100, ms) if hb else ms
            self.add('run %d' % step); ms -= step
            if hb and ms > 0: self.send('HB')

    def cmd(self, cmd, kind, run=5, **kw):
        s = self.send(cmd, **kw); self.run(run); self.add('expect %d %s' % (s, kind)); return s


def firmware_test_script(P=None):
    """script for firmware/mega/host_test (format in test_protocol_core.cpp). Lines without a prefix are checked
    against both the firmware core and, in tests/test_firmware_core.py, the simulated Mega; 'fw ' lines are
    firmware-only behaviour (documented in firmware/mega/README.md)."""
    P = P or _params(); lim = protocol.Limits(P); cur = dict(tt_deg=0.0, st_deg=0.0); S = _Script()
    S.add('# generated by benchsim.backends.real.firmware_test_script')
    S.add('cfg plant_rev_s %r' % P['auger']['rev_s'])
    # CRC agreement with protocol.crc8
    rng = random.Random(7)
    texts = [protocol.encode(dict(cmd='TT', seq=i, deg=rng.uniform(-10, 280), ms=rng.randint(0, 9000)))[:-13] + '}' for i in range(20)]
    texts += [''.join(rng.choice('abcdefghijklmnopqrstuvwxyz0123456789{}":,. -') for _ in range(rng.randint(1, 60))) for _ in range(20)]
    for t in texts: S.add('crc %02x %s' % (protocol.crc8(t.encode()), t))
    # validation parity: every vector's first reply must equal protocol.decode/validate's verdict
    for line, _ in validation_vectors(lim):
        seq, kind = expected_reply(line, lim, cur); S.add('v %d %s %s' % (seq, kind, line))
    for line in (protocol.encode(dict(cmd='TT', seq=1, deg=0, ms=0)).rstrip('\n'), protocol.encode(dict(cmd='TT', seq=2, deg=0.0, ms=0.0)).rstrip('\n')):
        seq, kind = expected_reply(line, lim, cur); S.add('fw v %d %s %s' % (seq, kind, line))

    S.add('# --- scale stream, tare, CAL'); S.add('reset')
    S.cmd('PING', 'ok'); S.cmd('STREAM', 'ok', on=True); S.add('mark'); S.run(1000); S.add('expect_samples 78 82')
    S.cmd('TARE', 'ok', run=150); S.cmd('CAL', 'ok', counts_per_g=420.0); S.cmd('STREAM', 'ok', on=False)
    S.add('mark'); S.run(300); S.add('expect_samples 0 1')

    S.add('# --- carousel move, BUSY rules, stage moves'); S.add('reset')
    s1 = S.cmd('TT', 'ack', deg=90.0, ms=4000); S.run(1000)
    S.cmd('ST', 'err:BUSY', deg=150.0, ms=2500); S.cmd('AUG', 'err:BUSY', rev=1.0, dir=1); S.cmd('TT', 'err:BUSY', deg=0.0, ms=8000)
    S.cmd('STREAM', 'ok', on=True); S.cmd('TARE', 'ok', run=150); S.cmd('STREAM', 'ok', on=False)
    S.run(3600); S.add('expect_done %d 1' % s1); S.add('fw expect_known tt 1'); S.add('fw expect_out tt on'); S.add('fw expect_out st off')
    S.add('fw expect_persist tt 1 90.0')
    S.cmd('TT', 'err:RANGE', deg=0.0, ms=3000)                    # 90 deg back needs >= 4000 - 50 ms
    s = S.cmd('ST', 'ack', deg=150.0, ms=2500); S.run(3000); S.add('expect_done %d 1' % s); S.add('fw expect_out st on')
    s = S.cmd('ST', 'ack', deg=0.0, ms=2500); S.run(3000); S.add('expect_done %d 1' % s); S.add('fw expect_out aug off')

    S.add('# --- comm watchdog'); S.add('reset')
    S.cmd('PING', 'ok'); S.run(1000, hb=False); S.add('expect_fault WDT 0')          # idle: no watchdog
    s1 = S.cmd('TT', 'ack', deg=45.0, ms=4000); S.run(700, hb=False); S.add('expect_fault WDT 1'); S.add('expect_done %d 0' % s1)
    S.add('fw expect_out tt off'); S.add('fw expect_known tt 0')
    S.cmd('TT', 'err:STATE', deg=0.0, ms=4000); S.cmd('CLR', 'ok', home=True); S.add('fw expect_known tt 1')
    s = S.cmd('TT', 'ack', deg=0.0, ms=4000); S.run(4500); S.add('expect_done %d 1' % s)

    S.add('# --- e-stop latch'); S.add('reset')
    s1 = S.cmd('TT', 'ack', deg=90.0, ms=4000); S.run(1000); S.add('estop 1'); S.run(20)
    S.add('expect_fault ESTOP 1'); S.add('fw expect_out tt off'); S.run(1000); S.add('expect_done %d 0' % s1)
    S.cmd('TT', 'err:ESTOP', deg=0.0, ms=8000); S.cmd('STOP', 'ok'); S.cmd('STREAM', 'ok', on=True); S.cmd('STREAM', 'ok', on=False); S.cmd('CLR', 'err:STATE')   # scale stays usable while latched
    S.add('estop 0'); S.run(600); S.cmd('CLR', 'ok', home=True); S.cmd('PING', 'ok')
    s = S.cmd('TT', 'ack', deg=0.0, ms=3000); S.run(3500); S.add('expect_done %d 1' % s)

    S.add('# --- auger dose, progress, reverse'); S.add('reset'); S.add('mark')
    s = S.cmd('AUG', 'ack', rev=2.0, dir=1); S.run(3500)
    S.add('expect_done %d 1' % s); S.add('expect_num %d rev 1.99 2.02' % s); S.add('expect_num %d stalls 0 0' % s)
    S.add('expect_progress %d 5' % s); S.add('fw expect_out aug off')
    S.add('fw expect_plant_deg 715 725')                                  # 2 rev forward (reverse_rev 0: no turn back)

    S.add('# --- jammed auger: 3 stalls -> AUGER_JAM'); S.add('reset'); S.add('jam 1')
    s = S.cmd('AUG', 'ack', rev=3.0, dir=1); S.run(3000); S.add('expect_fault AUGER_JAM 1'); S.add('expect_done %d 0' % s)
    S.add('fw expect_out aug off'); S.cmd('AUG', 'err:STATE', rev=1.0, dir=1); S.add('jam 0'); S.cmd('CLR', 'ok')
    s = S.cmd('AUG', 'ack', rev=1.0, dir=1); S.run(2500); S.add('expect_done %d 1' % s)

    S.add('# --- screw held by hand for 400 ms: stall, reverse 1/4, retry, finish'); S.add('reset')
    s = S.cmd('AUG', 'ack', rev=3.0, dir=1); S.run(600); S.add('jam 1'); S.run(400); S.add('jam 0'); S.run(6000)
    S.add('expect_done %d 1' % s); S.add('expect_num %d stalls 1 2' % s); S.add('expect_fault AUGER_JAM 0')

    S.add('# --- HX711 silent -> HX_TIMEOUT'); S.add('reset')
    S.cmd('STREAM', 'ok', on=True); S.run(200); S.add('hx 0'); S.run(300); S.add('expect_fault HX_TIMEOUT 1')
    S.cmd('TARE', 'err:STATE'); S.add('hx 1'); S.cmd('CLR', 'ok'); S.cmd('TARE', 'ok', run=150); S.cmd('STREAM', 'ok', on=False)

    S.add('# --- STOP during AUG and TT'); S.add('reset')
    s1 = S.cmd('AUG', 'ack', rev=5.0, dir=1); S.run(500); S.cmd('STOP', 'ok'); S.run(300); S.add('expect_done %d 0' % s1); S.add('fw expect_out aug off')
    s1 = S.cmd('TT', 'ack', deg=90.0, ms=4000); S.run(1000); S.cmd('STOP', 'ok'); S.run(500); S.add('expect_done %d 0' % s1)
    S.add('fw expect_known tt 1'); S.add('fw expect_out tt on')
    s = S.cmd('TT', 'ack', deg=90.0, ms=4000); S.run(4500); S.add('expect_done %d 1' % s)

    S.add('# --- firmware only: boot state, unknown position, CLR home'); S.add('fw reset unknown')
    S.add('fw expect_out tt off'); S.add('fw expect_out st off'); S.add('fw expect_out aug off')
    for c, kind, kw in (('PING', 'ok', {}), ('TT', 'err:STATE', dict(deg=10.0, ms=2000)), ('ST', 'err:STATE', dict(deg=10.0, ms=2000)),
                        ('CLR', 'ok', {}), ('TT', 'err:STATE', dict(deg=10.0, ms=2000)), ('CLR', 'ok', dict(home=True))):
        S.seq += 1; S.add('fw send ' + protocol.encode(dict(cmd=c, seq=S.seq, **kw)).rstrip('\n')); S.add('fw run 5'); S.add('fw expect %d %s' % (S.seq, kind))
    S.add('fw expect_out tt off')                                       # homing does not start pulses
    S.seq += 1; S.add('fw send ' + protocol.encode(dict(cmd='TT', seq=S.seq, deg=10.0, ms=2000)).rstrip('\n')); S.add('fw run 5')
    S.add('fw expect %d ack' % S.seq); S.add('fw expect_out tt on'); S.add('fw expect_persist tt 0 0.0')

    S.add('fw reset known tt=90 st=150')
    S.seq += 1; S.add('fw send ' + protocol.encode(dict(cmd='PING', seq=S.seq)).rstrip('\n')); S.add('fw run 5')
    S.add('fw expect_num %d tt 89.99 90.01' % S.seq); S.add('fw expect_num %d st 149.99 150.01' % S.seq)
    S.add('fw long 300'); S.add('fw run 5'); S.add('fw expect -1 err:BADCMD')

    S.add('fw reset'); S.add('fw estop 1'); S.add('fw run 10'); S.add('fw estop 0'); S.add('fw run 100')
    for kind, wait in (('err:STATE', 500), ('ok', 5)):
        S.seq += 1; S.add('fw send ' + protocol.encode(dict(cmd='CLR', seq=S.seq)).rstrip('\n')); S.add('fw run %d' % wait)
        S.add('fw expect %d %s' % (S.seq, kind))

    S.add('# firmware only: open-loop TT timeout (settle longer than the extra time)')
    S.add('fw cfg settle_ms 3000'); S.add('fw reset')
    S.seq += 1; S.add('fw send ' + protocol.encode(dict(cmd='TT', seq=S.seq, deg=10.0, ms=500)).rstrip('\n'))
    for _ in range(26): S.seq += 1; S.add('fw run 100'); S.add('fw send ' + protocol.encode(dict(cmd='HB', seq=S.seq)).rstrip('\n'))
    S.add('fw expect_fault TT_TIMEOUT 1'); S.add('fw expect_out tt off'); S.add('fw expect_known tt 0'); S.add('fw cfgclear')

    S.add('# firmware only: dose timeout, both-way jam, feedback glitch')
    S.add('fw cfg aug_timeout_ms 1000'); S.add('fw reset')
    S.seq += 1; S.add('fw send ' + protocol.encode(dict(cmd='AUG', seq=S.seq, rev=3.0, dir=1)).rstrip('\n'))
    for _ in range(12): S.seq += 1; S.add('fw run 100'); S.add('fw send ' + protocol.encode(dict(cmd='HB', seq=S.seq)).rstrip('\n'))
    S.add('fw expect_fault AUG_TIMEOUT 1'); S.add('fw expect_out aug off'); S.add('fw cfgclear')
    S.add('fw reset'); S.add('fw jam 2')
    S.seq += 1; a = S.seq; S.add('fw send ' + protocol.encode(dict(cmd='AUG', seq=a, rev=1.0, dir=1)).rstrip('\n'))
    for _ in range(10): S.seq += 1; S.add('fw run 100'); S.add('fw send ' + protocol.encode(dict(cmd='HB', seq=S.seq)).rstrip('\n'))
    S.add('fw expect_fault AUGER_JAM 1'); S.add('fw expect_done %d 0' % a)
    # A2 glitch: 2.0 s into a 2.4 s dose the reading jumps 170 deg the way the dose turns, for 8 ms. A jump that
    # early in a dose is absorbed by the high-water count anyway; near the end it would stop the dose early.
    for gate, rev, plant in (('', '1.99 2.02', '-725 -715'), ('fw cfg fb_max_step_deg 400', '2.05 2.5', '-705 -500')):
        if gate: S.add('# negative control: without the glitch gate the same glitch stops the dose early'); S.add(gate)
        S.add('fw reset')
        S.seq += 1; a = S.seq; S.add('fw send ' + protocol.encode(dict(cmd='AUG', seq=a, rev=2.0, dir=-1)).rstrip('\n'))
        for i in range(35):
            if i == 20: S.add('fw glitch 8 -170')
            S.seq += 1; S.add('fw run 100'); S.add('fw send ' + protocol.encode(dict(cmd='HB', seq=S.seq)).rstrip('\n'))
        S.add('fw expect_done %d 1' % a); S.add('fw expect_num %d rev %s' % (a, rev)); S.add('fw expect_plant_deg %s' % plant)
    S.add('fw cfgclear')
    # timed auger (no A2 wire, the bench default since 2026-10-17): 1 rev at 2 rev/s = 500 ms after aug_start_ms of spin-up.
    # A jammed screw is invisible in this mode: the dose still completes and no AUGER_JAM is raised.
    S.add('# firmware only: timed auger, no feedback wire'); S.add('fw cfg aug_timed 1'); S.add('fw cfg aug_rev_per_s 2'); S.add('fw cfg aug_start_ms 300'); S.add('fw cfg aug_coast_rev 0'); S.add('fw reset'); S.add('fw jam 1')
    S.seq += 1; a = S.seq; S.add('fw send ' + protocol.encode(dict(cmd='AUG', seq=a, rev=1.0, dir=1)).rstrip('\n'))
    for i in range(12):
        if i == 7: S.add('fw expect_done %d 0' % a)     # 700 ms: still in the 300 + 500 ms dose
        S.seq += 1; S.add('fw run 100'); S.add('fw send ' + protocol.encode(dict(cmd='HB', seq=S.seq)).rstrip('\n'))
    S.add('fw expect_done %d 1' % a); S.add('fw expect_num %d rev 0.99 1.02' % a); S.add('fw expect_num %d stalls 0 0' % a)
    S.add('fw expect_fault AUGER_JAM 0'); S.add('fw expect_out aug off'); S.add('fw jam 0'); S.add('fw cfgclear')
    return '\n'.join(S.lines) + '\n'


def run_firmware_host_test(exe, script_text, timeout=120):
    """run the compiled host test on a script. Returns dict(ok, passed, failed, failures, out_lines, returncode)."""
    r = subprocess.run([str(exe), '-'], input=script_text.encode('ascii'), capture_output=True, timeout=timeout)
    text = r.stdout.decode('ascii', errors='replace')
    out_lines = [l[4:] for l in text.splitlines() if l.startswith('OUT ')]
    fails = [l[5:] for l in text.splitlines() if l.startswith('FAIL ')]
    summ = [l for l in text.splitlines() if l.startswith('SUMMARY ')]
    p = f = None
    if summ:
        kv = dict(x.split('=') for x in summ[-1].split()[1:]); p, f = int(kv['pass']), int(kv['fail'])
    return dict(ok=r.returncode == 0 and f == 0, passed=p, failed=f, failures=fails, out_lines=out_lines, returncode=r.returncode,
                stderr=r.stderr.decode('ascii', errors='replace')[-2000:])


def _compact(body):
    """no whitespace outside JSON strings"""
    in_str = esc = False
    for c in body:
        if in_str:
            esc, in_str = (False, True) if esc else (c == '\\', c != '"')
        elif c == '"': in_str = True
        elif c in ' \t\r\n': return False
    return True


def check_output_lines(lines):
    """every firmware line must pass protocol.decode (CRC) and be compact with sorted keys; returns problems"""
    bad = []
    for line in lines:
        try: msg = protocol.decode(line)
        except protocol.ProtocolError as e: bad.append('%s: %s' % (line, e)); continue
        if list(msg) != sorted(msg) or not _compact(line.strip()[:-protocol.CRC_TAIL] + '}'): bad.append('not compact/sorted: ' + line)
    return bad


def compile_sketch(build_dir):
    """compile the sketch for the Mega 2560 with arduino-cli if it and the arduino:avr core are installed.
    Returns ('PASS'|'FAIL'|'SKIP', detail). Never installs anything (no network)."""
    cli = shutil.which('arduino-cli')
    if not cli: return 'SKIP', 'arduino-cli not installed'
    cores = subprocess.run([cli, 'core', 'list'], capture_output=True, text=True)
    if 'arduino:avr' not in cores.stdout: return 'SKIP', 'arduino-cli has no arduino:avr core (arduino-cli core install arduino:avr)'
    r = subprocess.run([cli, 'compile', '--fqbn', 'arduino:avr:mega:cpu=atmega2560', '--build-path', str(build_dir), str(SKETCH)],
                       capture_output=True, text=True)
    tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
    return ('PASS' if r.returncode == 0 else 'FAIL'), ' | '.join(tail)


def mjcf_joint_ranges_deg(path=SO101_MJCF):
    """{joint: (lo, hi)} in degrees from the fetched so101_new_calib.xml (XML only, no MuJoCo), or None"""
    if not Path(path).exists(): return None
    import xml.etree.ElementTree as ET
    out = {}
    for j in ET.parse(path).iter('joint'):
        if j.get('name') in JOINTS and j.get('range'):
            lo, hi = (float(x) for x in j.get('range').split()); out[j.get('name')] = (math.degrees(lo), math.degrees(hi))
    return out


def offline_checks(calibration_path=None, build_dir=None, log=print):
    """the `python -m benchsim hw-check` checks. Opens no port and imports neither pyserial nor lerobot.
    Returns rows dict(check, status PASS|FAIL|SKIP|INFO, detail)."""
    rows = []

    def row(check, status, detail=''):
        rows.append(dict(check=check, status=status, detail=detail))
        if log: log('%-4s %-52s %s' % (status, check, detail))

    loaded = [m for m in ('serial', 'lerobot') if m in sys.modules]
    row('benchsim.backends.real imports without pyserial/lerobot', 'FAIL' if loaded else 'PASS', 'already imported: %s' % loaded if loaded else '')
    for mod, why in (('serial', 'Mega port'), ('lerobot', 'arm buses')):
        row('optional dependency %s (%s)' % (mod, why), 'INFO', 'installed' if importlib.util.find_spec(mod) else "not installed (pip install -e '.[hardware]')")
    P = _params()
    row('[mega] baud matches electrical.md 4', 'PASS' if P['mega']['baud'] == 250000 else 'FAIL', str(P['mega']['baud']))
    path = Path(calibration_path or EXAMPLE_CALIBRATION)
    try:
        cal = json.loads(path.read_text()); ranges = mjcf_joint_ranges_deg()
        errs = validate_calibration(cal, ranges)
        row('calibration schema: %s' % path.name, 'FAIL' if errs else 'PASS',
            '; '.join(errs[:4]) if errs else 'joint limits %s' % ('checked against the MJCF' if ranges else 'not checked (SO-101 model not fetched)'))
        if not errs and 'example' in str(cal.get('status', '')).lower():
            row('calibration values measured', 'INFO', 'example placeholders: record them at bring-up (docs/bringup.md A1-A5)')
    except (OSError, json.JSONDecodeError) as e:
        row('calibration schema: %s' % path.name, 'FAIL', str(e))
    build_dir = Path(build_dir or paths.RUNS / 'firmware_host_test')
    try:
        b = build_firmware_host_test(build_dir)
        row('firmware core compiles on the host', 'PASS', '%s%s%s' % (Path(b['cxx']).name, ', ASan/UBSan' if b['sanitizers'] else '',
                                                                       ', warnings: ' + b['warnings'][:200] if b['warnings'] else ''))
    except FileNotFoundError as e:
        row('firmware core compiles on the host', 'SKIP', str(e)); b = None
    except RuntimeError as e:
        row('firmware core compiles on the host', 'FAIL', str(e)[-300:]); b = None
    if b:
        mism = firmware_config_parity(dump_firmware_config(b['exe']), P)
        row('firmware constants == bench_params.toml', 'FAIL' if mism else 'PASS', '; '.join('%s fw %s want %s' % m for m in mism[:5]))
        res = run_firmware_host_test(b['exe'], firmware_test_script(P))
        row('firmware host test (protocol parity, scenarios)', 'PASS' if res['ok'] else 'FAIL',
            '%s passed, %s failed%s' % (res['passed'], res['failed'], ('; ' + ' | '.join(res['failures'][:3])) if res['failures'] else ''))
        bad = check_output_lines(res['out_lines'])
        row('firmware output decodes with protocol.decode', 'FAIL' if bad or not res['out_lines'] else 'PASS',
            '%d lines%s' % (len(res['out_lines']), ('; ' + bad[0]) if bad else ''))
    st, detail = compile_sketch(build_dir / 'arduino')
    row('sketch compiles for the Mega 2560 (arduino-cli)', st, detail)
    loaded = [m for m in ('serial', 'lerobot') if m in sys.modules]
    row('no serial port opened, no lerobot import', 'FAIL' if loaded else 'PASS', 'imported: %s' % loaded if loaded else '')
    return rows
