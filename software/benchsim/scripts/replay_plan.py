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

T0 = time.time()
_print = print
def print(*args, **kw):                          # every log line carries the elapsed time
    _print('%6.1fs' % (time.time() - T0), *args, **kw)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from benchsim import layout, mechanisms, paths  # noqa: E402
from benchsim.bench import make_bench  # noqa: E402
from benchsim.interfaces import MegaError  # noqa: E402

PORTS = dict(port_mega=os.environ.get('WLB_MEGA', '/dev/cu.usbserial-1130'),
             port_pourer=os.environ.get('WLB_POURER', '/dev/cu.usbmodem58760435221'),
             port_transfer=os.environ.get('WLB_TRANSFER', '/dev/cu.usbmodem58CD1767761'))
CAL = os.path.join(paths.SIM_ROOT, 'benchsim', 'config', 'hardware_calibration.bench.json')
OVERRIDES = os.path.join(paths.SIM_ROOT, 'benchsim', 'config', 'pose_overrides.json')   # scripts/teach_poses.py writes it


def load_overrides():
    try:
        with open(OVERRIDES) as f: return json.load(f)
    except (OSError, ValueError): return {}


def save_overrides(ov):
    with open(OVERRIDES, 'w') as f: json.dump(ov, f, indent=1)


TAUGHT = os.path.join(paths.SIM_ROOT, 'benchsim', 'config', 'taught_poses.json')   # absolute hand-taught grasp poses
PICK = dict(back_mm=15.0, up_mm=70.0, lift_mm=60.0, n_descend=12, n_advance=8, n_lift=8, open_deg=85.0)
_KIN = {}


def kin():
    if not _KIN:
        from benchsim import scene
        from benchsim.kinematics import Kin
        m, b = scene.build(); K = Kin(m)
        cal = json.load(open(CAL))['arms']                 # IK bounds = the arms' calibrated (physical) limits, not the MJCF's
        names = ('shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll')
        for arm in K.range:
            for j, n in enumerate(names):
                J = cal[arm]['joints'][n]; K.range[arm][j] = [math.radians(J['min_deg']), math.radians(J['max_deg'])]
        _KIN['K'] = K; _KIN['m'] = m
    return _KIN['K'], _KIN['m']


SPOT_DZ_MM = {'transfer_carousel_pick': 15.0,   # bench 2026-10-18: the grab was 1-2 cm low (caught the carousel ring)
              'transfer_scale': 10.0}          # and the place on the scale 1 cm low


def load_taught():
    try:
        with open(TAUGHT) as f: return json.load(f)
    except (OSError, ValueError): return {}


def linear_pick(arm, q_touch, grip_close_deg, site='grasp_td', dz_mm=0.0):
    """straight-line top-down pick around a hand-taught touch pose, built RELATIVE to it (sim kinematics give the
    directions; the absolute sim/bench offset at this pose cancels): above-and-back -> straight down (jaws wide) ->
    advance onto the cup while the jaws close -> straight up. Returns four segments (joint, descend, advance, lift)."""
    K, m = kin()
    q_touch = np.asarray(q_touch, float)
    p0, R0 = K.site(arm, q_touch, site)
    K.set(arm, q_touch)
    p0 = p0 + np.array([0.0, 0.0, dz_mm])                                   # height correction for this spot
    gpos = lambda n: [K.d.geom_xpos[i] * 1000 for i in range(m.ngeom) if m.geom(i).name == '%s/%s' % (arm, n)][0]
    ff, fm = gpos('finger_fixed'), gpos('finger_moving')
    back = np.r_[(ff - fm)[:2], 0.0]; back /= np.linalg.norm(back)          # away from the cup, toward the fixed finger
    up = np.array([0.0, 0.0, 1.0]); P = PICK
    def solve(pts, seed, grips):
        out = []; q = seed.copy()
        for pt, g in zip(pts, grips):
            qs, perr, aerr = K.ik(arm, site, pt, z_axis=R0[:, 2], q0=q[:5].tolist() + [q[5]], w_ori=20.0)   # straight line first; the tool may tilt (<= ~15 deg at the top: the wrist flex limit)
            q = np.r_[np.asarray(qs, float)[:5], math.radians(g)]
            if perr > 4.0: raise ValueError('pick IK: %.1f mm off at %s' % (perr, np.round(pt, 1)))
            out.append(q.tolist())
        return out
    A = p0 + P['back_mm'] * back + P['up_mm'] * up; B = p0 + P['back_mm'] * back
    lin = lambda a, c, n: [a + (c - a) * t for t in np.linspace(0, 1, n)]
    descend = solve(lin(A, B, P['n_descend']), q_touch, [P['open_deg']] * P['n_descend'])
    adv_g = list(np.linspace(P['open_deg'], grip_close_deg, P['n_advance']))
    advance = solve(lin(B, p0, P['n_advance']), np.asarray(descend[-1]), adv_g)
    lift = solve(lin(p0, p0 + P['lift_mm'] * up, P['n_lift']), np.asarray(advance[-1]), [grip_close_deg] * P['n_lift'])
    return [dict(name='straight down, jaws wide (15 mm back)', phase='approach', kind='cartesian', qs=descend),
            dict(name='advance onto the cup while closing', phase='pick', kind='cartesian', qs=advance),
            dict(name='lift straight up', phase='carry', kind='cartesian', qs=lift)]


