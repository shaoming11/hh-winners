"""The three data contracts of the bench backend. Single source of truth; `export_schemas.py`
writes them to software/schemas/*.json for the frontend (TypeScript) and the Photon agent.

  1. HardwareCommand / HardwareReply   backend -> bench (sim or real).  Will change as the
                                        hardware comes up; every message carries `v`.
  2. ExperimentState                    backend -> frontend (poll / SSE) and -> MCP server.
                                        One snapshot that answers "what is the bench doing".
  3. Event / Alert / ApprovalRequest    the append-only log the frontend renders and the
                                        agent reads; alerts are the QA channel.

Conventions: angles in degrees (LeRobot "new calibration" = MJCF zero), masses in grams,
times: `ts` is wall-clock ISO-8601 UTC, `bench_t` is bench seconds (sim clock or real time
since connect).  Field names match bench/hal/protocol.py and the run_<stamp>.json records so
nothing is translated twice.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "0.1.0"

Backend = Literal["sim", "real"]
ArmRole = Literal["pourer", "transfer"]
Beaker = Literal["P1", "P2"]
# benchsim.process.steps: transfers run carousel_pick <-> scale_pan only; the rack/funnel are
# reached by the pourer inside a step, never addressed as a transfer endpoint.
Station = Literal["carousel_pick", "scale_pan"]
ArmStation = Literal["carousel_pick", "scale", "funnel", "rack_developer", "rack_water", "park"]
Reagent = Literal["developer", "water"]
StepType = Literal["TRANSFER", "POUR_TO_SCALE", "POUR_TO_FUNNEL", "CAROUSEL",
                   "DOSE_YEAST", "VERIFY_MASS", "WAIT", "STAGE"]
StagePosition = Literal["WORK", "ERUPT"]
Source = Literal["frontend", "agent", "operator", "backend", "sequencer"]

JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# =============================================================================================
# 1. Hardware commands  (backend -> bench)
# =============================================================================================
class _Cmd(Strict):
    v: str = Field(SCHEMA_VERSION, description="schema version of this command")
    id: str = Field(..., description="caller-chosen id; echoed in HardwareReply.id")
    source: Source = "frontend"
    note: str = Field("", description="free text: why this command was issued (goes in the log)")


# ---- Mega (carousel, stage, auger, scale) - mirrors bench/hal/protocol.py 1:1
class CarouselCmd(_Cmd):
    kind: Literal["carousel"] = "carousel"
    deg: float = Field(..., ge=-720, le=720, description="absolute deck angle; +90 = P2 under the auger")
    ms: int = Field(4000, ge=500, le=60000)


class StageCmd(_Cmd):
    kind: Literal["stage"] = "stage"
    position: StagePosition | None = Field(None, description="named position (preferred)")
    deg: float | None = Field(None, ge=0, le=150, description="raw crank angle if no position")
    ms: int = Field(2500, ge=1500, le=20000)


class AugerCmd(_Cmd):
    kind: Literal["auger"] = "auger"
    rev: float = Field(..., ge=-50, le=50, description="revolutions; negative = reverse (anti-jam)")


class MegaSimpleCmd(_Cmd):
    """the parameterless commands of the benchsim/firmware protocol (benchsim.protocol).
    Weight and mechanism positions are not asked for: they arrive on the sample stream and in
    ExperimentState."""
    kind: Literal["mega"] = "mega"
    cmd: Literal["ping", "stop", "clr", "hb"]


class StreamCmd(_Cmd):
    kind: Literal["stream"] = "stream"
    on: bool


class TareCmd(_Cmd):
    kind: Literal["tare"] = "tare"
    seconds: float = Field(0.5, gt=0, le=5)


# ---- Arms (SO-101 over the HAL)
class ArmGoalsCmd(_Cmd):
    kind: Literal["arm_goals"] = "arm_goals"
    role: ArmRole
    goals: dict[str, float] = Field(..., description="joint -> degrees; subset of JOINTS")
    duration_s: float = Field(2.0, gt=0, le=30, description="interpolation time")


class ArmTorqueCmd(_Cmd):
    kind: Literal["arm_torque"] = "arm_torque"
    role: ArmRole
    on: bool


class GripperCmd(_Cmd):
    kind: Literal["gripper"] = "gripper"
    role: ArmRole
    action: Literal["open", "close"]


class ArmStationCmd(_Cmd):
    """Move an arm to a pre-planned, collision-checked station pose (no free IK from outside)."""
    kind: Literal["arm_station"] = "arm_station"
    role: ArmRole
    station: ArmStation
    phase: Literal["approach", "grasp", "carry"] = "carry"


# ---- Process level (the vocabulary of benchsim/process/steps.py; steps.validate gates it before it runs)
class PlanStep(Strict):
    """One step of benchsim.process.steps.  `params` is checked by `steps.validate`, the only
    gate before execution - it is deliberately an open dict here so the two never drift."""
    type: StepType
    params: dict = Field(default_factory=dict, description="per-type params; see benchsim.process.steps")
    label: str = ""


class Plan(Strict):
    title: str
    steps: list[PlanStep]
    source: Literal["llm", "preset", "manual", "agent"] = "manual"
    notes: str = ""


class Recipe(Strict):
    developer_g: float = 39.0
    yeast_g: float = 7.0
    water_g: float = 30.0
    activate_s: float = 60.0
    quick: bool = Field(False, description="demo-slot plan: the same chemistry minus the yeast re-weigh and the "
                                          "final beaker return, for a run that finishes inside a 90 s slot")


class RunPlanCmd(_Cmd):
    """Validate a plan, request operator approval (unless pre-approved), then run it."""
    kind: Literal["run_plan"] = "run_plan"
    plan: Plan | None = Field(None, description="omit to run the preset with `recipe`")
    recipe: Recipe | None = None
    protocol_text: str = Field("", description="the plain-English protocol the plan came from")
    operator: str = ""
    speed: float = Field(1.0, gt=0, le=1.0)
    only: list[str] | None = Field(None, description="step-name prefixes to run, e.g. ['1','2']")
    approved: bool = Field(False, description="true = skip the approval gate (operator at the bench)")
    requested_by: str = Field("", description="who asked for this run (chat handle / name); the approver goes in `operator`")
    idempotency_key: str | None = Field(None, description="e.g. the chat message id; a repeat returns the first reply instead of a second request")


class HwReplayCmd(_Cmd):
    """Replay the planned arm paths (benchsim/reports/native_plans.json) through the REAL hardware code -
    LeRobotArm on a Feetech bus, MegaClient over a serial port, scripts/replay_plan.py's step logic - with the
    USB devices emulated by this bench's simulator.  The dry run of the physical bench, without the bench."""
    kind: Literal["hw_replay"] = "hw_replay"
    speed: float = Field(0.6, gt=0, le=1.0, description="fraction of the calibrated max arm speed (replay_plan --speed)")
    steps: list[str] | None = Field(None, description="step numbers to run, e.g. ['1', '4']; default all planned steps")
    requested_by: str = ""


