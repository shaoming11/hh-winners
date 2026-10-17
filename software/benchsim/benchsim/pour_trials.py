"""Phase 6: closed-loop pours on the simulator, a deliberate spill and a funnel pour.

    python -m benchsim.pour_trials              # trials + spill + funnel -> reports/pour_report.{md,json}, reports/pour_traces/*.csv
    python -m benchsim.pour_trials --calibrate  # 3 weighed-fill pours -> fill_offset_ml for [pour.developer] (architecture 5.2)
    python -m benchsim.pour_trials --quick      # one trial, no report

Each pour runs in a fresh world: the receiver P1 is teleported from its carousel pocket onto the scale pan (recorded
in the report), the developer beaker gets a fill in the Ledger, the pourer runs the native plan for step 2
(Executor: approach, side grasp, lift, carry, lower to pre-pour), the scale is tared with P1 empty, and the
PourController closes the loop on the simulated HX711 stream through MegaClient. The tilt goes to the arm through
ManifoldTilt (theta -> joint goal on the plan's tilt-in + pour manifold). After the controller finishes the beaker
is untilted to the pre-pour pose and the scale and the Ledger are read.
"""
import csv
import json
import math
import multiprocessing as mp
import sys
import time

import mujoco
import numpy as np

from . import paths, poses, state
from .bench import make_bench
from .chem.liquid import LiquidModel, SyntheticPour, beaker_cylinder
from .chem.vessels import DENSITY, Ledger
from .layout import load_params
from .process.executor import Executor
from .process.pour import PourController, fit_cut_law, funnel_pour
from .process.pour_sim import ManifoldTilt, manifold_table
from .units import m

REPORTS = paths.SIM_ROOT / 'reports'
TRACES = REPORTS / 'pour_traces'
STEP = {'dev': ('2 developer pour', 'P_dev', 'dev', 'rack_1', 40.0, 45.0, 'scale_pan'),
        'funnel': ('3 P1 funnel pour', 'P_fun', 'P1', 'scale_pan', 30.0, 65.0, 'funnel')}
PRE_POUR_SEGS = 6                     # approach, descend, close, lift, carry to above pre-pour, lower to pre-pour
TRIAL_FILLS_ML = [48.0, 51.5, 55.0, 58.5, 62.0, 65.5, 69.0, 72.5, 76.0, 80.0]
TRACE_EVERY = 2                       # keep every 2nd control tick (20 Hz) in the CSV traces


def grip_height(key):
    """grip height the phase-3 planner chose for this step (reports/native_plans.json), else the documented one"""
    name = STEP[key][0]
    try: return float(json.loads((REPORTS / 'native_plans.json').read_text())['steps'][name]['info']['grip_h_used'])
    except (OSError, KeyError, TypeError): return STEP[key][4]