def linear_place(arm, q_touch, grip_close_deg, site='grasp_td', dz_mm=0.0):
    """straight-line place around a hand-taught hold pose (relative, like linear_pick): arrive above it with the beaker
    clear of the receiver's lip -> straight down -> open the jaws -> back off -> straight up. Returns (above_q, segments)."""
    K, m = kin(); P = PICK
    q_touch = np.asarray(q_touch, float); q_touch[5] = math.radians(grip_close_deg)
    p0, R0 = K.site(arm, q_touch, site); K.set(arm, q_touch)
    p0 = p0 + np.array([0.0, 0.0, dz_mm])                                   # height correction for this spot
    gpos = lambda n: [K.d.geom_xpos[i] * 1000 for i in range(m.ngeom) if m.geom(i).name == '%s/%s' % (arm, n)][0]
    back = np.r_[(gpos('finger_fixed') - gpos('finger_moving'))[:2], 0.0]; back /= np.linalg.norm(back)
    up = np.array([0.0, 0.0, 1.0])
    def solve(pts, seed, grips):
        out = []; q = seed.copy()
        for pt, g in zip(pts, grips):
            qs, perr, aerr = K.ik(arm, site, pt, z_axis=R0[:, 2], q0=q[:5].tolist() + [q[5]], w_ori=20.0)
            q = np.r_[np.asarray(qs, float)[:5], math.radians(g)]
            if perr > 4.0: raise ValueError('place IK: %.1f mm off at %s' % (perr, np.round(pt, 1)))
            out.append(q.tolist())
        return out
    lin = lambda a, c, n: [a + (c - a) * t for t in np.linspace(0, 1, n)]
    above = p0 + P['up_mm'] * up
    down = solve(lin(above, p0, P['n_descend']), q_touch, [grip_close_deg] * P['n_descend'])
    release = [down[-1][:5] + [math.radians(grip_close_deg)], down[-1][:5] + [math.radians(P['open_deg'])]]
    off = solve(lin(p0, p0 + P['back_mm'] * back, P['n_advance']), np.asarray(release[-1]), [P['open_deg']] * P['n_advance'])
    rise = solve(lin(p0 + P['back_mm'] * back, p0 + P['back_mm'] * back + P['lift_mm'] * up, P['n_lift']), np.asarray(off[-1]),
                 [P['open_deg']] * P['n_lift'])
    return [dict(name='straight down into the receiver', phase='carry', kind='cartesian', qs=down),
            dict(name='release', phase='place', kind='grip', qs=release),
            dict(name='back off the cup', phase='retreat', kind='cartesian', qs=off),
            dict(name='straight up', phase='retreat', kind='cartesian', qs=rise)]


TRANSFER_STEPS = {'1': ('transfer_carousel_pick', 'transfer_scale'), '4': ('transfer_scale', 'transfer_carousel_pick')}
POURER_STEPS = {'2': 'pourer_rack1', '3': 'pourer_scale'}


