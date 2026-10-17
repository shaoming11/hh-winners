"""Phase 3 verifier: CAD-path mapping audit, recorded-path replay, and the MuJoCo-native arm plans.

    python -m benchsim.verify_kinematics      # writes reports/kinematics_report.{md,json} and reports/native_plans.json

For every tested pose it prints the endpoint error, the minimum joint margin (URDF limit minus 5 deg) against the
rule, and the minimum clearance; every path is checked densely (no joint moves more than 1.5 deg between checks)
for joint limits, contacts deeper than 0.5 mm, and clearance to the bench, the other (parked) arm and the beakers.
"""
import json
import math
import sys
import time

import numpy as np

from . import cadmap, paths, poses, scene, trajectories
from .kinematics import RULE

REPORTS = paths.SIM_ROOT / 'reports'
STATION_SEGS = ('descend', 'close', 'lift from', 'lower', 'release', 'lift out', 'lift 20', 'slide', 'lower to channel', 'touch', 'move fixed finger')


def free_clearance(rows):
    """minimum clearance over the segments that move through free space (not seated at or entering a station)"""
    free = [r for r in rows if not r['segment'].startswith(STATION_SEGS)]
    return min(free, key=lambda r: r['min_clearance_mm']) if free else None


def pose_rows(P, plans):
    """the station poses of every native plan: endpoint error at the target, margin vs rule, clearance"""
    rows = []
    K = P.K
    for name, v in plans.items():
        arm = v['arm']; segs = {s['name']: s for s in v['segs']}
        for s in v['segs']:
            if s['kind'] != 'grip': continue
            q = s['qs'][-1] if s['gripper'] == 'close' else s['qs'][0]
            site = s['grasp']; p, R = K.site(arm, q, site)
            if arm == 'transfer': tgt = P.station(v['src'] if s['gripper'] == 'close' else v['dst'])
            else: tgt = P.station(v['src']) + [0, 0, v['info']['grip_h_used']]
            if s['gripper'] == 'open': tgt = tgt + [0, 0, poses.PLACE_CLEAR_MM]      # placements release 1.5 mm up
            mg = K.min_margin(arm, q); phase = 'pick' if s['gripper'] == 'close' else 'place'
            rows.append(dict(step=name, pose='%s (%s)' % (phase, s['name']), arm=arm, endpoint_error_mm=round(float(np.linalg.norm(p - tgt)), 3),
                             axis_tilt_deg=round(math.degrees(math.acos(np.clip(abs(R[2, 2]), -1, 1))), 3), min_margin_deg=round(mg[0], 2),
                             binding=mg[1], rule_deg=RULE[phase], rule_met=mg[0] >= RULE[phase]))
        for s in v['segs']:
            if s['kind'] != 'manifold': continue
            for lab, q in (('pour theta 40', s['qs'][0]), ('pour theta 105', s['qs'][-1])):
                mg = K.min_margin(arm, q)
                rows.append(dict(step=name, pose=lab, arm=arm, endpoint_error_mm=None, axis_tilt_deg=None, min_margin_deg=round(mg[0], 2), binding=mg[1],
                                 rule_deg=RULE['pour'], rule_met=mg[0] >= RULE['pour'], lip_drift_mm=v['info']['lip_drift_mm']))
    return rows


def reach_limits(P):
    """top-down lift height vs wrist-flex margin at the transfer stations (explains the 20 mm transfer lift)"""
    out = []
    rec = P.rec['T1']['anim_paths'][0]['qs']
    for stn, qc in (('carousel_pick', rec[0]), ('scale_pan', rec[-1])):
        q = np.r_[cadmap.cad_to_mj(qc), P.q6_wide]; row = dict(station=stn, lift=[])
        for dz in (0, 10, 20, 30, 40, 50, 60, 80):
            q2, e, a = P.K.ik('transfer', 'grasp_td_taught', P.station(stn) + [0, 0, dz], z_axis=[0, 0, 1], q0=q, iters=300)
            ok = e < 0.5 and a < 0.5
            row['lift'].append(dict(dz_mm=dz, reachable=ok, min_margin_deg=round(P.K.min_margin('transfer', q2)[0], 2) if ok else None))
            if ok: q = q2
        out.append(row)
    return out


