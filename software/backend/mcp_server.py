"""MCP server for the Photon agent (and any other agent): read the experiment, control the bench
through the same gated command path the frontend uses, do QA, and write people's messages back
into the shared log so the frontend sees the conversation too.

Mounted by app.py at /mcp (streamable HTTP).  Every tool returns plain JSON-able dicts built from
backend/schemas.py so the agent and the frontend speak the same vocabulary.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ImageContent
from pydantic import TypeAdapter

from backend.schemas import (ALL_SCHEMAS, HardwareCommand, Plan, Recipe, RunPlanCmd, Source)
from backend.store import Store

INSTRUCTIONS = """You are talking to the Wet Lab Bench backend: a $500 two-arm robotic bench that runs
weighed chemistry (demo: elephant toothpaste - 12% H2O2 'developer', yeast catalyst, water) in a
MuJoCo twin or on the real hardware.  Read state with get_state / get_run / get_events / get_alerts.
Nothing moves without an operator: start_run and hardware commands from an agent create an
approval request; a human (frontend, or a known operator over chat) must call decide_approval.
safe_stop is always allowed and is the right answer to any doubt.  Use record_message so what
people said over chat lands in the shared log the frontend shows."""


def build(store: Store, runner) -> MCPServer:
    mcp = MCPServer("wet-lab-bench", instructions=INSTRUCTIONS, version="0.1.0")

    def _cmd(payload: dict, source: Source) -> dict:
        payload = dict(payload)
        payload.setdefault("id", f"mcp-{uuid.uuid4().hex[:8]}")
        payload["source"] = source
        cmd = TypeAdapter(HardwareCommand).validate_python(payload)
        return runner.command(cmd).model_dump()

    # ------------------------------------------------------------ read
    @mcp.tool(description="Snapshot of the whole bench: mode, current run (plan, step, doses), arms, Mega, scale, "
                          "vessels, chemistry, health, open alerts, pending approvals, recent events, run history. "
                          "detail='summary' trims events/history for chat.")
    def get_state(detail: Literal["summary", "full"] = "summary") -> dict:
        s = store.snapshot()
        if detail == "summary":
            s.recent_events = s.recent_events[-10:]
            s.history = s.history[:5]
            for a in s.arms.values():
                a.load = {}
        return s.model_dump()

    @mcp.tool(description="One run in full: the live run if run_id is omitted, else a past run by id "
                          "(ids from get_state().history). Includes per-step status and target vs actual doses.")
    def get_run(run_id: str | None = None) -> dict:
        s = store.snapshot()
        if run_id is None or (s.run and s.run.run_id == run_id):
            return s.run.model_dump() if s.run else {"error": "no run yet"}
        from backend.app import OUT_DIR
        p = OUT_DIR / f"run_{run_id}.json"
        if not p.exists():
            return {"error": f"no run {run_id}"}
        return json.loads(p.read_text())

    @mcp.tool(description="Log events newer than since_id (step changes, doses, faults, alerts, commands, chat "
                          "messages). kinds filters, e.g. ['fault','alert'].")
    def get_events(since_id: int = 0, limit: int = 100, kinds: list[str] | None = None) -> list[dict]:
        return [e.model_dump() for e in store.events_since(since_id, limit, kinds)]

    @mcp.tool(description="QA alerts (spill, e-stop, latched fault, settle overruns, dose errors, scale rate, "
                          "missing beaker, pending approvals). Open ones unless include_resolved.")
    def get_alerts(include_resolved: bool = False) -> list[dict]:
        with store.lock:
            return [a.model_dump() for a in store.alerts.values() if include_resolved or not a.resolved]

    @mcp.tool(description="Acknowledge an alert on someone's behalf (warnings/info resolve; criticals stay open "
                          "until the cause is cleared).")
    def acknowledge_alert(alert_id: str, by: str) -> dict:
        a = store.ack_alert(alert_id, by)
        return a.model_dump() if a else {"error": "no such alert"}

    @mcp.tool(description="Record that a person/channel was told about an alert, so nobody is told twice.")
    def mark_alert_notified(alert_id: str, channel: str) -> dict:
        store.mark_notified(alert_id, channel)
        return {"ok": True}

    @mcp.tool(description="Health check with plain-language findings and the action the operator should take. "
                          "Call this when someone asks 'is the bench ok?' or before approving a run.")
    def qa_check() -> dict:
        s = store.snapshot()
        findings: list[str] = []
        actions: list[str] = []
        if s.mode == "disconnected":
            findings.append("bench not connected"); actions.append("start the backend with a bench")
        if s.mega.estop:
            findings.append("e-stop pressed"); actions.append("release the e-stop, then send mega clr")
        if s.mega.fault:
            findings.append(f"Mega fault {s.mega.fault}"); actions.append("fix the cause, then mega clr")
        if s.mega.hx_hz is not None and s.health.scale_rate_hz is not None and s.health.scale_rate_hz < 70:
            findings.append(f"scale rate {s.health.scale_rate_hz:.0f} Hz < 70"); actions.append("check the HX711 wiring / rate pin")
        if s.health.spill_detected:
            findings.append(f"{s.health.spilled_g:.1f} g spilled"); actions.append("stop, goggles on, wipe the 12% peroxide, check the pour geometry")
        if s.health.arm_settle_overruns:
            findings.append(f"{s.health.arm_settle_overruns} arm settle overruns this run")
            actions.append("watch the pourer wrist; a 5 deg miss after 2.5 s is what stopped run 004135")
        if s.health.stalls:
            findings.append(f"{s.health.stalls} stalls/missed grasps")
        if s.run:
            for k, d in s.run.doses.items():
                if hasattr(d, "target") and d.actual is not None and d.error is not None and abs(d.error) > 2.0:
                    findings.append(f"dose {k} off by {d.error:+.2f} g")
        if s.health.servo_temp_max_c is None:
            findings.append("servo temperatures: not sensed (no current/temperature sensing on this bench; the e-stop is the protection)")
        for p in s.pending_approvals:
            findings.append(f"waiting for approval: {p.summary} (id {p.id})"); actions.append(f"decide_approval('{p.id}', ...)")
        ok = s.health.ok and not s.health.spill_detected
        return {"ok": ok, "mode": s.mode, "findings": findings or ["no issues"], "actions": actions,
                "open_alerts": [a.model_dump() for a in s.alerts], "bench_t": s.bench_t}

    @mcp.tool(description="Current camera frame (sim render or webcam). Cameras: overview, webcam, top, scale_cam.")
    def camera_snapshot(camera: str = "overview") -> ImageContent | dict:
        jpg = runner.snapshot_jpeg(camera)
        if not jpg:
            return {"error": "no frame available (rendering off or bench not connected)"}
        import base64
        return ImageContent(type="image", data=base64.b64encode(jpg).decode(), mimeType="image/jpeg")

    @mcp.tool(description="JSON Schema of a backend type: " + ", ".join(ALL_SCHEMAS))
    def get_schema(name: str) -> dict:
        if name not in ALL_SCHEMAS:
            return {"error": f"unknown schema; one of {list(ALL_SCHEMAS)}"}
        return TypeAdapter(ALL_SCHEMAS[name]).json_schema()

    # ------------------------------------------------------------ plan
    @mcp.tool(description="Validate a step plan against the bench's deterministic safety rules without running it. "
                          "Returns ok/problems/summary.")
    def validate_plan(plan: Plan) -> dict:
        v = runner.validate_plan(plan)
        return {"ok": v.ok, "problems": v.problems, "summary": v.summary}

    @mcp.tool(description="The preset elephant-toothpaste plan with these quantities (grams / seconds); use it as "
                          "quick=True drops the yeast re-weigh and the final beaker return, for a run that fits a "
                          "90-second demo slot (same chemistry, same eruption). Use it as "
                          "the base for a run instead of inventing steps.")
    def preset_plan(developer_g: float = 19.5, yeast_g: float = 3.5, water_g: float = 30.0, activate_s: float = 60.0,
                    quick: bool = False) -> dict:
        p = runner.preset_plan(Recipe(developer_g=developer_g, yeast_g=yeast_g, water_g=water_g, activate_s=activate_s,
                                      quick=quick))
        return p.model_dump()

    # ------------------------------------------------------------ control (gated)
    @mcp.tool(description="Ask to run an experiment. Validates, then creates an approval request (returns "
                          "err NEEDS_APPROVAL + request_id) - a human must approve via decide_approval. Give either "
                          "recipe (quantities for the preset) or a full plan. protocol_text = what the person asked for.")
    def start_run(recipe: Recipe | None = None, plan: Plan | None = None, protocol_text: str = "",
                  requested_by: str = "", speed: float = 1.0, only: list[str] | None = None) -> dict:
        cmd = RunPlanCmd(id=f"mcp-{uuid.uuid4().hex[:8]}", source="agent", recipe=recipe, plan=plan,
                         protocol_text=protocol_text, operator=requested_by, speed=speed, only=only, approved=False,
                         note=f"requested over chat by {requested_by}")
        return runner.start_run(cmd).model_dump()

    @mcp.tool(description="Pending approvals (runs or motion commands waiting for a human).")
    def list_approvals(include_decided: bool = False) -> list[dict]:
        with store.lock:
            return [a.model_dump() for a in store.approvals.values() if include_decided or a.status == "pending"]

    @mcp.tool(description="Approve or reject a pending request ON BEHALF OF a named human operator who said so in "
                          "chat. `by` must be the person's name/handle, never the agent. Approving a run starts it.")
    def decide_approval(request_id: str, decision: Literal["approve", "reject"], by: str) -> dict:
        if not by or by.lower() in ("agent", "bench", "claude", "bot"):
            return {"ok": False, "err": "REJECTED", "message": "approvals must name the human who decided"}
        return runner.decide(request_id, decision, by).model_dump()

    @mcp.tool(description="pause / resume / safe_stop / abort / reset the current run. safe_stop holds torque and "
                          "keeps grippers closed; it is always allowed and never needs approval.")
    def run_control(action: Literal["pause", "resume", "safe_stop", "abort", "reset"], by: str = "agent") -> dict:
        return runner.control(action, by=by).model_dump()

    @mcp.tool(description="Which preset start_run uses - the dashboard's 'full run | demo' switch. 'full' = the whole "
                          "process (yeast dose, water, activation, eruption); 'demo' = the ~80 s live-demo slot (yeast-water "
                          "pre-mixed in the flask: weigh the peroxide, pour it into the funnel, erupt). Omit mode to just read "
                          "it. Changing it rebuilds the sim bench (like reset), so it is refused while a run is active; sim "
                          "only, no approval. The hardware replay plays the same route either way.")
    def run_mode(mode: Literal["full", "demo"] | None = None, by: str = "agent") -> dict:
        if mode is None:
            steps = runner.preset_plan().steps
            return {"ok": True, "mode": runner.plan_mode, "steps": [st.label for st in steps]}
        rep = runner.set_plan_mode(mode, by=by).model_dump()
        rep["mode"] = runner.plan_mode
        return rep

    @mcp.tool(description="Send one HardwareCommand (see get_schema('HardwareCommand')): carousel/stage/auger/"
                          "tare/stream/mega(status|weight|ver|stop|clr)/arm_goals/gripper/arm_station/arm_torque/hw_replay. "
                          "Read-only and stop commands run at once; motion is refused during a run and, from an "
                          "agent, creates an approval request.")
    def hardware_command(command: dict[str, Any]) -> dict:
        return _cmd(command, "agent")

    @mcp.tool(description="Dry-run the PHYSICAL bench's code with no USB attached: replays the planned arm paths "
                          "(native_plans.json, the steps scripts/replay_plan.py plays on the real SO-101 arms and "
                          "carousel) through the real driver code - LeRobotArm on the Feetech bus, MegaClient over "
                          "the serial port - with the servos and the Mega emulated by the simulator. Progress shows "
                          "in get_state like a run (run_id starts 'hw-'), log lines in get_events. From the agent "
                          "it creates an approval request first. steps like ['1','4']; speed 0-1 (default 0.6).")
    def hardware_replay(speed: float = 0.6, steps: list[str] | None = None, requested_by: str = "") -> dict:
        return _cmd({"kind": "hw_replay", "speed": speed, "steps": steps, "requested_by": requested_by,
                     "note": f"requested over chat by {requested_by}" if requested_by else ""}, "agent")

    @mcp.tool(description="Recorded hardware replays, newest first: run_id, where it ran (emulated / usb / usb-fake), "
                          "outcome, steps, failed checks. Every hardware_replay is recorded.")
    def list_recordings() -> list[dict]:
        from backend.hardware import list_recordings as _list
        return _list(store.dir / "runs")

    @mcp.tool(description="Play a recorded hardware replay back in the SIM (nothing on the bench moves): the arms "
                          "follow the recorded joint angles and the steps/subgoals/checks change when they did. Shows "
                          "in get_state as a run with kind 'playback'. speed 1 = as recorded.")
    def play_recording(run_id: str, speed: float = 1.0, requested_by: str = "") -> dict:
        return _cmd({"kind": "playback", "run_id": run_id, "speed": speed, "requested_by": requested_by}, "agent")

    @mcp.tool(description="Sim only: press or release the e-stop to rehearse the safety path.")
    def simulate_estop(pressed: bool = True) -> dict:
        return runner.simulate_estop(pressed)

    # ------------------------------------------------------------ shared context
    @mcp.tool(description="Write a chat message into the shared log (frontend shows it). channel like 'imessage', "
                          "'sms', 'terminal'; person is the human's id/handle; direction inbound (they said) or "
                          "outbound (agent said).")
    def record_message(channel: str, person: str, text: str, direction: Literal["inbound", "outbound"] = "inbound",
                       person_name: str | None = None, space_id: str | None = None) -> dict:
        store.touch_person(person, name=person_name, channel=channel, space_id=space_id)
        ev = store.event("message", text, source="agent",
                         data={"channel": channel, "person": person, "direction": direction, "space_id": space_id})
        return {"event_id": ev.id}

    @mcp.tool(description="People who have talked to the bench (handle, name, channel, role, notes, last seen). "
                          "Use it to recognise someone across channels and to know who is an operator.")
    def get_people() -> dict:
        with store.lock:
            return dict(store.people)

    @mcp.tool(description="Remember something about a person (role='operator' lets them approve runs; subscribed=True "
                          "means they want alerts; notes are free text).")
    def update_person(person: str, name: str | None = None, role: str | None = None, subscribed: bool | None = None,
                      note: str | None = None, channel: str | None = None) -> dict:
        p = store.touch_person(person, name=name, role=role, subscribed=subscribed, channel=channel)
        if note:
            p.setdefault("notes", []).append({"ts": time.strftime("%Y-%m-%d %H:%M"), "note": note})
            store.save_people()
        return p

    @mcp.resource("bench://state", description="live ExperimentState JSON")
    def state_resource() -> str:
        return store.snapshot().model_dump_json()

    from backend import mcp_ux
    mcp_ux.register(mcp, store, runner)      # describe / get_delta / idempotent start_run / snooze / thread context
    return mcp
