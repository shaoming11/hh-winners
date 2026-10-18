"""Teach one absolute grasp pose by hand, for replay_plan's straight-line pick / place.

    python scripts/teach_one.py transfer_scale       # transfer arm: holding P1 resting in the scale pan

The arm goes to park, then above the spot with the jaws wide open, and its torque goes OFF: move it down so it would
hold the beaker where it rests (fixed finger against it), then create /tmp/claude-501/teach_ok (or press Enter).
The pose is saved to benchsim/config/taught_poses.json and the arm backs straight up and returns to park.
"""
import json, math, os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import replay_plan as rp  # noqa: E402
import teach_poses as tp  # noqa: E402

SPOTS = {   # name: (arm, step prefix, plan segment whose START is above the spot)
    'transfer_scale': ('transfer', '1', 'lower onto scale_pan'),
    'pourer_rack1': ('pourer', '2', 'descend to rack_1'),        # the peroxide beaker in the rack stand nearest the sled
    'pourer_scale': ('pourer', '3', 'descend to scale_pan'),     # P1 resting in the scale pan
}


def main():
    name = sys.argv[1]; arm_name, step, seg = SPOTS[name]
    plans = json.loads((rp.paths.SIM_ROOT / 'reports' / 'native_plans.json').read_text())['steps']
    key = [k for k in plans if k.split()[0] == step][0]; segs = plans[key]['segments']
    above = np.asarray([g for g in segs if g['name'] == seg][0]['qs'][0], float); above[5] = math.radians(85.0)
    park = np.asarray(segs[0]['qs'][0], float)
    bb = rp.make_bench('real', allow_hardware=True, **dict(rp.PORTS, port_mega=None, calibration_path=rp.CAL, dry_run=False))
    arm = bb.arms[arm_name]
    parks = {}
    for k in plans:                                    # each arm's park pose (up): the other arm must be out of the way
        if plans[k]['arm'] not in parks: parks[plans[k]['arm']] = plans[k]['segments'][0]['qs'][0]
    try:
        for nm, a in bb.arms.items():
            a.set_torque(True); rp.go(a, parks[nm], 0.5, 'park ' + nm, tol=8.0, timeout=15.0)
        rp.go(arm, above, 0.4, 'above the spot', tol=4.0, timeout=10.0)
        arm.set_torque(False)
        tp.wait_ok('%s: move it down so it would hold the beaker where it rests' % name)
        q = arm.read_positions()
        T = rp.load_taught(); T[name] = [float(x) for x in q]
        with open(rp.TAUGHT, 'w') as f: json.dump(T, f, indent=1)
        print('saved %s: %s' % (name, np.round(np.degrees(q), 1).tolist()), flush=True)
        arm.set_torque(True)
        up = q.copy(); up[1] -= math.radians(15); up[3] += math.radians(10)   # rough lift clear, then park
        rp.go(arm, up, 0.3, 'lift clear', tol=6.0, timeout=6.0)
        rp.go(arm, park, 0.5, 'park', tol=8.0, timeout=15.0)
    except KeyboardInterrupt:
        arm.set_torque(True); arm.set_goal(arm.read_positions(), 1.0); print('stopped: holding')
    finally:
        for a in bb.arms.values(): a.disconnect()


if __name__ == '__main__':
    main()