class RunControlCmd(_Cmd):
    kind: Literal["run_control"] = "run_control"
    action: Literal["pause", "resume", "safe_stop", "abort", "reset"]


class ApprovalCmd(_Cmd):
    kind: Literal["approval"] = "approval"
    request_id: str
    decision: Literal["approve", "reject"]
    by: str


HardwareCommand = Annotated[
    Union[CarouselCmd, StageCmd, AugerCmd, MegaSimpleCmd, StreamCmd, TareCmd,
          ArmGoalsCmd, ArmTorqueCmd, GripperCmd, ArmStationCmd,
          RunPlanCmd, RunControlCmd, ApprovalCmd, HwReplayCmd],
    Field(discriminator="kind"),
]


class HardwareReply(Strict):
    v: str = SCHEMA_VERSION
    id: str
    ok: bool
    err: Literal["RANGE", "BUSY", "STATE", "UNKNOWN", "ESTOP", "REJECTED", "NOT_CONNECTED",
                 "NEEDS_APPROVAL", "VALIDATION", "TIMEOUT", "INTERNAL", "EXPIRED"] | None = None
    message: str = ""
    data: dict = Field(default_factory=dict, description="cmd-specific payload (status, weight, request_id, run_id)")
    ts: str = Field(default_factory=now_iso)


# =============================================================================================
# 2. Experiment state  (backend -> frontend, -> MCP)
# =============================================================================================
Mode = Literal["disconnected", "idle", "planning", "awaiting_approval", "running", "paused",
               "safe_stop", "complete", "error"]


