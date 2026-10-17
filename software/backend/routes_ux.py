"""HTTP twins of backend/mcp_ux.py for the frontend: `register(app, store)` from app.py.

  GET /api/describe                 Describe
  GET /api/delta?since=<event id>   Delta
  GET /api/messages?person=&space_id=&limit=   chat log (both directions)
  POST /api/approvals/{id}/snooze {minutes}
  PATCH /api/people/{id}            Person preferences (notify_on, quiet_hours, role, ...)
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

from backend.describe import delta, describe
from backend.schemas import Person
from backend.store import Store


class Snooze(BaseModel):
    minutes: float = 10.0


def register(app: FastAPI, store: Store) -> None:
    # how long a pending approval lives before the asker must re-request (demo default: 30 min)
    store.approval_ttl_s = float(os.environ.get("WLB_APPROVAL_TTL_S", 1800))

    def _json(model) -> Response:
        return Response(model.model_dump_json(), media_type="application/json")

    @app.get("/api/describe")
    def api_describe():
        s = store.snapshot()
        with store.lock:
            last = store.events[-1].id if store.events else 0
        return _json(describe(s, last))

    @app.get("/api/delta")
    def api_delta(since: int = 0):
        return _json(delta(store, since))

    @app.get("/api/messages")
    def api_messages(person: str | None = None, space_id: str | None = None, limit: int = 50):
        return [e.model_dump(mode="json") for e in store.messages(person, space_id, limit)]

    @app.post("/api/approvals/{request_id}/snooze")
    def api_snooze(request_id: str, body: Snooze):
        r = store.snooze_approval(request_id, body.minutes)
        if r is None:
            raise HTTPException(404, "no such pending request")
        return _json(r)

    @app.patch("/api/people/{person_id}")
    def api_person(person_id: str, body: dict):
        allowed = set(Person.model_fields) - {"id", "first_seen", "last_seen", "notes"}
        fields = {k: v for k, v in body.items() if k in allowed}
        if "notify_on" in fields:
            fields["subscribed"] = bool(fields["notify_on"])
        p = store.touch_person(person_id, **fields)
        note = body.get("note")
        if note:
            p.setdefault("notes", []).append({"note": note})
            store.save_people()
        return p
