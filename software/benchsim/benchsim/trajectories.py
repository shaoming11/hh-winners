"""Audit of the recorded CAD-planner arm paths (tools/layout/anim_paths.json) replayed on the MJCF arms.

The recorded angles are in the CAD planner convention (see benchsim.cadmap). This module
1. searches the 32 joint-sign combinations and reports which keep every recorded station frame inside the
   MJCF joint limits and how far each lands from its station (``sign_search``);
2. replays every recorded frame (densified so no joint moves more than 2 deg between checks) with the other
   arm parked and the held beaker attached, and reports joint limits, margins, held-beaker tilt, pour-lip
   height over the receiver and contacts/clearance (``audit``).

Status labels: the mapping is called ``approximate`` (not calibrated) unless every station endpoint lands within
ENDPOINT_TOL_MM and every frame is inside the joint limits with no collision.
"""
import itertools
import json
import math

import numpy as np

from . import cadmap, paths, scene, state
from .kinematics import Kin

ENDPOINT_TOL_MM = 2.0
ARM_OF = {'A': 'pourer', 'B': 'transfer'}          # planner model tags (layout_final.md: pourer = model tag A)
RECEIVER = {'P_dev': 'scale_pan', 'P_wat': 'scale_pan', 'P_fun': 'funnel'}
SOURCE = {'P_dev': 'rack_1', 'P_wat': 'rack_3', 'P_fun': 'scale_pan', 'T1': 'carousel_pick', 'T2': 'scale_pan'}
DEST = {'T1': 'scale_pan', 'T2': 'carousel_pick'}


def load():
    return json.loads(paths.ANIM_PATHS.read_text())


def endpoint_tests(b, A=None):
    A = A or load(); st = b.st; steps = {s['step']: s for s in A['steps']}; tests = []
    for nm in ('P_dev', 'P_wat', 'P_fun'):
        s = steps[nm]; stn = SOURCE[nm]
        tests.append(dict(label='%s pick' % nm, arm='pourer', q_cad=np.radians(s['q_pick']), site='grasp_side',
                          target=np.r_[st[stn]['xy'], st[stn]['z'] + s['grip_h']], recorded_margin=s['pick']))
    for nm in ('T1', 'T2'):
        s = steps[nm]; seg = s['anim_paths'][0]['qs']
        for lab, q, stn, rec in (('first frame (pick)', seg[0], SOURCE[nm], s['pick']), ('last frame (place)', seg[-1], DEST[nm], s['place'])):
            tests.append(dict(label='%s %s' % (nm, lab), arm='transfer', q_cad=np.array(q), site='grasp_td',
                              target=np.r_[st[stn]['xy'], st[stn]['z']], recorded_margin=rec))
    return tests


def sign_search(K, b):
    fit = cadmap.load_fit(); q0 = np.radians(fit['q0_deg'])[:5]; tests = endpoint_tests(b); rows = []
    for s in itertools.product([1, -1], repeat=5):
        s = np.array(s, float); errs = []; inlim = True
        for t in tests:
            q = np.r_[q0 + s * t['q_cad'], 0.3]; inlim &= K.in_limits(t['arm'], q)
            p, _ = K.site(t['arm'], q, t['site']); errs.append(float(np.linalg.norm(p - t['target'])))
        rows.append(dict(signs=s.astype(int).tolist(), mean_err_mm=float(np.mean(errs)), max_err_mm=float(np.max(errs)), all_in_limits=bool(inlim)))
    rows.sort(key=lambda r: r['mean_err_mm'])
    return rows


def endpoint_table(K, b):
    rows = []
    for t in endpoint_tests(b):
        q = np.r_[cadmap.cad_to_mj(t['q_cad']), 0.3]; p, R = K.site(t['arm'], q, t['site'])
        mg, j = K.min_margin(t['arm'], q)
        rows.append(dict(pose=t['label'], arm=t['arm'], fk_mm=np.round(p, 1).tolist(), station_mm=np.round(t['target'], 1).tolist(),
                         residual_mm=round(float(np.linalg.norm(p - t['target'])), 2), min_margin_deg=round(mg, 2), binding=j,
                         recorded_margin_deg=round(t['recorded_margin'][0], 2), recorded_binding=t['recorded_margin'][1],
                         margin_diff_deg=round(mg - t['recorded_margin'][0], 2)))
    return rows


def _densify(qs, max_step_deg=2.0):
    out = [qs[0]]
    for a, b in zip(qs[:-1], qs[1:]):
        n = max(1, int(math.ceil(math.degrees(np.abs(b - a).max()) / max_step_deg)))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return out


def _held_T(sign, gh):
    """beaker frame in the gripper's grasp site frame. 'td': the grasp_td site is the beaker frame.
    side grasp: beaker axis = sign * site z (the hinge), bottom gh below the grasp centre along the axis"""
    T = np.eye(4)
    if sign == 'td': return T
    s = float(sign); T[:3, :3] = np.diag([1.0, s, s]); T[:3, 3] = [0, 0, -s * gh * 1e-3]     # metres (MJCF frame)
    return T


# where the beakers stand when each recorded step starts (demo_process 4); held beakers stay where the last held
# frame left them for the rest of the step
# recorded segment order is not time order (endpoints checked by FK): transfer = [carry, park->pick, place->park],
# pourer = [carry pick->pre-pour, tilt-in, pour 55->105, park->pick]; the pourer's return carry is not recorded
TIME_ORDER = {'transfer': [1, 0, 2], 'pourer': [3, 0, 1, 2]}
SEG_LABEL = {'transfer': {0: 'carry pick->place (held)', 1: 'approach park->pick', 2: 'retreat place->park'},
             'pourer': {0: 'carry pick->pre-pour (held)', 1: 'tilt-in (held)', 2: 'pour 55->105 deg (held)', 3: 'approach park->pick'}}
