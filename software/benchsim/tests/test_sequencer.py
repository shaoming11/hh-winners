import tempfile
from pathlib import Path

from benchsim import poses, runlog, state
from benchsim.bench import make_bench
from benchsim.layout import load_params
from benchsim.process import sequencer, skills
from benchsim.process import steps as S

PROTO = [S.Step('TRANSFER', dict(beaker='P1', src='carousel_pick', dst='scale_pan'), 'P1 to scale'),
         S.Step('VERIFY_MASS', dict(beaker='P1', target_g=0.0, tol_g=0.5), 'P1 empty'),
         S.Step('TRANSFER', dict(beaker='P1', src='scale_pan', dst='carousel_pick'), 'P1 back')]


def build():
    params = load_params(); bb = make_bench('sim'); P = poses.Planner(bb.world.m, bb.world.b)

    class Plans:
        def transfer(self, b, s, d): return P.plan_transfer(b, s, d)
    sk = skills.make_skills(bb, Plans(), params['gripper'], state.park_q(), params)

    def pre(ctx): bb.mega.command('STREAM', on=True); bb.mega.command('TARE')
    rl = runlog.RunLog(Path(tempfile.mkdtemp()), 'sim')
    return bb, sequencer.Sequencer(bb, sk, rl, safe_stop=skills.safe_stop(bb, state.park_q()), precheck=pre)


def test_transfer_verify_transfer_runs():
    bb, seq = build(); out = seq.run(PROTO)
    assert out['state'] == 'DONE' and out['passed'] == 3
    assert abs(out['steps'][0]['measured']['beaker_tare_g'] - 18.0) < 0.5


def test_stop_during_carry_keeps_beaker_and_torque():
    bb, seq = build(); w = bb.world; fired = {}

    def hook():
        if not fired and w.held.get('transfer') and w.beaker_pose('P1')[0][2] > 75:
            seq.ctx.request_stop('operator stop (test)'); fired['t'] = w.time
    seq.ctx.on_tick_hooks.append(hook)
    out = seq.run(PROTO)
    assert out['state'] == 'SAFE_STOP' and [r['status'] for r in out['steps']] == ['failed', 'skipped', 'skipped']
    bb.clock.sleep(1.0)
    assert w.held.get('transfer') == 'P1' and all(a.torque_enabled() for a in bb.arms.values())


def test_invalid_protocol_is_not_run():
    bb, seq = build(); out = seq.run([S.Step('STAGE', dict(position='ERUPT'))])
    assert out['state'] == 'FAILED' and out['steps'][0]['status'] == 'skipped'