class ArmState(Strict):
    role: ArmRole
    q_deg: dict[str, float] = Field(default_factory=dict, description="joint -> degrees")
    load: dict[str, float] = Field(default_factory=dict, description="joint -> load (sim: torque proxy)")
    torque_on: bool = True
    holding: str | None = Field(None, description="vessel latched in the jaws: P1, P2, developer, water, soap")
    moving: bool = False
    station: str | None = Field(None, description="last commanded station, if known")
    temp_c: dict[str, float] | None = Field(None, description="servo temperatures; null until firmware reports them")
    goal_deg: dict[str, float] | None = Field(None, description="last commanded joint goal; null before the first move")
    twin: dict | None = Field(None, description="commanded vs measured tool point (benchsim.dashboard.twin): "
                                                "measured_mm, commanded_mm, error_mm, joint_err_deg, settled")


class MegaState(Strict):
    connected: bool = False
    fw: str | None = None
    hx_hz: float | None = Field(None, description="load-cell sample rate; closed loop needs >= control.scale.min_rate_hz")
    estop: bool = False
    fault: str | None = Field(None, description="latched fault: ESTOP|AUGER_JAM|WDT|HX_TIMEOUT|TIMEOUT")
    carousel_deg: float = 0.0
    stage_deg: float = 0.0
    stage_position: StagePosition | None = None
    auger_rev: float = 0.0
    busy: list[str] = Field(default_factory=list)
    last_heartbeat_age_s: float | None = None


class ScaleState(Strict):
    gross_g: float | None = None
    tare_g: float = 0.0
    net_g: float | None = None
    rate_gps: float | None = Field(None, description="LSQ flow estimate during a pour")
    sigma_g: float | None = None
    settled: bool = False
    streaming: bool = False
    beaker_on_pan: Beaker | None = None


class VesselState(Strict):
    name: str
    at: str | None = Field(None, description="station / 'pourer' / 'transfer' (held) / 'flask'")
    contents_g: dict[str, float] = Field(default_factory=dict, description="reagent -> grams")
    total_g: float = 0.0


class ChemistryState(Strict):
    """Sim-only plant model (null on hardware until the camera estimates replace it)."""
    foam_h_mm: float = 0.0
    spilled_total_g: float = 0.0
    reaction_started: bool = False
    o2_released_l: float | None = None
    foam_peak_mm: float | None = None
    h2o2_left_g: float | None = None
    t_contact_s: float | None = Field(None, description="bench time the yeast met the peroxide")


class Dose(Strict):
    target: float
    actual: float | None = None
    error: float | None = None
    topups: int = 0
    theta_first: float | None = None
    rev_first_pass: float | None = None


class Subgoal(Strict):
    """One phase of a step as the arm plays it (approach, grip, lift, pour, set down, ...), with what it
    should achieve and what the bench measured.  Filled by the hardware replay (backend/replay_observer.py)."""
    index: int
    name: str = Field(..., description="what this part of the step is for: 'grip P1', 'pour developer into P1'")
    phase: str = Field(..., description="the plan's segment phase: approach | pick | carry | pour | drain | pour_back | place | retreat | park")
    status: Literal["pending", "running", "ok", "warning", "failed", "unchecked", "skipped"] = "pending"
    expect: str = Field("", description="the success criterion, in words")
    result: str = Field("", description="what was measured")
    code: str | None = Field(None, description="check code when not ok: GRASP_MISS, LIFT_NOT_SEEN, PLACE_NOT_SEEN, "
                                               "DROPPED, REACH_SHORT, SCALE_DISTURBED, DOSE_ERROR, FUNNEL_NOT_EMPTIED")
    t0: float | None = None
    t1: float | None = None


class StepState(Strict):
    index: int
    name: str
    status: Literal["pending", "running", "ok", "fault", "error", "skipped"] = "pending"
    detail: str = ""
    type: StepType | None = Field(None, description="benchsim step type; null for the precheck row")
    params: dict = Field(default_factory=dict, description="the step's params as validated")
    narration: dict | None = Field(None, description="benchsim.dashboard.narration.describe(): title, detail, "
                                                     "arm, chemical, amount_g, tol_g, science, clearance. "
                                                     "`title` is the friendly prose for this step "
                                                     "('Weighing out 39 g of hydrogen peroxide'); `name` stays terse.")
    t0: float | None = Field(None, description="bench seconds")
    t1: float | None = None
    subgoals: list[Subgoal] = Field(default_factory=list, description="hardware replay only: the step's phases and their checks")


