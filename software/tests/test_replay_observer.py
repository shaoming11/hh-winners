"""The replay's step meaning and subgoals are derived from the route file, never hand-written: this fails if a route
change (native_plans.json, replay_plan.bench_segments, pose overrides) breaks the derivation."""
import importlib.util
import sys
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOFTWARE / "benchsim"))

from backend.replay_observer import ReplayModel  # noqa: E402


def _rp():
    spec = importlib.util.spec_from_file_location("replay_plan_t", SOFTWARE / "benchsim" / "scripts" / "replay_plan.py")
    rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)
    return rp


def test_every_route_step_gets_a_meaning_and_subgoals():
    from benchsim.layout import load_params
    rp = _rp(); plans = rp.load_plans(); keys = list(plans)
    m = ReplayModel(rp, plans, keys, load_params())
    for row in m.rows():
        assert row.type in ("TRANSFER", "POUR_TO_SCALE", "POUR_TO_FUNNEL"), row.name
        names = [s.name for s in row.subgoals]
        assert any(n.startswith("grip ") for n in names) and any(n.startswith("set ") for n in names), (row.name, names)
        assert sum(len(g["segs"]) for g in m.groups[row.name]) == len(m._played(row.name))
        if row.type == "POUR_TO_SCALE":
            pour = next(s for s in row.subgoals if s.name.startswith("pour "))
            assert "g on the scale" in pour.expect
