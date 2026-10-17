"""Conversation-grade MCP tools, layered on mcp_server.build() without editing it:

  describe()                         two or three sentences, same wording as the frontend status line
  get_delta(since)                   what changed since an event id ("anything new?")
  start_run(...)                     replaces the basic one: idempotent, carries requested_by, explains refusals
  decide_approval(...)               replaces the basic one: EXPIRED is a distinct answer
  snooze_approval(id, minutes)       don't nag; pushes expiry
  get_thread_context(person|space)   what someone said in any channel, from the shared log
  set_person_preferences(...)        notify_on / quiet_hours / preferred_channel / role

`register(mcp, store, runner)` is called once from mcp_server.build().  Kept in its own module so the
backend/runner work (another session) and this work do not collide in one file.
"""
from __future__ import annotations

import time
import uuid
from typing import Literal

from pydantic import TypeAdapter

from backend.describe import delta as _delta, describe as _describe
from backend.schemas import Person, Plan, Recipe, RunPlanCmd
from backend.store import Store

RECIPE_LIMITS = {"developer_g": (1.0, 45.0), "yeast_g": (0.5, 10.0), "water_g": (1.0, 60.0), "activate_s": (1.0, 600.0)}


def _limits(runner) -> dict[str, tuple[float, float]]:
    lim = dict(RECIPE_LIMITS)
    cfg = getattr(runner, "cfg", None)
    if cfg is not None:
        try:
            lim["developer_g"] = (1.0, float(cfg.at("recipe.developer_max_g")))
            lim["yeast_g"] = (0.5, float(cfg.at("recipe.yeast_max_g")))
        except Exception:  # noqa: BLE001 - keep the defaults if the key is spelled differently
            pass
    return lim


def requires_for(recipe: Recipe | None) -> list[str]:
    r = recipe or Recipe()
    return [f"doses {r.developer_g:g} g of 12% peroxide (eye hazard)", f"doses {r.yeast_g:g} g yeast and {r.water_g:g} g water",
            "moves both arms, the carousel and the stage"]


