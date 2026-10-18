"""Full deterministic demo in simulation: the 9 steps of docs/demo_process.md through the sequencer, with the
analytic liquid, auger and foam models, a video, camera frames, a machine-readable run log and the lab notebook.

    python -m benchsim.demo_run                         # preset protocol (demo_process 4)
    python -m benchsim.demo_run --protocol-text FILE    # language layer: proposal -> validation -> approval -> run
    python -m benchsim.demo_run --stop-during-pour      # safe-stop demonstration: operator stop mid-pour

Outputs go to runs/<run_id>/ (run_log.json, scale.csv, joints.csv, pour traces, frames/, demo.mp4, notebook.*).
"""
import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

from . import paths, poses, runlog, state
from .bench import make_bench
from .chem.auger import AugerModel
from .chem.foam import FoamModel, load_flask
from .chem.liquid import LiquidModel, beaker_cylinder
from .chem.vessels import DENSITY, Ledger
from .layout import load_params
from .mechanisms import Mechanisms, first_pass_rev, topup_rev
from .process import skills as SK
from .process.executor import Executor, TaskFailed
from .process.pour import PourController, funnel_pour
from .process.pour_sim import ManifoldTilt, manifold_table
from .process.sequencer import Sequencer, StepFailed
from .process.steps import Step, demo_protocol
from .record import Recorder

PRE_POUR_SEGS = 6          # approach, descend, close, lift, carry to above pre-pour, lower to pre-pour
AFTER_UNTILT = 9           # raise from pre-pour, carry back, lower, release, lift out, park
CLEAR_SEGS = 1             # raise from pre-pour: after it the held beaker is clear of the funnel and the sled may move
INITIAL = dict(developer_ml=58.0, water_ml=50.0, hopper_g=30.0)       # rough operator loads (demo_process 5.2)
NATIVE = paths.SIM_ROOT / 'reports' / 'native_plans.json'
STEP_KEY = {('developer', 'P1'): ('P_dev', 'dev', 'rack_1', 45.0, '2 developer pour'), ('water', 'P2'): ('P_wat', 'water', 'rack_3', 45.0, '7 water pour')}


def grip_heights():
    try: d = json.loads(NATIVE.read_text())['steps']
    except OSError: d = {}
    g = lambda k, dflt: float(d.get(k, {}).get('info', {}).get('grip_h_used', dflt))
    return {'2 developer pour': g('2 developer pour', 40.0), '7 water pour': g('7 water pour', 40.0), 'funnel': g('3 P1 funnel pour', 30.0)}


