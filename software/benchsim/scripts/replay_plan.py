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

class WallClock:
    """time for the waits below: the wall on the real bench; an emulated bench (--emulate, the backend) swaps in its
    sim clock so every wait advances the simulated world instead"""
    def now(self): return time.time()
    def sleep(self, dt):
        if dt > 0: time.sleep(dt)


CLOCK = WallClock()
T0 = time.time()
_print = print
LOG_HOOKS = []                                   # callables(line): the backend forwards the log to its event store
STEP_HOOKS = []                                  # callables(step_key, 'start' | 'done')
SEG_HOOKS = []                                   # callables(step_key, segment, 'start' | 'done'): segments as played (bench_segments)
def print(*args, **kw):                          # every log line carries the elapsed time
    _print('%6.1fs' % (time.time() - T0), *args, **kw)
    for h in LOG_HOOKS: h(' '.join(str(x) for x in args).strip())


class ReplayStop(Exception):
    """raised from outside (the backend's stop button) to freeze the arms the way Ctrl-C does"""

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


SPOT_DZ_MM = {'transfer_carousel_side': 7.0,    # side poses taught by hand; the 20 deg tilt drops the fingertips ~7 mm, so the
              'transfer_scale_side': 8.0,      # grip point rises to keep them at the taught height (scale: + 2 mm release gap)
              'transfer_carousel_pick': 15.0,   # bench 2026-10-18: the grab was 1-2 cm low (caught the carousel ring)
              'transfer_scale': 10.0,          # and the place on the scale 1 cm low
              'pourer_rack1': 30.0}            # the pourer's peroxide grab 3 cm higher (2 + 1 after the second test)
OPEN_DEG = {'pourer': 55.0}                    # approach opening per arm (the pourer's side grasp: less wide)
BACK_MM = {'pourer': 8.0}                      # approach offset per arm
SPOT_BACK_MM = {'pourer_scale': 30.0}         # per spot (overrides the arm): P1 on the scale was tipped by an 8 mm approach
SPOT_CLOSE_DURING = {'pourer_scale'}          # close while advancing so P1's centre stays put (the rack grab closes after)
GRAB_SLIDE_MM = {}   # (spot: x, y) where the closing jaws end up vs the taught grip (10 mm toward the base was too close at the carousel)
SPOT_SHIFT_MM = {}   # (spot: x, y) moves both the pick and the place there
PLACE_SHIFT_MM = {'pourer_rack1': (-20.0, 0.0),
                  'transfer_scale': (-11.2, 9.9)}   # set P1 down 10 mm right + 10 mm toward the arm; the pan ring re-centres it, so step 4 picks at the taught spot   # place-back translation (world x, y): 2 cm to the operator's right
POUR_DZ_MM = {'2': -10.0}                      # 1 cm lower than the plan (was 2: the gripper touched P1)
POUR_PAN_DEG = {'2': -5.0}                     # base rotation of the peroxide pour; 1 deg = ~5 mm, NEGATIVE = operator's left (sim: +4 deg moves the beaker 17 mm right). 2026-10-18: 2 cm left of -1
SPOT_UP_MM = {'transfer_scale_side': 40.0}    # above the scale: 3 cm higher than the first side-grip run (top of the line may drift, see SPOT_IK_TOL)
SPOT_IK_TOL = {'transfer_scale_side': 10.0, 'transfer_scale': 10.0}   # transfer_scale: the top of the empty-jaw lift-off drifts ~5 mm  # at the elbow limit the line cannot stay vertical: ~1 mm off 10 mm up, ~4 mm at 20, ~8 mm at 40
SPOT_W_ORI = {}
CLOSE_AFTER_ADVANCE = {'pourer'}               # advance with the jaws open, THEN close (closing while moving shoved the beaker)
CARRY_TUCK_MM, CARRY_RISE_MM, CARRY_N = 30.0, 25.0, 16   # pourer carries arc around its base, closer to the arms


def load_taught():
    try:
        with open(TAUGHT) as f: return json.load(f)
    except (OSError, ValueError): return {}


