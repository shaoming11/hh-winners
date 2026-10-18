"""Save where an arm is right now (torque stays off) as a taught pose for replay_plan.

    python scripts/record_pose.py transfer transfer_carousel_side    # left arm, claw held around P1 from the side

Move the limp arm by hand to the pose, then run this. Nothing moves: the arm is only read.
"""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import replay_plan as rp  # noqa: E402


def main():
    arm_name, name = sys.argv[1], sys.argv[2]
    bb = rp.make_bench('real', allow_hardware=True, **dict(rp.PORTS, port_mega=None, calibration_path=rp.CAL, dry_run=True))   # dry run: read only, never touches torque
    try:
        q = bb.arms[arm_name].read_positions()
        T = rp.load_taught(); T[name] = [float(x) for x in q]
        with open(rp.TAUGHT, 'w') as f: json.dump(T, f, indent=1)
        print('saved %s (%s): %s' % (name, arm_name, ' '.join('%s %.1f' % (j, x) for j, x in
              zip(('pan', 'lift', 'elbow', 'wflex', 'wroll', 'grip'), np.degrees(q)))), flush=True)
    finally:
        for a in bb.arms.values(): a.disconnect()


if __name__ == '__main__':
    main()