class SimDemo:
    def __init__(self, out_root, seed=0, video=True, fps=15):
        self.params = P = load_params(); self.bb = bb = make_bench('sim', seed=seed); self.w = w = bb.world
        self.L = Ledger(w); self.LM = LiquidModel(w, self.L); self.aug = AugerModel(w, bb.mega_device, self.L, seed=seed)
        self.foam = FoamModel(w, self.L); load_flask(self.L)
        self.L.add('dev', 'developer', INITIAL['developer_ml'] * DENSITY['developer'])
        self.L.add('water', 'water', INITIAL['water_ml'] * DENSITY['water']); self.aug.fill(INITIAL['hopper_g'])
        R = P['recipe']
        if R.get('yeast_in_flask'):                     # MVP: the yeast-water mix is loaded into the flask by hand
            self.L.add('flask', 'yeast', R['yeast_g']); self.L.add('flask', 'water', R['water_g'])
        elif R.get('premixed_yeast_water'):             # P2 is loaded already holding the yeast-water mix
            self.L.add('P2', 'yeast', R['yeast_g']); self.L.add('P2', 'water', R['water_g'])
        self.planner = poses.Planner(w.m, w.b); self.gh = grip_heights()
        self.mech = Mechanisms(bb.mega, bench=None)
        self.rl = runlog.RunLog(out_root, 'sim', seed=seed); self.dir = self.rl.dir; (self.dir / 'frames').mkdir(exist_ok=True)
        self.rec = Recorder(w, self.dir, camera='overview', fps=fps, width=960, height=544, video_name='demo.mp4' if video else None)
        from .vision import SimCamera
        self.cams = {n: SimCamera(w, n, 640, 480) for n in ('bench_cam', 'foam_cam', 'overview')}
        self.pour_traces = []; self.notes = []; self.dose = {}; self.erupt_done_s = None
        self.L.update_visuals()

    # ------------------------------------------------------------------ helpers
    def frame(self, camera, label):
        import imageio.v3 as iio
        img, meta = self.cams[camera].grab(); p = self.dir / 'frames' / ('%07.2f_%s.png' % (self.w.time, camera))
        iio.imwrite(p, img); self.rl.frame(self.w.time, camera, p, label); return img

    def executor(self, ctx):
        return Executor(self.bb.arms, self.bb.clock, self.params['gripper'], state.park_q(), scale=lambda: self.bb.mega.read_mass(8),
                        events=ctx.events, on_tick=self._tick(ctx))

    def _tick(self, ctx):
        def t():
            self.L.update_visuals(); ctx.tick()
        return t

    def scale(self, n=24): return self.bb.mega.read_mass(n)

    def premix_flask(self, yeast_g, water_g):
        """live-demo loading (steps.flask_demo_protocol): the operator has mixed the yeast with the warm water and poured it into the flask"""
        self.L.add('flask', 'yeast', yeast_g); self.L.add('flask', 'water', water_g); self.L.update_visuals()

    # ------------------------------------------------------------------ skills
    def make_skills(self):
        base = SK.make_skills(self.bb, self, self.params['gripper'], state.park_q(), self.params)
        sk = dict(base)

        def transfer(step, ctx):
            p = step.params
            if p['src'] == 'carousel_pick':
                pocket = self.mech.pocket_at('pick')
                if self.mech.pockets[pocket] != p['beaker']: raise StepFailed('WRONG_POCKET', '%s is not at the pick' % p['beaker'])
                roi_img = self.frame('bench_cam', 'before pick %s' % p['beaker'])
            res = base['TRANSFER'](step, ctx)
            if p['src'] == 'carousel_pick': self.mech.remove(p['beaker'])
            if p['dst'] == 'carousel_pick': self.mech.insert(p['beaker'], 'pick')
            self.frame('bench_cam', 'after %s' % step.label)
            return res
        sk['TRANSFER'] = transfer

        def pour_to_scale(step, ctx):
            p = step.params; rec, src, src_station, lip, name = STEP_KEY[(p['reagent'], p['beaker'])]
            segs, info = self.planner.plan_pour(rec, src, src_station, self.gh[name], lip, 'scale_pan')
            ex = self.executor(ctx); ctx.state['active_arm'] = 'pourer'
            try: r = ex.run('pourer', segs[:PRE_POUR_SEGS], label=step.label + ' to pre-pour')
            except TaskFailed as e: raise StepFailed(e.code, e.detail)
            arm = self.bb.arms['pourer']; th, qs = manifold_table(self.planner, segs, info); tilt = ManifoldTilt(arm, th, qs, float(arm.goal()[5]))
            # absent = nothing has been put in this beaker yet (empty, 0 g); present but None = an auger
            # dose went in that no VERIFY_MASS has weighed yet (dose_yeast's convention).  A relative pour
            # adds on top of the live scale reading and does not need the number; an absolute one cannot be
            # computed without it, and must say so rather than add to None (which the sequencer would
            # rewrite into a bogus SAFE_STOP).
            base_g = self.scale(32); content0 = ctx.state['contents_g'].get(p['beaker'], 0.0)
            if p.get('relative'): target = p['target_g']
            elif content0 is None:
                raise StepFailed('CONTENT_UNKNOWN', '%s holds a dose that has not been weighed; VERIFY_MASS it first, '
                                                    'or pour relative to the scale' % p['beaker'])
            else: target = p['target_g'] - content0
            cfg = self.params['pour']; rho = DENSITY[p['reagent']]
            pc = PourController(cfg, beaker_cylinder(self.params), rho, target, p['tol_g'], p['reagent'])
            trace = []

            def samples():
                s = self.bb.mega.take_samples(); return [(x['t'] / 1000.0, x['w'] - base_g) for x in s]

            def set_theta(theta):
                tilt.set_theta(theta); trace.append((round(self.w.time, 3), round(theta, 2)))
                if len(trace) % 4 == 0: self.L.update_visuals()
                ctx.tick()

            def untilt(rate=60.0):
                thv = tilt.last if tilt.last is not None else 0.0
                while thv > 0: thv = max(thv - rate * 0.025, 0.0); tilt.set_theta(thv); self.bb.clock.sleep(0.025)
            ctx.state['pouring'] = untilt
            self.frame('overview', 'pour start %s' % step.label)
            res = pc.run(self.bb.clock, samples, set_theta)
            untilt(); ctx.state['pouring'] = None; self.bb.clock.sleep(1.5)
            added = self.scale(32) - base_g
            try: ex.run('pourer', segs[AFTER_UNTILT:], label=step.label + ' return', start_holding='grasp_side')
            except TaskFailed as e: raise StepFailed(e.code, e.detail)
            ctx.state['active_arm'] = None
            ctx.state['contents_g'][p['beaker']] = None if content0 is None else content0 + added
            self._save_pour_trace(step, res, trace)
            meas = dict(added_g=round(added, 3), content_g=None if content0 is None else round(content0 + added, 3), outcome=res.outcome, theta_first_deg=res.theta_first_deg,
                        theta_cut_deg=res.theta_cut_deg, pour_time_s=res.time_s, topup_pulses=res.topup_pulses, grip_h_mm=info['grip_h_used'],
                        spilled_total_g=round(self.L.spilled_mass(), 3), sim_truth_receiver_g=round(self.L.mass(p['beaker']), 3))
            tgt = dict(added_g=round(target, 3), tol_g=p['tol_g'])
            if res.outcome not in ('OK', 'OVERSHOOT') or abs(added - target) > p['tol_g']:
                raise StepFailed('POUR_' + res.outcome, '%s; added %.2f g vs %.2f +- %.2f' % (res.reason, added, target, p['tol_g']), meas)
            return dict(target=tgt, measured=meas, detail='%s: added %.2f g (error %+.2f)' % (res.outcome, added, added - target))
        sk['POUR_TO_SCALE'] = pour_to_scale

        def pour_to_funnel(step, ctx):
            bk = step.params['beaker']
            segs, info = self.planner.plan_pour('P_fun', bk, 'scale_pan', self.gh['funnel'], 65.0, 'funnel')
            ex = self.executor(ctx); ctx.state['active_arm'] = 'pourer'
            try: ex.run('pourer', segs[:PRE_POUR_SEGS], scale_station='src', label=step.label + ' to pre-pour')
            except TaskFailed as e: raise StepFailed(e.code, e.detail)
            arm = self.bb.arms['pourer']; th, qs = manifold_table(self.planner, segs, info); tilt = ManifoldTilt(arm, th, qs, float(arm.goal()[5]))
            flask0 = self.L.mass('flask'); src0 = self.L.mass(bk); trace = []

            def set_theta(theta):
                tilt.set_theta(theta); trace.append((round(self.w.time, 3), round(theta, 2)))
                if len(trace) % 4 == 0: self.L.update_visuals()
                ctx.tick()

            def untilt(rate=60.0):
                thv = tilt.last if tilt.last is not None else 0.0
                while thv > 0: thv = max(thv - rate * 0.025, 0.0); tilt.set_theta(thv); self.bb.clock.sleep(0.025)
            ctx.state['pouring'] = untilt
            self.frame('overview', 'funnel pour start %s' % step.label)
            prof = funnel_pour(self.params['pour'], self.bb.clock, set_theta)
            untilt(); ctx.state['pouring'] = None
            self.bb.clock.sleep(self.params['liquid']['funnel_delay_s'] + 0.5)
            back = segs[AFTER_UNTILT:]; erupt = None
            if step.params.get('erupt'):
                # the reaction is under way: lift the beaker clear of the funnel, push the sled out, then carry the beaker back
                try: ex.run('pourer', back[:CLEAR_SEGS], label=step.label + ' lift clear', start_holding='grasp_side')
                except TaskFailed as e: raise StepFailed(e.code, e.detail)
                erupt = sk['STAGE'](Step('STAGE', dict(position='ERUPT'), step.label + ' ERUPT'), ctx); back = back[CLEAR_SEGS:]
            try: ex.run('pourer', back, scale_station='dst', label=step.label + ' return', start_holding='grasp_side')
            except TaskFailed as e: raise StepFailed(e.code, e.detail)
            ctx.state['active_arm'] = None
            tare, how = (ctx.state['tare_g'].get(bk) or ctx.state['tare_g'].get('P1'), 'measured' if bk in ctx.state['tare_g'] else 'assumed = P1')
            left = self.scale(32) - tare; ctx.state['contents_g'][bk] = left
            meas = dict(left_in_beaker_g=round(left, 3), tare=how, sim_truth_delivered_to_flask_g=round(self.L.mass('flask') - flask0, 3),
                        sim_truth_poured_from_beaker_g=round(src0 - self.L.mass(bk), 3), spilled_total_g=round(self.L.spilled_mass(), 3),
                        profile_time_s=prof.get('time_s'))
            if erupt: meas['erupt_crank_deg'] = erupt['measured']['crank_deg']; meas['erupt_done_s'] = self.erupt_done_s
            if left > 2.0: raise StepFailed('FUNNEL_INCOMPLETE', '%.2f g left in %s' % (left, bk), meas)
            return dict(target=dict(left_in_beaker_g=0.0, tol_g=2.0), measured=meas, detail='%.2f g left in %s' % (left, bk))
        sk['POUR_TO_FUNNEL'] = pour_to_funnel

        def dose_yeast(step, ctx):
            p = step.params; A = self.params['auger']; M = self.params['auger_model']
            self.mech.carousel_to(p['beaker'], 'auger'); self.frame('bench_cam', 'P2 at the auger')
            rev = first_pass_rev(p['target_g'], A['g_per_rev_nominal'], A, M)
            done = self.mech.auger(rev, 'first')
            self.mech.carousel_to(p['beaker'], 'pick')
            self.dose[p['beaker']] = dict(target_g=p['target_g'], tol_g=p['tol_g'], max_topups=p.get('max_topups', 2), topups=0, passes=[done])
            ctx.state['contents_g'][p['beaker']] = None
            return dict(target=dict(first_pass_rev=round(rev, 2), first_pass_g=round(rev * A['g_per_rev_nominal'], 3)),
                        measured=dict(rev_done=done.get('rev_done'), sim_truth_in_beaker_g=round(self.L.mass(p['beaker']), 3), hopper_g=round(self.L.mass('hopper'), 3)),
                        detail='first pass %.2f rev; verified on the scale in the next steps' % rev)
        sk['DOSE_YEAST'] = dose_yeast

        def carousel(step, ctx):
            """turn the deck so the beaker's pocket is at the station (pre-mixed P2: brought to the pick spot)"""
            p = step.params
            mv = self.mech.carousel_to(p['beaker'], p['station']) or {}
            return dict(target=dict(station=p['station']), measured=dict(deck_deg=round(float(self.mech.deck), 2)),
                        detail='%s pocket at %s' % (p['beaker'], p['station']))
        sk['CAROUSEL'] = carousel

        def verify_mass(step, ctx):
            """scale check; for a beaker with a pending auger dose, short doses go back for top-ups (demo_process step 6)"""
            p = step.params; d = self.dose.get(p['beaker'])
            while True:
                try:
                    res = base['VERIFY_MASS'](step, ctx)
                    if d: res['measured'].update(topups=d['topups'], auger_passes=d['passes'])
                    return res
                except StepFailed as e:
                    m = e.measured.get('content_g')
                    if not d or m is None or m >= p['target_g'] - p['tol_g'] or d['topups'] >= d['max_topups']: raise
                    A = self.params['auger']; rev = topup_rev(p['target_g'], m, A['g_per_rev_nominal'], self.params['auger_model'])
                    self.notes.append('top-up %d: %.2f g short, %.2f rev' % (d['topups'] + 1, p['target_g'] - m, rev))
                    sk['TRANSFER'](Step('TRANSFER', dict(beaker=p['beaker'], src='scale_pan', dst='carousel_pick'), 'top-up: back'), ctx)
                    self.mech.carousel_to(p['beaker'], 'auger'); d['passes'].append(self.mech.auger(rev, 'topup')); d['topups'] += 1
                    self.mech.carousel_to(p['beaker'], 'pick')
                    sk['TRANSFER'](Step('TRANSFER', dict(beaker=p['beaker'], src='carousel_pick', dst='scale_pan'), 'top-up: to scale'), ctx)
        sk['VERIFY_MASS'] = verify_mass

        def stage(step, ctx):
            res = base['STAGE'](step, ctx); self.frame('foam_cam', 'stage at %s' % step.params['position'])
            if step.params['position'] == 'ERUPT': self.erupt_done_s = round(self.w.time, 3); ctx.log('erupt_done', label=step.label)
            return res
        sk['STAGE'] = stage
        return sk

    # plan provider used by skills.make_skills
    def transfer(self, beaker, src, dst):
        return self.planner.plan_transfer(beaker, src, dst)

    def _save_pour_trace(self, step, res, trace):
        p = self.dir / ('pour_%02d.csv' % (len(self.pour_traces) + 1))
        with open(p, 'w', newline='') as f:
            wr = csv.writer(f); wr.writerow(['t', 'state', 'theta_deg', 'm_f_g', 'q_hat_g_s', 'q_set_g_s'])
            for row in res.trace: wr.writerow(row)
        self.pour_traces.append(p)

    # ------------------------------------------------------------------ run
    def precheck(self, ctx):
        mega = self.bb.mega; mega.command('PING'); mega.command('STREAM', on=True); mega.command('TARE')
        m0 = self.scale(32)
        if abs(m0) > 0.5: raise RuntimeError('scale not zero after tare: %.2f g' % m0)
        for a in self.bb.arms.values():
            if not a.torque_enabled(): raise RuntimeError('arm torque off')
        img = self.frame('bench_cam', 'precheck')
        from .vision import beaker_check
        ctx.log('precheck', scale_g=round(m0, 3))

    def run(self, steps, source='preset', text=None, approval=None, stop_during_pour=False):
        sk = self.make_skills()
        seq = Sequencer(self.bb, sk, self.rl, safe_stop=SK.safe_stop(self.bb, state.park_q()), precheck=self.precheck)
        if stop_during_pour:
            fired = {}

            def hook():
                if not fired and self.LM.q_ml_s.get('dev', 0) > 0.5 and self.L.mass('P1') > 10.0:
                    seq.ctx.request_stop('operator stop during the developer pour'); fired['t'] = self.w.time
            seq.ctx.on_tick_hooks.append(hook)
        self.frame('overview', 'start')
        t_wall = time.time()
        out = seq.run(steps, source=source, text=text, approved_by=(approval or {}).get('operator', 'operator (sim, preset)'))
        if approval: self.rl.set_approval(approval)
        # observe the foam for a while after the last step (stage at ERUPT if it got there)
        t_obs = self.w.time; foam_frames = 0
        while self.w.time - t_obs < 14.0:
            self.bb.clock.sleep(0.5); self.L.update_visuals(); self.bb.mega.heartbeat()
            if int((self.w.time - t_obs) * 2) % 4 == 0: self.frame('foam_cam', 'foam t+%.1f s' % (self.w.time - t_obs)); foam_frames += 1
        self.rec.close()
        self._write(out, seq, time.time() - t_wall, stop_during_pour)
        return out

    def _write(self, out, seq, wall_s, stop_during_pour):
        d = self.dir
        with open(d / 'scale.csv', 'w', newline='') as f:
            wr = csv.writer(f); wr.writerow(['t_s', 'w_g', 'raw'])
            for t, wv, raw in self.bb.mega.sample_log[::2]: wr.writerow([round(t / 1000.0, 4), wv, raw])
        with open(d / 'joints.csv', 'w', newline='') as f:
            wr = csv.writer(f); wr.writerow(['t_s', 'scale_g'] + ['%s_%s_deg' % (a, j) for a in ('pourer', 'transfer') for j in state.ARM_JOINTS])
            for r in seq.ctx.trace: wr.writerow([r['t'], r['scale_g']] + r['pourer'] + r['transfer'])
        self.rl.set_traces(scale_csv=d / 'scale.csv', joints_csv=d / 'joints.csv', pour_traces=self.pour_traces)
        self.rl.d['video'] = 'demo.mp4' if (d / 'demo.mp4').exists() else None
        fs = self.foam.state(); events = [e for e in self.w.events if e['kind'] not in ('mega_cmd',)] + seq.ctx.events
        for f in self.bb.mega.faults: self.rl.fault(f.get('t', 0) / 1000.0, f.get('fault'), json.dumps(f))
        summary = dict(state=out['state'], passed=out['passed'], failed=out['failed'], skipped=out['skipped'],
                       masses=dict(vessels=self.L.snapshot()['vessels'], measured={r['label']: r['measured'] for r in out['steps'] if r['measured']}),
                       spilled_g=round(self.L.spilled_mass(), 3), foam_peak_mm=fs.get('peak_mm'), foam=fs, notes=self.notes,
                       sim_seconds=round(self.w.time, 2), wall_seconds=round(wall_s, 1), stop_during_pour_test=stop_during_pour,
                       final_state=dict(held=dict(self.w.held), torque={a: x.torque_enabled() for a, x in self.bb.arms.items()},
                                        beaker_tilt_deg={b: round(float(np.degrees(np.arccos(np.clip(self.w.d.body('beaker_' + b).xmat[8], -1, 1)))), 2)
                                                         for b in ('P1', 'P2', 'dev', 'water')},
                                        foam_at_neck_s=fs.get('t_foam_at_neck'), erupt_done_s=self.erupt_done_s),
                       assumptions=['P2 tare taken equal to P1 (never weighed empty in the documented run)',
                                    'liquid, auger and foam parameters are analytic-model values from bench_params.toml (many assumed)',
                                    'MuJoCo-native arm plans (CAD recorded paths are not hardware-calibrated)'])
        events.sort(key=lambda e: e['t'])
        self.rl.finish(summary, events=events)
        try:
            from .notebook import render
            render(self.dir)
        except Exception as e:
            print('notebook render failed:', e)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m benchsim.demo_run')
    ap.add_argument('--protocol-text', help='protocol text file for the language layer (proposal -> validation -> approval)')
    ap.add_argument('--approve', action='store_true', help='approve a valid proposal non-interactively (scripted demo only)')
    ap.add_argument('--stop-during-pour', action='store_true', help='request a safe stop in the middle of the developer pour')
    ap.add_argument('--no-video', action='store_true'); ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--out', default=str(paths.RUNS))
    a = ap.parse_args(argv)
    source, text, approval = 'preset', None, None
    if a.protocol_text:
        from .ai import pipeline
        text = Path(a.protocol_text).read_text()
        approver = pipeline.CommandLineApprover(operator='command line') if a.approve else pipeline.InteractiveApprover()
        res = pipeline.run(text, approver=approver)
        if not res.approved:
            print('protocol not approved:', res.to_dict().get('approval')); return 2
        steps = list(res.steps); source = res.proposal.source if hasattr(res, 'proposal') else 'llm'; approval = res.to_dict().get('approval')
    else:
        steps = demo_protocol()
    demo = SimDemo(Path(a.out), seed=a.seed, video=not a.no_video)
    out = demo.run(steps, source=source, text=text, approval=approval, stop_during_pour=a.stop_during_pour)
    print('run %s -> %s' % (out['state'], demo.dir))
    for r in out['steps']: print('  %-34s %-7s %s' % (r['label'], r['status'], (r['reason'] or '')[:110]))
    return 0 if out['state'] == 'DONE' else 1


if __name__ == '__main__':
    sys.exit(main())