def linear_pick(arm, q_touch, grip_close_deg, site='grasp_td', dz_mm=0.0, spot=None):
    """straight-line top-down pick around a hand-taught touch pose, built RELATIVE to it (sim kinematics give the
    directions; the absolute sim/bench offset at this pose cancels): above-and-back -> straight down (jaws wide) ->
    advance onto the cup while the jaws close -> straight up. Returns four segments (joint, descend, advance, lift)."""
    K, m = kin()
    q_touch = np.asarray(q_touch, float)
    p0, R0 = K.site(arm, q_touch, site)
    K.set(arm, q_touch)
    p0 = p0 + np.array([*SPOT_SHIFT_MM.get(spot, (0.0, 0.0)), dz_mm])      # height (and spot position) correction
    gpos = lambda n: [K.d.geom_xpos[i] * 1000 for i in range(m.ngeom) if m.geom(i).name == '%s/%s' % (arm, n)][0]
    ff, fm = gpos('finger_fixed'), gpos('finger_moving')
    back = np.r_[(ff - fm)[:2], 0.0]; back /= np.linalg.norm(back)          # away from the cup, toward the fixed finger
    up = np.array([0.0, 0.0, 1.0]); P = dict(PICK, open_deg=OPEN_DEG.get(arm, PICK['open_deg']), back_mm=SPOT_BACK_MM.get(spot, BACK_MM.get(arm, PICK['back_mm'])), up_mm=SPOT_UP_MM.get(spot, PICK['up_mm']), lift_mm=SPOT_UP_MM.get(spot, PICK['lift_mm']))
    def solve(pts, seed, grips):
        out = []; q = seed.copy()
        for pt, g in zip(pts, grips):
            qs, perr, aerr = K.ik(arm, site, pt, z_axis=R0[:, 2], q0=q[:5].tolist() + [q[5]], w_ori=SPOT_W_ORI.get(spot, 20.0))   # straight line first; the tool may tilt (<= ~15 deg at the top: the wrist flex limit)
            q = np.r_[np.asarray(qs, float)[:5], math.radians(g)]
            if perr > SPOT_IK_TOL.get(spot, 4.0): raise ValueError('pick IK: %.1f mm off at %s' % (perr, np.round(pt, 1)))
            out.append(q.tolist())
        return out
    A = p0 + P['back_mm'] * back + P['up_mm'] * up; B = p0 + P['back_mm'] * back
    p0 = p0 + np.r_[GRAB_SLIDE_MM.get(spot, (0.0, 0.0)), 0.0]               # where the closing jaws end up (staging A, B unchanged)
    lin = lambda a, c, n: [a + (c - a) * t for t in np.linspace(0, 1, n)]
    descend = solve(lin(A, B, P['n_descend']), q_touch, [P['open_deg']] * P['n_descend'])
    if arm in CLOSE_AFTER_ADVANCE and spot not in SPOT_CLOSE_DURING:          # fixed finger onto the cup first, then close
        advance = solve(lin(B, p0, P['n_advance']), np.asarray(descend[-1]), [P['open_deg']] * P['n_advance'])
        advance.append(advance[-1][:5] + [math.radians(grip_close_deg)])
    else:                                                                     # close while advancing (transfer)
        adv_g = list(np.linspace(P['open_deg'], grip_close_deg, P['n_advance']))
        advance = solve(lin(B, p0, P['n_advance']), np.asarray(descend[-1]), adv_g)
    lift = solve(lin(p0, p0 + P['lift_mm'] * up, P['n_lift']), np.asarray(advance[-1]), [grip_close_deg] * P['n_lift'])
    return [dict(name='straight down, jaws wide (15 mm back)', phase='approach', kind='cartesian', qs=descend),
            dict(name='advance onto the cup while closing', phase='pick', kind='cartesian', qs=advance),
            dict(name='lift straight up', phase='carry', kind='cartesian', qs=lift)]


def linear_place(arm, q_touch, grip_close_deg, site='grasp_td', dz_mm=0.0, spot=None):
    """straight-line place around a hand-taught hold pose (relative, like linear_pick): arrive above it with the beaker
    clear of the receiver's lip -> straight down -> open the jaws -> back off -> straight up. Returns (above_q, segments)."""
    K, m = kin(); P = dict(PICK, open_deg=OPEN_DEG.get(arm, PICK['open_deg']), back_mm=BACK_MM.get(arm, PICK['back_mm']), up_mm=SPOT_UP_MM.get(spot, PICK['up_mm']), lift_mm=SPOT_UP_MM.get(spot, PICK['lift_mm']))
    q_touch = np.asarray(q_touch, float); q_touch[5] = math.radians(grip_close_deg)
    p0, R0 = K.site(arm, q_touch, site); K.set(arm, q_touch)
    sx, sy = np.add(PLACE_SHIFT_MM.get(spot, (0.0, 0.0)), SPOT_SHIFT_MM.get(spot, (0.0, 0.0)))
    p0 = p0 + np.array([sx, sy, dz_mm])                                     # height / place-back correction for this spot
    gpos = lambda n: [K.d.geom_xpos[i] * 1000 for i in range(m.ngeom) if m.geom(i).name == '%s/%s' % (arm, n)][0]
    back = np.r_[(gpos('finger_fixed') - gpos('finger_moving'))[:2], 0.0]; back /= np.linalg.norm(back)
    up = np.array([0.0, 0.0, 1.0])
    def solve(pts, seed, grips):
        out = []; q = seed.copy()
        for pt, g in zip(pts, grips):
            qs, perr, aerr = K.ik(arm, site, pt, z_axis=R0[:, 2], q0=q[:5].tolist() + [q[5]], w_ori=SPOT_W_ORI.get(spot, 20.0))
            q = np.r_[np.asarray(qs, float)[:5], math.radians(g)]
            if perr > SPOT_IK_TOL.get(spot, 4.0): raise ValueError('place IK: %.1f mm off at %s' % (perr, np.round(pt, 1)))
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


def carry_arc(arm, q_from, q_to, site='grasp_side', name='carry'):
    """carry a held beaker upright along an arc around the arm's base, CARRY_TUCK_MM closer in and CARRY_RISE_MM higher
    than the nearer of the two ends (a straight joint move swings it out over the flask)"""
    K, m = kin()
    from benchsim import layout
    base = np.asarray(layout.load_bench()['stations'][arm + '_base']['xy'], float)
    qa, qb = np.asarray(q_from, float), np.asarray(q_to, float)
    pa, Ra = K.site(arm, qa, site); pb, _ = K.site(arm, qb, site)
    ang = lambda p: math.atan2(p[1] - base[1], p[0] - base[0])
    ta, tb = ang(pa), ang(pb); dt = (tb - ta + math.pi) % (2 * math.pi) - math.pi
    r = min(np.hypot(*(pa[:2] - base)), np.hypot(*(pb[:2] - base))) - CARRY_TUCK_MM
    z = max(pa[2], pb[2]) + CARRY_RISE_MM
    arc = [np.r_[base + r * np.array([math.cos(ta + dt * t), math.sin(ta + dt * t)]), z] for t in np.linspace(0, 1, CARRY_N)]
    blend = lambda a, b, k: [a + (b - a) * t for t in np.linspace(0, 1, k + 1)[1:]]
    pts = blend(pa, arc[0], 5) + arc[1:] + blend(arc[-1], pb, 5)[:-1]   # ease in and out (no posture jump)
    out = [qa.tolist()]; q = qa.copy()
    for pt in pts:
        qs, perr, aerr = K.ik(arm, site, pt, z_axis=Ra[:, 2], q0=q[:5].tolist() + [q[5]], w_ori=40.0, max_dev=0.3)   # upright, same posture
        q = np.r_[np.asarray(qs, float)[:5], qa[5]]
        if perr > 6.0: raise ValueError('carry arc IK: %.1f mm off' % perr)
        out.append(q.tolist())
    out.append(qb.tolist())
    return dict(name=name + ' (arc, close to the arms)', phase='carry', kind='cartesian', qs=out)


