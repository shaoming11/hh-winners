"""Hardware emulator: the real-hardware code path (LeRobotArm on a Feetech bus, MegaClient over SerialTransport) with
the USB devices replaced by the MuJoCo simulator.

    bb = make_bench('sim')                       # or the backend's own live sim bench
    hw = make_emulated_bench(bb)                 # BenchBackends('real', ...) whose devices are bb's world
    hw.arms['pourer'].set_torque(True)           # LeRobotArm -> SimServoBus -> SimArm
    hw.mega.motion('TT', 5, deg=90.0, ms=2000)   # SerialTransport -> LoopbackSerial -> SimMega

Everything above the bus is the code that drives the real bench: joint maps from the calibration JSON, the
fingerprint check, torque-on-without-snap, per-joint Goal_Velocity, write verification, the serial line framing.
Only the registers and the serial port are stand-ins:

- ``SimServoBus`` is a Feetech bus (``connect``/``disconnect``/``read(reg)``/``write(reg, values)``, raw ticks)
  whose Present_Position is the SimArm's joint angle mapped through the arm's calibration, and whose
  Goal_Position / Goal_Velocity / Torque_Enable writes drive that SimArm. It reports the calibration's recorded
  fingerprint, so ``check_fingerprint`` passes as it does on the right port.
- The Mega is ``LoopbackSerial`` (already in backends.real) on the sim bench's Mega transport, so the firmware
  emulation (SimMega) answers and the dashboard's wire panel still sees the traffic.

Time is the sim bench's clock: ``hw.clock`` advances the world on sleep, so a caller that waits with
``hw.clock.sleep`` sees the arms move. Nothing here opens a port or imports pyserial / lerobot.
"""
import math

import numpy as np

from .. import paths
from ..interfaces import BenchBackends, MegaClient
from . import real

BENCH_CALIBRATION = paths.CONFIG / 'hardware_calibration.bench.json'


class SimServoBus:
    """a LeRobotArm bus (raw registers, ticks) backed by a SimArm"""

    def __init__(self, sim_arm, arm_cal, ticks_per_rev, sts):
        self.arm = sim_arm; self.cal = arm_cal; self.map = real.JointMap(arm_cal, ticks_per_rev)
        self.tpr = ticks_per_rev; self.sts = sts; self.connected = False
        self.clipped = []                                  # goals past the MJCF range, clipped (see write)
        fp = arm_cal.get('fingerprint') or {n: [0, 0, ticks_per_rev - 1] for n in real.JOINTS}
        self.regs = {'Homing_Offset': {n: fp[n][0] for n in real.JOINTS},
                     'Min_Position_Limit': {n: fp[n][1] for n in real.JOINTS},
                     'Max_Position_Limit': {n: fp[n][2] for n in real.JOINTS},
                     'Acceleration': {n: 0 for n in real.JOINTS}, 'Goal_Velocity': {n: 0 for n in real.JOINTS}}
        self.regs['Goal_Position'] = self._present()

    # the arm's own SimArm (a Feed's TappedArm forwards attributes, so wrapped arms work too)
    def _q(self):
        return np.asarray(self.arm.read_positions(), float)

    def _present(self):
        return self.map.q_to_ticks(self._q())

    def connect(self): self.connected = True

    def disconnect(self): self.connected = False

    def read(self, reg):
        if not self.connected: raise ConnectionError('bus not connected')
        if reg == 'Present_Position': return self._present()
        if reg == 'Torque_Enable': return {n: int(bool(self.arm.torque_enabled())) for n in real.JOINTS}
        if reg == 'Moving': return {n: int(bool(self.arm.is_moving())) for n in real.JOINTS}
        if reg == 'Present_Load':
            loads = np.asarray(self.arm.read_loads(), float) / self.sts['load_unit_permille']
            return {n: (0x400 | min(int(round(-v)), 0x3FF)) if v < 0 else min(int(round(v)), 0x3FF) for n, v in zip(real.JOINTS, loads)}
        return dict(self.regs[reg])

    def write(self, reg, values):
        if not self.connected: raise ConnectionError('bus not connected')
        values = {n: int(v) for n, v in values.items()}
        self.regs.setdefault(reg, {}).update(values)
        if reg == 'Torque_Enable':
            on = any(self.regs['Torque_Enable'].values())
            if on != bool(self.arm.torque_enabled()): self.arm.set_torque(on)
        elif reg == 'Goal_Position':
            if not self.arm.torque_enabled(): return                         # a servo ignores goals with torque off
            goal = self.regs['Goal_Position']
            q = self.map.ticks_to_q({n: goal.get(n, 0) for n in real.JOINTS})
            # the calibrated limits (what the real servo takes) can reach past the MJCF joint range: the sim arm goes
            # as far as it can instead of refusing a goal the hardware would accept
            w = self.arm.w; aid = self.arm.aid
            lo, hi = w.m.actuator_ctrlrange[aid, 0], w.m.actuator_ctrlrange[aid, 1]
            qc = np.clip(q, lo, hi)
            if np.any(np.abs(qc - q) > 1e-6):
                self.clipped.append([round(float(np.degrees(v)), 1) for v in q])
            self.arm.set_goal(qc, speed_scale=self._speed_scale())

    def _speed_scale(self):
        """Goal_Velocity (steps/s per joint) as the SimArm's speed_scale: the fastest joint against the sim's max speed"""
        v = max(self.regs['Goal_Velocity'].values() or [0]) * self.sts['goal_velocity_unit_ticks_s']
        vmax = math.radians(self.arm.w.P['arm']['max_speed_deg_s']) * self.tpr / (2 * math.pi)
        return float(min(max(v / vmax, 0.05), 1.0)) if v > 0 else 1.0