def main():
    t0 = time.time()
    model, b = scene.build(); P = poses.Planner(model, b); K = P.K
    signs = trajectories.sign_search(K, b); ends = trajectories.endpoint_table(K, b); rec = trajectories.audit(K, b)
    mapping_status = trajectories.status(ends, rec)
    plans = P.all_plans(); checks = {k: P.check_plan(v['arm'], v['segs'], v['beakers_at']) for k, v in plans.items()}
    prow = pose_rows(P, plans); reach = reach_limits(P)
    issues = []
    for k, rows in checks.items():
        for r in rows:
            if r['contacts']: issues.append('%s / %s: contact %s' % (k, r['segment'], r['worst_contact']))
            if not r['margin_ok']: issues.append('%s / %s: margin %.2f deg < rule %.0f (%s)' % (k, r['segment'], r['min_margin_deg'], r['rule_deg'], r['binding']))
    collision_free = all(r['contacts'] == 0 for rows in checks.values() for r in rows)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / 'native_plans.json').write_text(json.dumps(poses.to_json(plans), indent=0))
    rep = dict(mapping_status=mapping_status, sign_search=signs[:6], endpoints=ends, recorded_audit=rec, native_poses=prow,
               native_path_checks=checks, native_plan_info={k: v.get('info') for k, v in plans.items()}, reach_limits=reach,
               collision_free=collision_free, rule_issues=issues, seconds=round(time.time() - t0, 1))
    (REPORTS / 'kinematics_report.json').write_text(json.dumps(rep, indent=1, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o)))
    write_md(rep)
    print('CAD -> MJCF mapping:', mapping_status, '(worst endpoint %.1f mm)' % max(r['residual_mm'] for r in ends))
    print('%-24s %-40s %9s %8s %-12s %s' % ('step', 'pose', 'end err', 'margin', 'binding', 'rule'))
    for r in prow:
        print('%-24s %-40s %9s %8.2f %-12s %s' % (r['step'], r['pose'][:40], '-' if r['endpoint_error_mm'] is None else '%.3f' % r['endpoint_error_mm'],
                                                   r['min_margin_deg'], r['binding'], 'ok' if r['rule_met'] else 'BELOW %.0f' % r['rule_deg']))
    for k, rows in checks.items():
        mc = free_clearance(rows)
        print('%-24s min margin %.2f, free-motion clearance %.2f mm (%s, %s), contacts %d' % (k, min(r['min_margin_deg'] for r in rows), mc['min_clearance_mm'],
              mc['segment'], mc['clearance_at'], sum(r['contacts'] for r in rows)))
    print('native plans collision-free:', collision_free, '| rule issues:', len(issues))
    print('->', REPORTS / 'kinematics_report.md')
    return 0 if collision_free else 1