def shift_block(arm, block, dz_mm, site='grasp_side'):
    """the same poses dz_mm lower/higher: every waypoint re-solved with its full gripper orientation kept"""
    if not dz_mm: return block
    K, m = kin(); out = []
    for g in block:
        qs = []
        for q in g['qs']:
            q = np.asarray(q, float); p, R = K.site(arm, q, site)
            sol, perr, aerr = K.ik(arm, site, p + np.array([0.0, 0.0, dz_mm]), z_axis=R[:, 2], x_axis=R[:, 0],
                                   q0=q[:5].tolist() + [q[5]], w_ori=100.0, max_dev=0.25)
            if perr > 3.0 or aerr > 3.0: raise ValueError('pour shift: %.1f mm / %.1f deg off' % (perr, aerr))
            qs.append(np.r_[np.asarray(sol, float)[:5], q[5]].tolist())
        out.append(dict(g, qs=qs))
    return out


def pourer_taught(segs, q_spot, spot, step=None):
    """pourer step with a hand-taught grab spot: straight-line grab there, the plan's carry / pour / raise in between,
    and the beaker put back on the same spot with a straight-line place"""
    names = [g['name'] for g in segs]
    close = math.degrees(segs[next(i for i, nm in enumerate(names) if nm.startswith('close on'))]['qs'][-1][5])
    dz = SPOT_DZ_MM.get(spot, 0.0)
    pick = linear_pick('pourer', q_spot, close, site='grasp_side', dz_mm=dz, spot=spot)
    place = linear_place('pourer', q_spot, close, site='grasp_side', dz_mm=dz, spot=spot)
    i_carry = names.index('carry to above pre-pour'); i_raise = names.index('raise from pre-pour')
    J = lambda name, phase, a, b: dict(name=name, phase=phase, kind='joint', qs=[list(a), list(b)])
    pour = shift_block('pourer', segs[i_carry + 1:i_raise + 1], POUR_DZ_MM.get(step, 0.0))   # lower / tilt / pour / untilt / raise
    dpan = math.radians(POUR_PAN_DEG.get(step, 0.0))                        # a pure base rotation of the whole pour
    if dpan: pour = [dict(g, qs=[[q[0] + dpan] + list(q[1:]) for q in g['qs']]) for g in pour]
    return ([J('park -> above the grab', 'approach', segs[0]['qs'][0], pick[0]['qs'][0])] + pick +
            [carry_arc('pourer', pick[-1]['qs'][-1], pour[0]['qs'][0], name='carry to above pre-pour')] + pour +
            [carry_arc('pourer', pour[-1]['qs'][-1], place[0]['qs'][0], name='carry back above the spot')] + place +
            [J('return to park', 'park', place[-1]['qs'][-1], segs[-1]['qs'][-1])])


TRANSFER_GRIP = 'top'      # 'top': the taught top-down grabs; 'side': the angled side grip (the FinRay jaws twisted P1 square to them)
TILT_DEG = 20.0            # transfer side grip: claw tilted this much further down than the hand-taught side pose
PICK_SHIFT_MM = {'transfer_scale_side': (-12.0, 0.0),    # bench 2026-10-18: the fixed finger came down on P1's lip / wall: grab 12 mm to the operator's right
                 'transfer_carousel_side': (-8.0, 0.0)}  # and at the carousel 8 mm to the right (no tolerance there)
PICK_BACK_MM = {'transfer_scale_side': 10.0}   # bench: the angled grab pushed too far forward and toppled P1: stop 10 mm short
PICK_VERTICAL = {'transfer_scale_side'}         # come straight down onto P1 there (along the tilted fingers shoved it over)
ANGLED = dict(in_mm=50.0, up_mm=50.0, lift_mm=60.0, out_mm=50.0, n=10)


def _rot(ax, t):
    ax = np.asarray(ax, float) / np.linalg.norm(ax); c, s_ = math.cos(t), math.sin(t); x, y, z = ax
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s_, x * z * (1 - c) + y * s_],
                     [y * x * (1 - c) + z * s_, c + y * y * (1 - c), y * z * (1 - c) - x * s_],
                     [z * x * (1 - c) - y * s_, z * y * (1 - c) + x * s_, c + z * z * (1 - c)]])


