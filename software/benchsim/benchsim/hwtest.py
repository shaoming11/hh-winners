"""Guided hardware test ladder: one rung at a time, stop at the first failure.

    python -m benchsim.hwtest --mega /dev/cu.usbserial-130                       # Mega and scale only
    python -m benchsim.hwtest --pourer /dev/cu.usbmodemA --calibration CAL        # one arm
    python -m benchsim.hwtest --mega M --pourer A --transfer B --calibration CAL --upto L3

Rungs (each must pass before the next runs):
    L0 offline     hw-check (firmware parity, calibration schema and MJCF limits); ports present.  Opens nothing.
    L1 read-only   dry run: Mega PING, scale stream, each arm's identity, joint readings and loads with torque OFF.
                   Every output is refused by the backend (DryRunTransport, LeRobotArm dry_run).
    L2 zero check  each arm resting in its folded rest pose: joint readings against a reference recorded on a good
                   day (--record-reference). Catches a re-seated horn or swapped servo before anything moves.
    L3 one axis    live, one confirmation per arm or axis: every arm joint +-5 deg at 10 % speed and back; the
                   carousel +-5 deg, the stage 0 -> 5 -> 0 deg, the auger 0.5 rev.

Moves happen only in L3 and only after the operator types MOVE. A failure stops the ladder and is written to the
report (reports/hwtest/<time>.json). Nothing here talks to the servos directly: the team's real backend
(benchsim.backends.real) does every read and write, with its own limit checks.
"""

import argparse
import json
import math
import os
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from . import paths
from .backends import real

RUNGS = ('L0', 'L1', 'L2', 'L3')
JOINTS = real.JOINTS
ZERO_TOL_DEG = 3.0              # L2: a re-seated STS3215 horn moves a joint by a whole spline tooth (>10 deg)
REST_LOAD_MAX = 300.0           # L1: permille of rated load with torque off and the arm resting
JOG_DEG = 5.0                   # L3 joint and carousel step
SPEED = 0.1                     # L3 arm speed scale
REPORT_DIR = paths.SIM_ROOT / 'reports' / 'hwtest'


class Stop(Exception):
    """a check failed: the ladder stops here"""


