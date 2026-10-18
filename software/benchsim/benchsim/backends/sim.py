"""MuJoCo simulation backend: world stepping, simulated SO-101 arms and a simulated Arduino Mega.

The simulated Mega consumes and produces the same JSON lines as the firmware (benchsim.protocol). Approximations
(labelled where they appear): servo response is the upstream MJCF position actuator (kp 998, kv 2.7, 3.35 N m)
driven along a rate-limited smoothstep; ``read_loads`` is actuator force over the force limit in per-mille, which
only approximates Feetech Present_Load (that register is a PWM-duty estimate, not a torque measurement); the scale
reads a slide-joint flexure through an HX711 model (80 Hz, counts, noise, one-count quantisation).
"""
import collections
import math

import mujoco
import numpy as np

from .. import protocol, scene, state
from ..units import m, mm


def smoothstep(x):
    x = min(max(x, 0.0), 1.0); return x * x * (3 - 2 * x)


class SimWorld:
    def __init__(self, model=None, builder=None, seed=0, params=None):
        if model is None: model, builder = scene.build()
        self.m = model; self.b = builder; self.d = mujoco.MjData(model); self.P = params or builder.P
        state.reset(model, self.d)
        self.rng = np.random.default_rng(seed); self.plugins = []; self.frame_hooks = []
        self.dt = model.opt.timestep
        self.estop = False; self.hx_fail = False; self.auger_jam = False
        self.welds = {}                                  # (arm, beaker) -> equality id
        for i in range(model.neq):
            n = model.equality(i).name
            if n.startswith('hold_'): _, arm, bk = n.split('_', 2); self.welds[(arm, bk)] = i
        self.held = {}                                   # arm -> beaker
        self.events = []

    @property
    def time(self): return float(self.d.time)

    def add_plugin(self, p):
        self.plugins.append(p); return p

    def step(self):
        for p in self.plugins: p.pre_step(self)
        mujoco.mj_step(self.m, self.d)
        for p in self.plugins: p.post_step(self)
        for h in self.frame_hooks: h(self)

    def advance(self, dt):
        n = max(1, int(round(dt / self.dt)))
        for _ in range(n): self.step()

    def idle(self, dt, chunk=0.05):
        """fast-forward a quiet wait: physics frozen (everything is holding still), analytic models and the Mega
        device keep running. Used only for long waits such as the 60 s yeast activation."""
        t_end = self.d.time + dt
        while self.d.time < t_end - 1e-9:
            h = min(chunk, t_end - self.d.time)
            for p in self.plugins:
                if hasattr(p, 'idle'): p.idle(self, h)
            self.d.time += h
            for hk in self.frame_hooks: hk(self)

    def log(self, kind, **kw):
        self.events.append(dict(t=round(self.time, 4), kind=kind, **kw))

    # ------------------------------------------------------------------ grasp constraint
    def attach(self, arm, beaker):
        """activate the weld between the gripper and the beaker at their current relative pose (the grasp model:
        a rigid constraint switched on only after the grasp is classified from the jaw angle and finger contacts)"""
        e = self.welds[(arm, beaker)]; g = self.m.body('%s/gripper' % arm).id; b = self.m.body('beaker_' + beaker).id
        Rg = self.d.xmat[g].reshape(3, 3); pg = self.d.xpos[g]; Rb = self.d.xmat[b].reshape(3, 3); pb = self.d.xpos[b]
        rel_p = Rg.T @ (pb - pg); rel_R = Rg.T @ Rb; q = np.zeros(4); mujoco.mju_mat2Quat(q, rel_R.reshape(9))
        # weld data: anchor (3), relpose pos (3), relpose quat (4), torquescale (1); relpose = body2 in body1 frame
        self.m.eq_data[e, 0:3] = 0.0; self.m.eq_data[e, 3:6] = rel_p; self.m.eq_data[e, 6:10] = q; self.m.eq_data[e, 10] = 1.0
        self.d.eq_active[e] = 1; self.held[arm] = beaker; self.log('attach', arm=arm, beaker=beaker)
        self._finger_contact(beaker, False)

    def _finger_contact(self, beaker, on):
        """while held, the weld replaces the compliant finger contact: drop the FINGER bit from the beaker's conaffinity"""
        from ..scene import FINGER
        bid = self.m.body('beaker_' + beaker).id
        for g in range(self.m.ngeom):
            if self.m.geom_bodyid[g] == bid and self.m.geom_contype[g]:
                self.m.geom_conaffinity[g] = (self.m.geom_conaffinity[g] | FINGER) if on else (self.m.geom_conaffinity[g] & ~FINGER)

    def detach(self, arm):
        bk = self.held.pop(arm, None)
        if bk is not None: self.d.eq_active[self.welds[(arm, bk)]] = 0; self._finger_contact(bk, True); self.log('detach', arm=arm, beaker=bk)
        return bk

    # ------------------------------------------------------------------ helpers
    def beaker_pose(self, name):
        b = self.d.body('beaker_' + name); return mm(b.xpos.copy()), b.xmat.reshape(3, 3).copy()

    def contacts_between(self, body_prefix_a, body_b):
        out = []
        for i in range(self.d.ncon):
            c = self.d.contact[i]
            b1 = self.m.body(self.m.geom_bodyid[c.geom1]).name; b2 = self.m.body(self.m.geom_bodyid[c.geom2]).name
            if (b1.startswith(body_prefix_a) and b2 == body_b) or (b2.startswith(body_prefix_a) and b1 == body_b):
                out.append((self.m.geom(c.geom1).name, self.m.geom(c.geom2).name, float(c.dist)))
        return out


