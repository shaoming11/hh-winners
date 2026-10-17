"""Conversation-UX tests: backend/describe.py (describe/delta), the new Store approval/message
helpers (expiry, snooze, messages), and the mcp_ux / routes_ux tools built on top of them.

Mirrors tests/test_backend.py's style: hand-built schema objects for the pure describe() cases,
a tmp_path Store for delta()/approvals/messages, and - for the tool-level tests - conftest's
session-scoped `app_client` (the one FastAPI TestClient and in-process MCP server shared by every
module, because the MCP session manager's run() may only be called once per process).
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

from backend.describe import delta, describe
from backend.schemas import (Alert, ApprovalRequest, ChemistryState, Describe, Delta, Dose,
                             ExperimentState, Recipe, RunState, RunSummary, StepState)
from backend.store import Store


# =============================================================================================
# a. describe() - hand-built ExperimentState, no store/runner needed
# =============================================================================================
def test_describe_idle_is_short_with_no_needs_human():
    s = ExperimentState(mode="idle")
    d = describe(s, 5)
    assert d.headline == "The bench is idle; nothing is moving."
    assert d.detail == ""
    assert d.needs_human is None
    assert d.last_event_id == 5


def test_describe_idle_with_history_mentions_last_run():
    hist = RunSummary(run_id="r1", backend="sim", started_at=None, outcome="complete", recipe=None,
                      doses={"developer_g": Dose(target=39.0, actual=38.5, error=-0.5)})
    s = ExperimentState(mode="idle", history=[hist])
    d = describe(s, 5)
    assert d.headline == "The bench is idle; nothing is moving."
    assert "Last run r1 complete" in d.detail
    assert "developer_g 38.50 g of 39 (-0.50)" in d.detail


def test_describe_awaiting_approval_names_asker_and_expiry():
    ar = ApprovalRequest(id="ar1", kind="run_plan", requested_by="agent", requested_by_person="jay",
                         summary="run it - developer 39g, yeast 7g", payload={}, status="pending",
                         expires_at="2026-10-17T12:34:56+00:00", asked_of=["op1"])
    s = ExperimentState(mode="awaiting_approval", pending_approvals=[ar])
    d = describe(s, 1)
    assert d.headline == "The bench is idle, waiting for an operator to approve a run."
    assert d.needs_human is not None
    assert "jay asked for" in d.needs_human
    assert '"run it"' in d.needs_human
    assert "ar1" in d.needs_human
    assert "12:34 UTC" in d.needs_human


def test_describe_running_reports_progress_doses_and_recipe():
    run = RunState(run_id="r42", backend="sim", outcome="running", current_step=0,
                   steps=[StepState(index=0, name="1 pour developer", status="running"),
                          StepState(index=1, name="2 activate", status="pending")],
                   progress=0.35, recipe=Recipe(developer_g=39.0, yeast_g=7.0, water_g=30.0),
                   requested_by="jay", operator="sam",
                   doses={"developer_g": Dose(target=39.0, actual=20.0, error=-1.0)})
    s = ExperimentState(mode="running", run=run, chemistry=ChemistryState(foam_h_mm=15.0))
    d = describe(s, 9)
    assert d.headline == 'Run r42 is 35% through: 1 pour developer.'
    assert d.detail == ("Doses so far: developer_g 20.00 g of 39 (-1.00). Foam column 15 mm. "
                        "Recipe 39 g developer, 7 g yeast, 30 g water (requested by jay, approved by sam).")
    assert d.needs_human is None


def test_describe_safe_stop_names_step_fault_and_critical_alert():
    run = RunState(run_id="r7", backend="sim", outcome="SAFE_STOP", current_step=0,
                   steps=[StepState(index=0, name="1 pour developer", status="fault"),
                          StepState(index=1, name="2 activate", status="pending")],
                   faults=["spill detected mid-pour"], progress=0.5)
    alert = Alert(id="al1", severity="critical", code="FAULT", message="SAFE_STOP triggered")
    s = ExperimentState(mode="safe_stop", run=run, alerts=[alert])
    d = describe(s, 3)
    assert d.headline == 'Run r7 safe-stopped while 1 pour developer: spill detected mid-pour. Arms holding, grippers closed.'
    assert d.needs_human == "Open critical alert: fault - SAFE_STOP triggered."


def test_describe_estop_and_mega_fault_take_priority_over_alerts():
    s = ExperimentState(mode="idle")
    s.mega.estop = True
    s.alerts = [Alert(id="a1", severity="critical", code="SPILL", message="spill")]
    d = describe(s, 1)
    assert "e-stop is pressed" in d.needs_human
    s2 = ExperimentState(mode="idle")
    s2.mega.fault = "AUGER_JAM"
    d2 = describe(s2, 1)
    assert "AUGER_JAM" in d2.needs_human


# =============================================================================================
# b. delta() - a real Store on tmp_path, fed by hand
# =============================================================================================
def test_delta_collects_changes_across_kinds(tmp_path):
    st = Store(out_dir=tmp_path)
    st.event("step", "1 developer pour: start")
    st.event("step", "1 developer pour: ok")
    a = st.alert("SPILL", "critical", "3 g on the table")
    r = st.request_approval("run_plan", {"kind": "run_plan", "id": "x"}, "run the experiment", "agent", person="jay")
    st.event("state", "finished run r9 complete after 12.3 s")
    st.event("message", "all good?", data={"person": "sam", "space_id": "dm-sam"})

    d = delta(st, 0)
    assert any(c == "done: 1 developer pour" for c in d.changes)
    assert "1 developer pour" in d.steps_completed
    assert any(x.id == a.id for x in d.alerts_opened)
    assert any(x.id == r.id for x in d.approvals)
    assert d.run_outcome == "complete"
    assert len(d.messages) == 1 and d.messages[0].message == "all good?"
    assert d.nothing_new is False

    # a dose that lands during a matching pour step is attached, keyed by the full recipe field name
    st.update(lambda s: setattr(s, "run", RunState(run_id="r9", backend="sim",
                                                   doses={"developer_g": Dose(target=39.0, actual=38.0, error=-1.0)})))
    d2 = delta(st, 0)
    assert "developer_g" in d2.doses and d2.doses["developer_g"].actual == 38.0

    last = d.last_event_id
    d3 = delta(st, last)
    assert d3.nothing_new is True
    assert d3.changes == [] and d3.messages == []


def test_delta_tracks_alert_resolution(tmp_path):
    st = Store(out_dir=tmp_path)
    a = st.alert("OVERRUN", "warning", "late")
    st.resolve_alerts("OVERRUN")
    d = delta(st, 0)
    assert a.code in d.alerts_resolved
    assert any(x.id == a.id for x in d.alerts_opened)


# =============================================================================================
# c. approval expiry / snooze / messages (Store, tmp_path)
# =============================================================================================
def test_expire_approvals_flips_awaiting_approval_back_to_idle(tmp_path):
    st = Store(out_dir=tmp_path)
    st.approval_ttl_s = -1
    st.update(lambda s: setattr(s, "mode", "awaiting_approval"))
    r = st.request_approval("run_plan", {"kind": "run_plan", "id": "y"}, "run it", "agent", person="jay")
    assert r.status == "pending"

    snap = st.snapshot()                      # snapshot() calls expire_approvals() first
    assert st.approvals[r.id].status == "expired"
    assert snap.mode == "idle"
    assert snap.pending_approvals == []


def test_snooze_pushes_expiry_past_snoozed_until(tmp_path):
    st = Store(out_dir=tmp_path)
    st.approval_ttl_s = 60                     # 1 minute - shorter than the snooze below
    r = st.request_approval("run_plan", {"kind": "run_plan", "id": "z"}, "run it", "agent")
    before = r.expires_at

    updated = st.snooze_approval(r.id, 5)
    assert updated is not None
    assert updated.snoozed_until is not None
    assert updated.expires_at is not None and updated.expires_at > before
    assert updated.expires_at >= updated.snoozed_until
    assert st.snooze_approval("nope", 5) is None


def test_messages_filter_by_person_and_space(tmp_path):
    st = Store(out_dir=tmp_path)
    st.event("message", "hi from sam s1", data={"person": "sam", "space_id": "s1"})
    st.event("message", "hi from jay s1", data={"person": "jay", "space_id": "s1"})
    st.event("message", "hi from sam s2", data={"person": "sam", "space_id": "s2"})

    assert [e.message for e in st.messages(person="sam")] == ["hi from sam s1", "hi from sam s2"]
    assert [e.message for e in st.messages(space_id="s1")] == ["hi from sam s1", "hi from jay s1"]
    assert [e.message for e in st.messages(person="sam", space_id="s1")] == ["hi from sam s1"]


# =============================================================================================
# d. MCP + HTTP, in-process against backend.app (module-scoped: one bench build for all of them)
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
def client(app_client):
    """shared session client from conftest.py (one MCP session manager per process)"""
    return app_client


def test_mcp_start_run_idempotent_duplicate(client):
    _, appmod = client
    mcp = appmod.mcp
    rep1 = call(mcp, "start_run", recipe={"developer_g": 39, "yeast_g": 7, "water_g": 30},
               requested_by="jay", idempotency_key="dup-1", only=["1"])
    assert rep1["err"] == "NEEDS_APPROVAL"
    rid1 = rep1["data"]["request_id"]

    rep2 = call(mcp, "start_run", recipe={"developer_g": 39, "yeast_g": 7, "water_g": 30},
               requested_by="jay", idempotency_key="dup-1", only=["1"])
    assert rep2["data"]["duplicate"] is True
    assert rep2["data"]["request_id"] == rid1

    pending = [a for a in call(mcp, "list_approvals") if a["status"] == "pending"]
    assert len(pending) == 1 and pending[0]["id"] == rid1

    done = call(mcp, "decide_approval", request_id=rid1, decision="reject", by="shao")
    assert done["ok"] is True


def test_mcp_start_run_validation_suggests_fix(client):
    _, appmod = client
    rep = call(appmod.mcp, "start_run", recipe={"developer_g": 80})
    assert rep["err"] == "VALIDATION"
    assert rep["data"]["suggested_recipe"]["developer_g"] == 45
    assert isinstance(rep["data"]["suggested_fix"], str) and rep["data"]["suggested_fix"]
    assert "limits" in rep["data"]


def test_mcp_decide_approval_expired(client):
    _, appmod = client
    store = appmod.store
    old_ttl = store.approval_ttl_s
    store.approval_ttl_s = -1
    r = store.request_approval("run_plan", {"kind": "run_plan", "id": "exp1"}, "run it", "agent", person="jay")
    store.approval_ttl_s = old_ttl

    rep = call(appmod.mcp, "decide_approval", request_id=r.id, decision="approve", by="shao")
    assert rep["ok"] is False and rep["err"] == "EXPIRED"
    assert "jay" in rep["message"]


def test_mcp_decide_approval_by_agent_is_rejected(client):
    _, appmod = client
    mcp = appmod.mcp
    rep = call(mcp, "start_run", recipe={"developer_g": 39}, requested_by="sam",
              idempotency_key="agent-reject-1", only=["1"])
    rid = rep["data"]["request_id"]

    out = call(mcp, "decide_approval", request_id=rid, decision="approve", by="agent")
    assert out["ok"] is False and out["err"] == "REJECTED"
    assert appmod.store.approvals[rid].status == "pending"

    cleanup = call(mcp, "decide_approval", request_id=rid, decision="reject", by="shao")
    assert cleanup["ok"] is True


def test_mcp_thread_context_after_record_message(client):
    _, appmod = client
    mcp = appmod.mcp
    call(mcp, "record_message", channel="imessage", person="+1777", text="hello from jay", person_name="Jay")
    ctx = call(mcp, "get_thread_context", person="+1777")
    assert any(e["message"] == "hello from jay" for e in ctx)


def test_mcp_set_person_preferences_then_get_people(client):
    _, appmod = client
    mcp = appmod.mcp
    p = call(mcp, "set_person_preferences", person="+1888", name="Sam", role="operator",
            notify_on=["run_complete", "critical"],
            quiet_hours={"start": "22:00", "end": "07:00", "tz": "America/New_York"},
            preferred_channel="imessage", note="prefers texts")
    assert p["notify_on"] == ["run_complete", "critical"]
    assert p["quiet_hours"]["start"] == "22:00"
    assert p["role"] == "operator"

    people = call(mcp, "get_people")
    assert people["+1888"]["role"] == "operator"
    assert people["+1888"]["notify_on"] == ["run_complete", "critical"]
    assert people["+1888"]["notes"][-1]["note"] == "prefers texts"


def test_http_describe_validates(client):
    c, _ = client
    r = c.get("/api/describe")
    assert r.status_code == 200
    d = Describe.model_validate(r.json())
    assert d.headline


def test_http_delta_since_zero(client):
    c, _ = client
    r = c.get("/api/delta", params={"since": 0})
    assert r.status_code == 200
    d = Delta.model_validate(r.json())
    assert d.since == 0


def test_http_messages_person_filter(client):
    c, _ = client
    c.post("/api/messages", json={"channel": "sms", "person": "+1234", "text": "hey bench", "direction": "inbound"})
    r = c.get("/api/messages", params={"person": "+1234"})
    assert r.status_code == 200
    msgs = r.json()
    assert any(m["message"] == "hey bench" for m in msgs)


def test_http_patch_person(client):
    c, _ = client
    r = c.patch("/api/people/+1234", json={"notify_on": ["warning"], "role": "guest", "note": "testing"})
    assert r.status_code == 200
    body = r.json()
    assert body["notify_on"] == ["warning"]
    assert body["subscribed"] is True
    assert body["notes"][-1]["note"] == "testing"


def test_http_snooze_success(client):
    c, appmod = client
    r = appmod.store.request_approval("run_plan", {"kind": "run_plan", "id": "snooze1"}, "run it", "agent")
    resp = c.post(f"/api/approvals/{r.id}/snooze", json={"minutes": 5})
    assert resp.status_code == 200
    assert resp.json()["snoozed_until"] is not None


def test_http_snooze_unknown_404(client):
    c, _ = client
    resp = c.post("/api/approvals/does-not-exist/snooze", json={"minutes": 5})
    assert resp.status_code == 404
