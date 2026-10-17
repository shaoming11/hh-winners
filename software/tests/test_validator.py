from bench.agent.validator import Validator
from bench.agent.vocab import Plan, Step, preset_elephant_toothpaste


def test_preset_plan_passes():
    v = Validator().check(preset_elephant_toothpaste())
    assert v.ok, v.problems


def test_rejects_too_much_peroxide():
    p = preset_elephant_toothpaste(developer_g=50.0)
    v = Validator().check(p)
    assert not v.ok and any("developer" in s for s in v.problems)


def test_rejects_unknown_reagent_and_op():
    p = Plan("bad", [Step("transfer", {"beaker": "P1", "src": "carousel_pick", "dst": "scale"}),
                     Step("dose_liquid", {"reagent": "acetone", "grams": 10.0}),
                     Step("teleport", {})])
    v = Validator().check(p)
    assert not v.ok
    assert any("unknown reagent" in s for s in v.problems)
    assert any("unknown operation" in s for s in v.problems)


def test_rejects_impossible_state():
    # pouring onto the scale with nothing on it
    p = Plan("bad", [Step("dose_liquid", {"reagent": "water", "grams": 10.0})])
    v = Validator().check(p)
    assert not v.ok and "no beaker on the scale" in v.problems[0]
    # moving a beaker that is not where the plan says
    p = Plan("bad", [Step("transfer", {"beaker": "P1", "src": "scale", "dst": "carousel_pick"})])
    assert not Validator().check(p).ok


def test_run_stage_must_be_last():
    p = Plan("bad", [Step("run_stage", {}), Step("wait", {"seconds": 5})])
    assert any("last step" in s for s in Validator().check(p).problems)
