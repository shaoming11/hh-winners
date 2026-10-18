import mujoco

from benchsim.backends.sim import SimWorld
from benchsim.chem.vessels import Ledger
from benchsim.process import steps


def test_demo_protocol_validates():
    ok, problems = steps.validate(steps.demo_protocol())
    assert ok, problems


def test_flask_demo_protocol_validates():
    demo = steps.flask_demo_protocol()
    ok, problems = steps.validate(demo)
    assert ok, problems
    assert [s.type for s in demo] == ['TRANSFER', 'POUR_TO_SCALE', 'POUR_TO_FUNNEL'] and demo[-1].params['erupt'] is True
    assert not {'DOSE_YEAST', 'VERIFY_MASS', 'WAIT'} & {s.type for s in demo}


def test_validator_rejects_bad_orders():
    bad = steps.demo_protocol(); bad.insert(0, steps.Step('STAGE', dict(position='ERUPT')))
    ok, problems = steps.validate(bad)
    assert not ok and any('ERUPT' in p for p in problems)
    bad = steps.demo_protocol(); bad[1].params['target_g'] = 500
    assert not steps.validate(bad)[0]


def test_erupt_rides_on_the_reaction_pour():
    demo = steps.demo_protocol()
    er = [s.params['erupt'] for s in demo if s.type == 'POUR_TO_FUNNEL']
    assert er[-1] and not any(er[:-1]) and 'STAGE' not in [s.type for s in demo]     # only the last funnel pour erupts
    late = demo + [steps.Step('WAIT', dict(seconds=5))]                     # the stage is at ERUPT after the reaction pour
    ok, problems = steps.validate(late)
    assert not ok and any('after ERUPT' in p for p in problems)
    empty = [steps.Step('TRANSFER', dict(beaker='P1', src='carousel_pick', dst='scale_pan')),
             steps.Step('POUR_TO_FUNNEL', dict(beaker='P1', erupt=True))]
    ok, problems = steps.validate(empty)
    assert not ok and any('nothing poured' in p for p in problems)


def test_ledger_weight_reaches_scale():
    w = SimWorld(); L = Ledger(w)
    L.add('dev', 'developer', 50.0)
    w.advance(0.3)
    fz = w.d.xfrc_applied[w.m.body('beaker_dev').id, 2]
    assert abs(fz + 0.050 * 9.81) < 1e-9
    taken = L.take('dev', 10.0)
    assert abs(taken['developer'] - 10.0) < 1e-9 and abs(L.mass('dev') - 40.0) < 1e-9