class Ladder:
    def __init__(self, args, input_fn=input, out=print, serial_factory=None, bus_factory=None, clock=None):
        self.a = args; self.ask = input_fn; self.say = out
        self.serial_factory = serial_factory; self.bus_factory = bus_factory
        self.clock = clock or real.RealClock()
        self.rows = []

    # ------------------------------------------------------------ plumbing
    def record(self, rung, name, status, detail=''):
        self.rows.append(dict(rung=rung, check=name, status=status, detail=detail))
        self.say('  %-4s %-48s %s' % (status, name, detail))
        if status == 'FAIL': raise Stop('%s %s: %s' % (rung, name, detail))

    def confirm(self, what):
        reply = self.ask('\n  %s\n  Type MOVE to go, anything else to stop: ' % what).strip()
        if reply != 'MOVE': raise Stop('operator did not confirm: %s' % what)

    def arms_wanted(self):
        return [(n, p) for n, p in (('pourer', self.a.pourer), ('transfer', self.a.transfer)) if p]

    def bench(self, dry_run):
        return real.make_real_bench(port_mega=self.a.mega, port_pourer=self.a.pourer, port_transfer=self.a.transfer,
                                    calibration_path=self.a.calibration, dry_run=dry_run,
                                    serial_factory=self.serial_factory, bus_factory=self.bus_factory)

    def reference_path(self):
        return Path(str(self.a.calibration) + '.reference.json') if self.a.calibration else None

    # ------------------------------------------------------------ L0 offline
    def L0(self):
        rows = real.offline_checks(calibration_path=self.a.calibration, log=lambda *a, **k: None)
        # the import-hygiene row is about this process's modules, not the hardware: skip it here
        bad = [r for r in rows if r['status'] == 'FAIL' and not r['check'].startswith('benchsim.backends.real imports')]
        self.record('L0', 'hw-check (firmware, calibration, protocol)', 'FAIL' if bad else 'PASS',
                    '; '.join('%s: %s' % (r.get('check', '?'), r.get('detail', '')) for r in bad) or '%d checks' % len(rows))
        if not (self.a.mega or self.arms_wanted()): self.record('L0', 'devices named', 'FAIL', 'give --mega and/or --pourer/--transfer')
        if self.arms_wanted() and not self.a.calibration: self.record('L0', 'calibration file', 'FAIL', '--calibration is required for the arms')
        if self.serial_factory is None and self.bus_factory is None:
            for name, port in [('mega', self.a.mega)] + self.arms_wanted():
                if port: self.record('L0', '%s port present' % name, 'PASS' if os.path.exists(port) else 'FAIL', port)
        if self.a.calibration:
            cal = real.load_calibration(self.a.calibration)
            for name, _ in self.arms_wanted():
                arm = cal['arms'][name]
                ticks = [arm['joints'][j].get('tick_at_zero') for j in JOINTS if 'tick_at_zero' in arm['joints'][j]]
                placeholder = all(t == 2047 for t in ticks)
                self.record('L0', '%s zero ticks measured' % name, 'WARN' if placeholder else 'PASS',
                            'all 2047: still the example placeholders (bring-up A3)' if placeholder else '')
                self.record('L0', '%s fingerprint recorded' % name, 'PASS' if arm.get('fingerprint') else 'WARN',
                            '' if arm.get('fingerprint') else 'null: port identity is not verified (bring-up A2)')

    # ------------------------------------------------------------ L1 read-only
    def L1(self):
        bb = self.bench(dry_run=True)
        try:
            for w in bb.warnings: self.record('L1', 'backend warning', 'WARN', w)
            if bb.mega is not None: self._l1_mega(bb)
            for name, arm in bb.arms.items(): self._l1_arm(name, arm)
        finally:
            bb.close()

    def _l1_mega(self, bb):
        m = bb.mega
        self.clock.sleep(2.5); m.take_samples()                        # a Mac's CH340 may reset the board on open
        p = m.command('PING')
        self.record('L1', 'Mega PING', 'PASS' if p.get('ok') and p.get('sim') is False else 'FAIL',
                    'fw %s, faults %s, estop %s, pos %s' % (p.get('fw'), p.get('faults'), p.get('estop'), p.get('pos')))
        if p.get('estop'): self.record('L1', 'e-stop released', 'WARN', 'D2 reads pressed or unwired: motion will be refused')
        m.command('STREAM', on=True); m.take_samples(); t_end = self.clock.now() + 2.0; got = []
        while self.clock.now() < t_end:
            m.heartbeat(); got += m.take_samples(); self.clock.sleep(0.05)
        m.command('STREAM', on=False)
        if len(got) < 5: self.record('L1', 'scale stream', 'FAIL', '%d samples in 2 s: check DT/SCK/5V/GND' % len(got))
        raw = np.array([s.get('raw', 0) for s in got], float)
        flat = raw.std() == 0.0
        self.record('L1', 'scale stream', 'FAIL' if flat else 'PASS',
                    '%d samples, raw %.0f +- %.0f%s' % (len(got), raw.mean(), raw.std(), ' (constant: HX711 not clocked?)' if flat else ''))

    def _l1_arm(self, name, arm):
        self.record('L1', '%s identity' % name, 'PASS', 'fingerprint checked' if arm.cal.get('fingerprint') else 'no fingerprint (warned)')
        if arm.torque_enabled(): self.record('L1', '%s torque off' % name, 'WARN', 'servos report torque ON (left as is in dry run)')
        q = arm.read_positions(); loads = arm.read_loads()
        lo, hi = arm.map.lo, arm.map.hi
        out = [(JOINTS[i], round(math.degrees(q[i]), 1)) for i in range(6) if not lo[i] - 1e-9 <= q[i] <= hi[i] + 1e-9]
        self.record('L1', '%s joints inside calibrated limits' % name, 'FAIL' if out else 'PASS',
                    ('outside: %s (wrong tick_at_zero/sign?)' % out) if out else ' '.join('%.0f' % math.degrees(v) for v in q))
        heavy = [(JOINTS[i], round(float(loads[i]))) for i in range(6) if abs(loads[i]) > REST_LOAD_MAX]
        self.record('L1', '%s loads at rest' % name, 'WARN' if heavy else 'PASS', ('high: %s' % heavy) if heavy else '')

    # ------------------------------------------------------------ L2 zero check
    def L2(self):
        if not self.arms_wanted(): self.record('L2', 'zero check', 'SKIP', 'no arms named'); return
        self.ask('\n  Rest each arm in its folded rest pose (lying on its own stops, torque off), then press Enter: ')
        bb = self.bench(dry_run=True)
        try:
            now = {name: arm.read_ticks() for name, arm in bb.arms.items()}
        finally:
            bb.close()
        path = self.reference_path()
        if self.a.record_reference:
            ref = json.loads(path.read_text()) if path.exists() else {}
            for name, ticks in now.items(): ref[name] = dict(ticks=ticks, recorded=time.strftime('%Y-%m-%d %H:%M'))
            path.write_text(json.dumps(ref, indent=1) + '\n')
            self.record('L2', 'reference recorded', 'PASS', str(path)); return
        if not path.exists(): self.record('L2', 'zero check', 'FAIL', 'no reference yet: run once with --record-reference on a known-good arm')
        ref = json.loads(path.read_text())
        tpr = real.load_calibration(self.a.calibration)['ticks_per_rev']
        for name, ticks in now.items():
            if name not in ref: self.record('L2', '%s zero check' % name, 'FAIL', 'no reference for this arm'); continue
            d = {j: (ticks[j] - ref[name]['ticks'][j]) * 360.0 / tpr for j in JOINTS}
            off = {j: round(v, 1) for j, v in d.items() if abs(v) > ZERO_TOL_DEG}
            self.record('L2', '%s zero check (ref %s)' % (name, ref[name]['recorded']), 'FAIL' if off else 'PASS',
                        ('moved: %s deg (re-seated horn? re-record A3 zero ticks)' % off) if off
                        else 'max %.1f deg' % max(abs(v) for v in d.values()))

    # ------------------------------------------------------------ L3 one axis at a time
    def L3(self):
        bb = self.bench(dry_run=False)
        try:
            for name, arm in bb.arms.items(): self._l3_arm(name, arm)
            if bb.mega is not None: self._l3_mega(bb.mega)
        finally:
            bb.close()

    def _wait_arm(self, arm, timeout=8.0):
        t_end = self.clock.now() + timeout
        while arm.is_moving():
            if self.clock.now() > t_end: return False
            self.clock.sleep(0.05)
        return True

    def _l3_arm(self, name, arm):
        self.confirm('%s: each joint moves %g deg and back at %d %% speed, one at a time. Arm clear, hand on its power plug.'
                     % (name, JOG_DEG, SPEED * 100))
        tol = math.radians(arm.cal['goal_tolerance_deg'])
        arm.set_torque(True)                                    # Goal = Present first: no snap
        try:
            for i, j in enumerate(JOINTS):
                q0 = arm.read_positions(); goal = q0.copy()
                room_up = arm.map.hi[i] - q0[i]; step = math.radians(JOG_DEG)
                goal[i] += step if room_up > step + 1e-3 else -step       # step toward the side with room
                try: arm.check_goal(goal)
                except ValueError as e: self.record('L3', '%s %s' % (name, j), 'FAIL', str(e))
                arm.set_goal(goal, speed_scale=SPEED)
                if not self._wait_arm(arm): self.record('L3', '%s %s' % (name, j), 'FAIL', 'still moving after 8 s')
                err = abs(arm.read_positions()[i] - goal[i])
                arm.set_goal(q0, speed_scale=SPEED); back = self._wait_arm(arm)
                err_back = abs(arm.read_positions()[i] - q0[i])
                ok = err <= tol and err_back <= tol and back
                self.record('L3', '%s %s %+g deg and back' % (name, j, math.degrees(goal[i] - q0[i])), 'PASS' if ok else 'FAIL',
                            'error %.2f / %.2f deg (tolerance %.1f)' % (math.degrees(err), math.degrees(err_back), math.degrees(tol)))
        finally:
            self.ask('\n  %s: support the arm, then press Enter to turn its torque off: ' % name)
            arm.set_torque(False)

    def _l3_mega(self, m):
        from .interfaces import MegaError
        self.clock.sleep(2.5); m.take_samples()
        p = m.command('PING')
        if p.get('estop') or p.get('faults'):
            self.record('L3', 'Mega ready to move', 'FAIL', 'faults %s, estop %s: release the e-stop and CLR first' % (p.get('faults'), p.get('estop')))
        if p.get('pos') != 'known':
            self.confirm('Carousel and stage positions are unknown. Put the deck at its 0 deg mark and the stage at WORK by hand, then confirm to home.')
            m.command('CLR', home=True)
        tt, st = p.get('tt') or 0.0, p.get('st') or 0.0
        steps = [('carousel %+g deg and back' % JOG_DEG, [('TT', dict(deg=tt + JOG_DEG, ms=2000)), ('TT', dict(deg=tt, ms=2000))]),
                 ('stage %+g deg and back' % JOG_DEG, [('ST', dict(deg=st + JOG_DEG, ms=2000)), ('ST', dict(deg=st, ms=2000))]),
                 ('auger 0.5 rev', [('AUG', dict(rev=0.5, dir=1))])]
        for label, moves in steps:
            self.confirm('Mega: %s.' % label)
            try:
                for cmd, kw in moves:
                    r = m.motion(cmd, done_timeout=12.0, **kw)
                    if not r.get('done'): raise MegaError({'err': 'no done', 'detail': str(r)})
                self.record('L3', label, 'PASS', 'done')
            except (MegaError, TimeoutError) as e:
                self.record('L3', label, 'FAIL', str(e))

    # ------------------------------------------------------------ driver
    def run(self):
        upto = RUNGS.index(self.a.upto)
        status = 'PASS'
        try:
            for rung in RUNGS[:upto + 1]:
                self.say('\n%s' % {'L0': 'L0 offline', 'L1': 'L1 read-only (dry run)', 'L2': 'L2 zero check (read-only)',
                                   'L3': 'L3 one axis at a time (LIVE)'}[rung])
                getattr(self, rung)()
        except Stop as e:
            status = 'STOPPED'; self.say('\nSTOPPED: %s' % e)
        except Exception as e:                                   # anything unexpected stops the ladder too
            status = 'ERROR'; self.say('\nERROR: %s' % e); self.rows.append(dict(rung='-', check='exception', status='ERROR', detail=traceback.format_exc()))
        if status == 'PASS': self.say('\nPASS: %s complete' % ', '.join(RUNGS[:upto + 1]))
        self.write_report(status)
        return status

    def write_report(self, status):
        if self.a.no_report: return
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        path = REPORT_DIR / ('%s.json' % time.strftime('%Y%m%d-%H%M%S'))
        path.write_text(json.dumps(dict(status=status, args=vars(self.a), rows=self.rows), indent=1, default=str) + '\n')
        self.say('report: %s' % path)


def parse(argv=None):
    ap = argparse.ArgumentParser(prog='python -m benchsim.hwtest', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--mega', help='Mega serial port')
    ap.add_argument('--pourer', help='pourer arm serial port')
    ap.add_argument('--transfer', help='transfer arm serial port')
    ap.add_argument('--calibration', help='hardware calibration JSON (needed for arms)')
    ap.add_argument('--upto', choices=RUNGS, default='L2', help='last rung to run (default L2: nothing moves)')
    ap.add_argument('--record-reference', action='store_true', help='L2: store today\'s rest-pose ticks as the reference')
    ap.add_argument('--no-report', action='store_true')
    return ap.parse_args(argv)


def main(argv=None):
    sys.exit(0 if Ladder(parse(argv)).run() == 'PASS' else 1)


if __name__ == '__main__':
    main()