class PourRig:
    """one fresh simulated bench with the liquid model, ready for a pour"""

    def __init__(self, seed=0):
        self.bb = make_bench('sim', seed=seed); self.w = self.bb.world; self.params = self.w.P
        self.L = Ledger(self.w); self.LM = LiquidModel(self.w, self.L)
        self.planner = poses.Planner(self.w.m, self.w.b); self.mega = self.bb.mega; self.clock = self.bb.clock
        self.setup = []

    def move_scale(self, offset_xy_mm):
        """shift the whole scale pan (and so the receiver in its locating ring) in the horizontal plane"""
        b = self.w.m.body('scale_pan').id; self.w.m.body_pos[b, :2] += m(np.asarray(offset_xy_mm, float))
        mujoco.mj_forward(self.w.m, self.w.d)
        self.setup.append('scale pan shifted by (%.1f, %.1f) mm from its update13_final position' % tuple(offset_xy_mm))

    def place(self, beaker, station, offset_xy_mm=(0.0, 0.0)):
        """teleport a beaker's freejoint upright onto a station (bottom 0.1 mm above it) and let it settle"""
        p = self.planner.station(station) + np.r_[offset_xy_mm, 0.1]
        adr = self.w.m.jnt_qposadr[self.w.m.joint('beaker_' + beaker).id]; dadr = self.w.m.jnt_dofadr[self.w.m.joint('beaker_' + beaker).id]
        self.w.d.qpos[adr:adr + 3] = m(p); self.w.d.qpos[adr + 3:adr + 7] = [1, 0, 0, 0]; self.w.d.qvel[dadr:dadr + 6] = 0
        mujoco.mj_forward(self.w.m, self.w.d); self.w.advance(0.5)
        self.setup.append('%s teleported to %s at (%.1f, %.1f, %.1f) mm' % ((beaker, station) + tuple(np.round(p, 1))))

    def to_prepour(self, key):
        """plan the step natively and run it up to the pre-pour pose; returns (segs, info, tilt actuator, grasp record)"""
        name, rec, beaker, src, gh_doc, lip, recv = STEP[key]
        gh = grip_height(key)
        segs, info = self.planner.plan_pour(rec, beaker, src, gh, lip, recv)
        ex = Executor(self.bb.arms, self.clock, self.params['gripper'], state.park_q(), events=self.w.events)
        r = ex.run('pourer', segs[:PRE_POUR_SEGS], label=name)
        th, qs = manifold_table(self.planner, segs, info)
        arm = self.bb.arms['pourer']; q6 = float(arm.goal()[5])
        return segs, info, ManifoldTilt(arm, th, qs, q6), r

    def tare(self):
        self.mega.command('STREAM', on=True); self.mega.command('TARE'); self.clock.sleep(0.3); self.mega.take_samples()

    def tilt_deg(self, beaker):
        return self.LM.tilt_deg(beaker)


class Tracer:
    """wraps the sample source and the tilt actuator so every control tick is logged with the simulator's truth"""

    def __init__(self, rig, src, recv, tilt, controller=None):
        self.rig = rig; self.src = src; self.recv = recv; self.tilt = tilt; self.c = controller; self.rows = []; self.last_w = None
        self.rho = DENSITY['developer']

    def samples(self):
        s = self.rig.mega.take_samples()
        if s: self.last_w = s[-1]['w']
        return [(x['t'] / 1000.0, x['w']) for x in s]

    def set_theta(self, th):
        self.tilt.set_theta(th); r = self.rig; LM = r.LM
        tr = self.c.res.trace[-1] if (self.c is not None and self.c.res.trace) else (None, 'FUNNEL', th, None, None, None)
        self.rows.append(dict(t=round(r.w.time, 4), state=tr[1], theta_cmd=round(th, 3), theta_beaker=round(r.tilt_deg(self.src), 3),
                              m_f=tr[3], q_hat=tr[4], q_set=tr[5], scale_w=self.last_w,
                              m_true=round(r.L.mass(self.recv), 4) if self.recv in r.L.v else None,
                              q_lip=round(LM.q_ml_s.get(self.src, 0.0) * self.rho, 4), in_flight=round(LM.in_flight_g(), 4),
                              spilled=round(r.L.spilled_mass(), 4), src_g=round(r.L.mass(self.src), 4)))


def untilt_and_read(rig, tilt, theta_from, rate=60.0):
    """back to the upright pre-pour pose at <= rate deg/s, wait, then read the scale (mean of 16 samples)"""
    dt = 0.025; th = theta_from
    while th > 0: th = max(th - rate * dt, 0.0); tilt.set_theta(th); rig.clock.sleep(dt)
    rig.clock.sleep(1.5)
    return rig.mega.read_mass(16)


def landing_stats(LM, src, recv):
    rows = [x for x in LM.landings if x['src'] == src and x['recv'] == recv and x['dist_mm'] is not None]
    if not rows: return None
    g = np.array([x['g'] for x in rows]); d = np.array([x['dist_mm'] for x in rows])
    return dict(mass_weighted_mm=round(float((g * d).sum() / g.sum()), 2), max_mm=round(float(d.max()), 2), min_mm=round(float(d.min()), 2))