def register(mcp, store: Store, runner) -> None:
    for old in ("start_run", "decide_approval"):
        try:
            mcp.remove_tool(old)
        except Exception:  # noqa: BLE001
            pass

    @mcp.tool(description="Two or three plain sentences about the bench right now (same wording as the frontend "
                          "status line): headline, detail, and what a human has to do if anything. Prefer this over "
                          "get_state for 'what's happening?'.")
    def describe() -> dict:
        s = store.snapshot()
        with store.lock:
            last = store.events[-1].id if store.events else 0
        return _describe(s, last).model_dump()

    @mcp.tool(description="What changed since an event id: steps finished, doses landed, alerts opened/resolved, "
                          "approvals requested/decided, run finished, chat messages. Use the last_event_id you were "
                          "given for this chat; nothing_new=true means say so briefly or stay quiet.")
    def get_delta(since: int = 0) -> dict:
        return _delta(store, since).model_dump()

    @mcp.tool(description="Ask to run an experiment. Validates, then creates an approval request (err NEEDS_APPROVAL "
                          "+ request_id, expires_at, requires=[why a human must decide]). A human operator must "
                          "decide via decide_approval. requested_by = the person asking (name/handle); "
                          "idempotency_key = the chat message id, so a re-sent message does not create a second "
                          "request. On VALIDATION the reply carries limits, suggested_recipe and suggested_fix.")
    def start_run(recipe: Recipe | None = None, plan: Plan | None = None, protocol_text: str = "",
                  requested_by: str = "", idempotency_key: str | None = None, speed: float = 1.0,
                  only: list[str] | None = None) -> dict:
        if idempotency_key and idempotency_key in store.idempotent:
            first = dict(store.idempotent[idempotency_key])
            first["data"] = {**first.get("data", {}), "duplicate": True}
            first["message"] = "duplicate of an earlier request; here is the first answer. " + first.get("message", "")
            return first
        cmd = RunPlanCmd(id=f"mcp-{uuid.uuid4().hex[:8]}", source="agent", recipe=recipe, plan=plan,
                         protocol_text=protocol_text, operator=requested_by, requested_by=requested_by, speed=speed,
                         only=only, approved=False, idempotency_key=idempotency_key,
                         note=f"requested over chat by {requested_by or 'someone'}")
        rep = runner.start_run(cmd)
        d = rep.model_dump()
        if rep.err == "VALIDATION":
            lim = _limits(runner)
            r0 = (recipe or Recipe()).model_dump()
            fix = {k: min(max(float(r0[k]), lo), hi) for k, (lo, hi) in lim.items() if k in r0}
            d["data"]["limits"] = {k: list(v) for k, v in lim.items()}
            if fix != {k: float(r0[k]) for k in fix}:
                d["data"]["suggested_recipe"] = fix
                d["data"]["suggested_fix"] = "clamp to " + ", ".join(f"{k} {v:g}" for k, v in fix.items() if float(r0[k]) != v)
            else:
                d["data"]["suggested_fix"] = "the plan's step order or state is impossible; use preset_plan as the base"
        if rep.err == "NEEDS_APPROVAL":
            rid = d["data"].get("request_id")
            with store.lock:
                req = store.approvals.get(rid)
                if req is not None:
                    req.requires = requires_for(recipe)
                    req.requested_by_person = requested_by
                    d["data"].update({"expires_at": req.expires_at, "requires": req.requires, "asked_of": req.asked_of})
        if idempotency_key:
            store.idempotent[idempotency_key] = d
        return d

    @mcp.tool(description="Approve or reject a pending request ON BEHALF OF a named human operator who said so in "
                          "chat. `by` must be the person's name/handle, never the agent. Approving a run starts it. "
                          "err EXPIRED means the asker must request again.")
    def decide_approval(request_id: str, decision: Literal["approve", "reject"], by: str) -> dict:
        if not by or by.lower() in ("agent", "bench", "claude", "bot", "me"):
            return {"ok": False, "err": "REJECTED", "message": "approvals must name the human who decided"}
        store.expire_approvals()
        with store.lock:
            req = store.approvals.get(request_id)
        if req is not None and req.status == "expired":
            return {"ok": False, "err": "EXPIRED", "id": request_id,
                    "message": f"that request expired at {req.expires_at}; ask {req.requested_by_person or 'the requester'} to request it again"}
        if req is not None and req.status in ("approved", "rejected"):
            return {"ok": False, "err": "STATE", "id": request_id, "message": f"already {req.status} by {req.decided_by}"}
        rep = runner.decide(request_id, decision, by)
        d = rep.model_dump()
        d["data"]["requested_by"] = req.requested_by_person if req else None
        return d

    @mcp.tool(description="Snooze a pending approval: nobody is reminded before `minutes` pass, and its expiry moves "
                          "out accordingly. Use when an operator says 'later' / 'ask me in 10'.")
    def snooze_approval(request_id: str, minutes: float = 10.0) -> dict:
        r = store.snooze_approval(request_id, minutes)
        return r.model_dump() if r else {"ok": False, "err": "STATE", "message": "no such pending request"}

    @mcp.tool(description="What a person said and was told, across every channel, oldest first; or everything in "
                          "one space. Use it when someone asks about another person's message ('what did Sam load?').")
    def get_thread_context(person: str | None = None, space_id: str | None = None, limit: int = 30) -> list[dict]:
        return [e.model_dump() for e in store.messages(person, space_id, limit)]

    @mcp.tool(description="Remember how a person wants to be treated: role (operator can approve), notify_on "
                          "(critical | warning | run_complete | approvals | all), quiet_hours {start,end,tz} (criticals "
                          "still go through), preferred_channel, name, and a free-text note.")
    def set_person_preferences(person: str, name: str | None = None,
                               role: Literal["operator", "student", "guest", "observer"] | None = None,
                               notify_on: list[Literal["critical", "warning", "run_complete", "approvals", "all"]] | None = None,
                               quiet_hours: dict | None = None, preferred_channel: str | None = None,
                               channel: str | None = None, note: str | None = None) -> dict:
        fields = dict(name=name, role=role, notify_on=notify_on, quiet_hours=quiet_hours,
                      preferred_channel=preferred_channel, channel=channel)
        if notify_on is not None:
            fields["subscribed"] = bool(notify_on)
        p = store.touch_person(person, **fields)
        if note:
            p.setdefault("notes", []).append({"ts": time.strftime("%Y-%m-%d %H:%M"), "note": note})
            store.save_people()
        try:
            return TypeAdapter(Person).validate_python(p).model_dump()
        except Exception:  # noqa: BLE001 - legacy fields in people.json
            return p
