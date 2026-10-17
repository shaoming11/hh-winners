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


def landing_stats(LM, src, recv, t_max=None):
    rows = [x for x in LM.landings if x['src'] == src and x['recv'] == recv and x['dist_mm'] is not None and (t_max is None or x['t'] <= t_max)]
    if not rows: return None
    g = np.array([x['g'] for x in rows]); d = np.array([x['dist_mm'] for x in rows])
    return dict(mass_weighted_mm=round(float((g * d).sum() / g.sum()), 2), max_mm=round(float(d.max()), 2), min_mm=round(float(d.min()), 2))


def manifold_steepness(tilt, th_lo, th_hi):
    """largest joint move (deg) per degree of tilt on the table between th_lo and th_hi, and where"""
    th = tilt.th; d = np.degrees(np.abs(np.diff(tilt.qs[:, :5], axis=0))).max(axis=1) / np.diff(th)
    sel = [i for i in range(len(d)) if th_lo <= th[i] < th_hi]
    if not sel: return None
    i = max(sel, key=lambda k: d[k]); return dict(max_joint_deg_per_deg=round(float(d[i]), 2), at_theta_deg=round(float(th[i]), 1))


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
    t_done = rig.w.time; spilled_pour = rig.L.spilled_mass() + sum(rig.LM._spill_buf['parts'].values())
    th_end = tr.rows[-1]['theta_cmd'] if tr.rows else 0.0
    m_scale = untilt_and_read(rig, tilt, th_end)
    m_true = rig.L.mass('P1')
    out = dict(label=label or 'fill %.1f mL seed %d' % (fill_ml, seed), seed=seed, fill_ml=fill_ml, target_g=target, tol_g=tol,
               outcome=res.outcome, reason=res.reason, final_true_g=round(m_true, 3), error_g=round(m_true - target, 3),
               controller_settled_g=res.final_g, scale_after_untilt_g=round(m_scale, 3), time_s=res.time_s,
               theta_first_deg=res.theta_first_deg, v_first_ml=res.v_first_ml,
               v_first_true_theta_deg=round(beaker_cylinder(params).theta_crit_deg(fill_ml), 2),
               theta_cut_deg=res.theta_cut_deg, q_cut_g_s=res.q_cut_g_s, m_cut_g=res.m_cut_g, cuts=res.cuts, topup_pulses=res.topup_pulses,
               max_theta_deg=res.max_theta_deg, spill_margin_g=res.spill_margin_g, spilled_g=round(rig.L.spilled_mass(), 3),
               spilled_during_pour_g=round(spilled_pour, 4), left_in_source_g=round(rig.L.mass('dev'), 3),
               landing=landing_stats(rig.LM, 'dev', 'P1', t_done), manifold=manifold_steepness(tilt, 40.0, max(res.max_theta_deg or 40.0, 41.0)), grip_h_mm=info['grip_h_used'], grasp=grasp.get('grasps'),
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
    ramp = [r for a, r in zip(tr.rows, tr.rows[1:]) if r['theta_cmd'] > a['theta_cmd'] and r['theta_cmd'] > 40.5]
    lag = max(ramp, key=lambda r: r['theta_cmd'] - r['theta_beaker']) if ramp else None
    rig.clock.sleep(params['liquid']['funnel_delay_s'] + 0.5)
    lnd = landing_stats(rig.LM, 'P1', 'funnel')
    rim = [x for x in rig.LM.landings if x['src'] == 'P1' and x['recv'] == 'funnel']
    return dict(label='funnel pour', content_g=content_g, delivered_to_flask_g=round(rig.L.mass('flask') - flask0, 3), left_in_P1_g=round(rig.L.mass('P1'), 3),
                spilled_g=round(rig.L.spilled_mass(), 3), in_flight_g=round(rig.LM.in_flight_g(), 4), landing=lnd, landing_limit_mm=40.0,
                funnel_rim_radius_mm=params['funnel']['rim_d'] / 2, lip_above_rim_mm=info['lip_above_rim'], grip_h_mm=info['grip_h_used'],
                profile_time_s=prof['time_s'], grasp=grasp.get('grasps'), manifold=manifold_steepness(tilt, 40.0, 105.0),
                ramp_tilt_lag=None if lag is None else dict(max_deg=round(lag['theta_cmd'] - lag['theta_beaker'], 2), at_theta_cmd=lag['theta_cmd']), setup=rig.setup, sim_s=round(rig.w.time, 2),
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


CALIBRATION_FILLS_ML = [60.0, 70.0, 80.0]


def calibration_jobs():
    """architecture 5.2: V_first offset from 3 weighed-fill pours (offset 0 and no low-fill PAUSE while calibrating)"""
    return [('scale', dict(seed=100 + i, fill_ml=f, reagent_over=dict(low_fill_ml=0.0, fill_offset_ml=0.0), label='calibration %.0f mL' % f,
                           keep_trace=False)) for i, f in enumerate(CALIBRATION_FILLS_ML)]


def summarize_calibration(rows):
    vt = beaker_cylinder(load_params()); out = []
    for r in rows:
        if 'error' in r or r.get('theta_first_deg') is None: out.append(dict(label=r.get('label'), failed=r.get('error') or r.get('outcome'))); continue
        out.append(dict(fill_ml=r['fill_ml'], theta_first_deg=r['theta_first_deg'], theta_true_deg=r['v_first_true_theta_deg'],
                        detection_lag_deg=round(r['theta_first_deg'] - r['v_first_true_theta_deg'], 2),
                        v_table_ml=round(vt.v_crit_ml(r['theta_first_deg']), 2), offset_ml=round(r['fill_ml'] - vt.v_crit_ml(r['theta_first_deg']), 2),
                        outcome=r['outcome'], error_g=r['error_g']))
    offs = [o['offset_ml'] for o in out if 'offset_ml' in o]
    return dict(pours=out, fill_offset_ml=round(float(np.mean(offs)), 2) if offs else None)


def pour_direction():
    """horizontal pour direction of step 2 (the native plan's dvec)"""
    try: d = json.loads((REPORTS / 'native_plans.json').read_text())['steps'][STEP['dev'][0]]['info']['dvec']
    except (OSError, KeyError, TypeError):
        rig = PourRig(0); name, rec, bk, src, _, lip, recv = STEP['dev']; d = rig.planner.plan_pour(rec, bk, src, grip_height('dev'), lip, recv)[1]['dvec']
    d = np.asarray(d[:2], float); return d / np.linalg.norm(d)


def spill_cases():
    """the deliberate spills: the receiver (with the scale pan it sits in) moved off its planned position"""
    d = pour_direction(); perp = np.array([-d[1], d[0]])
    a = 35.0 * perp; b = -22.0 * d + 22.0 * perp
    return [('spill A: receiver 35 mm across the pour direction', a, {}),
            ('spill B: receiver 31 mm diagonal (22 toward the pourer, 22 across)', b, {}),
            ('spill B without the spill check', b, dict(spill_check=False))]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    procs = int(next((a.split('=')[1] for a in argv if a.startswith('--procs=')), 5))
    if '--calibrate' in argv:
        c = summarize_calibration(run_jobs(calibration_jobs(), procs)); print(json.dumps(c, indent=1)); return 0
    if '--quick' in argv:
        r = scale_trial(1, 65.0, keep_trace=False); r.pop('events'); print(json.dumps(r, indent=1, default=str)); return 0
    t0 = time.time(); params = load_params()
    jobs = [('scale', dict(seed=i + 1, fill_ml=f, label='trial %02d' % (i + 1))) for i, f in enumerate(TRIAL_FILLS_ML)]
    jobs += [('scale', dict(seed=21, fill_ml=40.0, label='low fill 40 mL'))]
    for name, off, over in spill_cases():
        jobs.append(('scale', dict(seed=31, fill_ml=70.0, scale_offset_mm=off, cfg_over=over, label=name)))
    jobs.append(('funnel', dict(seed=41)))
    n_cal = len(CALIBRATION_FILLS_ML); rows = run_jobs(calibration_jobs() + jobs, procs)
    cal = summarize_calibration(rows[:n_cal]); rows = rows[n_cal:]
    print('synthetic 9.1 tracking test ...')
    syn = [synthetic_tracking(params['pour']['kp_deg_per_gs'], 0.3), synthetic_tracking(params['pour']['kp_deg_per_gs'], params['pour']['ki_deg_per_s_per_gs'])]
    report = build_report(rows, cal, syn, params, time.time() - t0)
    print(report['verdict'])
    return 0 if report['acceptance']['pass'] else 1


# ======================================================================= report
def _tilt_lag(rows, states=None):
    d = [abs(r['theta_cmd'] - r['theta_beaker']) for r in rows if (states is None or r['state'] in states)]
    return round(max(d), 2) if d else None


def build_report(rows, cal, syn, params, wall_s):
    import shutil
    shutil.rmtree(TRACES, ignore_errors=True); TRACES.mkdir(parents=True, exist_ok=True)
    errors = [r for r in rows if 'error' in r]
    trials = [r for r in rows if not ('error' in r) and r['label'].startswith('trial')]
    other = {r['label']: r for r in rows if 'error' not in r and not r['label'].startswith('trial')}
    funnel = next((r for r in rows if 'error' not in r and 'delivered_to_flask_g' in r), None)
    tol = params['recipe']['developer_tol_g']; P = params['pour']
    for r in rows:
        if 'error' in r: continue
        name = r['label'].split(':')[0].replace(' ', '_') if 'delivered_to_flask_g' not in r else 'funnel_pour'
        if 'trace' in r:
            r['tilt_lag_max_deg'] = _tilt_lag(r['trace'], ('FLOW', 'TOPUP_PULSE', 'TOPUP_FLOW'))
            r['trace_csv'] = write_trace(name.replace('(', '').replace(')', '').replace(',', ''), r.pop('trace'))
    e = np.array([r['error_g'] for r in trials]); within = [abs(x) <= tol for x in e]
    ok = [r for r in trials if r['outcome'] == 'OK']
    refit = fit_cut_law([(r['q_cut_g_s'], r['controller_settled_g'] - r['m_cut_g']) for r in ok if r['cuts'] == 1 and r['q_cut_g_s'] is not None])
    after_cut = [r['controller_settled_g'] - r['m_cut_g'] for r in ok if r['cuts'] == 1]
    law = [P['cut_a_g'] + P['cut_b_s'] * r['q_cut_g_s'] for r in ok if r['cuts'] == 1]
    spills = {k: v for k, v in other.items() if k.startswith('spill')}
    acc = dict(trials=len(trials), within_tol=int(sum(within)), tol_g=tol, need=9, pass_trials=bool(len(trials) >= 10 and sum(within) >= 9),
               spill_demonstrated=bool(any(v['spilled_g'] > 0 for v in spills.values())), errors=[dict(label=x['label'], error=x['error']) for x in errors])
    acc['pass'] = bool(acc['pass_trials'] and acc['spill_demonstrated'] and not errors)
    stats = dict(mean_error_g=round(float(e.mean()), 3), std_error_g=round(float(e.std(ddof=1)), 3), max_abs_error_g=round(float(np.abs(e).max()), 3),
                 time_mean_s=round(float(np.mean([r['time_s'] for r in trials])), 2), time_max_s=round(float(max(r['time_s'] for r in trials)), 2),
                 controller_vs_true_max_g=round(float(max(abs(r['controller_settled_g'] - r['final_true_g']) for r in trials)), 3),
                 after_cut_mean_g=round(float(np.mean(after_cut)), 3) if after_cut else None,
                 cut_law_mean_g=round(float(np.mean(law)), 3) if law else None, spill_margin_min_g=min((r['spill_margin_g'] for r in trials
                                                                                                         if r['spill_margin_g'] is not None), default=None),
                 tilt_lag_max_deg=max(r['tilt_lag_max_deg'] for r in trials), wall_s=round(wall_s, 1))
    verdict = ('pour trials: %d/%d within +-%.0f g (mean %+.2f g, sd %.2f g, max |e| %.2f g, %.1f s mean per pour); spill shown: %s; %s'
               % (acc['within_tol'], acc['trials'], tol, stats['mean_error_g'], stats['std_error_g'], stats['max_abs_error_g'], stats['time_mean_s'],
                  acc['spill_demonstrated'], 'PASS' if acc['pass'] else 'FAIL'))
    rep = dict(phase='6 pour', verdict=verdict, acceptance=acc, stats=stats, trials=trials, low_fill=other.get('low fill 40 mL'), spills=spills,
               funnel=funnel, calibration=cal, cut_law_refit=refit, synthetic_tracking=[{k: v for k, v in s.items() if k != 'by_case'} for s in syn],
               synthetic_tracking_cases=syn, config=dict(liquid=params['liquid'], pour=params['pour']),
               notes=['analytic liquid model, not CFD (benchsim/chem/liquid.py)', 'P1 is teleported from its carousel pocket onto the scale pan before each '
                      'pour (the phase-5 transfer is not re-run here)', 'errors are against the Ledger mass in P1 after untilt (truth); the controller '
                      'reads the simulated HX711 stream only'])
    (REPORTS / 'pour_report.json').write_text(json.dumps(rep, indent=1, default=str))
    (REPORTS / 'pour_report.md').write_text(render_md(rep, params))
    return rep


def _f(x, fmt='%.2f'):
    return '-' if x is None else fmt % x


def render_md(rep, params):
    A = rep['acceptance']; S = rep['stats']; P = params['pour']; L = params['liquid']; out = []
    w = out.append
    w('# Phase 6: analytic liquid model and closed-loop pouring\n')
    w('Generated by `python -m benchsim.pour_trials` (simulation only). **%s**\n' % rep['verdict'])
    w('## What is modelled (analytic, not CFD)\n')
    w('- **Tilted cylinder** (`chem/liquid.py: TiltedCylinder`): beaker inside r %.1f mm, h %.1f mm; flat horizontal free surface (no slosh, '
      'no meniscus). Volume vs tilt and surface height above the lip by quadrature; V_c(theta) and its inverse theta_first(V). Checked '
      'against the closed forms (pi r^2 (h - r tan theta) for small tilt, 2/3 r^2 h for the ungula) in `tests/test_pour.py`.' %
      (params['beaker']['od'] / 2 - params['beaker']['wall'], params['beaker']['height'] - params['beaker']['floor']))
    w('- **Weir flow over the lip** (approximation): Q = Cd 2/3 sqrt(2g) w (h - h_hold)^1.5 with Cd %.2f, effective lip width %.0f mm, '
      'hold-up head %.1f mm (all assumed, `[liquid]`). Viscosity and surface tension beyond h_hold are ignored.' % (L['cd'], L['lip_width_mm'], L['hold_head_mm']))
    w('- **Stream**: %.0f ms lip run-down, then a drag-free ballistic fall from the outer lip at the critical-depth velocity sqrt(g 2h/3) '
      'along the pour direction. Mass in flight is tracked as parcels; a parcel is caught by the highest opening it falls through '
      '(beaker: inner radius; funnel: rim radius %.0f mm -> flask after %.1f s) in proportion to the overlap of a %.0f mm jet disc '
      'with the opening; the rest is `Ledger.spill` (removed from the balance, even if it would land on the pan).' %
      (L['transport_delay_s'] * 1000, params['funnel']['rim_d'] / 2, L['funnel_delay_s'], L['jet_radius_mm']))
    w('- **Impact force** of the landing stream (m_dot v_z) is applied to the receiver beaker (`impact_force = %s`), so the scale reads the '
      'stream overshoot; **after-drip** %.2f mL per pour (tau %.1f s); **residual film** %.1f mL never drains.\n' %
      (str(L['impact_force']).lower(), L['drip_ml'], L['drip_tau_s'], L['residual_film_ml']))
    w('## Acceptance\n')
    w('| check | result |\n|---|---|')
    w('| trials within +-%.0f g (need >= %d of %d) | **%d / %d** |' % (A['tol_g'], A['need'], A['trials'], A['within_tol'], A['trials']))
    w('| final error (true mass in P1 - 39 g) | mean %+.3f g, sd %.3f g, max abs %.3f g |' % (S['mean_error_g'], S['std_error_g'], S['max_abs_error_g']))
    w('| time per pour (controller start at the pre-pour pose -> settled) | mean %.1f s, max %.1f s |' % (S['time_mean_s'], S['time_max_s']))
    w('| controller settled reading vs truth | max %.3f g apart |' % S['controller_vs_true_max_g'])
    w('| spill demonstrated | %s |' % ('yes' if A['spill_demonstrated'] else 'no'))
    w('| runner errors | %s |\n' % (A['errors'] or 'none'))
    w('## Closed-loop trials (target 39 g developer onto P1)\n')
    w('Fresh world per trial; seed = HX711 noise seed. theta_first = commanded tilt when first drop was detected; theta_c(fill) = where the '
      'fill truly reaches the lip. Landing = distance of the stream from the receiver axis at its rim (mass-weighted / max).\n')
    w('| trial | fill mL | seed | outcome | true g | error g | settled g | time s | theta_first (theta_c) | V_first mL | theta_cut | q_cut g/s | landing mm | spilled g | tilt lag deg | trace |')
    w('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for r in rep['trials']:
        ld = r['landing'] or {}
        w('| %s | %.1f | %d | %s | %.2f | %+.2f | %.2f | %.1f | %s (%.1f) | %s | %s | %s | %s / %s | %s | %s | `%s` |' % (
            r['label'], r['fill_ml'], r['seed'], r['outcome'], r['final_true_g'], r['error_g'], r['controller_settled_g'], r['time_s'],
            _f(r['theta_first_deg'], '%.1f'), r['v_first_true_theta_deg'], _f(r['v_first_ml'], '%.1f'), _f(r['theta_cut_deg'], '%.1f'),
            _f(r['q_cut_g_s']), _f(ld.get('mass_weighted_mm'), '%.1f'), _f(ld.get('max_mm'), '%.1f'), _f(r['spilled_g'], '%.3f'),
            _f(r.get('tilt_lag_max_deg')), r.get('trace_csv')))
    w('')
    w('Landing and tilt lag are taken while the controller runs (tilt lag = largest commanded - actual beaker tilt in FLOW). The few mg spilled '
      'per trial are after-drip that falls from the lip while the harness untilts the beaker back to the pre-pour pose after DONE '
      '(spilled during the pour itself: max %s g). The step-2 pours stay below theta %.0f deg. Above about 85 deg the native manifold moves up to '
      '%s deg of joint per degree of tilt (see Funnel pour).\n' % (_f(max(r['spilled_during_pour_g'] for r in rep['trials']), '%.4f'),
                                                                  max(r['max_theta_deg'] for r in rep['trials']) + 1,
                                                                  _f((rep['funnel'] or {}).get('manifold', {}).get('max_joint_deg_per_deg'), '%.0f')))
    rf = rep['cut_law_refit']
    w('**Cut law.** Configured a = %.2f g, b = %.2f s predicts %s g after the cut on average; the scale actually gained %s g after the cut. '
      'Least-squares refit on these pours (architecture 5.4 procedure): %s. q_cut spans only %s-%s g/s, because the loop has brought the '
      'flow down to q_min before the cut, so b is not identifiable from these pours (5.4 asks for pours spanning 1-8 g/s). It is reported, '
      '**not applied**; the trials above use the configured values. The configured law cuts about %s g early on average, which is the '
      'mean error.\n' % (P['cut_a_g'], P['cut_b_s'], _f(S['cut_law_mean_g']), _f(S['after_cut_mean_g']),
                         'a = %.3f g, b = %.3f s (n %d, rms %.3f g)' % (rf['a_g'], rf['b_s'], rf['n'], rf['rms_g']) if rf else 'n/a',
                         _f(min(r['q_cut_g_s'] for r in rep['trials'])), _f(max(r['q_cut_g_s'] for r in rep['trials'])),
                         _f(S['cut_law_mean_g'] - S['after_cut_mean_g']) if S['cut_law_mean_g'] is not None and S['after_cut_mean_g'] is not None else '-'))
    c = rep['calibration']
    w('**Fill inference (5.2).** `fill_offset_ml = %.1f` in `[pour.developer]` comes from three weighed-fill calibration pours (offset 0, '
      'low-fill PAUSE off); this run repeated them:\n' % P['developer']['fill_offset_ml'])
    w('| fill mL | theta_first | theta_c | detection lag deg | V_table mL | offset mL | outcome | error g |\n|---|---|---|---|---|---|---|---|')
    for o in c['pours']:
        if 'offset_ml' in o: w('| %.0f | %.2f | %.2f | %.2f | %.2f | %.2f | %s | %+.2f |' % (o['fill_ml'], o['theta_first_deg'], o['theta_true_deg'],
                                                                                         o['detection_lag_deg'], o['v_table_ml'], o['offset_ml'], o['outcome'], o['error_g']))
        else: w('| %s | failed: %s |||||||' % (o['label'], o['failed']))
    w('\nMean offset this run: %s mL. The offset is mostly first-drop detection lag (the 3-sample, 0.3 g rule on a 0.5 s line fit while '
      'the tilt ramps at %.0f deg/s), plus the %.1f mm hold-up head.\n' % (_f(c['fill_offset_ml']), P['ramp_rate_deg_s'], L['hold_head_mm']))
    w('## Flow tracking (architecture 5.3 / 9.1)\n')
    w('Acceptance in the architecture: q* tracked within +-1 g/s after 1.5 s for 1-8 g/s. Tested on the MuJoCo-free synthetic plant '
      '(same lip-flow relations, `SyntheticPour`) with a constant q*, over 1/2/4/8 g/s, fills 55/80 mL, lip width 10/14/20 mm and hold-up head '
      '0/0.5/1 mm (72 cases); error = max |q_hat - q*| from 1.5 s to 6 s after first drop:\n')
    w('| Kp deg/(g/s) | Ki deg/s/(g/s) | cases within 1 g/s | median worst | worst |\n|---|---|---|---|---|')
    for s_ in rep['synthetic_tracking']:
        w('| %.2f | %.2f | %d / %d | %.2f | %.2f |' % (s_['kp'], s_['ki'], s_['within_1g_s'], s_['cases'], s_['median_g_s'], s_['worst_g_s']))
    w('\nThe architecture\'s initial Ki = 0.3 misses the criterion: with the feed-forward holding the current flow, the PI acts as an '
      'integral flow loop with time constant (tau_lip + G Kp)/(G Ki), where G = rho |dV_c/dtheta| is about 3 g/deg and tau_lip = 1.3-2.7 s is the '
      'drain time of the liquid standing above the lip. That gives 2-3.5 s with Ki 0.3. The config uses Ki = %.2f (Kp unchanged, %.2f). '
      'Retune on hardware. In the MuJoCo pours, |q_hat - q*| includes the set-point ramp-down near the target (q* falls at 0.6 q per second), '
      'so it is larger than in the constant set-point test: worst per trial %s g/s.\n' % (P['ki_deg_per_s_per_gs'], P['kp_deg_per_gs'],
                                                                                      ', '.join(_f((r['tracking'] or {}).get('max_err_g_s')) for r in rep['trials'])))
    lf = rep['low_fill']
    if lf:
        w('## Low reagent\n')
        w('Fill 40 mL (below the 46 mL PAUSE line): outcome **%s**: %s. theta_first %s deg, V_first %s mL, %.2f g reached P1, %.2f g spilled, '
          '%.1f s.\n' % (lf['outcome'], lf['reason'], _f(lf['theta_first_deg'], '%.1f'), _f(lf['v_first_ml'], '%.1f'), lf['final_true_g'], lf['spilled_g'], lf['time_s']))
    w('## Deliberate spill\n')
    w('P1 sits in the WS-02 locating ring (2.2 mm radial play), so the receiver offset is applied to the whole scale pan with P1 in it, as if WS-01 '
      'were clamped off its JG-06 jig position. The arm pours along the unchanged native plan. Fill 70 mL, seed 31.\n')
    w('| case | pan offset mm (x, y) | outcome | P1 true g | spilled g | left in source g | theta max | time s | reason |\n|---|---|---|---|---|---|---|---|---|')
    for k, v in rep['spills'].items():
        off = next((x for x in v['setup'] if x.startswith('scale pan shifted')), '')
        w('| %s | %s | %s | %.2f | %.2f | %.2f | %s | %.1f | %s |' % (k, off.replace('scale pan shifted by ', '').replace(' mm from its update13_final position', ''),
                                                                    v['outcome'], v['final_true_g'], v['spilled_g'], v['left_in_source_g'], _f(v['max_theta_deg'], '%.1f'),
                                                                    v['time_s'], v['reason']))
    w('\n- **A (total miss):** nothing reaches P1, so first drop is never detected; the ramp stops at theta_table(46 mL - offset) and the controller '
      'untilts and pauses (`PAUSE_NO_FLOW`, "refill, or the stream misses the receiver"). Everything that crossed the lip before the untilt is spilled.')
    w('- **B (partial miss):** part of the stream lands in P1, so the loop runs. The flow the scale sees is low, so the controller tilts further. '
      'The mass-deficit check (an addition to section 5: tilt-implied mass out vs scale gain, armed %.1f s after first drop, %.1f s hold) '
      'pauses with `PAUSE_SPILL` and leaves the rest in the source. Without it the pour runs to the 105 deg manifold end (`PAUSE_LOW_REAGENT`) '
      'and empties the source. The check fires late because the liquid standing above the lip (6-18 g at 1-8 g/s) looks like a deficit '
      'during the start-up transient. Its smallest margin in the 10 normal trials was %s g (negative would mean a false alarm). The real fix is '
      'upstream: check the receiver position (JG-06, the place check) before pouring.' % (P['spill_arm_s'], P['spill_hold_s'], _f(S['spill_margin_min_g'])))
    w('- **Toward the pourer is a collision, not a spill:** during the tilt-in the source beaker\'s lower edge swings below the receiver rim. '
      'With the receiver moved 33 mm toward the pourer, the developer beaker\'s floor strikes P1\'s wall at theta 34 deg (MuJoCo contacts '
      'beaker_dev_floor / beaker_P1 wall boxes; the scale read 27 g at contact). Seen while choosing the spill geometry, not part of these runs.\n')
    f = rep['funnel']
    if f:
        ld = f['landing'] or {}
        w('## Funnel pour (POUR_TO_FUNNEL, fixed profile)\n')
        w('P1 with %.1f g developer is picked from the scale (grip %.0f mm, lip %.0f mm above the funnel rim), fast to 40 deg, %.0f deg/s to %.0f deg, '
          'hold %.1f s, two-stage untilt, drip hold %.1f s. Open loop (nothing weighs the flask).\n' %
          (f['content_g'], f['grip_h_mm'], f['lip_above_rim_mm'], P['funnel_rate_deg_s'], P['funnel_theta_deg'], P['funnel_hold_s'], P['drip_hold_s']))
        w('| quantity | value |\n|---|---|')
        w('| delivered to the flask | %.2f g of %.1f g |' % (f['delivered_to_flask_g'], f['content_g']))
        w('| left in P1 (residual film) | %.2f g |' % f['left_in_P1_g'])
        w('| spilled | %.2f g |' % f['spilled_g'])
        w('| landing offset from the funnel axis at the rim (mass-weighted / max) | %s / %s mm (limit %.0f mm; rim radius %.0f mm) |' % (
            _f(ld.get('mass_weighted_mm'), '%.1f'), _f(ld.get('max_mm'), '%.1f'), f['landing_limit_mm'], f['funnel_rim_radius_mm']))
        w('| tilt range while liquid landed | %s deg |' % f['landing_theta_range'])
        rl = f.get('ramp_tilt_lag') or {}; mf = f.get('manifold') or {}
        w('| max commanded - actual beaker tilt on the ramp to %.0f deg | %s deg at commanded %s deg |' % (P['funnel_theta_deg'], _f(rl.get('max_deg')), _f(rl.get('at_theta_cmd'), '%.1f')))
        w('| steepest native-manifold step (joint deg per tilt deg) | %s at theta %s deg |' % (_f(mf.get('max_joint_deg_per_deg'), '%.1f'), _f(mf.get('at_theta_deg'), '%.0f')))
        w('| profile time | %.1f s |' % f['profile_time_s'])
        w('| trace | `%s` |\n' % f.get('trace_csv'))
        w('The ramp lag is kinematic, not the liquid load: the same lag appears with an empty beaker. Between theta about 85 and 96 deg the native '
          'manifold (phase-3 continuation IK, which allows at most 17 deg per step) moves elbow and wrist flex by up to 17 deg per degree of tilt. '
          'At %.0f deg/s that saturates both actuators (load +-1000 per-mille), so the beaker trails the command until 105 deg. The liquid has '
          'mostly left by then, so the delivered mass is unaffected. A planner-side fix (a smoother branch, or a joint-speed-aware tilt rate on '
          'that stretch) belongs to phase 3.\n' % P['funnel_rate_deg_s'])
    w('## Setup and harness notes\n')
    t1 = rep['trials'][0] if rep['trials'] else None
    if t1:
        w('- Receiver: %s. Developer: %s.' % (t1['setup'][0], t1['setup'][1]))
        w('- The pourer runs the first %d segments of the native step-2 plan (grip height %.0f mm from reports/native_plans.json) through the '
          'phase-5 Executor; the grasp is classified from the jaw angle (%s) and held by the phase-5 weld. Pre-pour reached at %.1f s sim.' % (
              PRE_POUR_SEGS, t1['grip_h_mm'], ', '.join('%s %.2f deg vs %.2f' % (g['outcome'], g['jaw_deg'], g['expected_deg']) for g in (t1['grasp'] or [])),
              t1['prepour_sim_s']))
    w('- Tilt actuator: theta -> joint goal by linear interpolation of the plan\'s tilt-in (theta from forward kinematics of the held beaker) and '
      'the 1-deg pour manifold; goals go to SimArm.set_goal at %.0f Hz. Largest commanded - actual beaker tilt while pouring: %s deg.' % (
          1 / P['control_dt_s'], _f(S['tilt_lag_max_deg'])))
    w('- Scale samples come from MegaClient (STREAM, TARE) on the simulated HX711 (80 Hz, %.2f g noise). The flexure reading includes the '
      'stream impact. Total wall time %.0f s (5 processes).' % (params['scale']['noise_g'], S['wall_s']))
    w('- Traces (`reports/pour_traces/*.csv`, every %dnd control tick): t, state, theta_cmd, theta_beaker (actual), m_f, q_hat, q_set, '
      'scale_w (latest raw sample), m_true (Ledger), q_lip (true lip flow g/s), in_flight, spilled, src_g.\n' % TRACE_EVERY)
    w('## Known gaps\n')
    w('- Every `[liquid]` coefficient is assumed; the plant time constant (liquid above the lip) scales with lip width and hold-up head. '
      'The gain choice was checked over lip width 10-20 mm and hold-up head 0-1 mm on the synthetic plant only.')
    w('- No slosh, no wave over the lip on fast untilt, no teapot effect (liquid running back under the lip at low flow), no viscosity: the '
      'architecture\'s two-stage untilt exists for slosh this model cannot produce.')
    w('- Spilled liquid leaves the balance even if it would land on the WS-02 pan and be weighed.')
    w('- The fill offset and the cut law are simulator values. Both must be re-measured on the bench (architecture 5.2, 5.4).')
    w('- Settled is |q_hat| < %.2f g/s and window sigma < %.2f g: the architecture\'s 0.05 g is below the per-sample HX711 noise.' % (P['settle_flow_g_s'], P['settle_sigma_g']))
    w('- Water pours (step 7) use the same controller; `[pour.water] fill_offset_ml` is assumed equal to the developer value and was not simulated here.')
    return '\n'.join(out) + '\n'


if __name__ == '__main__':
    sys.exit(main())