class SimClock:
    def __init__(self, world): self.w = world

    def now(self): return self.w.time

    def sleep(self, dt):
        if dt > 0: self.w.advance(dt)


class Plugin:
    def pre_step(self, w): pass

    def post_step(self, w): pass


# ======================================================================= arms
class SimArm(Plugin):
    """Feetech STS3215 arm on the MuJoCo position actuators. Goals are followed along a smoothstep whose duration
    comes from the largest joint move at ``max_speed_deg_s`` (rate limit); ``read_positions`` is quantised to the
    servo's 4096 ticks per turn."""
    TICK = 2 * math.pi / 4096

    def __init__(self, world, arm):
        self.w = world; self.name = arm; m = world.m
        self.qadr = state.qadr(m, arm); self.aid = state.actadr(m, arm)
        self.dadr = np.array([m.jnt_dofadr[m.joint('%s/%s' % (arm, j)).id] for j in state.ARM_JOINTS])
        self.vmax = math.radians(world.P['arm']['max_speed_deg_s'])
        self.gain0 = m.actuator_gainprm[self.aid].copy(); self.bias0 = m.actuator_biasprm[self.aid].copy()
        self.torque = True; self.traj = None; self.connected = False; self.jaw_stop = None
        self.frange = m.actuator_forcerange[self.aid, 1].copy()
        world.add_plugin(self)

    def connect(self): self.connected = True

    def disconnect(self): self.connected = False

    def read_positions(self):
        q = self.w.d.qpos[self.qadr].copy(); return np.round(q / self.TICK) * self.TICK

    def read_loads(self):
        """approximation of Feetech Present_Load: actuator force / force limit, signed per-mille"""
        return np.round(1000 * self.w.d.actuator_force[self.aid] / self.frange)

    def goal(self):
        return self.w.d.ctrl[self.aid].copy() if self.traj is None else self.traj[2].copy()

    def set_goal(self, q, speed_scale=1.0):
        if not self.torque: raise RuntimeError('%s: torque disabled' % self.name)
        q = np.asarray(q, float); lo = self.w.m.actuator_ctrlrange[self.aid, 0]; hi = self.w.m.actuator_ctrlrange[self.aid, 1]
        if np.any(q < lo - 1e-9) or np.any(q > hi + 1e-9):
            raise ValueError('%s goal outside joint range: %s' % (self.name, np.round(np.degrees(q), 1)))
        q0 = self.w.d.ctrl[self.aid].copy(); dq = np.abs(q - q0)
        dur = max(float(np.max(dq[:5])) / (self.vmax * speed_scale), float(dq[5]) / (self.vmax * speed_scale), 0.02) * 1.5
        self.traj = (self.w.time, q0, q, dur)

    def set_torque(self, enabled):
        m = self.w.m
        if enabled: m.actuator_gainprm[self.aid] = self.gain0; m.actuator_biasprm[self.aid] = self.bias0; self.w.d.ctrl[self.aid] = self.w.d.qpos[self.qadr]
        else: m.actuator_gainprm[self.aid, 0] = 0; m.actuator_biasprm[self.aid, 1:3] = 0
        self.torque = bool(enabled); self.traj = None
        self.w.log('torque', arm=self.name, enabled=bool(enabled))

    def torque_enabled(self): return self.torque

    def hold_here(self):
        self.traj = None; self.w.d.ctrl[self.aid] = self.w.d.qpos[self.qadr]

    def is_moving(self):
        return self.traj is not None or float(np.abs(self.w.d.qvel[self.dadr]).max()) > 0.02

    def goal_error(self):
        return self.w.d.ctrl[self.aid] - self.w.d.qpos[self.qadr]

    def pre_step(self, w):
        if self.traj is not None and self.torque:
            t0, q0, q1, dur = self.traj; s = smoothstep((w.time - t0) / dur)
            w.d.ctrl[self.aid] = q0 + (q1 - q0) * s
            if s >= 1.0: self.traj = None
            self.cmd6 = float(w.d.ctrl[self.aid[5]])
        elif not hasattr(self, 'cmd6'): self.cmd6 = float(w.d.ctrl[self.aid[5]])
        if getattr(self, 'jaw_stop', None) is not None:     # the held beaker stops the jaw where it closed
            w.d.ctrl[self.aid[5]] = max(self.cmd6, self.jaw_stop)

    # ------------------------------------------------------------------ grasp physics (simulator only)
    GRASP_CHECK_S = 0.01

    def post_step(self, w):
        """holding model: the fin-ray fingers are compliant TPU, which MuJoCo contacts do not capture, so a held
        beaker is a weld constraint. It engages only when both finger contact boxes touch the same beaker while
        the jaw is being driven closed (gripper goal below the measured jaw angle); it releases as soon as the
        jaw is driven open. The process layer never sees the weld; it classifies grasps from the jaw angle."""
        if w.time - getattr(self, '_last_grasp_check', -1) < self.GRASP_CHECK_S: return
        self._last_grasp_check = w.time
        q6 = w.d.qpos[self.qadr[5]]; goal6 = getattr(self, 'cmd6', w.d.ctrl[self.aid[5]])
        held = w.held.get(self.name)
        if held is not None:
            if goal6 > self.jaw_stop + 0.03 or not self.torque: w.detach(self.name); self.jaw_stop = None
            return
        if goal6 >= q6 - 0.005: return                    # not closing
        touch = {}
        for i in range(w.d.ncon):
            c = w.d.contact[i]
            for ga, gb in ((c.geom1, c.geom2), (c.geom2, c.geom1)):
                n = w.m.geom(ga).name
                if n in ('%s/finger_fixed' % self.name, '%s/finger_moving' % self.name):
                    bn = w.m.body(w.m.geom_bodyid[gb]).name
                    if bn.startswith('beaker_'): touch.setdefault(bn[7:], set()).add(n.rsplit('_', 1)[1])
        for bk, sides in touch.items():
            if sides == {'fixed', 'moving'}: w.attach(self.name, bk); self.jaw_stop = float(q6); break


