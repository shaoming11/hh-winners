"""Protocol text -> step plan, via the Claude API (docs/plan_36h.md "The AI layer").

The model only proposes a step list in the fixed vocabulary; nothing moves until the
deterministic Validator passes it and the operator approves.  If the API is unreachable (no
key, no Wi-Fi) the preset plan is returned instead, flagged as such.
"""
from __future__ import annotations

import json
import os
import re

from .vocab import Plan, Step, SYSTEM_PROMPT, preset_elephant_toothpaste

MODEL = "claude-sonnet-5"


def plan_from_text(text: str, model: str = MODEL, timeout_s: float = 30.0) -> Plan:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        p = preset_elephant_toothpaste()
        p.notes = "ANTHROPIC_API_KEY not set - using the preset plan"
        return p
    try:
        import anthropic
        client = anthropic.Anthropic(timeout=timeout_s)
        msg = client.messages.create(
            model=model, max_tokens=1200, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        raw = "".join(getattr(b, "text", "") for b in msg.content)
        return parse_plan(raw, source="llm")
    except Exception as e:  # noqa: BLE001 - any failure falls back to the preset, visibly
        p = preset_elephant_toothpaste()
        p.notes = f"LLM unavailable ({type(e).__name__}: {e}) - using the preset plan"
        return p


def parse_plan(raw: str, source: str = "llm") -> Plan:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no JSON object in the model reply")
    obj = json.loads(m.group(0))
    steps = []
    for s in obj.get("steps", []):
        s = dict(s)
        op = s.pop("op", None)
        steps.append(Step(str(op), s))
    return Plan(str(obj.get("title", "untitled")), steps, source=source)