BEAKERS_AT = {'T1': {}, 'P_dev': {'P1': 'scale_pan'}, 'P_fun': {'P1': 'scale_pan'}, 'T2': {'P1': 'scale_pan'},
              'P_wat': {'P1': 'carousel_pick', 'P2': 'scale_pan'}}


def audit(K, b, A=None, gripper_open=None):
    A = A or load(); st = b.st; park = state.park_q(); res = []
    fit = cadmap.load_fit(); beaker_h = b.P['beaker']['height']; r_lip = b.P['beaker']['od'] / 2
    for s in A['steps']:
        arm = ARM_OF[s['arm']]; other = {a: park for a in scene.ARMS if a != arm}
        seg_rows = []
        K.beaker_override = {bk: (np.r_[st[stn]['xy'], st[stn]['z']] * 1e-3, np.array([1.0, 0, 0, 0])) for bk, stn in BEAKERS_AT[s['step']].items()}
        for k in TIME_ORDER[arm]:
            seg = s['anim_paths'][k]
            qs = [np.r_[cadmap.cad_to_mj(q), cadmap.cad_gripper_to_mj(seg['q6'])] for q in seg['qs']]
            dense = _densify(qs)
            held = None
            if seg['held'] is not None:
                site = 'grasp_td' if seg['held'] == 'td' else 'grasp_side'
                sign = 'td' if seg['held'] == 'td' else None
                if sign is None:                       # side grasp: pick the hinge sign that makes the beaker upright at frame 0
                    p, R = K.site(arm, qs[0], 'grasp_side'); sign = 1.0 if R[2, 2] > 0 else -1.0
                beaker = 'P1' if s['step'] in ('T1', 'T2', 'P_fun') else ('dev' if s['step'] == 'P_dev' else 'water')
                held = (beaker, _held_T(sign, seg['gh']), site)
            inlim = all(K.in_limits(arm, q) for q in dense)
            margins = [K.min_margin(arm, q) for q in dense]; mm_ = min(margins, key=lambda x: x[0])
            tilts, lips, pens, clr = [], [], [], (1e9, '')
            for i, q in enumerate(dense):
                ign = (held[0],) if held else ()
                c = K.contacts(arm, q, other, held)
                deep = [x for x in c if x[2] > 0.5]
                if deep: pens.append((i, max(deep, key=lambda x: x[2])))
                if i % 3 == 0 or i == len(dense) - 1:
                    cl = K.clearance(arm, q, other, held)
                    if cl[0] < clr[0]: clr = cl
                if held:
                    hb = K.d.body('beaker_' + held[0]); Rb = hb.xmat.reshape(3, 3); pb = hb.xpos * 1000
                    tilt = math.degrees(math.acos(np.clip(Rb[2, 2], -1, 1))); tilts.append(tilt)
                    if s['step'] in RECEIVER:
                        u = Rb[:, 2]; top = pb + beaker_h * u; down = np.array([0, 0, -1.0]) - u * (-u[2])
                        lip = top + r_lip * down / max(np.linalg.norm(down), 1e-9) if np.linalg.norm(down) > 1e-6 else top
                        rc = st[RECEIVER[s['step']]]
                        rim = rc['z'] + (beaker_h if RECEIVER[s['step']] == 'scale_pan' else 0.0)
                        lips.append((tilt, lip[2] - rim, float(np.linalg.norm(lip[:2] - np.asarray(rc['xy'])))))
            row = dict(segment=k, label=SEG_LABEL[arm][k], frames=len(qs), checked=len(dense), held=None if held is None else held[0], all_in_limits=inlim,
                       min_margin_deg=round(mm_[0], 2), binding=mm_[1], penetrations=len(pens),
                       worst_penetration=None if not pens else dict(frame=pens[0][0], pair=pens[0][1][:2], depth_mm=round(max(p[1][2] for p in pens), 2)),
                       min_clearance_mm=round(clr[0], 2), clearance_at=clr[1])
            if tilts: row.update(tilt_deg_range=[round(min(tilts), 1), round(max(tilts), 1)])
            if lips:
                pour = [x for x in lips if x[0] > 35]
                if pour: row.update(lip_above_rim_mm_range=[round(min(x[1] for x in pour), 1), round(max(x[1] for x in pour), 1)],
                                    lip_axis_offset_mm_range=[round(min(x[2] for x in pour), 1), round(max(x[2] for x in pour), 1)])
            seg_rows.append(row)
            if held:                                   # the beaker stays where the last held frame put it
                K.set(arm, dense[-1], other, held); hb = K.d.body('beaker_' + held[0])
                K.beaker_override[held[0]] = (hb.xpos.copy(), hb.xquat.copy())
        res.append(dict(step=s['step'], arm=arm, recorded=dict((k, s[k]) for k in ('pick', 'place', 'carry', 'pour', 'clearance_mm', 'clearance_at',
                                                                                    'lip_above_rim', 'landing_offset_mm') if k in s), segments=seg_rows))
    K.beaker_override = {}
    return res


def status(endpoints, audit_rows):
    worst = max(r['residual_mm'] for r in endpoints)
    frames_ok = all(seg['all_in_limits'] and seg['penetrations'] == 0 for s in audit_rows for seg in s['segments'])
    if worst <= ENDPOINT_TOL_MM and frames_ok: return 'calibrated'
    return 'approximate'