def pourer_taught(segs, q_spot, spot):
    """pourer step with a hand-taught grab spot: straight-line grab there, the plan's carry / pour / raise in between,
    and the beaker put back on the same spot with a straight-line place"""
    names = [g['name'] for g in segs]
    close = math.degrees(segs[next(i for i, nm in enumerate(names) if nm.startswith('close on'))]['qs'][-1][5])
    dz = SPOT_DZ_MM.get(spot, 0.0)
    pick = linear_pick('pourer', q_spot, close, site='grasp_side', dz_mm=dz)
    place = linear_place('pourer', q_spot, close, site='grasp_side', dz_mm=dz)
    i_carry = names.index('carry to above pre-pour'); i_raise = names.index('raise from pre-pour')
    J = lambda name, phase, a, b: dict(name=name, phase=phase, kind='joint', qs=[list(a), list(b)])
    return ([J('park -> above the grab', 'approach', segs[0]['qs'][0], pick[0]['qs'][0])] + pick +
            [J('carry to above pre-pour', 'carry', pick[-1]['qs'][-1], segs[i_carry]['qs'][-1])] + segs[i_carry + 1:i_raise + 1] +
            [J('carry back above the spot', 'carry', segs[i_raise]['qs'][-1], place[0]['qs'][0])] + place +
            [J('return to park', 'park', place[-1]['qs'][-1], segs[-1]['qs'][-1])])


def taught_segments(segs, key):
    """transfer steps whose pick and place spots are both hand-taught: park -> straight-line pick -> carry with the
    beaker clear above the receiver -> straight-line place -> park (the plan's slide / channel moves are not used)"""
    T = load_taught()
    pour = POURER_STEPS.get(key.split()[0])
    if pour and pour in T: return pourer_taught(segs, T[pour], pour)
    spots = TRANSFER_STEPS.get(key.split()[0])
    if not spots or not all(sp in T for sp in spots): return segs
    names = [g['name'] for g in segs]
    close = math.degrees(segs[names.index('close on P1')]['qs'][-1][5])
    park0, park1 = segs[0]['qs'][0], segs[-1]['qs'][-1]
    pick = linear_pick('transfer', T[spots[0]], close, dz_mm=SPOT_DZ_MM.get(spots[0], 0.0))
    place = linear_place('transfer', T[spots[1]], close, dz_mm=SPOT_DZ_MM.get(spots[1], 0.0))
    J = lambda name, phase, a, b: dict(name=name, phase=phase, kind='joint', qs=[list(a), list(b)])
    return ([J('park -> above the pick', 'approach', park0, pick[0]['qs'][0])] + pick +
            [J('carry, beaker clear above the receiver', 'carry', pick[-1]['qs'][-1], place[0]['qs'][0])] + place +
            [J('return to park', 'park', place[-1]['qs'][-1], park1)])


def apply_overrides(segs, key, ov=None):
    """hand-taught corrections (deg per joint) for poses of step ``key``: the taught segment and the slow (non-joint)
    segments touching it shift by the offset; the neighbouring joint moves end / start at the shifted pose"""
    ov = load_overrides() if ov is None else ov
    segs = [dict(g, qs=[list(q) for q in g['qs']]) for g in segs]
    for name, d in (ov.get(key) or {}).items():
        names = [g['name'] for g in segs]
        if name not in names: continue
        i = names.index(name); off = np.radians(np.asarray(d, float))
        lo = i
        while lo > 0 and segs[lo - 1]['kind'] != 'joint': lo -= 1
        hi = i
        while hi + 1 < len(segs) and segs[hi + 1]['kind'] != 'joint': hi += 1
        for g in segs[lo:hi + 1]: g['qs'] = [list(np.asarray(q) + off) for q in g['qs']]
        if lo > 0: segs[lo - 1]['qs'][-1] = list(np.asarray(segs[lo - 1]['qs'][-1]) + off)
        if hi + 1 < len(segs): segs[hi + 1]['qs'][0] = list(np.asarray(segs[hi + 1]['qs'][0]) + off)
    return segs
REACH_DEG = 5.0          # a segment's last waypoint counts as reached inside this (gravity sag is ~3 deg)
NEAR_DEG = 2.0           # segment ends near the cups (approach / pick / place / retreat)
GRIP_HOLD_S = 0.4        # after the jaws close or open
APPROACH_GRIP_DEG = 85.0 # jaws almost fully open on every approach: the widest margin for a cup that is a bit off
POUR_JUMP_DEG = 3.0      # the planned pour manifold swings the arm through ~17 deg/sample near 84-96 deg tilt: stop before
POUR_DRAIN_S = 1.5       # hold at the deepest smooth tilt so the beaker empties
PASS_DEG = 12.0          # intermediate waypoints: move on once inside this (the arm flows through them)
# rest pose: both arms folded back (lift back, elbow folded), where they hold themselves with the power off
# (measured 2026-10-18 as the mean of both arms resting, pulled just inside the calibrated limits)
REST_DEG = [-9.0, -99.0, 93.0, -10.0, 0.0, 0.0]
WAYPOINT_TIMEOUT_S = 2.0          # last waypoint of a segment
PASS_TIMEOUT_S = 0.4              # intermediate waypoints