# ======================================================================= one closed-loop pour onto the scale
def scale_trial(seed, fill_ml, target=None, tol=None, scale_offset_mm=None, cfg_over=None, reagent_over=None, label=None, keep_trace=True):
    t_wall = time.time(); params = load_params(); R = params['recipe']
    target = R['developer_g'] if target is None else target; tol = R['developer_tol_g'] if tol is None else tol
    rig = PourRig(seed)
    if scale_offset_mm is not None: rig.move_scale(scale_offset_mm)
    rig.place('P1', 'scale_pan', scale_offset_mm if scale_offset_mm is not None else (0.0, 0.0))
    rig.L.add('dev', 'developer', fill_ml * DENSITY['developer'])
    rig.setup.append('dev filled with %.1f mL developer (%.2f g) in the Ledger' % (fill_ml, fill_ml * DENSITY['developer']))
    segs, info, tilt, grasp = rig.to_prepour('dev')
    t_pre = rig.w.time; rig.tare()
    cfg = dict(params['pour'], **(cfg_over or {}))
    if reagent_over: cfg['developer'] = dict(cfg['developer'], **reagent_over)
    pc = PourController(cfg, beaker_cylinder(params), DENSITY['developer'], target, tol, 'developer')
    tr = Tracer(rig, 'dev', 'P1', tilt, pc)
    res = pc.run(rig.clock, tr.samples, tr.set_theta)
    th_end = tr.rows[-1]['theta_cmd'] if tr.rows else 0.0
    m_scale = untilt_and_read(rig, tilt, th_end)
    m_true = rig.L.mass('P1')
    out = dict(label=label or 'fill %.1f mL seed %d' % (fill_ml, seed), seed=seed, fill_ml=fill_ml, target_g=target, tol_g=tol,
               outcome=res.outcome, reason=res.reason, final_true_g=round(m_true, 3), error_g=round(m_true - target, 3),
               controller_settled_g=res.final_g, scale_after_untilt_g=round(m_scale, 3), time_s=res.time_s,
               theta_first_deg=res.theta_first_deg, v_first_ml=res.v_first_ml,
               v_first_true_theta_deg=round(beaker_cylinder(params).theta_crit_deg(fill_ml), 2),
               theta_cut_deg=res.theta_cut_deg, q_cut_g_s=res.q_cut_g_s, m_cut_g=res.m_cut_g, cuts=res.cuts, topup_pulses=res.topup_pulses,
               max_theta_deg=res.max_theta_deg, spill_margin_g=res.spill_margin_g, spilled_g=round(rig.L.spilled_mass(), 3), left_in_source_g=round(rig.L.mass('dev'), 3),
               landing=landing_stats(rig.LM, 'dev', 'P1'), grip_h_mm=info['grip_h_used'], grasp=grasp.get('grasps'),
               prepour_sim_s=round(t_pre, 2), sim_s=round(rig.w.time, 2), wall_s=round(time.time() - t_wall, 1), setup=rig.setup,
               events=res.events, tracking=tracking_stats(res), mass_balance_g=round(rig.L.mass('dev') + rig.L.mass('P1') + rig.L.spilled_mass()
                                                                                    + rig.LM.in_flight_g() - fill_ml * DENSITY['developer'], 6))
    if keep_trace: out['trace'] = tr.rows
    return out


def tracking_stats(res):
    """flow tracking in FLOW: |q_hat - q*| more than 1.5 s after first drop (architecture 9.1 asks for <= 1 g/s)"""
    flow = [x for x in res.trace if x[1] == 'FLOW']
    if not flow: return None
    t0 = flow[0][0]; e = [abs(x[4] - x[5]) for x in flow if x[0] - t0 >= 1.5]
    return None if not e else dict(max_err_g_s=round(max(e), 3), mean_err_g_s=round(float(np.mean(e)), 3), n=len(e))


