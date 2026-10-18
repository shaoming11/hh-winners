"""Dry run on the real bench: play reports/native_plans.json on the two SO-101 followers, one step at a time.

    python scripts/replay_plan.py                 # all steps, 30 % speed, waits for Enter before each step
    python scripts/replay_plan.py --speed 0.5 --steps 1 4
    python scripts/replay_plan.py --no-mega       # arms only (the carousel is not turned)

Each step: the carousel turns so the right pocket is at the pick spot (steps that use it), then the step's arm
replays its planned joint path (the plan's joint angles, mapped by hardware_calibration.bench.json). The other arm
stays parked. Torque comes on holding the present pose (no snap); Ctrl-C freezes both arms where they are (torque
stays on, nothing is dropped). Ports from WLB_MEGA / WLB_POURER / WLB_TRANSFER or the defaults below.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from benchsim import layout, mechanisms, paths  # noqa: E402
from benchsim.bench import make_bench  # noqa: E402

PORTS = dict(port_mega=os.environ.get('WLB_MEGA', '/dev/cu.usbserial-1130'),
             port_pourer=os.environ.get('WLB_POURER', '/dev/cu.usbmodem58760435221'),
             port_transfer=os.environ.get('WLB_TRANSFER', '/dev/cu.usbmodem58CD1767761'))
CAL = os.path.join(paths.SIM_ROOT, 'benchsim', 'config', 'hardware_calibration.bench.json')
REACH_DEG = 3.0          # a waypoint counts as reached inside this (largest joint error)
# rest pose: both arms folded back (lift back, elbow folded), where they hold themselves with the power off
# (measured 2026-10-18 as the mean of both arms resting, pulled just inside the calibrated limits)
REST_DEG = [-9.0, -99.0, 93.0, -10.0, 0.0, 0.0]
WAYPOINT_TIMEOUT_S = 8.0


def deck_for_step(name, bench):
    """deck angle that puts the step's carousel pocket at the pick spot (None: the step does not use the carousel)"""
    if 'carousel' not in name: return None
    C = bench['params']['carousel']; brg = mechanisms.station_bearings(bench)
    pocket = mechanisms.INITIAL_POCKETS.index('P2' if 'P2' in name else 'P1')
    return mechanisms.deck_angle(C['pocket_ids_deg'][pocket], brg['pick'], C['deck_range_deg'])


def go(arm, q, speed, label=''):
    """command one waypoint and wait until every joint is within REACH_DEG (or the timeout)"""
    arm.set_goal(np.asarray(q, float), speed_scale=speed)
    t0 = time.time(); err = float('nan'); misses = 0
    while time.time() - t0 < WAYPOINT_TIMEOUT_S:
        try:
            err = np.degrees(np.abs(arm.read_positions() - np.asarray(q, float)))[:5].max(); misses = 0
        except ConnectionError as e:                  # a dropped status packet: the arm keeps its goal, try again
            misses += 1
            if misses >= 10: raise
            time.sleep(0.05); continue
        if err < REACH_DEG: return err
        time.sleep(0.03)
    print('   %s: waypoint not reached in %.0f s (largest joint error %.1f deg), continuing' % (label, WAYPOINT_TIMEOUT_S, err), flush=True)
    return err