class Validation(Strict):
    ok: bool
    problems: list[str] = Field(default_factory=list)
    summary: str = ""


class RunState(Strict):
    run_id: str
    backend: Backend
    kind: Literal["sequencer", "hw_replay"] = Field("sequencer", description="sequencer = the closed-loop process; "
                                                   "hw_replay = the planned arm paths played through the hardware code")
    current_subgoal: str | None = Field(None, description="hw_replay: 'step name / subgoal name' being played now")
    started_at: str | None = None
    finished_at: str | None = None
    operator: str = Field("", description="the human who approved / started it")
    requested_by: str = Field("", description="the human who asked for it (may differ from operator)")
    protocol_text: str = ""
    plan: Plan | None = None
    validation: Validation | None = None
    recipe: Recipe | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    steps: list[StepState] = Field(default_factory=list)
    current_step: int | None = Field(None, description="index into steps")
    doses: dict[str, Dose | float] = Field(default_factory=dict, description="name -> Dose, or a scalar (tare_g, *_to_flask_g, foam_*)")
    faults: list[str] = Field(default_factory=list)
    outcome: Literal["not started", "running", "paused", "complete", "SAFE_STOP", "aborted", "rejected by validator"] = "not started"
    bench_seconds: float = 0.0
    wall_seconds: float = 0.0
    notebook_html: str | None = Field(None, description="URL of the lab-notebook page once finished")
    progress: float = Field(0.0, ge=0, le=1)


class Health(Strict):
    """QA / monitoring. Everything here is computed by the backend's watchdog, not the sequencer."""
    ok: bool = True
    comms_latency_ms: float | None = None
    scale_rate_hz: float | None = None
    arm_settle_overruns: int = Field(0, description="moves that did not settle in time (precursor to the fault that stopped run 004135)")
    stalls: int = 0
    servo_temp_max_c: float | None = Field(None, description="null until the firmware reports temperatures")
    spill_detected: bool = Field(False, description="sim: chem.spilled_total_g > threshold; real: CV on the webcam")
    spilled_g: float = 0.0
    camera_ok: bool | None = None
    beaker_check: dict[str, bool] = Field(default_factory=dict, description="camera: beaker present where the plan expects it")
    last_check_ts: str | None = None
    open_alerts: int = 0


class Alert(Strict):
    id: str
    ts: str = Field(default_factory=now_iso)
    severity: Literal["info", "warning", "critical"]
    code: str = Field(..., description="SPILL | ESTOP | FAULT | OVERRUN | SCALE_RATE | DOSE_ERROR | COMMS | TEMP | BEAKER_MISSING | NEEDS_APPROVAL")
    message: str
    run_id: str | None = None
    step: str | None = None
    data: dict = Field(default_factory=dict)
    acknowledged_by: str | None = None
    acknowledged_at: str | None = None
    resolved: bool = False
    notified: list[str] = Field(default_factory=list, description="channels/people the agent told (e.g. 'imessage:+1555')")


class ApprovalRequest(Strict):
    id: str
    ts: str = Field(default_factory=now_iso)
    kind: Literal["run_plan", "hardware_command"]
    requested_by: Source = Field(..., description="which system asked (agent/frontend/...)")
    requested_by_person: str = Field("", description="the human behind the request, if known")
    summary: str
    requires: list[str] = Field(default_factory=list, description="why a human must decide: 'moves the arms', 'doses 20 g of 12% peroxide', ...")
    payload: dict = Field(..., description="the HardwareCommand awaiting approval")
    status: Literal["pending", "approved", "rejected", "expired"] = "pending"
    expires_at: str | None = Field(None, description="pending requests expire; the asker must re-request")
    asked_of: list[str] = Field(default_factory=list, description="operators who were told about it (person ids)")
    snoozed_until: str | None = Field(None, description="don't remind anyone before this")
    decided_by: str | None = None
    decided_at: str | None = None


class MediaRefs(Strict):
    live_stream_url: str | None = Field(None, description="MJPEG of the sim/webcam, if the backend renders one")
    latest_snapshot: dict[str, str] = Field(default_factory=dict, description="camera name -> URL of the latest still")
    run_video_url: str | None = None