MEGA = None              # set in main(); the sled can run in the background while an arm moves
SLED = {}                # {'seq', 't_end', 'deg'} while a background stage move is running


def mega_tick():
    """while a background stage move runs: read its replies and keep the Mega's 500 ms comm watchdog fed"""
    if not SLED or MEGA is None: return
    MEGA._pump(); MEGA._keepalive()
    if MEGA.faults: raise MegaError(MEGA.faults[-1])
    for r in MEGA.replies.get(SLED['seq'], []):
        if 'err' in r: raise MegaError(r)
        if r.get('done'):
            print('   sled at %.0f deg' % r['deg'], flush=True); SLED.clear(); return
    if time.time() > SLED['t_end']: raise TimeoutError('sled move seq %d not done' % SLED['seq'])


def nap(seconds):
    """sleep, but keep a background sled move serviced"""
    t_end = time.time() + seconds
    while True:
        mega_tick(); left = t_end - time.time()
        if left <= 0: return
        time.sleep(min(left, 0.05))


def sled_start(deg, St):
    """send the stage move and return at once (its ack is checked); mega_tick() follows it to done"""
    seq = MEGA.send('ST', deg=float(deg), ms=int(St['move_s'] * 1000)); MEGA.wait(seq, key=('ack',))
    SLED.update(seq=seq, t_end=time.time() + St['move_s'] + St['timeout_extra_s'] + 3, deg=deg)
    print('   sled moving to %.0f deg (in parallel with the arm)' % deg, flush=True)


def sled_wait():
    while SLED: nap(0.05)


def turn_deck(mega, deg, bench):
    """carousel move with one retry: a TT_TIMEOUT that does not reproduce happened once on the bench"""
    for attempt in (1, 2):
        cur = mega.command('PING').get('tt')
        if cur is not None and abs(deg - cur) <= 2.0: return dict(deg=cur)          # already there (inside the noise)
        cur = cur or 0.0
        ms = int(max(1000, abs(deg - cur) / 45.0 * 1000 * bench['params']['carousel']['min_s_per_45deg']) + 200)
        try: return mega.motion('TT', done_timeout=ms / 1000 + 6, deg=float(deg), ms=ms)
        except MegaError as e:
            if attempt == 2: raise
            print('   carousel: %s, re-homing and retrying once' % e, flush=True); mega.command('CLR', home=True)


def deck_for_step(name, bench):
    """deck angle that puts the step's carousel pocket at the pick spot (None: the step does not use the carousel)"""
    if 'carousel' not in name: return None
    C = bench['params']['carousel']; brg = mechanisms.station_bearings(bench)
    pocket = mechanisms.INITIAL_POCKETS.index('P2' if 'P2' in name else 'P1')
    return mechanisms.deck_angle(C['pocket_ids_deg'][pocket], brg['pick'], C['deck_range_deg'])


def go(arm, q, speed, label='', tol=REACH_DEG, timeout=WAYPOINT_TIMEOUT_S, quiet=False, joints=5):
    """command one waypoint and wait until every joint is within tol (or the timeout)"""
    try: span = np.degrees(np.abs(arm.read_positions() - np.asarray(q, float)))[:5].max()
    except ConnectionError: span = 90.0
    arm.set_goal(np.asarray(q, float), speed_scale=speed)
    timeout = max(timeout, 3.0 * span / (arm.vmax_deg_s * speed) + (0.0 if quiet else 1.0))   # long moves get the time they need
    t0 = time.time(); err = float('nan'); misses = 0
    while time.time() - t0 < timeout:
        try:
            err = np.degrees(np.abs(arm.read_positions() - np.asarray(q, float)))[:joints].max(); misses = 0
        except ConnectionError as e:                  # a dropped status packet: the arm keeps its goal, try again
            misses += 1
            if misses >= 10: raise
            time.sleep(0.05); continue
        if err < tol: return err
        nap(0.03)
    if not quiet:
        try: d = np.degrees(arm.read_positions() - np.asarray(q, float))
        except ConnectionError: d = np.full(6, np.nan)
        names = ('pan', 'lift', 'elbow', 'wflex', 'wroll', 'grip')
        print('   %s: %.1f deg off after %.1f s, continuing (%s)' % (label, err, timeout, ' '.join('%s %+.0f' % (k, v) for k, v in zip(names, d))), flush=True)
    return err


