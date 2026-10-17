"""Deterministic safety gate for LLM-proposed plans (docs/plan_36h.md, docs/pitch.md).

Plain code, no AI.  Rejects unknown operations and fields, unknown reagents, amounts outside
the bench limits (peroxide <= 45 g, yeast <= 10 g, water <= 60 g, waits <= 10 min), impossible
states (pouring from a beaker that is not on the scale, transferring a beaker that is not where
the plan says it is, dosing powder into a beaker that is not at the auger), and plans that
would exceed the flask's safe charge.  The operator still approves the plan before anything moves.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from bench.config import Config, load
from .vocab import BEAKERS, Plan, REAGENTS, STEP_SPECS, Step


@dataclass
class Verdict:
    ok: bool
    problems: list[str] = field(default_factory=list)
    summary: str = ""


class Validator:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or load()
        r = self.cfg.at("recipe")
        self.limits = {"developer": float(r["developer_max_g"]), "water": 60.0,
                       "yeast": float(r["yeast_max_g"]), "wait_s": 600.0}

    def check(self, plan: Plan) -> Verdict:
        problems: list[str] = []
        # bench state model: where each beaker is, what it holds, what is in the flask
        where = {"P1": "carousel_pick", "P2": "carousel_pick"}
        contents = {"P1": {}, "P2": {}}
        flask: dict[str, float] = {}
        carousel_at_pick = {"P1"}              # which beaker sits in the pick pocket now
        auger_beaker = "P2"
        totals = {"developer": 0.0, "water": 0.0, "yeast": 0.0}
        for i, st in enumerate(plan.steps, 1):
            tag = f"step {i} {st}"
            spec = STEP_SPECS.get(st.op)
            if spec is None:
                problems.append(f"{tag}: unknown operation"); continue
            extra = set(st.args) - set(spec)
            missing = set(spec) - set(st.args)
            if extra or missing:
                problems.append(f"{tag}: fields mismatch (extra {sorted(extra)}, missing {sorted(missing)})"); continue
            try:
                for k, typ in spec.items():
                    st.args[k] = typ(st.args[k])
            except (TypeError, ValueError):
                problems.append(f"{tag}: bad field types"); continue

            on_scale = [b for b, w in where.items() if w == "scale"]
            if st.op == "transfer":
                b, s, d = st.args["beaker"], st.args["src"], st.args["dst"]
                if b not in BEAKERS: problems.append(f"{tag}: unknown beaker"); continue
                if s not in ("carousel_pick", "scale") or d not in ("carousel_pick", "scale") or s == d:
                    problems.append(f"{tag}: transfers are carousel_pick <-> scale only"); continue
                if where[b] != s:
                    problems.append(f"{tag}: {b} is at {where[b]}, not {s}"); continue
                if d == "scale" and on_scale:
                    problems.append(f"{tag}: the scale already holds {on_scale[0]}"); continue
                if s == "carousel_pick" and b not in carousel_at_pick:
                    problems.append(f"{tag}: {b} is not in the pick pocket (carousel must index first)"); continue
                where[b] = d
                if d == "carousel_pick":
                    carousel_at_pick = {b}
            elif st.op == "dose_liquid":
                rg, g = st.args["reagent"], st.args["grams"]
                if rg not in ("developer", "water"):
                    problems.append(f"{tag}: unknown reagent {rg!r} (known: {list(REAGENTS)})"); continue
                if not (1.0 <= g <= self.limits[rg]):
                    problems.append(f"{tag}: {g} g of {rg} outside 1..{self.limits[rg]} g"); continue
                if not on_scale:
                    problems.append(f"{tag}: no beaker on the scale to pour into"); continue
                totals[rg] += g
                contents[on_scale[0]][rg] = contents[on_scale[0]].get(rg, 0) + g
            elif st.op == "dose_powder":
                g = st.args["grams"]
                if not (0.5 <= g <= self.limits["yeast"]):
                    problems.append(f"{tag}: {g} g yeast outside 0.5..{self.limits['yeast']} g"); continue
                if where[auger_beaker] != "carousel_pick":
                    problems.append(f"{tag}: {auger_beaker} must be back in the carousel to be dosed"); continue
                totals["yeast"] += g
                contents[auger_beaker]["yeast"] = contents[auger_beaker].get("yeast", 0) + g
                carousel_at_pick = {auger_beaker}   # the dose cycle ends with P2 at the pick pocket
            elif st.op == "pour_into_funnel":
                b = st.args["beaker"]
                if b not in BEAKERS: problems.append(f"{tag}: unknown beaker"); continue
                if where[b] != "scale":
                    problems.append(f"{tag}: {b} must be on the scale (the pourer picks it there)"); continue
                for k, v in contents[b].items():
                    flask[k] = flask.get(k, 0) + v
                contents[b] = {}
            elif st.op == "wait":
                if not (0 < st.args["seconds"] <= self.limits["wait_s"]):
                    problems.append(f"{tag}: wait outside 0..{self.limits['wait_s']} s")
            elif st.op == "run_stage":
                if i != len(plan.steps):
                    problems.append(f"{tag}: run_stage must be the last step")
                if any(w == "scale" for w in where.values()):
                    pass  # allowed, but the pourer must be parked - the sequencer enforces it
        if totals["developer"] > self.limits["developer"]:
            problems.append(f"total peroxide {totals['developer']} g exceeds {self.limits['developer']} g")
        if flask.get("developer", 0) > 0 and flask.get("yeast", 0) == 0 and totals["yeast"] > 0 \
                and any(s.op == "run_stage" for s in plan.steps):
            problems.append("the catalyst never reaches the flask before run_stage")
        summary = (f"{len(plan.steps)} steps; totals developer {totals['developer']:.1f} g, "
                   f"yeast {totals['yeast']:.1f} g, water {totals['water']:.1f} g; "
                   f"flask ends with {', '.join(f'{k} {v:.1f} g' for k, v in flask.items()) or 'nothing'}")
        return Verdict(not problems, problems, summary)