def angled_grip(arm, q_taught, dz_mm=0.0, tilt_deg=TILT_DEG, site='grasp_side', shift_xy=(0.0, 0.0)):
    """the hand-taught side grip turned into an angled one: same grip point (dz_mm higher), the claw rotated
    tilt_deg further down about the horizontal axis across the fingers (the jaws still squeeze horizontally).
    Returns (q, p0, R, fingers): the pose, the grip point, the site frame and the unit finger direction."""
    K, m = kin(); q_taught = np.asarray(q_taught, float)
    p0, R0 = K.site(arm, q_taught, site); K.set(arm, q_taught)
    gi = [j for j in range(m.nbody) if m.body(j).name == arm + '/gripper'][0]
    f = p0 - K.d.xpos[gi] * 1000; f /= np.linalg.norm(f); f_loc = R0.T @ f
    fh = f.copy(); fh[2] = 0.0; h = np.cross(fh, [0.0, 0.0, 1.0])
    R = _rot(h, math.radians(tilt_deg)) @ R0
    if (R @ f_loc)[2] > f[2]: R = _rot(h, -math.radians(tilt_deg)) @ R0      # dip the fingers, never raise them
    p0 = p0 + np.array([0.0, 0.0, dz_mm])
    q, e, a = K.ik(arm, site, p0, z_axis=R[:, 2], x_axis=R[:, 0], q0=list(q_taught), w_ori=20.0)
    if any(shift_xy):                                   # a sideways shift: solved from the unshifted angled pose
        p0 = p0 + np.array([shift_xy[0], shift_xy[1], 0.0])
        q, e, a = K.ik(arm, site, p0, z_axis=R[:, 2], x_axis=R[:, 0], q0=list(q), w_ori=20.0)
    if e > 2.0 or a > 2.0: raise ValueError('angled grip IK: %.1f mm / %.1f deg off' % (e, a))
    q = np.asarray(q, float); q[5] = q_taught[5]
    return q, p0, R, R @ f_loc


def _angled_line(arm, q0, pts, R, grips, site='grasp_side'):
    K, m = kin(); out = []; q = np.asarray(q0, float)
    for pt, g in zip(pts, grips):
        qs, e, a = K.ik(arm, site, pt, z_axis=R[:, 2], x_axis=R[:, 0], q0=q[:5].tolist() + [q[5]], w_ori=20.0)
        q = np.r_[np.asarray(qs, float)[:5], math.radians(g)]
        if e > 4.0: raise ValueError('angled line IK: %.1f mm off at %s' % (e, np.round(pt, 1)))
        out.append(q.tolist())
    return out


def pick_offset(arm, T, spot):
    """world (x, y) shift of a pick from its taught grip point: PICK_SHIFT_MM plus PICK_BACK_MM pulled back toward the arm"""
    sh = np.asarray(PICK_SHIFT_MM.get(spot, (0.0, 0.0)), float)
    if PICK_BACK_MM.get(spot):
        f = angled_grip(arm, T[spot], SPOT_DZ_MM.get(spot, 0.0))[3][:2]; sh = sh - PICK_BACK_MM[spot] * f / np.linalg.norm(f)
    return sh


def angled_pick(arm, q_taught, grip_close_deg, dz_mm=0.0, spot=None, shift_xy=(0.0, 0.0)):
    """in along the fingers with the jaws wide (the beaker slides into the jaws, centred) -> close in place -> straight up"""
    q, p0, R, f = angled_grip(arm, q_taught, dz_mm, shift_xy=tuple(shift_xy)); A = ANGLED; wide = OPEN_DEG.get(arm, PICK['open_deg'])
    lin = lambda a, c, n: [a + (c - a) * t for t in np.linspace(0, 1, n)]
    start = p0 + [0, 0, A['up_mm']] if spot in PICK_VERTICAL else p0 - A['in_mm'] * f
    advance = _angled_line(arm, q, lin(start, p0, A['n']), R, [wide] * A['n'])
    close = [advance[-1], advance[-1][:5] + [math.radians(grip_close_deg)]]
    lift = _angled_line(arm, close[-1], lin(p0, p0 + [0, 0, A['lift_mm']], A['n']), R, [grip_close_deg] * A['n'])
    return [dict(name='advance onto the cup along the fingers, jaws wide', phase='approach', kind='cartesian', qs=advance),
            dict(name='close on the cup', phase='pick', kind='grip', qs=close),
            dict(name='lift straight up', phase='carry', kind='cartesian', qs=lift)]


def angled_place(arm, q_taught, grip_close_deg, dz_mm=0.0, shift_xy=(0.0, 0.0)):
    """above -> straight down into the receiver -> open -> back out along the fingers -> up"""
    q, p0, R, f = angled_grip(arm, q_taught, dz_mm, shift_xy=shift_xy); A = ANGLED; wide = OPEN_DEG.get(arm, PICK['open_deg'])
    lin = lambda a, c, n: [a + (c - a) * t for t in np.linspace(0, 1, n)]
    down = _angled_line(arm, q, lin(p0 + [0, 0, A['up_mm']], p0, A['n']), R, [grip_close_deg] * A['n'])
    release = [down[-1], down[-1][:5] + [math.radians(wide)]]
    back = p0 - A['out_mm'] * f
    out = _angled_line(arm, release[-1], lin(p0, back, A['n']), R, [wide] * A['n'])
    up = _angled_line(arm, out[-1], lin(back, back + [0, 0, 30.0], 5), R, [wide] * 5)
    return [dict(name='straight down into the receiver', phase='carry', kind='cartesian', qs=down),
            dict(name='release', phase='place', kind='grip', qs=release),
            dict(name='back out along the fingers', phase='retreat', kind='cartesian', qs=out),
            dict(name='straight up', phase='retreat', kind='cartesian', qs=up)]


FUNNEL_XY = (450.0, 282.0)   # sim funnel axis (bench_params stations.funnel)


