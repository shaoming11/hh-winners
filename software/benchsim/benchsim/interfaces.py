"""Backend-independent interfaces. The process controller (benchsim.process) only talks to these; the MuJoCo
backend (benchsim.backends.sim) and the hardware backend (benchsim.backends.real) implement them.

Units at this boundary: joint vectors are 6 values in radians in the official SO-101 MJCF convention
(so101_new_calib: shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper). The hardware backend
converts to and from Feetech ticks with its calibration file. Loads are Feetech ``Present_Load`` style: signed
per-mille of the maximum torque.
"""
from typing import Optional, Protocol

import numpy as np

from . import protocol


class Clock(Protocol):
    def now(self) -> float: ...                       # seconds
    def sleep(self, dt: float) -> None: ...           # sim: advances physics; hardware: real sleep


class ArmBackend(Protocol):
    name: str
    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def read_positions(self) -> np.ndarray: ...       # (6,) rad
    def read_loads(self) -> np.ndarray: ...           # (6,) signed per-mille of max torque
    def set_goal(self, q: np.ndarray, speed_scale: float = 1.0) -> None: ...   # rate-limited joint goal
    def set_torque(self, enabled: bool) -> None: ...
    def torque_enabled(self) -> bool: ...
    def is_moving(self) -> bool: ...


class MegaTransport(Protocol):
    def write_line(self, line: str) -> None: ...
    def read_lines(self) -> list: ...                 # complete lines received since the last call


class MegaError(RuntimeError):
    def __init__(self, reply):
        super().__init__('%s: %s' % (reply.get('err') or reply.get('fault'), reply.get('detail', ''))); self.reply = reply
        self.code = reply.get('err') or reply.get('fault')


class MegaClient:
    """host side of the Mega protocol over any transport: sequence numbers, replies, the sample stream, faults"""

    def __init__(self, transport: MegaTransport, clock: Clock):
        self.t = transport; self.clock = clock; self.seq = 0
        self.replies = {}; self.samples = []; self.faults = []; self.progress = {}; self.log = []
        self.last_sample = None; self.last_tx = -1e9; self.keepalive = True
        self.sample_log = []                          # append-only (t_ms, grams, raw) archive for run traces

    def _pump(self):
        for line in self.t.read_lines():
            try: msg = protocol.decode(line)
            except protocol.ProtocolError as e:
                self.log.append(('bad-line', line, str(e))); continue
            if 'w' in msg: self.samples.append(msg); self.last_sample = msg; self.sample_log.append((msg.get('t'), msg['w'], msg.get('raw')))
            elif 'fault' in msg: self.faults.append(msg); self.log.append(('fault', msg))
            elif 'aug' in msg: self.progress[msg['seq']] = msg
            elif 'seq' in msg: self.replies.setdefault(msg['seq'], []).append(msg); self.log.append(('reply', msg))

    def send(self, cmd: str, **args) -> int:
        self.seq += 1; msg = dict(cmd=cmd, seq=self.seq, **args)
        if cmd != 'HB': self.log.append(('send', msg))
        self.t.write_line(protocol.encode(msg)); self.last_tx = self.clock.now()
        return self.seq

    def _keepalive(self):
        """heartbeat every 100 ms while the host is waiting, so the 500 ms comm watchdog only fires if the host dies"""
        if self.keepalive and self.clock.now() - self.last_tx >= 0.1: self.send('HB')

    def wait(self, seq, key=('ack', 'ok', 'err'), timeout=2.0, poll=0.005):
        """first reply to seq that has one of the keys; raises MegaError on err"""
        t_end = self.clock.now() + timeout
        while True:
            self._pump()
            for r in self.replies.get(seq, []):
                if 'err' in r: raise MegaError(r)
                if any(k in r for k in key): return r
            if self.clock.now() >= t_end: raise TimeoutError('no %s for seq %d' % ('/'.join(key), seq))
            self._keepalive(); self.clock.sleep(poll)

    def command(self, cmd, timeout=2.0, **args):
        """send and wait for ack/ok (raises MegaError on err). A successful CLR also clears the host's fault list."""
        r = self.wait(self.send(cmd, **args), timeout=timeout)
        if cmd == 'CLR' and r.get('ok'): self.faults.clear()
        return r

    def motion(self, cmd, done_timeout, heartbeat=0.1, on_tick=None, **args):
        """send a TT/ST/AUG, wait for ack, then for done (heartbeats keep the comm watchdog alive)"""
        seq = self.send(cmd, **args); self.wait(seq, key=('ack',))
        t_end = self.clock.now() + done_timeout; t_hb = self.clock.now()
        while True:
            self._pump()
            for r in self.replies.get(seq, []):
                if r.get('done'): return r
            if self.faults: raise MegaError(self.faults[-1])
            if self.clock.now() >= t_end: raise TimeoutError('%s seq %d not done in %.1f s' % (cmd, seq, done_timeout))
            self._keepalive()
            if on_tick: on_tick()
            self.clock.sleep(0.01)

    def heartbeat(self):
        self.send('HB'); self._pump()

    def take_samples(self):
        self._pump(); s = self.samples; self.samples = []; return s

    def read_mass(self, n=8, timeout=2.0) -> float:
        """mean of the next n scale samples (grams)"""
        self.take_samples(); got = []; t_end = self.clock.now() + timeout
        while len(got) < n:
            self._keepalive(); self.clock.sleep(0.0125); got += self.take_samples()
            if self.clock.now() > t_end: raise TimeoutError('scale stream silent')
        return float(np.mean([s['w'] for s in got[:n]]))


class BenchBackends:
    """what the process controller receives from the single selection entry point (benchsim.bench.make_bench)"""

    def __init__(self, mode, clock, arms, mega: MegaClient, camera=None, world=None):
        self.mode = mode; self.clock = clock; self.arms = arms; self.mega = mega; self.camera = camera; self.world = world
