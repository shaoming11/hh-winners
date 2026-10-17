"""Backend tests: schemas, store, watchdog, runner (in-process on the sim), HTTP API, MCP tools.

The runner / HTTP fixtures build a MuJoCo world (a few seconds each); runner tests are ordered so
that each one leaves the bench in a state the next one can use.  Run json records written by
test runs are removed again at the end of the module.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.schemas import (ALL_SCHEMAS, ArmGoalsCmd, CarouselCmd, ChemistryState, ExperimentState,
                             HardwareCommand, MegaState, MegaSimpleCmd, Recipe, RunPlanCmd, StageCmd, TareCmd)
from backend.store import Store
from backend.watchdog import Watchdog
from bench.config import load
from bench.paths import OUT_DIR

SOFTWARE = Path(__file__).resolve().parents[1]
CMD = TypeAdapter(HardwareCommand)


def wait_for(pred, timeout: float, dt: float = 0.05, what: str = "condition"):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(dt)
    raise AssertionError(f"timed out after {timeout} s waiting for {what}")


# =============================================================================================
# a. schemas
# =============================================================================================
def test_command_union_round_trips():
    cmd = CMD.validate_python({"kind": "carousel", "id": "c1", "deg": 90, "source": "operator"})
    assert isinstance(cmd, CarouselCmd) and cmd.ms == 4000
    again = CMD.validate_json(cmd.model_dump_json())
    assert again == cmd
    for payload, typ in [({"kind": "stage", "id": "s", "position": "ERUPT"}, StageCmd),
                         ({"kind": "tare", "id": "t"}, TareCmd),
                         ({"kind": "mega", "id": "m", "cmd": "ping"}, MegaSimpleCmd),
                         ({"kind": "arm_goals", "id": "a", "role": "pourer", "goals": {"wrist_roll": 10}}, ArmGoalsCmd),
                         ({"kind": "run_plan", "id": "r", "recipe": {"developer_g": 39}}, RunPlanCmd)]:
        c = CMD.validate_python(payload)
        assert isinstance(c, typ)
        assert CMD.validate_json(c.model_dump_json()) == c
    with pytest.raises(ValidationError):
        CMD.validate_python({"kind": "teleport", "id": "x"})
    with pytest.raises(ValidationError):            # extra="forbid"
        CMD.validate_python({"kind": "tare", "id": "t", "bogus": 1})


def test_stage_deg_out_of_range_rejected():
    with pytest.raises(ValidationError):
        CMD.validate_python({"kind": "stage", "id": "s", "deg": 170})
    with pytest.raises(ValidationError):
        StageCmd(id="s", deg=-1)
    assert StageCmd(id="s", deg=150).deg == 150


def test_export_schemas_writes_all_files():
    r = subprocess.run([sys.executable, "backend/export_schemas.py"], cwd=SOFTWARE, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = SOFTWARE / "schemas"
    for name in ALL_SCHEMAS:
        doc = json.loads((out / f"{name}.json").read_text())
        assert doc["title"] == name and doc["$schema"].endswith("2020-12/schema")
    index = json.loads((out / "index.json").read_text())
    assert set(index["schemas"]) == set(ALL_SCHEMAS)


def test_nan_serialises_as_null():
    s = ExperimentState(bench_t=float("nan"))
    d = json.loads(s.model_dump_json())
    assert d["bench_t"] is None
    s.chemistry = ChemistryState(foam_h_mm=float("inf"))
    assert json.loads(s.model_dump_json())["chemistry"]["foam_h_mm"] is None


# =============================================================================================
# b. store
# =============================================================================================
def test_store_events_persist_and_reload(tmp_path):
    st = Store(out_dir=tmp_path)
    e1 = st.event("log", "hello")
    e2 = st.event("message", "hi there", source="agent", data={"channel": "sms"})
    assert (e1.id, e2.id) == (1, 2)
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[1])["message"] == "hi there"
    st2 = Store(out_dir=tmp_path)
    assert [e.id for e in st2.events] == [1, 2]
    assert st2.event("log", "after reload").id == 3
    assert [e.kind for e in st2.events_since(0)] == ["log", "message", "log"]
    assert [e.id for e in st2.events_since(1)] == [2, 3]
    assert [e.id for e in st2.events_since(0, kinds=["message"])] == [2]
    assert len(st2.events_since(0, limit=1)) == 1


def test_store_alert_dedupe_and_ack(tmp_path):
    st = Store(out_dir=tmp_path)
    a = st.alert("SPILL", "critical", "3 g on the table")
    assert st.alert("SPILL", "critical", "again") is a           # deduped within the (no-)run
    b = st.alert("SPILL", "critical", "third", dedupe=False)
    assert b is not a
    w = st.alert("OVERRUN", "warning", "late")
    assert st.ack_alert(w.id, "shao").resolved is True
    assert st.ack_alert(a.id, "shao").resolved is False          # criticals stay open
    assert st.ack_alert("nope", "x") is None
    snap = st.snapshot()
    assert {x.id for x in snap.alerts} == {a.id, b.id} and snap.health.open_alerts == 2
    assert st.resolve_alerts("SPILL") == 2
    assert st.snapshot().alerts == []
    # a different run_id is a different dedupe bucket
    st.update(lambda s: s.__setattr__("run", None))
    assert st.alert("SPILL", "critical", "new").id not in (a.id, b.id)


def test_store_approvals(tmp_path):
    st = Store(out_dir=tmp_path)
    r = st.request_approval("run_plan", {"kind": "run_plan", "id": "x"}, "run it", "agent")
    assert r.status == "pending" and st.snapshot().pending_approvals[0].id == r.id
    d = st.decide(r.id, "approve", "shao")
    assert d.status == "approved" and d.decided_by == "shao"
    assert st.decide(r.id, "reject", "shao") is None             # already decided
    assert st.decide("missing", "approve", "shao") is None
    assert st.snapshot().pending_approvals == []
    r2 = st.request_approval("hardware_command", {}, "move", "agent")
    assert st.decide(r2.id, "reject", "shao").status == "rejected"
    kinds = [e.kind for e in st.events_since(0)]
    assert kinds.count("approval") == 4


def test_store_people(tmp_path):
    st = Store(out_dir=tmp_path)
    st.touch_person("+1555", name="Jay", channel="imessage")
    p = Store(out_dir=tmp_path).people["+1555"]
    assert p["name"] == "Jay" and p["channel"] == "imessage" and "last_seen" in p


# =============================================================================================
# c. watchdog
# =============================================================================================
@pytest.fixture()
def wd(tmp_path):
    st = Store(out_dir=tmp_path)
    return st, Watchdog(st, load())


def feed(st: Store, w: Watchdog, **attrs) -> None:
    """Put fields on the store's state (as the runner's _publish does) and run the QA pass."""
    st.update(lambda x: [setattr(x, k, v) for k, v in attrs.items()])
    w.evaluate(st.snapshot())


def open_codes(st: Store) -> dict[str, list]:
    out: dict[str, list] = {}
    for a in st.alerts.values():
        if not a.resolved:
            out.setdefault(a.code, []).append(a)
    return out


def test_watchdog_estop(wd):
    st, w = wd
    feed(st, w, mode="idle", mega=MegaState(estop=True))
    al = open_codes(st)["ESTOP"]
    assert len(al) == 1 and al[0].severity == "critical"
    assert st.state.health.ok is False
    feed(st, w, mega=MegaState(estop=False))
    assert "ESTOP" not in open_codes(st)
    assert st.state.health.ok is True


def test_watchdog_spill(wd):
    st, w = wd
    feed(st, w, mode="idle", chemistry=ChemistryState(spilled_total_g=0.3))
    assert "SPILL" not in open_codes(st) and st.state.health.spill_detected is False
    feed(st, w, chemistry=ChemistryState(spilled_total_g=1.2))
    a = open_codes(st)["SPILL"][0]
    assert a.severity == "critical" and a.data["spilled_g"] == 1.2
    assert st.state.health.spill_detected and st.state.health.spilled_g == 1.2


def test_watchdog_overrun_and_dose(wd):
    st, w = wd
    w.on_log("[  12.0s] pourer did not settle: 5.0 deg off after 2.5 s", "2 developer pour to 39 g")
    assert w.overruns == 1
    a = open_codes(st)["OVERRUN"][0]
    assert a.severity == "warning" and "5.0 deg" in a.message and a.step == "2 developer pour to 39 g"
    w.on_log("plain line", None)
    assert w.overruns == 1
    w.on_dose("developer", 39.0, 39.5, "2")
    assert "DOSE_ERROR" not in open_codes(st)
    w.on_dose("developer", 39.0, 42.5, "2")
    d = open_codes(st)["DOSE_ERROR"][0]
    assert d.data == {"dose": "developer", "target": 39.0, "actual": 42.5}
    w.on_dose("yeast", 7.0, 8.0, "5b")                            # tol 0.7
    assert len(open_codes(st)["DOSE_ERROR"]) == 2
    feed(st, w, mode="idle")
    assert st.state.health.arm_settle_overruns == 1


# =============================================================================================
# d. runner (in-process, sim, no rendering)
# =============================================================================================
class _Rig:
    def __init__(self, store, runner):
        self.store, self.runner = store, runner
        self.run_ids: list[str] = []

    @property
    def mode(self):
        return self.store.state.mode

    def start(self, only, source="operator", approved=True, **kw):
        cmd = RunPlanCmd(id=f"t-{int(time.time()*1000)}", source=source, approved=approved, only=only,
                         operator="pytest" if approved else "", **kw)
        rep = self.runner.start_run(cmd)
        if rep.ok:
            self.run_ids.append(rep.data["run_id"])
        return rep

    def wait_mode(self, *modes, timeout=120.0):
        return wait_for(lambda: self.mode in modes and self.mode, timeout, what=f"mode in {modes} (now {self.mode})")

    def wait_finished(self, timeout=120.0):
        self.wait_mode("complete", "safe_stop", "error", timeout=timeout)
        wait_for(lambda: not self.runner.running(), 10, what="run thread to exit")
        return self.store.state.run

    def reset(self):
        rep = self.runner.control("reset", by="pytest")
        assert rep.ok, rep.message
        assert self.mode == "idle"


@pytest.fixture(scope="module")
def rig(tmp_path_factory):
    from backend.runner import BenchRunner
    store = Store(out_dir=tmp_path_factory.mktemp("backend"))
    runner = BenchRunner(store, load(), backend="sim", render=False)
    runner.connect()
    r = _Rig(store, runner)
    yield r
    if runner.running():
        runner.control("safe_stop", by="teardown")
        try:
            r.wait_finished(60)
        except AssertionError:
            pass
    for rid in r.run_ids:                       # do not leave test runs in the real history
        (OUT_DIR / f"run_{rid}.json").unlink(missing_ok=True)


def test_runner_connected(rig):
    s = rig.store.snapshot()
    assert s.mode == "idle" and s.backend == "sim" and s.mega.connected and s.mega.fw
    assert set(s.arms) == {"pourer", "transfer"} and s.vessels["dev"].total_g == pytest.approx(60.3, abs=0.5)
    assert s.chemistry is not None
    ExperimentState.model_validate_json(s.model_dump_json())


def test_runner_validator_rejects(rig):
    rep = rig.start(None, recipe=Recipe(developer_g=80))
    assert rep.ok is False and rep.err == "VALIDATION" and "target 80.0 g outside" in rep.message
    assert rep.data["validation"]["ok"] is False
    assert rig.mode == "idle" and not rig.runner.running()


def test_runner_agent_run_needs_approval_then_reject(rig):
    rep = rig.start(["1"], source="agent", approved=False)
    assert rep.err == "NEEDS_APPROVAL" and rep.data["request_id"]
    assert rig.mode == "awaiting_approval"
    assert rig.store.snapshot().pending_approvals[0].kind == "run_plan"
    rep2 = rig.runner.decide(rep.data["request_id"], "reject", "shao")
    assert rep2.ok and "rejected" in rep2.message
    assert rig.mode == "idle" and rig.store.snapshot().pending_approvals == []
    assert rig.runner.decide(rep.data["request_id"], "approve", "shao").err == "STATE"


def test_runner_approved_short_run_completes(rig):
    rig.reset()
    rep = rig.start(["1"])
    assert rep.ok, rep.message
    run_id = rep.data["run_id"]
    assert rig.mode == "running"
    run = rig.wait_finished()
    assert run.outcome == "complete" and rig.mode == "complete"
    assert [s.name for s in run.steps] == ["1 P1 carousel -> scale"]
    assert [s.type for s in run.steps] == ["TRANSFER"]
    assert all(s.status == "ok" for s in run.steps)
    assert run.progress == 1.0
    s = rig.store.snapshot()
    assert s.vessels["P1"].at == "transfer" or s.scale.beaker_on_pan == "P1"
    assert any(h.run_id == run_id for h in s.history) or s.run.run_id == run_id
    assert s.run.notebook_html and s.run.notebook_html.startswith("/runs/")


def test_runner_reset_gives_fresh_bench(rig):
    rig.reset()
    s = rig.store.snapshot()
    assert s.run is None and s.mode == "idle"
    assert s.vessels["P1"].at == "carousel" and s.vessels["P1"].total_g == 0
    assert s.scale.beaker_on_pan is None
    assert s.vessels["dev"].total_g == pytest.approx(60.3, abs=0.5)
    assert s.bench_t < 1.0


def test_runner_only_one_excludes_erupt_and_motion_is_busy(rig):
    rig.reset()
    rep = rig.start(["1"])
    assert rep.ok, rep.message
    names = [s.name for s in rig.store.state.run.steps]
    assert names == ["1 P1 carousel -> scale"]            # not "10 ERUPT"
    wait_for(lambda: rig.store.state.bench_t > 0.3, 20, what="sim stepping")
    assert rig.runner.control("pause").ok
    rig.wait_mode("paused", timeout=10)
    busy = rig.runner.command(CarouselCmd(id="b", deg=90, source="operator"))
    assert busy.err == "BUSY"
    # Even a Mega PING needs the world to advance (the simulated device answers in its next
    # pre_step), and a paused run is suspended inside a frame hook, so nothing may step it.
    # Refused at once rather than queued behind a run that is not stepping.
    ping = rig.runner.command(MegaSimpleCmd(id="st", cmd="ping", source="operator"))
    assert ping.err == "BUSY" and "paused" in ping.message
    assert rig.runner.control("resume").ok
    run = rig.wait_finished()
    assert run.outcome == "complete" and [s.status for s in run.steps] == ["ok"]
    rig.reset()                                           # a finished bench must be reset before it runs again
    assert rig.runner.start_run(RunPlanCmd(id="z", only=["99"], approved=True)).err == "VALIDATION"


def test_runner_pause_resume(rig):
    rig.reset()
    rep = rig.start(["1", "2"])
    assert rep.ok, rep.message
    wait_for(lambda: rig.store.state.bench_t > 1.0, 30, what="sim stepping")
    t_req = time.monotonic()
    assert rig.runner.control("pause", by="pytest").ok
    rig.wait_mode("paused", timeout=5)
    assert time.monotonic() - t_req < 5
    t_paused = rig.store.state.bench_t
    time.sleep(1.0)
    assert rig.store.state.bench_t == t_paused
    assert rig.runner.running()
    assert rig.runner.control("resume", by="pytest").ok
    rig.wait_mode("running", timeout=5)
    wait_for(lambda: rig.store.state.bench_t > t_paused + 0.5, 5, what="bench time to advance after resume")


def test_runner_safe_stop(rig):
    if not rig.runner.running():
        rig.reset()
        assert rig.start(["1", "2"]).ok
        wait_for(lambda: rig.store.state.bench_t > 1.0, 30, what="sim stepping")
    run_id = rig.store.state.run.run_id
    rep = rig.runner.control("safe_stop", by="pytest")
    assert rep.ok
    run = rig.wait_finished(timeout=30)
    assert run.outcome == "SAFE_STOP" and rig.mode == "safe_stop"
    assert run.faults and "safe_stop requested by pytest" in run.faults[-1]
    assert any(s.status == "fault" for s in run.steps)
    faults = [a for a in rig.store.alerts.values() if a.code == "FAULT" and not a.resolved]
    assert faults and faults[0].severity == "critical" and faults[0].run_id == run_id
    assert rig.store.state.health.ok is False or rig.store.snapshot().health.open_alerts > 0
    assert rig.runner.control("pause").err == "STATE"


def test_runner_reset_after_safe_stop_clears_alerts(rig):
    rig.reset()
    s = rig.store.snapshot()
    assert s.run is None and s.alerts == [] and s.vessels["P1"].at == "carousel"
    assert s.vessels["dev"].total_g == pytest.approx(60.3, abs=0.5)


def test_runner_direct_commands(rig):
    r = rig.runner
    rep = r.command(CarouselCmd(id="c", deg=90, source="operator"))
    assert rep.ok, rep.message
    assert rig.store.state.mega.carousel_deg == pytest.approx(90, abs=2)
    rep = r.command(StageCmd(id="s", position="ERUPT", source="frontend"))
    assert rep.ok, rep.message
    assert rig.store.state.mega.stage_position == "ERUPT" and rig.store.state.mega.stage_deg > 140
    assert r.command(StageCmd(id="s2", position="WORK", source="operator")).ok
    assert rig.store.state.mega.stage_position == "WORK"
    rep = r.command(TareCmd(id="t", source="operator"))
    assert rep.ok and rep.data.get("tared")
    rep = r.command(MegaSimpleCmd(id="m", cmd="ping", source="operator"))
    assert rep.ok and rep.data.get("ok") and rep.data.get("fw")
    rep = r.command(CarouselCmd(id="a", deg=0, source="agent"))
    assert rep.err == "NEEDS_APPROVAL"
    req = rig.store.approvals[rep.data["request_id"]]
    assert req.kind == "hardware_command" and req.status == "pending"
    rep2 = r.decide(req.id, "approve", "shao")                   # approving executes it
    assert rep2.ok and rep2.message.startswith("approved by shao")
    assert rig.store.state.mega.carousel_deg == pytest.approx(0, abs=2)
    rep = r.command(ArmGoalsCmd(id="g", role="pourer", goals={"shoulder_pan": 500}, source="operator"))
    assert rep.err == "RANGE" and "shoulder_pan" in rep.message
    rep = r.command(ArmGoalsCmd(id="g2", role="pourer", goals={"nonsense": 1}, source="operator"))
    assert rep.ok is False and rep.err in ("REJECTED", "RANGE")
    assert r.control("bogus").err == "UNKNOWN"
    assert rig.mode == "idle"


# =============================================================================================
# f. MCP tools, in-process against the same runner
# =============================================================================================
def call(_mcp, _tool, **args):
    res = asyncio.run(_mcp.call_tool(_tool, args))
    assert not res.is_error, res.content
    if res.structured_content is not None:
        sc = res.structured_content
        return sc["result"] if set(sc) == {"result"} else sc
    assert len(res.content) == 1, res.content
    return json.loads(res.content[0].text)


@pytest.fixture(scope="module")
def mcp(rig):
    from backend import mcp_server
    return mcp_server.build(rig.store, rig.runner)


def test_mcp_read_tools(rig, mcp):
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"get_state", "qa_check", "start_run", "decide_approval", "hardware_command", "simulate_estop",
            "record_message", "get_people", "update_person", "validate_plan", "preset_plan"} <= names
    s = call(mcp, "get_state", detail="summary")
    st = ExperimentState.model_validate(s)
    assert st.mode == "idle" and len(st.recent_events) <= 10 and all(a.load == {} for a in st.arms.values())
    assert len(call(mcp, "get_state", detail="full")["recent_events"]) >= len(st.recent_events)
    q = call(mcp, "qa_check")
    assert q["mode"] == "idle" and q["ok"] is True
    assert any("servo temperatures" in f for f in q["findings"])
    assert call(mcp, "get_schema", name="Event")["title"] == "Event"
    assert "error" in call(mcp, "get_schema", name="Nope")
    evs = call(mcp, "get_events", kinds=["command"], limit=5)
    assert isinstance(evs, list) and all(e["kind"] == "command" for e in evs)


def test_mcp_plan_tools(mcp):
    p = call(mcp, "preset_plan", developer_g=39, yeast_g=7, water_g=30, activate_s=60)
    assert p["source"] == "preset" and p["steps"][-1]["type"] == "STAGE"
    v = call(mcp, "validate_plan", plan=p)
    assert v["ok"] is True
    bad = {"title": "bad", "steps": [{"type": "POUR_TO_SCALE",
                                      "params": {"reagent": "acetone", "beaker": "P1", "target_g": 10, "tol_g": 1}}]}
    v = call(mcp, "validate_plan", plan=bad)
    assert v["ok"] is False and "unknown reagent acetone" in v["problems"][0]


def test_mcp_start_run_gated(rig, mcp):
    rep = call(mcp, "start_run", recipe={"developer_g": 39}, protocol_text="make it foam", requested_by="jay", only=["1"])
    assert rep["err"] == "NEEDS_APPROVAL" and rig.mode == "awaiting_approval"
    rid = rep["data"]["request_id"]
    assert [a["id"] for a in call(mcp, "list_approvals")] == [rid]
    refused = call(mcp, "decide_approval", request_id=rid, decision="approve", by="agent")
    assert refused["ok"] is False and refused["err"] == "REJECTED"
    assert rig.store.approvals[rid].status == "pending"
    q = call(mcp, "qa_check")
    assert any("waiting for approval" in f for f in q["findings"])
    rig.runner.wd.evaluate(rig.store.snapshot())
    assert "NEEDS_APPROVAL" in open_codes(rig.store)
    done = call(mcp, "decide_approval", request_id=rid, decision="reject", by="jay")
    assert done["ok"] is True and rig.mode == "idle"
    rig.runner.wd.evaluate(rig.store.snapshot())
    assert "NEEDS_APPROVAL" not in open_codes(rig.store)
    bad = call(mcp, "start_run", recipe={"developer_g": 80})
    assert bad["err"] == "VALIDATION"


def test_mcp_messages_and_people(rig, mcp):
    r = call(mcp, "record_message", channel="imessage", person="+1555", text="is the bench ok?", person_name="Jay")
    ev = rig.store.events_since(r["event_id"] - 1, kinds=["message"])[0]
    assert ev.message == "is the bench ok?" and ev.data["channel"] == "imessage" and ev.source == "agent"
    people = call(mcp, "get_people")
    assert people["+1555"]["name"] == "Jay"
    p = call(mcp, "update_person", person="+1555", role="operator", subscribed=True, note="knows the bench")
    assert p["role"] == "operator" and p["subscribed"] is True and p["notes"][-1]["note"] == "knows the bench"
    assert call(mcp, "get_people")["+1555"]["role"] == "operator"


def test_mcp_simulate_estop(rig, mcp):
    assert call(mcp, "simulate_estop", pressed=True)["ok"]
    rig.runner._publish()
    rig.runner.wd.evaluate(rig.store.snapshot())
    assert rig.store.state.mega.estop is True
    al = open_codes(rig.store)["ESTOP"]
    assert al[0].severity == "critical"
    q = call(mcp, "qa_check")
    assert q["ok"] is False and any("e-stop" in f for f in q["findings"])
    rep = call(mcp, "hardware_command", command={"kind": "carousel", "deg": 0})
    assert rep["err"] == "NEEDS_APPROVAL"                        # agent motion still gated, estop or not
    rig.runner.decide(rep["data"]["request_id"], "reject", "jay")
    assert call(mcp, "simulate_estop", pressed=False)["ok"]
    rig.runner._publish()
    rig.runner.wd.evaluate(rig.store.snapshot())
    assert "ESTOP" not in open_codes(rig.store)
    assert rig.store.state.mega.fault == "ESTOP"                 # latched until clr
    rep = call(mcp, "hardware_command", command={"kind": "mega", "cmd": "clr"})
    assert rep["ok"] is True
    assert rig.store.state.mega.fault is None
    rig.runner.wd.evaluate(rig.store.snapshot())
    assert rig.store.state.health.ok is True and call(mcp, "qa_check")["ok"] is True


# =============================================================================================
# e. HTTP
# =============================================================================================
@pytest.fixture(scope="module")
def client(app_client):
    """shared session client from conftest.py (one MCP session manager per process)"""
    return app_client


def test_http_state_and_schema(client):
    c, appmod = client
    r = c.get("/api/state")
    assert r.status_code == 200
    s = ExperimentState.model_validate(r.json())
    assert s.mode == "idle" and s.backend == "sim"
    r = c.get("/api/schemas/HardwareCommand")
    assert r.status_code == 200 and "oneOf" in r.json() or "discriminator" in json.dumps(r.json())
    assert c.get("/api/schemas/Nope").status_code == 404
    assert c.get("/api").json()["mcp"] == "/mcp"
    assert c.get("/").headers["content-type"].startswith("text/html")   # the dashboard page


def test_http_command_validation(client):
    c, _ = client
    r = c.post("/api/command", json={"kind": "stage", "deg": 170})
    assert r.status_code == 422 and r.json()["err"] == "VALIDATION" and r.json()["ok"] is False
    r = c.post("/api/command", json={"kind": "mega", "cmd": "ping", "source": "frontend"})
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["id"].startswith("http-")
    r = c.post("/api/command", json={"kind": "carousel", "deg": 45, "source": "agent"})
    body = r.json()
    assert body["err"] == "NEEDS_APPROVAL"
    rid = body["data"]["request_id"]
    assert [a["id"] for a in c.get("/api/approvals").json()] == [rid]
    r = c.post(f"/api/approvals/{rid}", json={"decision": "reject", "by": "shao"})
    assert r.json()["ok"] is True and c.get("/api/approvals").json() == []


def test_http_messages_people_events(client):
    c, _ = client
    r = c.post("/api/messages", json={"channel": "sms", "person": "+1999", "text": "hello bench", "person_name": "Sam"})
    eid = r.json()["event_id"]
    evs = c.get("/api/events", params={"kinds": "message", "since": eid - 1}).json()
    assert evs and evs[-1]["id"] == eid and evs[-1]["message"] == "hello bench"
    assert c.get("/api/people").json()["+1999"]["name"] == "Sam"
    r = c.post("/api/plan/validate", json={"title": "t", "steps": [{"type": "WAIT", "params": {"seconds": 5}}]})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_http_runs_and_alerts(client):
    c, _ = client
    runs = c.get("/api/runs").json()
    assert runs and {"run_id", "outcome", "backend"} <= set(runs[0])
    one = c.get(f"/api/runs/{runs[0]['run_id']}")
    assert one.status_code == 200 and one.json()["outcome"] == runs[0]["outcome"]
    assert c.get("/api/runs/nope").status_code == 404
    assert c.get("/api/alerts").json() == []
    assert c.post("/api/alerts/nope/ack", json={"by": "x"}).status_code == 404


def test_http_sse_stream(client):
    """Starlette's TestClient buffers whole responses, so drive the ASGI app directly and hang up
    after the first `state` frame."""
    _, appmod = client
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
             "path": "/api/stream", "raw_path": b"/api/stream", "query_string": b"", "root_path": "",
             "headers": [(b"host", b"testserver"), (b"accept", b"text/event-stream")],
             "client": ("127.0.0.1", 1234), "server": ("testserver", 80)}

    async def go():
        chunks: list[bytes] = []
        start: dict = {}
        hung_up = asyncio.Event()

        async def receive():
            await hung_up.wait()
            return {"type": "http.disconnect"}

        async def send(msg):
            if msg["type"] == "http.response.start":
                start.update(msg)
            elif msg["type"] == "http.response.body":
                chunks.append(msg.get("body", b""))
                if b"\n\n" in b"".join(chunks):
                    hung_up.set()

        await asyncio.wait_for(appmod.app(scope, receive, send), 20)
        return start, b"".join(chunks).decode()

    start, text = asyncio.run(go())
    appmod.store.update(lambda s: None)              # wake the SSE waiter thread so it exits now
    assert start["status"] == 200
    assert dict(start["headers"])[b"content-type"].startswith(b"text/event-stream")
    frame = text.split("\n\n")[0].splitlines()
    assert frame[0] == "event: state" and frame[1].startswith("id: ")
    data = next(l for l in frame if l.startswith("data: "))[6:]
    ExperimentState.model_validate_json(data)