def tucked_route(a, park, arm='transfer'):
    """a -> park through 0-2 waypoints that move some joints to their park value first; scored on the lowest grip-point
    height along the way, among the routes that keep the arm >= 200 mm from the funnel axis"""
    import itertools
    K, m = kin(); a = np.asarray(a, float); park = np.asarray(park, float)
    ids = [j for j in range(m.nbody) if m.body(j).name in ('%s/%s' % (arm, n) for n in ('gripper', 'wrist', 'lower_arm', 'moving_jaw_so101_v1'))]
    def score(pts):
        lo, near = 1e9, 1e9
        for x, y in zip(pts[:-1], pts[1:]):
            for t in np.linspace(0, 1, 12):
                q = x + (y - x) * t; lo = min(lo, K.site(arm, q, 'grasp_side')[0][2]); K.set(arm, q)
                near = min(near, min(np.linalg.norm(K.d.xpos[i][:2] * 1000 - FUNNEL_XY) for i in ids))
        return lo if near >= 200.0 else -1e9 + near
    best = None
    for first in [()] + [c for r in (1, 2) for c in itertools.combinations((1, 2, 3), r)]:
        for second in [()] + [c for r in (1, 2) for c in itertools.combinations([j for j in (1, 2, 3) if j not in first], r)]:
            m1 = a.copy(); m1[list(first)] = park[list(first)] if first else m1[list(first)]
            m2 = m1.copy(); m2[list(second)] = park[list(second)] if second else m2[list(second)]
            pts = [a] + ([m1] if first else []) + ([m2] if second else []) + [park]
            sc = score(pts)
            if best is None or sc > best[0]: best = (sc, pts)
    return [list(p) for p in best[1]]