def play_segment(arm, seg, speed):
    qs = seg['qs']
    if seg['kind'] == 'joint' and len(qs) == 2: qs = qs[1:]          # joint moves: straight to the end
    for q in qs: go(arm, q, speed, seg['name'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--speed', type=float, default=0.3, help='fraction of the calibration max speed (default 0.3)')
    ap.add_argument('--steps', nargs='*', help='step numbers to run (default all), e.g. 1 4')
    ap.add_argument('--no-mega', action='store_true', help='leave the carousel alone')
    ap.add_argument('--yes', action='store_true', help='do not wait for Enter between steps')
    ap.add_argument('--rest', action='store_true', help='only send both arms to the rest pose, then torque off')
    ap.add_argument('--check', action='store_true', help='pre-flight only: open the ports read-only, check every waypoint, move nothing')
    a = ap.parse_args()
    plans = json.loads((paths.SIM_ROOT / 'reports' / 'native_plans.json').read_text())['steps']
    order = [k for k in plans if not a.steps or k.split()[0] in a.steps]
    bench = layout.load_bench()
    kw = dict(PORTS, calibration_path=CAL, dry_run=a.check)
    if a.no_mega: kw['port_mega'] = None
    bb = make_bench('real', allow_hardware=True, **kw)
    arms = bb.arms
    mega = None if a.no_mega else bb.mega
    if mega is not None:                          # opening the CH340 port resets the Mega: wait for the boot line
        time.sleep(2.5)
        try: bb.transport.read_lines()
        except Exception: pass
    # pre-flight: every planned waypoint must be inside the arm's calibrated limits, or nothing moves
    bad = []
    for k in order + [x for x in plans if x not in order][:0]:
        for seg in plans[k]['segments']:
            for q in seg['qs']:
                try: arms[plans[k]['arm']].check_goal(np.asarray(q, float))
                except ValueError as e: bad.append('%s / %s: %s' % (k, seg['name'], e))
    for name, arm in arms.items():
        try: arm.check_goal(np.radians(REST_DEG))
        except ValueError as e: bad.append('rest pose / %s: %s' % (name, e))
    if bad:
        print('pre-flight FAILED, nothing moved:'); [print('  ', b) for b in bad[:20]]
        print('  (%d waypoints outside the calibrated limits)' % len(bad)); return 1
    print('pre-flight ok: every waypoint of %d steps is inside the calibrated limits' % len(order))
    if a.check: return 0
    for w in getattr(bb, 'warnings', []): print('warning:', w)
    try:
        for name, arm in arms.items(): arm.set_torque(True); print('%s torque on (holding the present pose)' % name)
        if mega is not None:
            mega.command('CLR', home=True)
        rest = np.radians(REST_DEG)
        if a.rest:
            for name, arm in arms.items():
                if not a.yes: input('\nEnter: move %s to the rest pose (slow) ' % name)
                go(arm, rest, min(a.speed, 0.3), 'rest ' + name)
            for arm in arms.values(): arm.set_torque(False)
            print('both arms at rest, torque off'); return 0
        # park both arms first, one at a time (the plan assumes the other arm is parked)
        park = {}
        for k in plans:
            arm_name = plans[k]['arm']
            if arm_name not in park: park[arm_name] = plans[k]['segments'][0]['qs'][0]
        for name, q in park.items():
            if not a.yes: input('\nEnter: move %s to its park pose (slow) ' % name)
            go(arms[name], q, min(a.speed, 0.3), 'park ' + name)
        for k in order:
            s = plans[k]; arm = arms[s['arm']]
            deck = deck_for_step(k, bench)
            msg = '\nEnter: step %s (%s arm%s) ' % (k, s['arm'], '' if deck is None else ', carousel to %.1f deg first' % deck)
            if a.yes: print(msg)
            else: input(msg)
            if deck is not None and mega is not None:
                cur = mega.command('PING').get('tt') or 0.0
                ms = int(max(1000, abs(deck - cur) / 45.0 * 1000 * bench['params']['carousel']['min_s_per_45deg']) + 200)
                r = mega.motion('TT', done_timeout=ms / 1000 + 6, deg=float(deck), ms=ms)
                print('   carousel at %.1f deg' % r['deg'], flush=True)
            for seg in s['segments']:
                print('   %-38s %s' % (seg['name'], seg['phase']), flush=True)
                play_segment(arm, seg, a.speed)
        for name, arm in arms.items():
            if not a.yes: input('\nEnter: return %s to the rest pose ' % name)
            go(arm, rest, min(a.speed, 0.3), 'rest ' + name)
        for arm in arms.values(): arm.set_torque(False)
        print('\ndone: both arms back at rest, torque off')
    except (KeyboardInterrupt, ConnectionError, TimeoutError) as stop_reason:
        print('\nstopping:', type(stop_reason).__name__, stop_reason)
        for name, arm in arms.items():
            try: arm.set_goal(arm.read_positions(), 1.0)
            except Exception as e: print(name, 'freeze failed:', e)
        print('\nstopped: both arms frozen in place, torque on')
    finally:
        for name, arm in arms.items():
            try: arm.disconnect()
            except Exception: pass


if __name__ == '__main__':
    main()
