"""Prose-ready facts for chat and the frontend status line, computed server-side so every surface
says the same thing: `describe()` (two or three sentences) and `delta()` (what changed since an
event id).  No AI here; the agent narrates on top of this instead of re-reading a 1 KB snapshot."""
from __future__ import annotations

from backend.schemas import Alert, ApprovalRequest, Delta, Describe, Dose, ExperimentState
from backend.store import Store

MODE_TEXT = {
    "disconnected": "The bench is not connected.",
    "idle": "The bench is idle; nothing is moving.",
    "planning": "A plan is being prepared.",
    "awaiting_approval": "The bench is idle, waiting for an operator to approve a run.",
    "running": "A run is in progress.",
    "paused": "The run is paused; the arms are holding position.",
    "safe_stop": "The bench safe-stopped: arms holding, grippers closed, servos off.",
    "complete": "The last run finished.",
    "error": "The backend hit an error; the bench needs a human.",
}


def _title(step) -> str:
    """the dashboard caption's wording for a step (benchsim narration), else the terse name"""
    n = getattr(step, "narration", None)
    return (n or {}).get("title") or step.name


def _titles(store: Store) -> dict[str, str]:
    run = store.state.run
    return {st.name: _title(st) for st in run.steps} if run else {}


def _dose_words(doses: dict) -> list[str]:
    out = []
    for k, d in doses.items():
        if isinstance(d, Dose) and d.actual is not None:
            err = f" ({d.error:+.2f})" if d.error is not None else ""
            out.append(f"{k} {d.actual:.2f} g of {d.target:.0f}{err}")
    return out


def describe(s: ExperimentState, last_event_id: int) -> Describe:
    head = MODE_TEXT.get(s.mode, s.mode)
    detail: list[str] = []
    needs: str | None = None
    r = s.run
    if r is not None:
        step = _title(r.steps[r.current_step]) if r.current_step is not None and r.current_step < len(r.steps) else None
        if r.outcome == "running" and step:
            head = f"Run {r.run_id} is {int(r.progress * 100)}% through: {step[0].lower() + step[1:]}."
        elif r.outcome == "complete":
            head = f"Run {r.run_id} finished after {r.bench_seconds:.0f} s of bench time."
        elif r.outcome == "SAFE_STOP":
            where = next((_title(st) for st in r.steps if st.status in ("fault", "error")), step)
            head = f"Run {r.run_id} safe-stopped while {where[0].lower() + where[1:] if where else 'running'}: {r.faults[-1] if r.faults else 'no detail'}. Arms holding, grippers closed."
        dw = _dose_words(r.doses)
        if dw:
            detail.append("Doses so far: " + ", ".join(dw) + ".")
        if s.chemistry and s.chemistry.foam_h_mm > 0:
            detail.append(f"Foam column {s.chemistry.foam_h_mm:.0f} mm.")
        who = f" (requested by {r.requested_by}, approved by {r.operator})" if r.requested_by and r.requested_by != r.operator else (f" (operator {r.operator})" if r.operator else "")
        if who and r.outcome == "running":
            detail.append(f"Recipe {r.recipe.developer_g:.0f} g developer, {r.recipe.yeast_g:.0f} g yeast, {r.recipe.water_g:.0f} g water{who}.")
    if s.mega.estop:
        needs = "The e-stop is pressed; release it and clear the fault before anything can move."
    elif s.mega.fault:
        needs = f"The Mega has a latched {s.mega.fault} fault; fix the cause, then clear it."
    elif s.pending_approvals:
        p = s.pending_approvals[0]
        who = f"{p.requested_by_person} asked for" if p.requested_by_person else "Waiting on"
        needs = f"{who} \"{p.summary.split(' - ')[0]}\"; an operator has to approve (id {p.id})" + (f", expires {p.expires_at[11:16]} UTC." if p.expires_at else ".")
    elif s.alerts:
        crit = [a for a in s.alerts if a.severity == "critical"]
        if crit:
            needs = f"Open critical alert: {crit[0].code.lower().replace('_', ' ')} - {crit[0].message}."
    if s.mode == "idle" and not detail and s.history:
        h = s.history[0]
        dw = _dose_words(h.doses)
        detail.append(f"Last run {h.run_id} {h.outcome}" + (f": {', '.join(dw)}" if dw else "") + ".")
    return Describe(headline=head, detail=" ".join(detail), needs_human=needs, last_event_id=last_event_id)


def delta(store: Store, since: int) -> Delta:
    evs = store.events_since(since, limit=1000)
    d = Delta(since=since, last_event_id=evs[-1].id if evs else since)
    titles = _titles(store)
    for e in evs:
        if e.kind == "step" and e.message.endswith(": ok"):
            name = e.message[: -len(": ok")]
            d.steps_completed.append(name)
            d.changes.append(f"done: {titles.get(name, name)}")
        elif e.kind == "step" and e.message.endswith(": start"):
            name = e.message[: -len(": start")]
            d.changes.append(f"now: {titles.get(name, name)}")
        elif e.kind == "alert":
            aid = e.data.get("alert_id")
            a = store.alerts.get(aid) if aid else None
            if a and "acknowledged" not in e.message:
                d.alerts_opened.append(a)
                d.changes.append(f"alert {a.severity} {a.code.lower().replace('_', ' ')}: {a.message}")
        elif e.kind == "approval":
            rid = e.data.get("request_id")
            r = store.approvals.get(rid) if rid else None
            if r and r not in d.approvals:
                d.approvals.append(r)
            d.changes.append(e.message)
        elif e.kind == "state" and " run " in e.message and ("complete" in e.message or "SAFE_STOP" in e.message):
            d.run_outcome = "complete" if "complete" in e.message else "SAFE_STOP"
            d.changes.append(e.message)
        elif e.kind == "message":
            d.messages.append(e)
        elif e.kind == "command" and e.source != "sequencer":
            d.changes.append(e.message)
    run = store.state.run
    if run is not None:
        for k, v in run.doses.items():
            if isinstance(v, Dose) and v.actual is not None and any(k in c for c in d.changes) is False:
                # a dose that landed in the window shows up as a finished pour step; attach the number
                if any(k.split("_")[0] in c for c in d.changes):
                    d.doses[k] = v
    resolved = [a.code for a in store.alerts.values() if a.resolved and any(e.data.get("alert_id") == a.id for e in evs)]
    d.alerts_resolved = sorted(set(resolved))
    d.nothing_new = not d.changes and not d.messages
    return d
