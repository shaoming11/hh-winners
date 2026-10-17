"""Backend-independent arm motion: path following, gripper actions and grasp classification.

Everything here talks to ArmBackend and Clock only (positions, loads, goals), so the same code drives the
simulator and the hardware. Grasps are classified from the observed jaw angle after a torque-limited close,
the way the real gripper detects a miss (demo_process 3): closing past the expected contact angle means
nothing is between the fingers.
"""
import math
from dataclasses import dataclass, field

import numpy as np


class MotionFault(RuntimeError):
    def __init__(self, code, detail=''):
        super().__init__('%s: %s' % (code, detail)); self.code = code; self.detail = detail


@dataclass
class GraspResult:
    outcome: str                  # 'grasped' | 'miss' | 'ambiguous'
    jaw_deg: float
    expected_deg: float
    load_permille: float
    detail: str = ''


@dataclass
class MotionLog:
    rows: list = field(default_factory=list)

    def add(self, **kw): self.rows.append(kw)


def densify(qs, max_step_deg=1.0):
    out = [np.asarray(qs[0], float)]
    for a, b in zip(qs[:-1], qs[1:]):
        a, b = np.asarray(a, float), np.asarray(b, float)
        n = max(1, int(math.ceil(math.degrees(np.abs(b[:5] - a[:5]).max()) / max_step_deg)))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return out


def follow(arm, qs, clock, speed_deg_s=40.0, rate_hz=50.0, track_tol_deg=6.0, stall_s=0.4, settle_tol_deg=0.8, settle_timeout=3.0,
           on_tick=None, log=None):
    """stream goals along a joint path at a constant joint speed (largest joint), like LeRobot goal streaming.
    Raises MotionFault('STALL') if the tracking error stays above track_tol_deg for stall_s (blocked or unreachable)."""
    path = densify(qs); seg = [0.0]
    for a, b in zip(path[:-1], path[1:]): seg.append(seg[-1] + math.degrees(np.abs(b[:5] - a[:5]).max()))
    total = seg[-1]; v = speed_deg_s; dt = 1.0 / rate_hz; t0 = clock.now(); bad_since = None; worst = 0.0
    while True:
        s = min(v * (clock.now() - t0), total)
        k = int(np.searchsorted(seg, s, side='right') - 1); k = min(k, len(path) - 2) if len(path) > 1 else 0
        if len(path) > 1 and seg[k + 1] > seg[k]: f = (s - seg[k]) / (seg[k + 1] - seg[k]); q = path[k] + (path[k + 1] - path[k]) * f
        else: q = path[-1]
        arm.set_goal(q)
        clock.sleep(dt)
        if on_tick: on_tick()
        err = float(np.degrees(np.abs(arm.read_positions()[:5] - q[:5])).max()); worst = max(worst, err)
        if err > track_tol_deg:
            bad_since = bad_since if bad_since is not None else clock.now()
            if clock.now() - bad_since > stall_s:
                arm_hold(arm); raise MotionFault('STALL', '%s tracking error %.1f deg' % (getattr(arm, 'name', 'arm'), err))
        else: bad_since = None
        if s >= total: break
    t_end = clock.now() + settle_timeout
    while True:
        err = float(np.degrees(np.abs(arm.read_positions()[:5] - path[-1][:5])).max())
        if err < settle_tol_deg and not arm.is_moving(): break
        if clock.now() > t_end: arm_hold(arm); raise MotionFault('STALL', '%s did not settle: %.1f deg from goal' % (getattr(arm, 'name', 'arm'), err))
        clock.sleep(dt)
        if on_tick: on_tick()
    if log is not None: log.add(kind='follow', arm=getattr(arm, 'name', ''), configs=len(path), path_deg=round(total, 1), worst_track_deg=round(worst, 2))


def arm_hold(arm):
    """stop where we are (keep torque: never drop a held beaker)"""
    if hasattr(arm, 'hold_here'): arm.hold_here()
    else: arm.set_goal(arm.read_positions())


def gripper_to(arm, q6, clock, timeout=1.5, settle_s=0.25):
    """move only the gripper; returns when the jaw has stopped (contact or goal)"""
    q = arm.read_positions().copy(); goal = q.copy(); goal[:5] = arm.goal()[:5] if hasattr(arm, 'goal') else q[:5]; goal[5] = q6
    arm.set_goal(goal); t_end = clock.now() + timeout; last = arm.read_positions()[5]; still = 0.0
    while clock.now() < t_end:
        clock.sleep(0.02); j = arm.read_positions()[5]
        still = still + 0.02 if abs(j - last) < math.radians(0.15) else 0.0; last = j
        if still >= settle_s: break
    return float(arm.read_positions()[5])


def close_and_classify(arm, clock, q6_expected, q6_command, contact_tol_deg, miss_margin_deg):
    """torque-limited close to q6_command (past contact), then classify from where the jaw stopped"""
    jaw = gripper_to(arm, q6_command, clock)
    load = float(arm.read_loads()[5])
    d = math.degrees(jaw - q6_expected)
    if abs(d) <= contact_tol_deg: out = 'grasped'
    elif d < -miss_margin_deg: out = 'miss'
    else: out = 'ambiguous'
    return GraspResult(out, round(math.degrees(jaw), 2), round(math.degrees(q6_expected), 2), load,
                       'jaw stopped %.2f deg from the expected contact angle' % d)


def assert_parked(arm, park_q, tol_deg=1.0):
    err = float(np.degrees(np.abs(arm.read_positions()[:5] - np.asarray(park_q)[:5])).max())
    if err > tol_deg: raise MotionFault('NOT_PARKED', '%s is %.1f deg from park' % (getattr(arm, 'name', 'arm'), err))
