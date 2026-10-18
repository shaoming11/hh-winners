"""Hand-tune the demo's key poses on the real arms; replay_plan.py applies the corrections.

    python scripts/teach_poses.py                 # every key pose of the 4-step demo, one after another
    python scripts/teach_poses.py --only 2        # the poses of step 2 only
    python scripts/teach_poses.py --clear         # forget all corrections

For each pose: the arm plays its planned path up to the pose (the other arm stays parked), torque goes OFF on that
arm (hold it), you move it by hand to where it should be, then create the file /tmp/claude-501/teach_ok (or press
Enter in this terminal). The difference (your pose - the planned pose) is saved to
benchsim/config/pose_overrides.json; torque comes back on holding your pose and the arm retraces to park.
replay_plan.py shifts that pose and the slow approach / lift-off segments around it by the same joint offsets.
"""
import argparse
import json
import math
import os
import select
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import replay_plan as rp  # noqa: E402

OK_FILE = '/tmp/claude-501/teach_ok'
# (step prefix, segment whose END is the pose, what it is)
KEY_POSES = [
    ('1', 'touch fixed finger to P1', 'transfer: pick P1 at the carousel'),
    ('1', 'lower onto scale_pan', 'transfer: set P1 down on the scale'),
    ('2', 'descend to rack_1', 'pourer: grab the peroxide in the rack'),
    ('2', 'lower to pre-pour', 'pourer: peroxide pre-pour over the scale'),
    ('3', 'descend to scale_pan', 'pourer: grab P1 on the scale'),
    ('3', 'lower to pre-pour', 'pourer: P1 pre-pour over the funnel'),
    ('4', 'touch fixed finger to P1', 'transfer: pick P1 on the scale'),
    ('4', 'lower onto carousel_pick', 'transfer: set P1 back in the carousel'),
]


def wait_ok(label):
    if os.path.exists(OK_FILE): os.remove(OK_FILE)
    print('\n>>> %s: torque OFF, move the arm by hand. Then say it is good (teach_ok) or press Enter.' % label, flush=True)
    while True:
        if os.path.exists(OK_FILE): os.remove(OK_FILE); return
        r, _, _ = select.select([sys.stdin], [], [], 0.2)
        if r: sys.stdin.readline(); return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', nargs='*', help='step numbers to teach (default: all key poses)')
    ap.add_argument('--clear', action='store_true')
    ap.add_argument('--speed', type=float, default=0.5)
    a = ap.parse_args()
    if a.clear:
        if os.path.exists(rp.OVERRIDES): os.remove(rp.OVERRIDES)
        print('pose corrections cleared'); return 0
    plans = json.loads((rp.paths.SIM_ROOT / 'reports' / 'native_plans.json').read_text())['steps']
    bench = rp.layout.load_bench()
    bb = rp.make_bench('real', allow_hardware=True, **dict(rp.PORTS, port_mega=None, calibration_path=rp.CAL, dry_run=False))
    arms = bb.arms
    ov = rp.load_overrides()
    try:
        for arm in arms.values(): arm.set_torque(True)
        park = {}
        for k in plans:
            if plans[k]['arm'] not in park: park[plans[k]['arm']] = plans[k]['segments'][0]['qs'][0]
        for name, q in park.items(): rp.go(arms[name], q, a.speed, 'park ' + name, tol=8.0, timeout=15.0)
        for step, seg_name, label in KEY_POSES:
            if a.only and step not in a.only: continue
            key = [k for k in plans if k.split()[0] == step][0]; s = plans[key]; arm = arms[s['arm']]
            segs = rp.bench_segments(s['segments'], key)            # already includes earlier corrections
            idx = [i for i, g in enumerate(segs) if g['name'] == seg_name][0]
            print('\n=== %s (%s, step %s)' % (label, s['arm'], key), flush=True)
            for g in segs[:idx + 1]:
                print('   %-38s %s' % (g['name'], g['phase']), flush=True); rp.play_segment(arm, g, a.speed)
            planned = np.asarray(s['segments'][[g['name'] for g in s['segments']].index(seg_name)]['qs'][-1], float)
            arm.set_torque(False)
            wait_ok(label)
            q = arm.read_positions()
            d = np.degrees(q - planned); d[5] = 0.0                  # the gripper opening is not taught here
            ov.setdefault(key, {})[seg_name] = [round(float(x), 2) for x in d]
            rp.save_overrides(ov)
            print('   saved: %s' % ' '.join('%s %+.1f' % (n, x) for n, x in zip(('pan', 'lift', 'elbow', 'wflex', 'wroll', 'grip'), d)), flush=True)
            arm.set_torque(True)                                      # holds the taught pose
            for g in reversed(segs[:idx + 1]):                        # back out the way it came
                back = dict(g); back['qs'] = g['qs'][::-1]; back['kind'] = 'cartesian' if len(g['qs']) > 2 else g['kind']
                rp.play_segment(arm, back, a.speed)
            rp.go(arm, park[s['arm']], a.speed, 'park', tol=8.0, timeout=15.0)
        print('\nall done; corrections in %s' % rp.OVERRIDES)
    except KeyboardInterrupt:
        for arm in arms.values():
            try: arm.set_torque(True); arm.set_goal(arm.read_positions(), 1.0)
            except Exception: pass
        print('\nstopped: arms holding where they are')
    finally:
        for arm in arms.values():
            try: arm.disconnect()
            except Exception: pass


if __name__ == '__main__':
    main()