class ExperimentState(Strict):
    """THE snapshot. GET /api/state returns it; SSE /api/events streams it; MCP get_state wraps it."""
    v: str = SCHEMA_VERSION
    ts: str = Field(default_factory=now_iso)
    bench_t: float = Field(0.0, description="bench seconds (sim clock, or seconds since connect)")
    backend: Backend = "sim"
    mode: Mode = "disconnected"
    run: RunState | None = None
    arms: dict[str, ArmState] = Field(default_factory=dict)
    mega: MegaState = Field(default_factory=MegaState)
    scale: ScaleState = Field(default_factory=ScaleState)
    vessels: dict[str, VesselState] = Field(default_factory=dict, description="P1, P2, developer, water, soap, flask")
    chemistry: ChemistryState | None = None
    health: Health = Field(default_factory=Health)
    alerts: list[Alert] = Field(default_factory=list, description="open (unresolved) alerts")
    pending_approvals: list[ApprovalRequest] = Field(default_factory=list)
    recent_events: list["Event"] = Field(default_factory=list, description="last ~50 log events")
    media: MediaRefs = Field(default_factory=MediaRefs)
    history: list["RunSummary"] = Field(default_factory=list, description="previous runs, newest first")


class RunSummary(Strict):
    run_id: str
    backend: Backend
    started_at: str | None
    outcome: str
    recipe: Recipe | None
    doses: dict[str, Dose | float] = Field(default_factory=dict)
    faults: list[str] = Field(default_factory=list)
    foam_h_mm: float | None = None
    bench_seconds: float = 0.0


class Describe(Strict):
    """Prose-ready facts for a chat reply (same wording as the frontend's status line)."""
    headline: str = Field(..., description="one sentence: what the bench is doing")
    detail: str = Field("", description="one or two sentences: doses so far, what is waiting on whom")
    needs_human: str | None = Field(None, description="one sentence if a person has to do something, else null")
    ts: str = Field(default_factory=now_iso)
    last_event_id: int = 0


class Delta(Strict):
    """What changed since an event id - the answer to 'anything new?'."""
    since: int
    last_event_id: int
    changes: list[str] = Field(default_factory=list, description="human-readable, newest last")
    steps_completed: list[str] = Field(default_factory=list)
    doses: dict[str, Dose] = Field(default_factory=dict)
    alerts_opened: list[Alert] = Field(default_factory=list)
    alerts_resolved: list[str] = Field(default_factory=list)
    approvals: list[ApprovalRequest] = Field(default_factory=list, description="requested or decided in the window")
    run_outcome: str | None = Field(None, description="set when a run finished in the window")
    messages: list["Event"] = Field(default_factory=list, description="chat messages in the window")
    nothing_new: bool = False


class Person(Strict):
    id: str
    name: str | None = None
    role: Literal["operator", "student", "guest", "observer"] | None = None
    channel: str | None = None
    preferred_channel: str | None = None
    space_id: str | None = None
    subscribed: bool | None = Field(None, description="legacy: True == notify_on all")
    notify_on: list[Literal["critical", "warning", "run_complete", "approvals", "all"]] | None = None
    quiet_hours: dict | None = Field(None, description="{'start':'23:00','end':'08:00','tz':'America/New_York'}; criticals still go through")
    notes: list[dict] = Field(default_factory=list)
    first_seen: str | None = None
    last_seen: str | None = None


# =============================================================================================
# 3. Events  (the append-only log)
# =============================================================================================
EventKind = Literal["log", "step", "dose", "fault", "alert", "command", "reply", "approval",
                    "camera", "message", "state", "note"]


class Event(Strict):
    id: int
    ts: str = Field(default_factory=now_iso)
    bench_t: float = 0.0
    level: Literal["debug", "info", "warning", "error"] = "info"
    kind: EventKind
    run_id: str | None = None
    step: str | None = None
    source: Source = "backend"
    message: str
    data: dict = Field(default_factory=dict)


ExperimentState.model_rebuild()
Delta.model_rebuild()

ALL_SCHEMAS = {
    "HardwareCommand": HardwareCommand,
    "HardwareReply": HardwareReply,
    "ExperimentState": ExperimentState,
    "Event": Event,
    "Alert": Alert,
    "ApprovalRequest": ApprovalRequest,
    "Plan": Plan,
    "RunSummary": RunSummary,
    "Delta": Delta,
    "Describe": Describe,
    "Person": Person,
}