# ======================================================================= Mega
class SimMega(Plugin):
    """device-side emulation of the Mega firmware on the JSON-lines protocol"""
    WDT_S = 0.5
    PROGRESS_S = 0.2
    MOVE_TOL_DEG = 0.6

    def __init__(self, world):
        self.w = world; P = world.P; self.lim = protocol.Limits(P); self.inbox = collections.deque(); self.outbox = []
        m = world.m
        self.tt_act = m.actuator('carousel').id; self.st_act = m.actuator('crank').id
        self.tt_jnt = m.joint('carousel'); self.st_jnt = m.joint('crank')
        self.gains = {a: (m.actuator_gainprm[a].copy(), m.actuator_biasprm[a].copy()) for a in (self.tt_act, self.st_act)}
        S = P['scale']; self.k_flex = S['stiffness_n_per_m']; self.counts_per_g = S['counts_per_g']; self.noise_g = S['noise_g']
        self.sample_dt = 1.0 / S['rate_hz']; self.next_sample = 0.0; self.streaming = False
        self.offset_counts = 8_388_608 * 0.0 + 41_237.0   # arbitrary HX711 zero (raw counts), removed by tare
        self.tare_counts = None
        self.flex_adr = m.jnt_qposadr[m.joint('scale_flex').id]
        A = P['auger']; self.A = A
        self.motion = None; self.faults = set(); self.last_rx = None; self.armed = False
        self.aug_angle = 0.0; self.aug_hooks = []                # callbacks(revs_delta) -> dosing model
        self.limp = False; self.tare_pending = None
        world.add_plugin(self)

    # ---------------------------------------------------------- transport side
    def receive(self, line):
        self.inbox.append(line)

    def emit(self, msg):
        msg = dict(msg); msg.setdefault('t', int(round(self.w.time * 1000))); self.outbox.append(protocol.encode(msg))

    def drain(self):
        out = self.outbox; self.outbox = []; return out

    # ---------------------------------------------------------- state
    def tt_deg(self): return math.degrees(self.w.d.qpos[self.tt_jnt.qposadr[0]])

    def st_deg(self): return math.degrees(self.w.d.qpos[self.st_jnt.qposadr[0]])

    def grams_true(self):
        """force through the flexure, as grams (includes the pan)"""
        return -self.k_flex * self.w.d.qpos[self.flex_adr] / 9.81 * 1000

    def raw_counts(self):
        g = self.grams_true() + self.w.rng.normal(0, self.noise_g)
        return int(round(self.offset_counts + g * self.counts_per_g))

    def set_limp(self, limp):
        m = self.w.m
        for a in (self.tt_act, self.st_act):
            if limp: m.actuator_gainprm[a, 0] = 0; m.actuator_biasprm[a, 1:3] = 0
            else: m.actuator_gainprm[a], m.actuator_biasprm[a] = self.gains[a][0].copy(), self.gains[a][1].copy()
        if not limp:
            self.w.d.ctrl[self.tt_act] = self.w.d.qpos[self.tt_jnt.qposadr[0]]; self.w.d.ctrl[self.st_act] = self.w.d.qpos[self.st_jnt.qposadr[0]]
        self.limp = limp

    def fault(self, code, **kw):
        if code in self.faults: return
        self.faults.add(code); self.emit(dict(fault=code, **kw)); self.w.log('fault', code=code, **kw)
        if self.motion and self.motion['cmd'] == 'AUG': self.motion = None
        if code in ('ESTOP', 'WDT'): self.motion = None; self.set_limp(True)
        elif code.endswith('_TIMEOUT'): self.motion = None; self.set_limp(True)

    # ---------------------------------------------------------- commands
    def handle(self, line):
        try:
            cmd = protocol.decode(line)
        except protocol.ProtocolError as e:
            self.emit(dict(seq=-1, err=e.code, detail=e.detail)); return
        self.last_rx = self.w.time; self.armed = True
        seq = cmd.get('seq', -1)
        try:
            name = protocol.validate(cmd, self.lim, dict(tt_deg=self.tt_deg(), st_deg=self.st_deg()))
        except protocol.ProtocolError as e:
            self.emit(dict(seq=seq, err=e.code, detail=e.detail)); return
        if name == 'HB': return
        if name == 'PING':                       # like the firmware's reply_ping: the axis angles ride along
            self.emit(dict(seq=seq, ok=True, fw='benchsim-mega 0.1', sim=True, tt=round(self.tt_deg(), 2), st=round(self.st_deg(), 2))); return
        if name == 'STOP':
            if self.motion and self.motion['cmd'] == 'AUG': self.w.log('auger_stop', revs=self.motion['done_rev'])
            self.motion = None
            if not self.limp: self.w.d.ctrl[self.tt_act] = self.w.d.qpos[self.tt_jnt.qposadr[0]]; self.w.d.ctrl[self.st_act] = self.w.d.qpos[self.st_jnt.qposadr[0]]
            self.emit(dict(seq=seq, ok=True)); return
        if name == 'CLR':
            if 'ESTOP' in self.faults and self.w.estop: self.emit(dict(seq=seq, err='STATE', detail='e-stop still pressed')); return
            self.faults.clear(); self.set_limp(False); self.emit(dict(seq=seq, ok=True)); return
        # scale commands move nothing, so they stay available while the e-stop is latched (bring-up, weighing)
        if name == 'STREAM': self.streaming = cmd['on']; self.next_sample = self.w.time; self.emit(dict(seq=seq, ok=True)); return
        if name == 'TARE':                       # mean of the next 8 conversions (0.1 s at 80 SPS), then reply
            if 'HX_TIMEOUT' in self.faults: self.emit(dict(seq=seq, err='STATE', detail='HX711 fault')); return
            self.tare_pending = dict(seq=seq, vals=[], next=self.w.time); return
        if name == 'CAL': self.counts_per_g = float(cmd['counts_per_g']); self.emit(dict(seq=seq, ok=True)); return
        if 'ESTOP' in self.faults: self.emit(dict(seq=seq, err='ESTOP', detail='latched')); return
        if self.faults: self.emit(dict(seq=seq, err='STATE', detail='faults latched: %s' % sorted(self.faults))); return
        if self.motion is not None:
            self.emit(dict(seq=seq, err='BUSY', detail='%s running' % self.motion['cmd'])); return
        if self.limp: self.set_limp(False)
        if name in ('TT', 'ST'):
            act, jnt = (self.tt_act, self.tt_jnt) if name == 'TT' else (self.st_act, self.st_jnt)
            extra = self.w.P['carousel' if name == 'TT' else 'stage']['timeout_extra_s']
            self.motion = dict(cmd=name, seq=seq, t0=self.w.time, a0=self.w.d.ctrl[act], a1=math.radians(cmd['deg']), dur=max(cmd['ms'] / 1000.0, 1e-3),
                               act=act, jadr=jnt.qposadr[0], timeout=cmd['ms'] / 1000.0 + extra)
        else:
            self.motion = dict(cmd='AUG', seq=seq, t0=self.w.time, target_rev=float(cmd['rev']), dir=cmd['dir'], done_rev=0.0, phase='dose',
                               stalls=0, last_check=self.w.time, last_angle=0.0, rev_at_start=0.0, reverse_left=0.0, next_prog=self.w.time,
                               timeout=self.A['dose_timeout_s'])
        self.emit(dict(seq=seq, ack=True)); self.w.log('mega_cmd', cmd=cmd)

    # ---------------------------------------------------------- per step
    def pre_step(self, w):
        while self.inbox: self.handle(self.inbox.popleft())
        self._watchdogs(w)
        mo = self.motion
        if mo is None: return
        if w.time - mo['t0'] > mo['timeout']:
            code = {'TT': 'TT_TIMEOUT', 'ST': 'ST_TIMEOUT', 'AUG': 'AUG_TIMEOUT'}[mo['cmd']]
            self.fault(code, seq=mo['seq']); return
        if mo['cmd'] in ('TT', 'ST'):
            s = smoothstep((w.time - mo['t0']) / mo['dur']); w.d.ctrl[mo['act']] = mo['a0'] + (mo['a1'] - mo['a0']) * s
            if s >= 1 and abs(math.degrees(w.d.qpos[mo['jadr']] - mo['a1'])) < self.MOVE_TOL_DEG:
                self.emit(dict(seq=mo['seq'], done=True, cmd=mo['cmd'], deg=round(math.degrees(w.d.qpos[mo['jadr']]), 2)))
                w.log('mega_done', cmd=mo['cmd'], deg=round(math.degrees(w.d.qpos[mo['jadr']]), 2)); self.motion = None
        else:
            self._auger(w, mo, w.dt)

    def idle(self, w, dt):
        while self.inbox: self.handle(self.inbox.popleft())
        self._stream(w, until=w.time + dt)
        if self.motion and self.motion['cmd'] == 'AUG': self._auger(w, self.motion, dt)

    def post_step(self, w):
        self._stream(w, until=w.time)
        tp = self.tare_pending
        if tp is not None and w.time >= tp['next']:
            tp['vals'].append(self.raw_counts()); tp['next'] += self.sample_dt
            if len(tp['vals']) == 8:
                self.tare_counts = int(round(np.mean(tp['vals']))); self.tare_pending = None
                self.emit(dict(seq=tp['seq'], ok=True, tare=self.tare_counts))

    def _stream(self, w, until):
        while self.streaming and self.next_sample <= until + 1e-12:
            t_ms = int(round(self.next_sample * 1000)); self.next_sample += self.sample_dt
            if w.hx_fail:
                if not getattr(self, '_hx_last', None): self._hx_last = self.next_sample
                if self.next_sample - self._hx_last > max(0.1, 4 * self.sample_dt): self.fault('HX_TIMEOUT')
                continue
            self._hx_last = None
            raw = self.raw_counts(); ref = self.tare_counts if self.tare_counts is not None else self.offset_counts
            self.outbox.append(protocol.encode(dict(w=round((raw - ref) / self.counts_per_g, 3), raw=raw, t=t_ms)))

    def _watchdogs(self, w):
        if w.estop and 'ESTOP' not in self.faults: self.fault('ESTOP')
        if self.armed and self.last_rx is not None and w.time - self.last_rx > self.WDT_S and 'WDT' not in self.faults and self.motion is not None:
            self.fault('WDT', aug=round(self.motion['done_rev'], 3) if self.motion and self.motion['cmd'] == 'AUG' else None)

    def _auger(self, w, mo, dt):
        """revolution counting on the feedback angle; stall rule: < 5 deg progress in 150 ms -> stop, reverse 1/4, retry;
        3 stalls -> AUGER_JAM (electrical.md 6)"""
        A = self.A; rate = 360.0 / A['rev_s']
        moving = not w.auger_jam
        if mo['phase'] == 'reverse':
            step = min(rate * dt, mo['reverse_left']) if moving or True else 0.0
            self.aug_angle -= step * mo['dir']; mo['reverse_left'] -= step
            if mo['reverse_left'] <= 1e-9:
                mo['phase'] = 'dose' if mo['done_rev'] < mo['target_rev'] - 1e-9 else 'finish'; mo['last_check'] = w.time; mo['last_angle'] = self.aug_angle
            return
        if mo['phase'] == 'finish':
            self.emit(dict(seq=mo['seq'], done=True, cmd='AUG', rev=round(mo['done_rev'], 3), stalls=mo['stalls']))
            w.log('mega_done', cmd='AUG', rev=round(mo['done_rev'], 3), stalls=mo['stalls']); self.motion = None; return
        step = rate * dt if moving else 0.0
        step = min(step, (mo['target_rev'] - mo['done_rev']) * 360.0)
        self.aug_angle += step * mo['dir']; mo['done_rev'] += step / 360.0
        for h in self.aug_hooks: h(step / 360.0 * mo['dir'])
        if w.time >= mo['next_prog']:
            self.emit(dict(aug=round(mo['done_rev'], 3), seq=mo['seq'])); mo['next_prog'] = w.time + self.PROGRESS_S
        if w.time - mo['last_check'] >= A['stall_window_s']:
            if abs(self.aug_angle - mo['last_angle']) < A['stall_min_deg'] and mo['done_rev'] < mo['target_rev'] - 1e-9:
                mo['stalls'] += 1; w.log('auger_stall', n=mo['stalls'], rev=round(mo['done_rev'], 3))
                if mo['stalls'] >= A['max_stalls']: self.fault('AUGER_JAM', seq=mo['seq'], rev=round(mo['done_rev'], 3)); return
                mo['phase'] = 'reverse'; mo['reverse_left'] = A['reverse_rev'] * 360.0
            mo['last_check'] = w.time; mo['last_angle'] = self.aug_angle
        if mo['done_rev'] >= mo['target_rev'] - 1e-9 and mo['phase'] == 'dose':
            mo['phase'] = 'reverse'; mo['reverse_left'] = A['reverse_rev'] * 360.0      # reverse 1/4 turn against dribble


class SimTransport:
    """in-process transport to the simulated Mega (same lines as the serial port)"""

    def __init__(self, mega: SimMega): self.mega = mega

    def write_line(self, line): self.mega.receive(line)

    def read_lines(self): return self.mega.drain()
