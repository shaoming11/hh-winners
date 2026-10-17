"""Project one benchsim run into the backend's contracts.

There is one bench and one source of truth: the `benchsim.feed/1` snapshot that `benchsim.dashboard.feed.Feed`
already builds for the dashboard.  This module turns that same snapshot into the `ExperimentState` pieces the
agents, the MCP tools and the QA watchdog read, so the two views can never drift - the dashboard and the agent
are looking at the same numbers from the same poll.

    parts = project(snap, bench, ledger)        # -> ProjectedParts (arms, mega, scale, vessels, chemistry, bench_t)

What comes from where: arms, scale, vessels, spill and the foam model come out of the feed snapshot; the Mega's
mechanism positions (carousel, stage, auger) are read off the simulated device, which the feed does not carry
because the wire panel shows them as protocol lines instead.  Nothing here raises: a field the sim has not filled
yet becomes None, because this runs inside a physics hook.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.schemas import (JOINTS, ArmState, ChemistryState, MegaState, ScaleState, VesselState)

# benchsim's Sequencer states -> the backend's Mode vocabulary.  PRECHECK is "running": something is moving.
SEQ_TO_MODE = {"IDLE": "idle", "PRECHECK": "running", "RUNNING": "running",
               "DONE": "complete", "SAFE_STOP": "safe_stop", "FAILED": "error"}

# benchsim's per-step status -> StepState.status
STEP_STATUS = {"pending": "pending", "running": "running", "passed": "ok",
               "failed": "fault", "skipped": "skipped"}


@dataclass
class ProjectedParts:
    arms: dict
    mega: MegaState
    scale: ScaleState
    vessels: dict
    chemistry: ChemistryState | None
    bench_t: float


def _num(x, nd: int | None = None):
    """float or None; never raises, never lets a NaN through (FastAPI's json.dumps would)"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return round(v, nd) if nd is not None else v


def _joints(values) -> dict[str, float]:
    """benchsim's 6-vector (already degrees in a feed snapshot) -> {joint: deg}"""
    if not values:
        return {}
    return {j: (_num(v, 2) or 0.0) for j, v in zip(JOINTS, values)}


def arms_from(snap: dict) -> dict[str, ArmState]:
    out = {}
    for role, a in (snap.get("arms") or {}).items():
        out[role] = ArmState(
            role=role,
            q_deg=_joints(a.get("q_deg")),
            load=_joints(a.get("load_pm")),
            torque_on=bool(a.get("torque", True)),
            holding=a.get("holding"),
            moving=bool(a.get("moving", False)),
            goal_deg=_joints(a.get("goal_deg")) or None,
            twin=a.get("twin"),
        )
    return out


def mega_from(snap: dict, bench) -> MegaState:
    """mechanism positions off the simulated device; faults and the sample stream off the client"""
    dev = getattr(bench, "mega_device", None)
    w = getattr(bench, "world", None)
    faults = (snap.get("faults") or [])
    latched = None
    if faults:
        last = faults[-1]
        latched = last.get("fault") if isinstance(last, dict) else str(last)
    stage_deg = _num(dev.st_deg(), 1) if dev is not None else None
    return MegaState(
        connected=True,
        fw="WLB-MEGA (benchsim)",
        hx_hz=_num((snap.get("scale") or {}).get("rate_hz")),
        estop=bool(getattr(w, "estop", False)) if w is not None else False,
        fault=latched,
        carousel_deg=_num(dev.tt_deg(), 1) or 0.0 if dev is not None else 0.0,
        stage_deg=stage_deg or 0.0,
        stage_position=None if stage_deg is None else ("ERUPT" if stage_deg > 140 else ("WORK" if stage_deg < 10 else None)),
        auger_rev=_num(getattr(dev, "aug_angle", 0.0), 2) or 0.0,
        busy=[],
        last_heartbeat_age_s=0.0,
    )


def scale_from(snap: dict, bench, locations: dict | None = None) -> ScaleState:
    sc = snap.get("scale") or {}
    dev = getattr(bench, "mega_device", None)
    net = _num(sc.get("g"), 2)
    tare = 0.0
    counts = _num(getattr(dev, "counts_per_g", None)) if dev is not None else None
    tare_counts = _num(getattr(dev, "tare_counts", None)) if dev is not None else None
    if counts and tare_counts is not None:            # tare_counts is None until the first TARE
        tare = _num(tare_counts / counts, 2) or 0.0
    return ScaleState(
        gross_g=None if net is None else _num(net + tare, 2),
        tare_g=tare,
        net_g=net,
        streaming=bool(getattr(dev, "streaming", False)) if dev is not None else False,
        beaker_on_pan=_on_pan(locations),
    )


def _on_pan(locations: dict | None):
    """which beaker the process believes is on the pan.  The sequencer's own `ctx.state['beakers']`
    is the authority - the skills move it as they place and pick, so it survives the end of a step."""
    for name, where in (locations or {}).items():
        if where == "scale_pan":
            return name if name in ("P1", "P2") else None
    return None


def vessels_from(snap: dict, locations: dict | None = None) -> dict[str, VesselState]:
    """benchsim's ledger keys (dev/water/hopper/P1/P2/flask) kept verbatim - the dashboard renders
    these names, and renaming them here would split the vocabulary in two."""
    out = {}
    held = {}
    for role, a in (snap.get("arms") or {}).items():
        if a.get("holding"):
            held[a["holding"]] = role
    for name, contents in (snap.get("vessels") or {}).items():
        c = {k: (_num(v, 2) or 0.0) for k, v in (contents or {}).items()}
        at = held.get(name) or (locations or {}).get(name) or _home(name)
        out[name] = VesselState(name=name, at=at, contents_g=c, total_g=_num(sum(c.values()), 2) or 0.0)
    return out


def _home(name: str) -> str | None:
    if name in ("P1", "P2"):
        return "carousel"
    if name in ("dev", "water"):
        return "rack"
    if name == "hopper":
        return "auger"
    if name == "flask":
        return "stage"
    return None


def chemistry_from(snap: dict) -> ChemistryState | None:
    foam = (snap.get("probes") or {}).get("foam")
    spilled = _num(snap.get("spilled_g"), 2)
    if foam is None and spilled is None:
        return None
    f = foam or {}
    return ChemistryState(
        foam_h_mm=_num(f.get("column_mm"), 1) or 0.0,
        spilled_total_g=spilled or 0.0,
        reaction_started=f.get("t_contact") is not None,
        o2_released_l=None if f.get("o2_ml") is None else _num(f["o2_ml"] / 1000.0, 4),
        foam_peak_mm=_num(f.get("peak_mm"), 1),
        h2o2_left_g=_num(f.get("h2o2_left_g"), 2),
        t_contact_s=_num(f.get("t_contact"), 2),
    )


def project(snap: dict, bench, ledger=None, locations: dict | None = None) -> ProjectedParts:
    """`locations`: the sequencer's `ctx.state['beakers']` (beaker -> station), the authority on where
    each beaker is once a run has moved it."""
    return ProjectedParts(
        arms=arms_from(snap),
        mega=mega_from(snap, bench),
        scale=scale_from(snap, bench, locations),
        vessels=vessels_from(snap, locations),
        chemistry=chemistry_from(snap),
        bench_t=_num(snap.get("t"), 3) or 0.0,
    )


def steps_from(snap: dict) -> list[dict]:
    """feed steps -> StepState kwargs (the runner owns t0/t1, which the feed does not track)"""
    rows = []
    for st in snap.get("steps") or []:
        rows.append(dict(index=st["index"], name=st.get("label") or st.get("type", ""),
                         status=STEP_STATUS.get(st.get("status"), "pending"),
                         detail=st.get("reason", ""), type=st.get("type")))
    return rows


def mode_from(snap: dict, *, awaiting_approval: bool = False, paused: bool = False,
              run_active: bool = False) -> str:
    """`run_active` is the runner's own phase.  The sequencer reaches DONE before the run is over -
    benchsim's demo watches the foam for 14 s after the last step, and the record is written after
    that - so a terminal mode is the runner's to declare, never the feed's."""
    if awaiting_approval:
        return "awaiting_approval"
    if paused:
        return "paused"
    mode = SEQ_TO_MODE.get(snap.get("seq_state"), "idle")
    if run_active and mode in ("complete", "safe_stop", "error", "idle"):
        return "running"
    return mode
