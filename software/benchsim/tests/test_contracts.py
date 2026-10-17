import mujoco

from benchsim.backends.sim import SimWorld
from benchsim.chem.vessels import Ledger
from benchsim.process import steps


def test_demo_protocol_validates():
    ok, problems = steps.validate(steps.demo_protocol())
    assert ok, problems


def test_validator_rejects_bad_orders():
    bad = steps.demo_protocol(); bad.insert(0, steps.Step('STAGE', dict(position='ERUPT')))
    ok, problems = steps.validate(bad)
    assert not ok and any('ERUPT' in p for p in problems)
    bad = steps.demo_protocol(); bad[1].params['target_g'] = 500
    assert not steps.validate(bad)[0]


def test_ledger_weight_reaches_scale():
    w = SimWorld(); L = Ledger(w)
    L.add('dev', 'developer', 50.0)
    w.advance(0.3)
    fz = w.d.xfrc_applied[w.m.body('beaker_dev').id, 2]
    assert abs(fz + 0.050 * 9.81) < 1e-9
    taken = L.take('dev', 10.0)
    assert abs(taken['developer'] - 10.0) < 1e-9 and abs(L.mass('dev') - 40.0) < 1e-9