# ======================================================================= funnel pour
def funnel_trial(seed=0, content_g=None):
    t_wall = time.time(); params = load_params(); content_g = params['recipe']['developer_g'] if content_g is None else content_g
    rig = PourRig(seed); rig.place('P1', 'scale_pan'); rig.L.add('P1', 'developer', content_g)
    rig.setup.append('P1 holds %.1f g developer in the Ledger (the scale pour result)' % content_g)
    flask0 = rig.L.mass('flask')
    segs, info, tilt, grasp = rig.to_prepour('funnel')
    tr = Tracer(rig, 'P1', 'flask', tilt)
    prof = funnel_pour(params['pour'], rig.clock, tr.set_theta)
    rig.clock.sleep(params['liquid']['funnel_delay_s'] + 0.5)
    lnd = landing_stats(rig.LM, 'P1', 'funnel')
    rim = [x for x in rig.LM.landings if x['src'] == 'P1' and x['recv'] == 'funnel']
    return dict(content_g=content_g, delivered_to_flask_g=round(rig.L.mass('flask') - flask0, 3), left_in_P1_g=round(rig.L.mass('P1'), 3),
                spilled_g=round(rig.L.spilled_mass(), 3), in_flight_g=round(rig.LM.in_flight_g(), 4), landing=lnd, landing_limit_mm=40.0,
                funnel_rim_radius_mm=params['funnel']['rim_d'] / 2, lip_above_rim_mm=info['lip_above_rim'], grip_h_mm=info['grip_h_used'],
                profile_time_s=prof['time_s'], grasp=grasp.get('grasps'), setup=rig.setup, sim_s=round(rig.w.time, 2),
                wall_s=round(time.time() - t_wall, 1), landing_theta_range=None if not rim else [round(min(x['theta'] for x in rim), 1),
                                                                                                  round(max(x['theta'] for x in rim), 1)],
                trace=tr.rows)


# ======================================================================= synthetic (MuJoCo-free) studies
def synthetic_tracking(kp, ki, setpoints=(1.0, 2.0, 4.0, 8.0), fills=(55.0, 80.0), lip_widths=(10.0, 14.0, 20.0), holds=(0.0, 0.5, 1.0)):
    """architecture 9.1 acceptance on the synthetic plant: constant q*, error after 1.5 s, over plant variations"""
    P = load_params(); vt = beaker_cylinder(P); worst = []
    for qs in setpoints:
        for fill in fills:
            for lw in lip_widths:
                for hh in holds:
                    P2 = dict(P); P2['liquid'] = dict(P['liquid'], lip_width_mm=lw, hold_head_mm=hh)
                    pl = SyntheticPour(P2, fill, seed=int(qs * 100 + fill + lw + hh * 10))
                    cfg = dict(P['pour'], kp_deg_per_gs=kp, ki_deg_per_s_per_gs=ki, q_min_g_s=qs, q_ceiling_g_s=qs, spill_check=False)
                    cfg['developer'] = dict(cfg['developer'], low_fill_ml=0.0)
                    pc = PourController(cfg, vt, 1.04, 1000.0, 2.0, 'developer'); pl.set_theta(pc.start(pl.now()))
                    while not pc.done and pl.now() < 40 and not (pc.t_first is not None and pl.now() - pc.t_first > 6.0):
                        pl.sleep(cfg['control_dt_s']); pl.set_theta(pc.tick(pl.now(), pl.samples()))
                    tr = [x for x in pc.res.trace if x[1] == 'FLOW']
                    if not tr: worst.append(dict(q_set=qs, fill=fill, lip_w=lw, hold=hh, max_err=None)); continue
                    t0 = tr[0][0]; e = [abs(x[4] - qs) for x in tr if 1.5 <= x[0] - t0 <= 6.0]
                    worst.append(dict(q_set=qs, fill=fill, lip_w=lw, hold=hh, max_err=round(max(e), 3)))
    errs = [w['max_err'] for w in worst if w['max_err'] is not None]
    return dict(kp=kp, ki=ki, cases=len(worst), within_1g_s=sum(e <= 1.0 for e in errs), worst_g_s=round(max(errs), 3),
                median_g_s=round(float(np.median(errs)), 3), by_case=worst)


