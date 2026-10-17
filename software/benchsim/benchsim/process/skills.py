"""Step implementations (skills) used by the sequencer. Backend independent: they use the ArmBackend/MegaClient
interfaces, a plan provider (MuJoCo-native plans in simulation, taught trajectory files on hardware) and, for the
analytic process models, the injected pour/dose/carousel helpers.

Masses: the scale is tared once with the empty pan at PRECHECK; every later reading is absolute. Beaker tares are
measured when an empty beaker is placed on the pan (P1, step 1). P2 is never weighed empty in the documented run,
so its tare is taken equal to P1's (same EISCO beaker model) - an assumption recorded in the run log.
"""
import math

import numpy as np

from .executor import Executor, TaskFailed
from .motion import MotionFault, arm_hold
from .sequencer import StepFailed, StopRequested


class Skills(dict):
    """mapping step type -> callable(step, ctx); built by make_skills"""


def make_skills(bench, plans, gripper_cfg, park_q, params, extra=None):
    """plans: object with transfer(beaker, src, dst) -> segs. extra: dict of additional skills (pour, dose, carousel)"""
    sk = Skills()

    def scale_mass(n=16):
        return bench.mega.read_mass(n)

    def executor(ctx):
        return Executor(bench.arms, bench.clock, gripper_cfg, park_q, scale=lambda: scale_mass(8), events=ctx.events, on_tick=ctx.tick)

    def transfer(step, ctx):
        p = step.params; segs = plans.transfer(p['beaker'], p['src'], p['dst'])
        ctx.state['active_arm'] = 'transfer'
        try:
            rec = executor(ctx).run('transfer', segs, scale_station='dst' if p['dst'] == 'scale_pan' else 'src', label=step.label)
        except TaskFailed as e:
            raise StepFailed(e.code, e.detail, dict(grasps=e.record.get('grasps')))
        finally:
            ctx.state['active_arm'] = None
        ctx.state['beakers'][p['beaker']] = p['dst']
        measured = dict(grasp_jaw_deg=rec['grasps'][0]['jaw_deg'] if rec['grasps'] else None, scale=rec['scale'])
        if p['dst'] == 'scale_pan':
            m = scale_mass(24); measured['scale_after_g'] = round(m, 3)
            ctx.state['masses']['on_scale'] = m
            content = ctx.state['contents_g'].get(p['beaker'], 0.0)
            if p['beaker'] not in ctx.state['tare_g'] and content == 0.0:
                ctx.state['tare_g'][p['beaker']] = m; measured['beaker_tare_g'] = round(m, 3)
        return dict(measured=measured, detail='grasp %s' % (rec['grasps'][0]['outcome'] if rec['grasps'] else '-'))
    sk['TRANSFER'] = transfer

    def tare_of(ctx, beaker):
        if beaker in ctx.state['tare_g']: return ctx.state['tare_g'][beaker], 'measured'
        ref = ctx.state['tare_g'].get('P1')
        if ref is None: raise StepFailed('NO_TARE', 'no beaker tare measured yet')
        return ref, 'assumed equal to P1 (%.2f g)' % ref

    def verify_mass(step, ctx):
        p = step.params; tare, how = tare_of(ctx, p['beaker'])
        m = scale_mass(32); content = m - tare; err = content - p['target_g']
        ctx.state['contents_g'][p['beaker']] = content
        res = dict(target=dict(content_g=p['target_g'], tol_g=p['tol_g']), measured=dict(scale_g=round(m, 3), tare_g=round(tare, 3), tare=how,
                                                                                       content_g=round(content, 3), error_g=round(err, 3)))
        if abs(err) > p['tol_g']: raise StepFailed('OUT_OF_TOLERANCE', 'content %.2f g vs %.2f +- %.2f' % (content, p['target_g'], p['tol_g']), res['measured'])
        res['detail'] = 'content %.2f g (error %+.2f g)' % (content, err); return res
    sk['VERIFY_MASS'] = verify_mass

    def wait(step, ctx):
        secs = float(step.params['seconds']); t_end = ctx.clock.now() + secs
        w = getattr(bench, 'world', None)
        while ctx.clock.now() < t_end - 1e-9:
            chunk = min(0.5, t_end - ctx.clock.now())
            if w is not None and hasattr(w, 'idle'): w.idle(chunk); bench.mega.heartbeat()     # sim: quiet fast-forward
            else: ctx.clock.sleep(chunk)
            ctx.tick()
        return dict(target=dict(seconds=secs), measured=dict(seconds=secs), detail=step.params.get('reason', ''))
    sk['WAIT'] = wait

    def stage(step, ctx):
        S = params['stage']; deg = S['erupt_deg'] if step.params['position'] == 'ERUPT' else S['work_deg']
        for a in bench.arms.values():
            if a.is_moving(): raise StepFailed('ARM_MOVING', 'the stage may not move while an arm moves')
        r = bench.mega.motion('ST', done_timeout=S['move_s'] + S['timeout_extra_s'], deg=float(deg), ms=int(S['move_s'] * 1000), on_tick=ctx.tick)
        ctx.state['stage'] = step.params['position']
        return dict(target=dict(crank_deg=deg), measured=dict(crank_deg=r.get('deg')), detail='stage at %s' % step.params['position'])
    sk['STAGE'] = stage

    for k, v in (extra or {}).items(): sk[k] = v
    return sk


def safe_stop(bench, park_q):
    """safe-stop path for any backend: untilt a pouring arm if the pour skill left an untilt action, then hold every
    arm where it is with torque on. Grippers are not commanded (a held beaker stays held)."""
    def fn(ctx, reason):
        untilt = ctx.state.get('pouring')
        if untilt is not None:
            try: untilt(); ctx.log('safe_stop_untilt', ok=True)
            except Exception as e: ctx.log('safe_stop_untilt', ok=False, error=repr(e))
            ctx.state['pouring'] = None
        for name, a in bench.arms.items():
            arm_hold(a)
            ctx.log('safe_stop_hold', arm=name, torque=a.torque_enabled(), jaw_deg=round(math.degrees(a.read_positions()[5]), 2))
    return fn