def bench_segments(segs, key=None):
    """the plan's segments, adjusted for the bench: jaws wide open while approaching a cup (until they close); the
    pour manifold cut before its arm-flip region, a drain hold, then the pour retraced back to the 40 deg pose
    (the plan's untilt starts at 40 deg, which made the arm snap back from 105 deg)"""
    out = []; closed = False
    if key is not None: segs = taught_segments(apply_overrides(segs, key), key)
    for seg in segs:
        seg = dict(seg); qs = [list(q) for q in seg['qs']]
        if seg['phase'] == 'pick': qs[0][5] = math.radians(APPROACH_GRIP_DEG); closed = True
        elif seg['phase'] == 'approach' and not closed:
            for q in qs: q[5] = math.radians(APPROACH_GRIP_DEG)
        if seg['name'].startswith('pour manifold'):
            d = np.degrees(np.abs(np.diff(np.array(qs), axis=0)))[:, :4].max(axis=1)
            cut = next((i for i, x in enumerate(d) if x > POUR_JUMP_DEG), len(qs) - 1)
            qs = qs[:cut + 1]
            seg['qs'] = qs; seg['name'] = 'pour to %.0f deg tilt (smooth part)' % (40 + 65.0 * cut / max(1, len(d))); out.append(seg)
            out.append(dict(name='drain %.1f s' % POUR_DRAIN_S, phase='drain', kind='hold', qs=[qs[-1]]))
            out.append(dict(name='retrace the pour to 40 deg', phase='pour_back', kind='cartesian', qs=qs[::-1]))
            continue
        seg['qs'] = qs; out.append(seg)
    return out