# ======================================================================= parallel runner and report
def _run(job):
    kind, kw = job
    try: return (scale_trial if kind == 'scale' else funnel_trial)(**kw)
    except Exception as e:                                            # report, do not hide
        import traceback; return dict(label=kw.get('label', kind), error='%s: %s' % (type(e).__name__, e), tb=traceback.format_exc())


def run_jobs(jobs, procs=5):
    if procs <= 1: return [_run(j) for j in jobs]
    with mp.get_context('spawn').Pool(procs) as pool: return pool.map(_run, jobs, chunksize=1)


def write_trace(name, rows):
    TRACES.mkdir(parents=True, exist_ok=True); p = TRACES / ('%s.csv' % name)
    if not rows: return None
    keep = rows[::TRACE_EVERY]
    if rows[-1] is not keep[-1]: keep.append(rows[-1])
    with open(p, 'w', newline='') as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys())); wr.writeheader(); wr.writerows(keep)
    return str(p.relative_to(paths.SIM_ROOT))


def calibrate(procs=3):
    """architecture 5.2: V_first offset from 3 weighed-fill pours (no low-fill PAUSE while calibrating)"""
    fills = [60.0, 70.0, 80.0]
    jobs = [('scale', dict(seed=100 + i, fill_ml=f, reagent_over=dict(low_fill_ml=0.0, fill_offset_ml=0.0), label='calibration %.0f mL' % f, keep_trace=False))
            for i, f in enumerate(fills)]
    rows = run_jobs(jobs, procs); vt = beaker_cylinder(load_params()); out = []
    for r in rows:
        if 'error' in r: print(r['label'], r['error']); continue
        off = r['fill_ml'] - vt.v_crit_ml(r['theta_first_deg'])
        out.append(dict(fill_ml=r['fill_ml'], theta_first_deg=r['theta_first_deg'], v_table_ml=round(vt.v_crit_ml(r['theta_first_deg']), 2), offset_ml=round(off, 2),
                        theta_true_deg=r['v_first_true_theta_deg'], outcome=r['outcome'], error_g=r['error_g'], q_cut_g_s=r['q_cut_g_s']))
        print(out[-1])
    mean = float(np.mean([o['offset_ml'] for o in out])); print('fill_offset_ml = %.1f   (mean of %d)' % (mean, len(out)))
    return dict(pours=out, fill_offset_ml=round(mean, 2))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    procs = int(next((a.split('=')[1] for a in argv if a.startswith('--procs=')), 5))
    if '--calibrate' in argv:
        c = calibrate(procs); (REPORTS / 'pour_calibration.json').write_text(json.dumps(c, indent=1)); return 0
    if '--quick' in argv:
        r = scale_trial(1, 65.0, keep_trace=False); r.pop('events'); print(json.dumps(r, indent=1, default=str)); return 0
    t0 = time.time(); params = load_params()
    jobs = [('scale', dict(seed=i + 1, fill_ml=f, label='trial %02d' % (i + 1))) for i, f in enumerate(TRIAL_FILLS_ML)]
    jobs += [('scale', dict(seed=21, fill_ml=40.0, label='low fill 40 mL'))]
    for name, off in SPILL_CASES.items():
        jobs.append(('scale', dict(seed=31, fill_ml=70.0, scale_offset_mm=off, label=name)))
    jobs.append(('funnel', dict(seed=41)))
    rows = run_jobs(jobs, procs)
    syn = [synthetic_tracking(params['pour']['kp_deg_per_gs'], 0.3), synthetic_tracking(params['pour']['kp_deg_per_gs'], params['pour']['ki_deg_per_s_per_gs'])]
    report = build_report(rows, syn, params, time.time() - t0)
    print(report['verdict'])
    return 0 if report['acceptance']['pass'] else 1


# receiver offsets for the deliberate spill, mm in world XY (set from the step-2 pour direction in the report)
SPILL_CASES = {}


if __name__ == '__main__':
    sys.exit(main())
