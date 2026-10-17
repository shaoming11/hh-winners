"""Phase 5 demo: carousel -> scale (transfer arm, top-down), rack -> scale (pourer, side grasp) and a deliberate
miss, run through the backend-independent executor on the simulator.

    python -m benchsim.grasp_demo                 # -> reports/grasp_demo/{*.png, *.mp4, grasp_report.json}
    python -m benchsim.grasp_demo --calibrate     # measure the jaw contact angles in simulation
"""
import json
import math
import sys

import numpy as np

from . import paths, poses, state
from .bench import make_bench
from .layout import load_params
from .process import motion
from .process.executor import Executor, TaskFailed
from .record import Recorder

OUT = paths.SIM_ROOT / 'reports' / 'grasp_demo'


class HoldMonitor:
    """sim-only diagnostic: how far the held beaker moves relative to the gripper, and its tilt, while held"""

    def __init__(self, w):
        self.w = w; self.ref = None; self.max_slip = 0.0; self.max_tilt = 0.0; self.samples = 0

    def __call__(self):
        w = self.w
        for arm, bk in w.held.items():
            g = w.d.body('%s/gripper' % arm); b = w.d.body('beaker_' + bk)
            rel = g.xmat.reshape(3, 3).T @ (b.xpos - g.xpos)
            if self.ref is None: self.ref = rel.copy()
            self.max_slip = max(self.max_slip, float(np.linalg.norm(rel - self.ref) * 1000))
            self.max_tilt = max(self.max_tilt, float(np.degrees(np.arccos(np.clip(b.xmat[8], -1, 1)))))
            self.samples += 1
        if not w.held: self.ref = None


def scenario(name, arm_name, plan_fn, scale_station, prep=None, camera='bench_cam'):
    bb = make_bench('sim'); w = bb.world; P = poses.Planner(w.m, w.b); params = load_params()
    if prep: prep(w)
    mega = bb.mega; mega.command('STREAM', on=True); mega.command('TARE')
    rec = Recorder(w, OUT, camera=camera, fps=25, width=960, height=544, video_name='%s.mp4' % name)
    mon = HoldMonitor(w)
    stills = {'close on': 'grasp', 'lift from': 'lift', 'carry': 'carry', 'release': 'placement'}

    def on_segment(arm, sg, k):
        for key, lab in stills.items():
            if sg['name'].startswith(key): rec.still('%s_%d_%s' % (name, k, lab), '%s: %s' % (lab, sg['name']))
    ex = Executor(bb.arms, bb.clock, params['gripper'], state.park_q(), scale=lambda: mega.read_mass(8), events=w.events,
                  on_tick=mon, on_segment=on_segment)
    rec.still('%s_0_start' % name, 'starting pose')
    segs = plan_fn(P); result = dict(scenario=name, arm=arm_name)
    try:
        r = ex.run(arm_name, segs, scale_station=scale_station, label=name); result.update(status='passed', record=r)
    except TaskFailed as e:
        result.update(status='failed', code=e.code, detail=e.detail, record=e.record)
        rec.still('%s_8_failed' % name, 'task failed: %s (%s)' % (e.code, e.detail))
    bb.clock.sleep(0.5); rec.still('%s_9_final' % name, 'final pose')
    result.update(hold_slip_max_mm=round(mon.max_slip, 3), hold_tilt_max_deg=round(mon.max_tilt, 3), sim_seconds=round(w.time, 2),
                  stills=rec.stills, video='%s.mp4' % name, final_beaker_positions={k: np.round(w.beaker_pose(k)[0], 1).tolist() for k in ('P1', 'dev')},
                  events=[e for e in w.events if e['kind'] in ('attach', 'detach', 'grasp', 'release', 'abort_retreat')])
    rec.close()
    return result


def calibrate():
    out = {}
    for grasp, arm, plan in (('td', 'transfer', lambda P: P.plan_transfer('P1', 'carousel_pick', 'scale_pan')),
                             ('side', 'pourer', lambda P: P.plan_side_transfer('dev', 'rack_1', 'scale_pan', 48.0))):
        bb = make_bench('sim'); w = bb.world; P = poses.Planner(w.m, w.b); a = bb.arms[arm]
        for sg in plan(P):
            if sg['kind'] == 'grip':
                jaw = motion.gripper_to(a, P.q6_contact - math.radians(10), bb.clock); out[grasp] = round(math.degrees(jaw), 2); break
            motion.follow(a, sg['qs'], bb.clock)
    print('jaw contact angles measured in simulation (deg):', out)
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if '--calibrate' in argv: calibrate(); return 0
    import shutil
    shutil.rmtree(OUT, ignore_errors=True); OUT.mkdir(parents=True, exist_ok=True)

    def remove_p1(w):                                   # deliberate miss: the pick pocket is empty
        adr = w.m.jnt_qposadr[w.m.joint('beaker_P1').id]; w.d.qpos[adr:adr + 3] = [0.95, 0.10, 0.0]
        import mujoco; mujoco.mj_forward(w.m, w.d)
    results = [scenario('carousel_to_scale', 'transfer', lambda P: P.plan_transfer('P1', 'carousel_pick', 'scale_pan'), 'dst'),
               scenario('rack_to_scale', 'pourer', lambda P: P.plan_side_transfer('dev', 'rack_1', 'scale_pan', 48.0), 'dst', camera='overview'),
               scenario('deliberate_miss', 'transfer', lambda P: P.plan_transfer('P1', 'carousel_pick', 'scale_pan'), 'dst', prep=remove_p1)]
    ok = (results[0]['status'] == 'passed' and results[1]['status'] == 'passed' and results[2]['status'] == 'failed'
          and results[2].get('code') == 'GRASP_MISS')
    (OUT / 'grasp_report.json').write_text(json.dumps(dict(pass_=ok, results=results), indent=1, default=str))
    for r in results:
        g = r['record'].get('grasps', [])
        print('%-18s %-7s %s grasps=%s scale=%s slip=%.2f mm tilt=%.2f deg' % (r['scenario'], r['status'], r.get('code', ''),
              [(x['outcome'], x['jaw_deg'], x['expected_deg']) for x in g], r['record'].get('scale'), r['hold_slip_max_mm'], r['hold_tilt_max_deg']))
    print('grasp demo:', 'PASS' if ok else 'FAIL', '->', OUT)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
