"""The deterministic plan gate: `benchsim.process.steps.validate`.

This is the ONLY gate in front of anything the backend or the agent starts - `/api/plan/validate`,
the `validate_plan` MCP tool and `start_run` all go through it.  It is stateful: it tracks where each
beaker is and what it holds, so it rejects impossible orderings, not just out-of-range numbers.

(The older `bench.agent.validator`, used by the retired standalone `scripts/run_demo.py --protocol`
path, was tested here until `bench/` was removed.)
"""
from benchsim.process import steps
from benchsim.process.steps import Step


def test_preset_plan_passes():
    ok, problems = steps.validate(steps.demo_protocol())
    assert ok, problems


def test_rejects_too_much_developer():
    """over the pourer's per-pour ceiling - the quantity guard the agent's recipes hit first"""
    ok, problems = steps.validate(steps.demo_protocol({**_recipe(), "developer_g": 80.0}))
    assert not ok
    assert any("outside 1..60" in s for s in problems), problems


def test_rejects_unknown_step_type_and_reagent():
    ok, problems = steps.validate([Step("TELEPORT", {}),
                                   Step("TRANSFER", dict(beaker="P1", src="carousel_pick", dst="scale_pan")),
                                   Step("POUR_TO_SCALE", dict(reagent="acetone", beaker="P1", target_g=10.0, tol_g=1.0))])
    assert not ok
    assert any("unknown step type" in s for s in problems), problems
    assert any("unknown reagent" in s for s in problems), problems


def test_rejects_missing_params():
    ok, problems = steps.validate([Step("TRANSFER", dict(beaker="P1"))])
    assert not ok and any("missing src, dst" in s for s in problems), problems


def test_rejects_pour_with_nothing_on_the_scale():
    ok, problems = steps.validate([Step("POUR_TO_SCALE", dict(reagent="water", beaker="P1", target_g=10.0, tol_g=1.0))])
    assert not ok and any("P1 is not on the scale" in s for s in problems), problems


def test_rejects_moving_a_beaker_that_is_elsewhere():
    """P1 starts in the pick pocket, so it cannot be lifted off the scale first"""
    ok, problems = steps.validate([Step("TRANSFER", dict(beaker="P1", src="scale_pan", dst="carousel_pick"))])
    assert not ok and any("P1 is at carousel_pick, not scale_pan" in s for s in problems), problems


def test_rejects_two_beakers_on_the_scale():
    ok, problems = steps.validate([Step("TRANSFER", dict(beaker="P1", src="carousel_pick", dst="scale_pan")),
                                   Step("TRANSFER", dict(beaker="P2", src="carousel_pick", dst="scale_pan"))])
    assert not ok
    assert any("is at carousel_aux, not carousel_pick" in s or "scale occupied by P1" in s for s in problems), problems


def test_rejects_yeast_over_the_auger_limit():
    ok, problems = steps.validate([Step("DOSE_YEAST", dict(beaker="P2", target_g=20.0, tol_g=0.7))])
    assert not ok and any("yeast 20.0 g outside 0.5..12" in s for s in problems), problems


def test_rejects_tolerance_below_the_scale_floor():
    ok, problems = steps.validate([Step("TRANSFER", dict(beaker="P1", src="carousel_pick", dst="scale_pan")),
                                   Step("POUR_TO_SCALE", dict(reagent="developer", beaker="P1", target_g=39.0, tol_g=0.1))])
    assert not ok and any("tolerance below 0.5 g" in s for s in problems), problems


def test_rejects_erupt_before_anything_is_poured():
    ok, problems = steps.validate([Step("STAGE", dict(position="ERUPT"))])
    assert not ok and any("ERUPT with nothing poured" in s for s in problems), problems


def test_rejects_work_after_erupt():
    """once the stage has run, only putting a beaker back is allowed"""
    plan = steps.demo_protocol() + [Step("WAIT", dict(seconds=5.0, reason="after"))]
    ok, problems = steps.validate(plan)
    assert not ok and any("only returning a beaker to the carousel may run after ERUPT" in s for s in problems), problems


def test_rejects_wait_longer_than_the_run_window():
    ok, problems = steps.validate([Step("WAIT", dict(seconds=10_000.0))])
    assert not ok and any("wait outside 0..600 s" in s for s in problems), problems


def test_rejects_water_onto_yeast_poured_absolute():
    """relative=False would wash out the yeast already weighed into the beaker"""
    plan = [Step("DOSE_YEAST", dict(beaker="P2", target_g=7.0, tol_g=0.7)),
            Step("TRANSFER", dict(beaker="P2", src="carousel_pick", dst="scale_pan")),
            Step("POUR_TO_SCALE", dict(reagent="water", beaker="P2", target_g=30.0, tol_g=2.0, relative=False))]
    ok, problems = steps.validate(plan)
    assert not ok and any("relative to the yeast mass" in s for s in problems), problems


def _recipe():
    return dict(developer_g=39.0, developer_tol_g=2.0, yeast_g=7.0, yeast_tol_g=0.7,
                water_g=30.0, water_tol_g=2.0, activate_wait_s=60.0)