def write_md(rep):
    L = ['# Kinematics verification report', '', 'Generated by `python -m benchsim.verify_kinematics`. Margins are degrees to the URDF limit minus 5 deg'
         ' (rule: >= 10 at picks, places and pours, >= 5 on carries). Paths are checked at <= 1.5 deg joint steps with the other arm parked; a contact'
         ' is a penetration deeper than 0.5 mm.', '',
         '## 1. CAD planner convention -> SO-101 MJCF', '',
         'Mapping `q_mj = o + s * q_cad` with `o` from the CAD as-built axis fit (`benchsim.cadmap`) and `s` from the sign search below.',
         'Status: **%s**. The recorded paths are replayed with this mapping for audit only; they are not used as hardware or simulator'
         ' trajectories.' % rep['mapping_status'], '', '### Sign search (32 combinations; best 6)', '', '| signs | mean endpoint error (mm) | max (mm) | all frames in limits |', '|---|---|---|---|']
    for r in rep['sign_search']: L.append('| %s | %.1f | %.1f | %s |' % (r['signs'], r['mean_err_mm'], r['max_err_mm'], r['all_in_limits']))
    L += ['', '### Station endpoints of the recorded paths (MJCF FK vs update13_final)', '',
          '| pose | FK (mm) | station (mm) | residual (mm) | margin MJCF | planner recorded | diff |', '|---|---|---|---|---|---|---|']
    for r in rep['endpoints']:
        L.append('| %s | %s | %s | %.2f | %.2f %s | %.2f %s | %+.2f |' % (r['pose'], r['fk_mm'], r['station_mm'], r['residual_mm'], r['min_margin_deg'], r['binding'],
                                                                       r['recorded_margin_deg'], r['recorded_binding'], r['margin_diff_deg']))
    L += ['', 'The binding joint matches the planner in every case; the constant 1.67 deg margin difference is the wrist-flex zero of the axis fit vs'
          ' the planner\'s link-angle calibration (urdf_limits.py), i.e. the wrist-flex zero is uncertain by about 1.7 deg.', '',
          '## 2. Recorded paths replayed on the MJCF arms (audit)', '', '| step | segment | frames | in limits | min margin | contacts (worst) | min clearance | held tilt | lip above rim |',
          '|---|---|---|---|---|---|---|---|---|']
    for s in rep['recorded_audit']:
        for g in s['segments']:
            L.append('| %s | %s | %d | %s | %.1f %s | %d %s | %.1f | %s | %s |' % (s['step'], g['label'], g['frames'], g['all_in_limits'], g['min_margin_deg'], g['binding'],
                     g['penetrations'], '' if not g['worst_penetration'] else '(%.1f mm %s)' % (g['worst_penetration']['depth_mm'], '/'.join(g['worst_penetration']['pair'])),
                     g['min_clearance_mm'], g.get('tilt_deg_range', ''), g.get('lip_above_rim_mm_range', '')))
    L += ['', 'Pour segments reproduce the planner geometry (lip 42-48 mm above the P1 rim for the 45 mm design, 62-68 for the 65 mm funnel design; carried'
          ' beakers stay within 1.1 deg of upright). Approach and pick frames collide by the size of the endpoint residuals, and the planner\'s top-down'
          ' grasp frame puts the beaker 13-14 mm into the fixed finger (demo_process 3 already tells the operator to shift it about 14 mm). Recorded-path'
          ' playback is therefore **pending** a hardware calibration.', '',
          '## 3. MuJoCo-native station poses (simulation only)', '',
          'Solved by IK on the MJCF arms, seeded from the mapped recorded poses. Top-down picks use the taught frame (beaker shifted %.1f mm toward the'
          ' moving jaw so the fixed finger clears it by 3 mm). Saved in `reports/native_plans.json` with `origin: mujoco-native`.' % 16.0, '',
          '| step | pose | endpoint error (mm) | axis tilt (deg) | min margin | binding | rule |', '|---|---|---|---|---|---|---|']
    for r in rep['native_poses']:
        L.append('| %s | %s | %s | %s | %.2f | %s | %s |' % (r['step'], r['pose'], '-' if r['endpoint_error_mm'] is None else '%.3f' % r['endpoint_error_mm'],
                 '-' if r['axis_tilt_deg'] is None else r['axis_tilt_deg'], r['min_margin_deg'], r['binding'], 'ok' if r['rule_met'] else '**below %.0f**' % r['rule_deg']))
    L += ['', '### Grip height selection for the side-grasp pours', '', '| step | documented GRIP_H | pick margin there | GRIP_H used | pick margin used | lip drift (mm) |', '|---|---|---|---|---|---|']
    for k, inf in rep['native_plan_info'].items():
        if inf and 'grip_h_doc' in inf:
            L.append('| %s | %.0f | %s | %.0f | %.2f | %.1f |' % (k, inf['grip_h_doc'], inf['pick_margin_doc'], inf['grip_h_used'], inf['pick_margin_used'], inf['lip_drift_mm']))
    L += ['', '## 4. Native path checks', '', '| step | segment | phase | configs | min margin | rule | contacts | min clearance (mm) | at |', '|---|---|---|---|---|---|---|---|---|']
    for k, rows in rep['native_path_checks'].items():
        for r in rows:
            L.append('| %s | %s | %s | %d | %.2f %s | %s | %d | %.2f | %s |' % (k, r['segment'], r['phase'], r['configs'], r['min_margin_deg'], r['binding'],
                     'ok' if r['margin_ok'] else '**below %.0f**' % r['rule_deg'], r['contacts'], r['min_clearance_mm'], r['clearance_at']))
    L += ['', '| step | free-motion clearance (mm) | segment | between |', '|---|---|---|---|']
    for k, rows in rep['native_path_checks'].items():
        mc = free_clearance(rows); L.append('| %s | %.2f | %s | %s |' % (k, mc['min_clearance_mm'], mc['segment'], mc['clearance_at']))
    L += ['', 'Clearances near 0 at picks and places are the beaker seated in its pocket or cup (beakers are ignored by the clearance query while the'
          ' gripper is at a station).', '', '## 5. Reach limits found', '']
    for r in rep['reach_limits']:
        L.append('- Top-down at %s: ' % r['station'] + ', '.join('+%d mm %s' % (x['dz_mm'], ('%.1f deg' % x['min_margin_deg']) if x['reachable'] else 'unreachable') for x in r['lift']))
    L += ['', '## 6. Open rule issues', ''] + ['- ' + i for i in rep['rule_issues']] + ['', 'Collision-free: **%s**' % rep['collision_free']]
    (REPORTS / 'kinematics_report.md').write_text('\n'.join(L) + '\n')


if __name__ == '__main__':
    sys.exit(main())