def taught_segments(segs, key):
    """transfer steps whose pick and place spots are both hand-taught: park -> straight-line pick -> carry with the
    beaker clear above the receiver -> straight-line place -> park (the plan's slide / channel moves are not used)"""
    T = load_taught()
    pour = POURER_STEPS.get(key.split()[0])
    if pour and pour in T: return pourer_taught(segs, T[pour], pour, key.split()[0])
    spots = TRANSFER_STEPS.get(key.split()[0])
    site = 'grasp_td'
    if TRANSFER_GRIP == 'side' and spots and all(sp.replace('_pick', '') + '_side' in T for sp in spots):   # angled side grip (2026-10-18)
        spots = tuple(sp.replace('_pick', '') + '_side' for sp in spots); site = 'grasp_side'
    if not spots or not all(sp in T for sp in spots): return segs
    names = [g['name'] for g in segs]
    close = math.degrees(segs[names.index('close on P1')]['qs'][-1][5])
    park0, park1 = segs[0]['qs'][0], segs[-1]['qs'][-1]
    if site == 'grasp_side':                                 # angled grip built from the hand-taught side poses
        pick = angled_pick('transfer', T[spots[0]], close, dz_mm=SPOT_DZ_MM.get(spots[0], 0.0), spot=spots[0],
                           shift_xy=pick_offset('transfer', T, spots[0]))
        # a beaker grabbed off-centre (PICK_SHIFT_MM) sits off-centre in the jaws: the place shifts the claw by the same
        # offset, turned with the claw (else P1 lands on the cup rim and falls over: bench 2026-10-18)
        sh = pick_offset('transfer', T, spots[0])
        if sh.any():
            yaw = lambda sp: (lambda f: math.atan2(f[1], f[0]))(angled_grip('transfer', T[sp], SPOT_DZ_MM.get(sp, 0.0))[3])
            d = yaw(spots[1]) - yaw(spots[0]); sh = np.array([[math.cos(d), -math.sin(d)], [math.sin(d), math.cos(d)]]) @ sh
        place = angled_place('transfer', T[spots[1]], close, dz_mm=SPOT_DZ_MM.get(spots[1], 0.0), shift_xy=tuple(sh))
    else:
        pick = linear_pick('transfer', T[spots[0]], close, site=site, dz_mm=SPOT_DZ_MM.get(spots[0], 0.0), spot=spots[0])
        place = linear_place('transfer', T[spots[1]], close, site=site, dz_mm=SPOT_DZ_MM.get(spots[1], 0.0), spot=spots[1])
    J = lambda name, phase, a, b: dict(name=name, phase=phase, kind='joint', qs=[list(a), list(b)])
    def via(a, park, name, phase, out):
        """park <-> a low pose at the scale, through joint-order waypoints: of the orders tried, the one whose hand stays
        highest, keeping the arm >= 20 cm (sim) from the funnel axis (going straight cut through the funnel / flask)"""
        pts = tucked_route(a, park)
        if not out: pts = pts[::-1]
        return [J('%s (%d/%d)' % (name, i + 1, len(pts) - 1), phase, pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    at_scale = site == 'grasp_side'
    head = (via(pick[0]['qs'][0], park0, 'park -> above the pick, tucked', 'approach', False) if at_scale and 'scale' in spots[0]
            else [J('park -> above the pick', 'approach', park0, pick[0]['qs'][0])])
    tail = (via(place[-1]['qs'][-1], park1, 'return to park, tucked', 'park', True) if at_scale and 'scale' in spots[1]
            else [J('return to park', 'park', place[-1]['qs'][-1], park1)])
    return (head + pick + [J('carry, beaker clear above the receiver', 'carry', pick[-1]['qs'][-1], place[0]['qs'][0])] +
            place + tail)


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
POUR_EXTRA_ROLL_DEG = {'3': 25.0}   # funnel pour: past the smooth 84 deg part, the wrist roll alone turns this much further (past flat, so it empties)
POUR_DRAIN_S = 1.5       # hold at the deepest smooth tilt so the beaker empties
GRAB_HELD_DEG = 1.5      # jaws stopped this far short of the closed command = a beaker is in them (side grip: held 2.9-3.4, missed 0.2-0.5)
GRABS = []               # (step, held, deg short) for the run summary
PASS_DEG = 12.0          # intermediate waypoints: move on once inside this (the arm flows through them)
# rest pose: both arms folded back (lift back, elbow folded), where they hold themselves with the power off
# (measured 2026-10-18 as the mean of both arms resting, pulled just inside the calibrated limits)
REST_DEG = [-9.0, -99.0, 93.0, -10.0, 0.0, 0.0]
WAYPOINT_TIMEOUT_S = 2.0          # last waypoint of a segment
PASS_TIMEOUT_S = 0.4              # intermediate waypoints


USE_TAUGHT = True        # hand-taught poses are real-bench corrections; the emulated bench (the simulator) plays the plan
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
    if CLOCK.now() > SLED['t_end']: raise TimeoutError('sled move seq %d not done' % SLED['seq'])


def nap(seconds):
    """sleep, but keep a background sled move serviced"""
    t_end = CLOCK.now() + seconds
    while True:
        mega_tick(); left = t_end - CLOCK.now()
        if left <= 0: return
        CLOCK.sleep(min(left, 0.05))


def sled_start(deg, St):
    """send the stage move and return at once (its ack is checked); mega_tick() follows it to done"""
    seq = MEGA.send('ST', deg=float(deg), ms=int(St['move_s'] * 1000)); MEGA.wait(seq, key=('ack',))
    SLED.update(seq=seq, t_end=CLOCK.now() + St['move_s'] + St['timeout_extra_s'] + 3, deg=deg)
    print('   sled moving to %.0f deg (in parallel with the arm)' % deg, flush=True)


def sled_wait():
    while SLED: nap(0.05)


def mega_start(mega, bench):
    """clear faults WITHOUT forgetting where the axes are (CLR home only when the Mega has lost track: it declares the
    axes at home without moving them), then bring the sled out to WORK, the start position of every run"""
    p = mega.command('PING')
    mega.command('CLR', home=True) if p.get('pos') == 'unknown' else mega.command('CLR')
    St = bench['params']['stage']; st = mega.command('PING').get('st')
    if st is None or abs(st - St['work_deg']) > 2.0:
        r = mega.motion('ST', done_timeout=St['move_s'] + St['timeout_extra_s'] + 3, deg=float(St['work_deg']), ms=int(St['move_s'] * 1000))
        print('sled out to %.0f deg (start position)' % r['deg'], flush=True)


def turn_deck(mega, deg, bench):
    """carousel move. The closed-loop deck settles big moves within ~1 deg but can stall on a small correction (bench
    2026-10-18: 5 deg short, the 5 deg retry timed out too), so a miss is retried by backing off 20 deg and coming in
    again with a full move; within 3 deg counts as there."""
    lo, hi = bench['params']['carousel']['deck_range_deg']
    def move(tgt):
        cur = mega.command('PING').get('tt') or 0.0
        ms = int(max(1000, abs(tgt - cur) / 45.0 * 1000 * bench['params']['carousel']['min_s_per_45deg']) + 200)
        try: return mega.motion('TT', done_timeout=ms / 1000 + 6, deg=float(tgt), ms=ms), None
        except MegaError as e:
            p = mega.command('PING')
            mega.command('CLR', home=True) if p.get('pos') == 'unknown' else mega.command('CLR')
            return None, e
    for attempt in (1, 2, 3):
        cur = mega.command('PING').get('tt')
        if cur is not None and abs(deg - cur) <= 2.0: return dict(deg=cur)          # already there (inside the noise)
        if attempt > 1:                                                             # back off for a full-size approach
            back = deg - 20.0 if deg - 20.0 >= lo else deg + 20.0
            move(back)
        r, e = move(deg)
        if r is not None: return r
        now = mega.command('PING').get('tt')
        if now is not None and abs(now - deg) <= 3.0:   # it got there, still hunting at the tolerance edge
            print('   carousel: %s, but it is at %.1f deg (target %.1f): fine' % (e, now, deg), flush=True)
            return dict(deg=now)
        if attempt == 3: raise e
        print('   carousel: %s at %s deg, backing off 20 deg and trying again' % (e, now), flush=True)


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
    t0 = CLOCK.now(); err = float('nan'); misses = 0
    while CLOCK.now() - t0 < timeout:
        try:
            err = np.degrees(np.abs(arm.read_positions() - np.asarray(q, float)))[:joints].max(); misses = 0
        except ConnectionError as e:                  # a dropped status packet: the arm keeps its goal, try again
            misses += 1
            if misses >= 10: raise
            CLOCK.sleep(0.05); continue
        if err < tol: return err
        nap(0.03)
    if not quiet:
        try: d = np.degrees(arm.read_positions() - np.asarray(q, float))
        except ConnectionError: d = np.full(6, np.nan)
        names = ('pan', 'lift', 'elbow', 'wflex', 'wroll', 'grip')
        print('   %s: %.1f deg off after %.1f s, continuing (%s)' % (label, err, timeout, ' '.join('%s %+.0f' % (k, v) for k, v in zip(names, d))), flush=True)
    return err


def bench_segments(segs, key=None, arm=None):
    """the plan's segments, adjusted for the bench: jaws wide open while approaching a cup (until they close); the
    pour manifold cut before its arm-flip region, a drain hold, then the pour retraced back to the 40 deg pose
    (the plan's untilt starts at 40 deg, which made the arm snap back from 105 deg)"""
    out = []; closed = False
    if key is not None and USE_TAUGHT: segs = taught_segments(apply_overrides(segs, key), key)
    for seg in segs:
        seg = dict(seg); qs = [list(q) for q in seg['qs']]
        wide = math.radians(OPEN_DEG.get(arm, APPROACH_GRIP_DEG))
        if seg['phase'] == 'pick': qs[0][5] = max(qs[0][5], wide) if seg['name'].startswith('advance') else wide; closed = True
        elif seg['phase'] == 'approach' and not closed:
            for q in qs: q[5] = wide
        if seg['name'].startswith('pour manifold'):
            d = np.degrees(np.abs(np.diff(np.array(qs), axis=0)))[:, :4].max(axis=1)
            cut = next((i for i, x in enumerate(d) if x > POUR_JUMP_DEG), len(qs) - 1)
            qs = qs[:cut + 1]
            seg['qs'] = qs; seg['name'] = 'pour to %.0f deg tilt (smooth part)' % (40 + 65.0 * cut / max(1, len(d))); out.append(seg)
            extra = POUR_EXTRA_ROLL_DEG.get((key or '').split(' ')[0], 0.0)
            if extra:                                   # wrist roll only, on in the direction the pour was rolling
                sgn = 1.0 if qs[-1][4] >= qs[0][4] else -1.0
                more = [qs[-1][:4] + [qs[-1][4] + sgn * math.radians(extra) * t] + qs[-1][5:] for t in np.linspace(0, 1, 9)[1:]]
                out.append(dict(name='roll %.0f deg further (past flat)' % extra, phase='pour', kind='cartesian', qs=[qs[-1]] + more))
                qs = qs + more
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
    near = seg['phase'] in ('approach', 'pick', 'place', 'retreat') or seg['name'].startswith('straight down')   # at the cups: finish the move before the jaws open
    grip = seg['phase'] in ('pick', 'place')                                 # the jaws must finish closing / opening
    go(arm, qs[-1], speed, seg['name'], tol=NEAR_DEG if near else REACH_DEG, joints=6 if grip else 5)
    if grip: nap(GRIP_HOLD_S)
    if seg['name'].startswith(('straight down', 'advance onto')):   # where the arm really ended up at the cup (sag check)
        d = np.degrees(arm.read_positions() - np.asarray(qs[-1], float))
        print('   landed: ' + ' '.join('%s %+.1f' % (j, x) for j, x in zip(('pan', 'lift', 'elbow', 'wflex', 'wroll'), d[:5])), flush=True)
    if seg['phase'] == 'pick':                    # did the jaws stop on a beaker, or close on air?
        short = math.degrees(qs[-1][5] - arm.read_positions()[5]) * -1
        held = short > GRAB_HELD_DEG
        GRABS.append((seg.get('step', '?'), held, round(short, 1)))
        print('   grab: %s (jaws stopped %.1f deg short of closed)' % ('HELD' if held else 'MISS?', short), flush=True)
        if not held and arm.name == 'transfer':     # carrying on would lower the empty claw onto the beaker where it still sits
            raise ReplayStop('transfer grab missed (jaws %.1f deg short of closed): stopping before the place' % short)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--speed', type=float, default=0.48, help='fraction of the calibration max speed (default 0.48)')
    ap.add_argument('--cycles', type=int, default=1, help='repeat the whole run (the 4-step demo resets itself)')
    ap.add_argument('--steps', nargs='*', help='step numbers to run (default all), e.g. 1 4')
    ap.add_argument('--no-mega', action='store_true', help='leave the carousel alone')
    ap.add_argument('--yes', action='store_true', help='do not wait for Enter between steps')
    ap.add_argument('--end-turn', type=float, default=90.0, help='turn the carousel by this many degrees at the very end, relative to where it is (0 = none; default 90)')
    ap.add_argument('--rest', action='store_true', help='only send both arms to the rest pose, then torque off')
    ap.add_argument('--emulate', action='store_true', help='no USB: the same code on emulated servos and Mega (the simulator)')
    ap.add_argument('--check', action='store_true', help='pre-flight only: open the ports read-only, check every waypoint, move nothing')
    a = ap.parse_args()
    if a.emulate:
        from benchsim.backends.emu import make_emulated_bench
        global CLOCK
        sim_bb = make_bench('sim')
        bb = make_emulated_bench(sim_bb, CAL, dry_run=a.check, with_mega=not a.no_mega)
        CLOCK = bb.clock
        print('emulated bench: LeRobotArm + SerialTransport on the simulator (no ports opened)')
    else:
        kw = dict(PORTS, calibration_path=CAL, dry_run=a.check)
        if a.no_mega: kw['port_mega'] = None
        bb = make_bench('real', allow_hardware=True, **kw)
    return replay(bb, a)


def load_plans():
    return json.loads((paths.SIM_ROOT / 'reports' / 'native_plans.json').read_text())['steps']


def select_steps(plans, steps=None):
    """the steps to play: the ones named, else the recipe's default route"""
    R = layout.load_params()['recipe']
    if R.get('yeast_in_flask'): default = ('1', '2', '3', '4')          # MVP: peroxide only, yeast-water already in the flask
    elif R.get('premixed_yeast_water'): default = ('1', '2', '3', '4', '6', '8', '9')
    else: default = tuple(k.split()[0] for k in plans)
    return [k for k in plans if k.split()[0] in (steps or default)]


def replay(bb, a):
    """the dry run on an opened bench (real or emulated); ``a`` carries speed, steps, no_mega, yes, end_turn, rest, check"""
    global USE_TAUGHT
    USE_TAUGHT = not getattr(bb, 'emulated', False)
    plans = load_plans()
    order = select_steps(plans, a.steps)
    last_funnel = [k for k in order if 'funnel' in k][-1:]                # the sled goes out after the last funnel pour
    bench = layout.load_bench()
    arms = bb.arms
    mega = None if a.no_mega else bb.mega
    global MEGA; MEGA = mega
    if mega is not None and not getattr(bb, 'emulated', False):   # opening the CH340 port resets the Mega: wait for the boot line
        CLOCK.sleep(2.5)
        try: bb.transport.read_lines()
        except Exception: pass
    # pre-flight: every planned waypoint must be inside the arm's calibrated limits, or nothing moves
    bad = []
    for k in order + [x for x in plans if x not in order][:0]:
        for seg in bench_segments(plans[k]['segments'], k, plans[k]['arm']):
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
            mega_start(mega, bench)                     # sled out (it retracts only after the last pour, until the next run)
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
        for cyc in range(getattr(a, 'cycles', 1)):
            if cyc:
                print('\n===== run %d of %d =====' % (cyc + 1, a.cycles), flush=True)
                if mega is not None: mega_start(mega, bench)     # sled back out for the next run
            for k in order:
                s = plans[k]; arm = arms[s['arm']]
                deck = deck_for_step(k, bench)
                msg = '\nEnter: step %s (%s arm%s) ' % (k, s['arm'], '' if deck is None else ', carousel to %.1f deg first' % deck)
                if a.yes: print(msg)
                else: input(msg)
                for h in STEP_HOOKS: h(k, 'start')
                if deck is not None and mega is not None:
                    # the four pockets are 90 deg apart: whichever cup sits at the pick spot is the one the operator loaded,
                    # so only nudge to the nearest pocket alignment (never carry the loaded cup away)
                    cur = mega.command('PING').get('tt') or 0.0; C = bench['params']['carousel']
                    cands = [deck + 90.0 * n for n in range(-4, 5) if C['deck_range_deg'][0] <= deck + 90.0 * n <= C['deck_range_deg'][1]]
                    deck = min(cands, key=lambda d: abs(d - cur))
                    r = turn_deck(mega, deck, bench)
                    print('   carousel at %.1f deg' % r['deg'], flush=True)
                funnel = 'funnel' in k
                for seg in bench_segments(s['segments'], k, s['arm']):
                    fast = funnel and seg['phase'] == 'pour' and not seg['name'].startswith('untilt')   # tilt-in + pour: all at once
                    print('   %-38s %s%s' % (seg['name'], seg['phase'], '  (all at once)' if fast else ''), flush=True)
                    for h in SEG_HOOKS: h(k, seg, 'start')
                    seg = dict(seg, step=k.split()[0])
                    play_segment(arm, seg, 1.0 if fast else a.speed)
                    for h in SEG_HOOKS: h(k, seg, 'done')
                    if k in last_funnel and seg['phase'] == 'drain' and mega is not None:
                        # the pour is done: the sled retracts at once, the arm retraces / retreats meanwhile
                        # (the beaker's lip stays >= 65 mm above the funnel rim through the pour, so the funnel passes under it)
                        sled_start(bench['params']['stage']['erupt_deg'], bench['params']['stage'])
                sled_wait()
                # never start the next step (maybe the other arm) before this arm is really back at park
                end = s['segments'][-1]['qs'][-1]
                err = go(arm, end, a.speed, 'back at park', tol=8.0, timeout=15.0)
                if not err < 8.0: raise TimeoutError('%s arm did not get back to park (%.0f deg off)' % (s['arm'], err))
                for h in STEP_HOOKS: h(k, 'done')
            if mega is not None and a.end_turn:             # finale: the carousel turns a.end_turn deg from where it is
                cur = mega.command('PING').get('tt') or 0.0; lo, hi = bench['params']['carousel']['deck_range_deg']
                tgt = cur + a.end_turn
                if not lo <= tgt <= hi: tgt = cur - a.end_turn     # past the range end: the short way back (not a 270 deg swing)
                r = turn_deck(mega, tgt, bench); print('carousel turned %+.0f deg to %.0f deg (end)' % (tgt - cur, r['deg']), flush=True)
            if mega is not None:                            # and the sled back out to WORK, ready for the next run
                St = bench['params']['stage']
                r = mega.motion('ST', done_timeout=St['move_s'] + St['timeout_extra_s'] + 3, deg=float(St['work_deg']), ms=int(St['move_s'] * 1000))
                print('sled back out to %.0f deg (end)' % r['deg'], flush=True)
        if GRABS:
            print('\ngrabs: %d/%d held' % (sum(g[1] for g in GRABS), len(GRABS)))
            for st, held, short in GRABS: print('   step %s: %s (%.1f deg short of closed)' % (st, 'held' if held else 'MISS?', short))
        print('\ndone: both arms at park (up), torque on')      # no folded rest pose: it sat in the other arm's way
        return 0
    except (KeyboardInterrupt, ReplayStop, ConnectionError, TimeoutError, MegaError) as stop_reason:
        print('\nstopping:', type(stop_reason).__name__, stop_reason)
        for name, arm in arms.items():
            try: arm.set_goal(arm.read_positions(), 1.0)
            except Exception as e: print(name, 'freeze failed:', e)
        print('\nstopped: both arms frozen in place, torque on')
        return 2
    finally:
        for name, arm in arms.items():
            try: arm.disconnect()
            except Exception: pass


if __name__ == '__main__':
    main()