class _MegaDevice:
    """the device side LoopbackSerial wants (receive / drain), over a sim bench's Mega transport"""

    def __init__(self, transport): self.t = transport

    def receive(self, line): self.t.write_line(line)

    def drain(self): return self.t.read_lines()


def make_emulated_bench(sim_bb, calibration_path=None, dry_run=False, with_mega=True, share_mega_log=True):
    """BenchBackends('real') built by backends.real.make_real_bench, its buses and serial port on ``sim_bb``'s world.
    ``share_mega_log`` appends the emulated Mega traffic to the sim bench's MegaClient log (the dashboard wire panel
    reads that log)."""
    cal = real.load_calibration(calibration_path or BENCH_CALIBRATION)
    P = sim_bb.world.P
    sim_arms = dict(sim_bb.arms)

    def bus_factory(port, ids):
        name = port.split(':', 1)[1]
        return SimServoBus(sim_arms[name], cal['arms'][name], cal['ticks_per_rev'], P['sts3215'])

    def serial_factory(**kw):
        return real.LoopbackSerial(_MegaDevice(sim_bb.mega.t), **kw)

    bb = real.make_real_bench(port_mega='emu:mega' if with_mega else None, port_pourer='emu:pourer',
                              port_transfer='emu:transfer', calibration_path=calibration_path or BENCH_CALIBRATION,
                              dry_run=dry_run, serial_factory=serial_factory, bus_factory=bus_factory, params=P)
    bb.clock = sim_bb.clock                    # the world's clock: sleeping moves the sim, nothing waits on the wall
    if bb.mega is not None:
        bb.mega.clock = sim_bb.clock
        if share_mega_log:
            bb.mega.log = sim_bb.mega.log
            pump, host = bb.mega._pump, sim_bb.mega

            def _pump():                       # the sim bench's client is not pumping (this one drains the line):
                pump()                         # hand it the scale sample, so its feed and the dashboard show the weight
                if bb.mega.last_sample is not None: host.last_sample = bb.mega.last_sample
            bb.mega._pump = _pump
    bb.world = sim_bb.world; bb.emulated = True
    return bb
