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
    "safe_stop": "The bench stopped safely: the arms are holding what they held, grippers closed.",
    "complete": "The last run finished.",
    "error": "The backend hit an error; the bench needs a human.",
}

# Reagent keys -> what a person calls them.  The dose keys come from the recipe (developer_g, ...);
# "developer" is the trade name for the 12 % peroxide and means nothing to anyone else.
REAGENT_WORDS = {"developer": "peroxide", "developer_g": "peroxide", "yeast": "yeast", "yeast_g": "yeast",
                 "water": "water", "water_g": "warm water", "foam_peak_mm": "foam peak"}


def reagent_word(key: str) -> str:
    return REAGENT_WORDS.get(key, key.replace("_g", "").replace("_", " "))


def _title(step) -> str:
    """the dashboard caption's wording for a step (benchsim narration), else the terse name"""
    n = getattr(step, "narration", None)
    return (n or {}).get("title") or step.name


def _titles(store: Store) -> dict[str, str]:
    run = store.state.run
    return {st.name: _title(st) for st in run.steps} if run else {}


def _dose_words(doses: dict) -> list[str]:
    """what went in, as a person would say it: '19.3 g of peroxide (0.7 g under the 20 g target)'"""
    out = []
    for k, d in doses.items():
        if isinstance(d, Dose) and d.actual is not None:
            if d.error is None or abs(d.error) < 0.05:
                out.append(f"{d.actual:.1f} g of {reagent_word(k)}")
            else:
                off = "over" if d.error > 0 else "under"
                out.append(f"{d.actual:.1f} g of {reagent_word(k)} ({abs(d.error):.1f} g {off} the {d.target:.0f} g target)")
    return out


def _replay_words(r) -> tuple[str, list[str]]:
    """a hardware replay: the planned arm paths played through the hardware code.  It measures (subgoal checks,
    grams on the scale) but never corrects, so say what it found rather than what it achieved."""
    lower = lambda t: t[0].lower() + t[1:] if t else t
    step = r.steps[r.current_step] if r.current_step is not None and r.current_step < len(r.steps) else None
    failed = [(st, sg) for st in r.steps for sg in st.subgoals if sg.status == "failed"]
    warned = [(st, sg) for st in r.steps for sg in st.subgoals if sg.status == "warning"]
    if r.outcome == "running" and step is not None:
        now = r.current_subgoal.split(" / ", 1)[-1] if r.current_subgoal else ""
        head = (f"The hardware replay is on step {r.current_step + 1} of {len(r.steps)}: {lower(_title(step))}"
                + (f", now {now}" if now else "") + ".")
    elif r.outcome == "complete":
        head = (f"The hardware replay played all {len(r.steps)} steps in {r.bench_seconds:.0f} s"
                + (f"; {len(failed)} check{'s' if len(failed) != 1 else ''} failed." if failed else ", every check passed."
                   if not warned else f", with {len(warned)} warning{'s' if len(warned) != 1 else ''}."))
    elif r.outcome == "SAFE_STOP":
        where = _title(step) if step else ""
        head = (f"The hardware replay was stopped" + (f" during {lower(where)}" if where else "")
                + ". The arms are frozen where they were, torque on.")
    else:
        head = f"The hardware replay ended: {r.outcome}."
    detail = [f"{st.name}: {sg.name} failed - {sg.result}." for st, sg in failed[:3]]
    detail += [f"{st.name}: {sg.name} - {sg.result}." for st, sg in warned[:2] if sg.code == "DOSE_ERROR"]
    if len(failed) > 3:
        detail.append(f"({len(failed) - 3} more failed checks in the run.)")
    detail.append("A replay plays fixed arm paths and does not correct anything; the checks only report.")
    return head, detail


def describe(s: ExperimentState, last_event_id: int) -> Describe:
    head = MODE_TEXT.get(s.mode, s.mode)
    detail: list[str] = []
    needs: str | None = None
    r = s.run
    if r is not None and r.kind == "hw_replay":
        head, detail = _replay_words(r)
        r = None                                      # the sequencer wording below does not apply
    if r is not None:
        step =_title(r.steps[r.current_step]) if r.current_step is not None and r.current_step < len(r.steps) else None
        lower = lambda t: t[0].lower() + t[1:] if t else t
        if r.outcome == "running" and step:
            head = f"The run is {int(r.progress * 100)}% through; right now it is {lower(step)}."
        elif r.outcome == "complete":
            head = f"The run finished, {r.bench_seconds:.0f} s of bench time from start to eruption."
        elif r.outcome == "SAFE_STOP":
            where = next((_title(st) for st in r.steps if st.status in ("fault", "error")), step)
            why = r.faults[-1] if r.faults else ""
            head = (f"The run stopped safely while {lower(where) if where else 'it was running'}"
                    + (f" - {why}" if why else "") + ". The arms are holding what they held, grippers closed.")
        dw = _dose_words(r.doses)
        if dw:
            detail.append(("In so far: " if r.outcome == "running" else "What went in: ") + ", ".join(dw) + ".")
        if s.chemistry and s.chemistry.foam_h_mm > 0:
            detail.append(f"The foam is {s.chemistry.foam_h_mm:.0f} mm up the flask.")
        if r.outcome == "running" and r.recipe is not None:
            who = (f", {r.requested_by}'s request, approved by {r.operator}" if r.requested_by and r.requested_by != r.operator
                   else (f", approved by {r.operator}" if r.operator else ""))
            detail.append(f"It is making {r.recipe.developer_g:.0f} g peroxide, {r.recipe.yeast_g:.0f} g yeast "
                          f"and {r.recipe.water_g:.0f} g warm water{who}.")
    if s.mega.estop:
        needs = "The e-stop is pressed; release it and clear the fault before anything can move."
    elif s.mega.fault:
        needs = f"The Mega has a latched {s.mega.fault} fault; fix the cause, then clear it."
    elif s.pending_approvals:
        p = s.pending_approvals[0]
        who = f"{p.requested_by_person} asked for" if p.requested_by_person else "Waiting on"
        needs = (f"{who} \"{p.summary.split(' - ')[0]}\" and it needs an operator's go-ahead"
                 + (f" before {p.expires_at[11:16]} UTC" if p.expires_at else "") + f" (request {p.id}).")
    elif s.alerts:
        crit = [a for a in s.alerts if a.severity == "critical"]
        if crit:
            needs = f"Something needs a person: {crit[0].message}"
    if s.mode == "idle" and not detail and s.history:
        h = s.history[0]
        dw = _dose_words(h.doses)
        outcome = {"complete": "finished cleanly", "SAFE_STOP": "was stopped partway"}.get(h.outcome, h.outcome)
        detail.append(f"The last run {outcome}" + (f": {', '.join(dw)}" if dw else "") + ".")
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
