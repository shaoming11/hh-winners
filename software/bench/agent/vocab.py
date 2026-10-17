"""The bench's step vocabulary (docs/plan_36h.md "The AI layer").

The LLM may only emit these steps; the validator checks every one against the bench's
capabilities; the sequencer executes them.  Nothing here invents motions - each step maps to
pre-planned, collision-checked primitives.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

REAGENTS = {"developer": "12 % H2O2 (40-volume clear developer), rack pocket 1",
            "water": "warm water, rack pocket 3",
            "soap": "dish soap + dye, pre-loaded in the flask by hand"}
STATIONS = ("carousel_pick", "scale", "funnel", "rack_developer", "rack_water")
BEAKERS = ("P1", "P2")

STEP_SPECS = {
    "dose_liquid":     {"reagent": str, "grams": float},
    "dose_powder":     {"grams": float},
    "transfer":        {"beaker": str, "src": str, "dst": str},
    "pour_into_funnel": {"beaker": str},
    "carousel_to":     {"pocket": str},
    "wait":            {"seconds": float},
    "run_stage":       {},
}


@dataclass
class Step:
    op: str
    args: dict = field(default_factory=dict)

    def __str__(self) -> str:
        a = ", ".join(f"{k}={v}" for k, v in self.args.items())
        return f"{self.op}({a})"


@dataclass
class Plan:
    title: str
    steps: list[Step]
    source: Literal["llm", "preset", "manual"] = "preset"
    notes: str = ""


SYSTEM_PROMPT = """You convert a chemistry protocol written in plain English into a JSON list of
steps for a small robotic bench. The bench has: two 100 mL beakers P1 and P2 on a carousel, a
scale, a yeast auger that doses into the beaker under it, a reagent rack holding a "developer"
beaker (12 % hydrogen peroxide) and a "water" beaker, and a funnel into a flask on a stage.
Only these operations exist, with exactly these fields:

  {"op":"dose_liquid","reagent":"developer"|"water","grams":<number>}   pour onto the beaker on the scale, by weight
  {"op":"dose_powder","grams":<number>}                                  auger yeast into the carousel beaker, verified on the scale
  {"op":"transfer","beaker":"P1"|"P2","src":<station>,"dst":<station>}   stations: carousel_pick, scale
  {"op":"pour_into_funnel","beaker":"P1"|"P2"}                            empty that beaker into the flask
  {"op":"wait","seconds":<number>}
  {"op":"run_stage"}                                                      move the flask to the audience

Reply with ONLY a JSON object: {"title": str, "steps": [ ... ]}. Use the fewest steps that
achieve the protocol. The standard elephant-toothpaste run is: transfer P1 carousel_pick->scale,
dose_liquid developer, pour_into_funnel P1, transfer P1 scale->carousel_pick, dose_powder,
transfer P2 carousel_pick->scale, dose_liquid water, wait 60, pour_into_funnel P2,
transfer P2 scale->carousel_pick, run_stage."""


def preset_elephant_toothpaste(developer_g=39.0, yeast_g=7.0, water_g=30.0, activate_s=60.0) -> Plan:
    return Plan("Elephant toothpaste (preset)", [
        Step("transfer", {"beaker": "P1", "src": "carousel_pick", "dst": "scale"}),
        Step("dose_liquid", {"reagent": "developer", "grams": developer_g}),
        Step("pour_into_funnel", {"beaker": "P1"}),
        Step("transfer", {"beaker": "P1", "src": "scale", "dst": "carousel_pick"}),
        Step("dose_powder", {"grams": yeast_g}),
        Step("transfer", {"beaker": "P2", "src": "carousel_pick", "dst": "scale"}),
        Step("dose_liquid", {"reagent": "water", "grams": water_g}),
        Step("wait", {"seconds": activate_s}),
        Step("pour_into_funnel", {"beaker": "P2"}),
        Step("transfer", {"beaker": "P2", "src": "scale", "dst": "carousel_pick"}),
        Step("run_stage", {}),
    ], source="preset")