def play_segment(arm, seg, speed):
    if seg['kind'] == 'hold':
        nap(POUR_DRAIN_S); return
    qs = seg['qs']
    if seg['kind'] == 'joint' and len(qs) == 2: qs = qs[1:]          # joint moves: straight to the end
    vmax = arm.vmax_deg_s * speed
    prev = None
    for q in qs[:-1]:                             # stream the path on a clock: each waypoint after its planned spacing
        q = np.asarray(q, float)
        dt = 0.0 if prev is None else float(np.degrees(np.abs(q - prev))[:5].max()) / vmax
        try: arm.set_goal(q, speed_scale=speed)
        except ConnectionError: pass              # a dropped packet: the next waypoint supersedes it
        nap(max(dt, 0.02)); prev = q
    near = seg['phase'] in ('approach', 'pick', 'place', 'retreat')        # close to the cups: tighter end
    grip = seg['phase'] in ('pick', 'place')                                 # the jaws must finish closing / opening
    go(arm, qs[-1], speed, seg['name'], tol=NEAR_DEG if near else REACH_DEG, joints=6 if grip else 5)
    if grip: nap(GRIP_HOLD_S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--speed', type=float, default=0.6, help='fraction of the calibration max speed (default 0.6)')
    ap.add_argument('--steps', nargs='*', help='step numbers to run (default all), e.g. 1 4')
    ap.add_argument('--no-mega', action='store_true', help='leave the carousel alone')
    ap.add_argument('--yes', action='store_true', help='do not wait for Enter between steps')
    ap.add_argument('--end-turn', type=float, default=90.0, help='carousel angle at the very end (0 = no turn; default 90)')
    ap.add_argument('--rest', action='store_true', help='only send both arms to the rest pose, then torque off')
    ap.add_argument('--check', action='store_true', help='pre-flight only: open the ports read-only, check every waypoint, move nothing')
    a = ap.parse_args()
    plans = json.loads((paths.SIM_ROOT / 'reports' / 'native_plans.json').read_text())['steps']
    R = layout.load_params()['recipe']
    if R.get('yeast_in_flask'): default = ('1', '2', '3', '4')          # MVP: peroxide only, yeast-water already in the flask
    elif R.get('premixed_yeast_water'): default = ('1', '2', '3', '4', '6', '8', '9')
    else: default = tuple(k.split()[0] for k in plans)
    order = [k for k in plans if k.split()[0] in (a.steps or default)]
    last_funnel = [k for k in order if 'funnel' in k][-1:]                # the sled goes out after the last funnel pour
    bench = layout.load_bench()
    kw = dict(PORTS, calibration_path=CAL, dry_run=a.check)
    if a.no_mega: kw['port_mega'] = None
    bb = make_bench('real', allow_hardware=True, **kw)
    arms = bb.arms
    mega = None if a.no_mega else bb.mega
    global MEGA; MEGA = mega
    if mega is not None:                          # opening the CH340 port resets the Mega: wait for the boot line
        time.sleep(2.5)
        try: bb.transport.read_lines()
        except Exception: pass
    # pre-flight: every planned waypoint must be inside the arm's calibrated limits, or nothing moves
    bad = []
    for k in order + [x for x in plans if x not in order][:0]:
        for seg in bench_segments(plans[k]['segments'], k):
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
        rest = np.radians(REST_DEG)
        if mega is not None:
            mega.command('CLR', home=True)
            St = bench['params']['stage']               # the sled starts out (flask under the funnel); it retracts only
            st = mega.command('PING').get('st')         # after the last pour, and stays retracted until the next run
            if st is None or abs(st - St['work_deg']) > 2.0:
                r = mega.motion('ST', done_timeout=St['move_s'] + St['timeout_extra_s'] + 3, deg=float(St['work_deg']), ms=int(St['move_s'] * 1000))
                print('sled out to %.0f deg (start position)' % r['deg'], flush=True)
        if a.rest:
            for name, arm in arms.items():
                if not a.yes: input('\nEnter: move %s to the rest pose (slow) ' % name)
                go(arm, rest, min(a.speed, 0.3), 'rest ' + name)
            for arm in arms.values(): arm.set_torque(False)
            print('both arms at rest, torque off'); return 0
        # from wherever they are (usually rest) both arms go to the plan's park pose, one at a time
        park = {}
        for k in plans:
            if plans[k]['arm'] not in park: park[plans[k]['arm']] = plans[k]['segments'][0]['qs'][0]
        for name, q in park.items():
            if not a.yes: input('\nEnter: move %s to the park pose ' % name)
            err = go(arms[name], q, a.speed, 'park ' + name, tol=8.0, timeout=15.0)
            if not err < 8.0: raise TimeoutError('%s did not reach park (%.0f deg off)' % (name, err))
        for k in order:
            s = plans[k]; arm = arms[s['arm']]
            deck = deck_for_step(k, bench)
            msg = '\nEnter: step %s (%s arm%s) ' % (k, s['arm'], '' if deck is None else ', carousel to %.1f deg first' % deck)
            if a.yes: print(msg)
            else: input(msg)
            if deck is not None and mega is not None:
                r = turn_deck(mega, deck, bench)
                print('   carousel at %.1f deg' % r['deg'], flush=True)
            funnel = 'funnel' in k
            for seg in bench_segments(s['segments'], k):
                fast = funnel and seg['phase'] == 'pour' and not seg['name'].startswith('untilt')   # tilt-in + pour: all at once
                print('   %-38s %s%s' % (seg['name'], seg['phase'], '  (all at once)' if fast else ''), flush=True)
                play_segment(arm, seg, 1.0 if fast else a.speed)
                if k in last_funnel and seg['phase'] == 'drain' and mega is not None:
                    # the pour is done: the sled retracts at once, the arm retraces / retreats meanwhile
                    # (the beaker's lip stays >= 65 mm above the funnel rim through the pour, so the funnel passes under it)
                    sled_start(bench['params']['stage']['erupt_deg'], bench['params']['stage'])
            sled_wait()
            # never start the next step (maybe the other arm) before this arm is really back at park
            end = s['segments'][-1]['qs'][-1]
            err = go(arm, end, a.speed, 'back at park', tol=8.0, timeout=15.0)
            if not err < 8.0: raise TimeoutError('%s arm did not get back to park (%.0f deg off)' % (s['arm'], err))
        if mega is not None and a.end_turn:             # finale: the next cup comes round to the pick spot
            r = turn_deck(mega, a.end_turn, bench); print('carousel turned to %.0f deg (end)' % r['deg'], flush=True)
        for name, arm in arms.items():
            if not a.yes: input('\nEnter: return %s to the rest pose ' % name)
            go(arm, rest, min(a.speed, 0.3), 'rest ' + name)
        for arm in arms.values(): arm.set_torque(False)
        print('\ndone: both arms back at rest, torque off')
    except (KeyboardInterrupt, ConnectionError, TimeoutError, MegaError) as stop_reason:
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
