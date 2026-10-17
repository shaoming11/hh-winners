"""The one place state lives.  Thread-safe; every mutation bumps `version` and wakes SSE
listeners.  Events are appended to out/backend/events.jsonl so a restart keeps the log; run
history is read from the existing out/run_<stamp>.json records written by
the runner here (same format, so old runs show up too)."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from collections import deque
from pathlib import Path
from typing import Callable, Iterable

OUT_DIR = Path(__file__).resolve().parents[1] / "out"
from backend.schemas import (Alert, ApprovalRequest, Event, EventKind, ExperimentState, Recipe,
                             RunSummary, Source, now_iso)

# WLB_BACKEND_DIR moves the whole store (events.jsonl, people.json, run records) somewhere else.
# The test suite points it at a tmp dir so a test run never writes into the demo's shared store.
BACKEND_DIR = Path(os.environ["WLB_BACKEND_DIR"]) if os.environ.get("WLB_BACKEND_DIR") else OUT_DIR / "backend"


class Store:
    def __init__(self, out_dir: Path | None = None, keep_events: int = 2000):
        self.dir = Path(out_dir or BACKEND_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.version = 0
        self.state = ExperimentState()
        self.events: deque[Event] = deque(maxlen=keep_events)
        self.alerts: dict[str, Alert] = {}
        self.approvals: dict[str, ApprovalRequest] = {}
        self.history: list[RunSummary] = []
        self.people: dict[str, dict] = {}            # shared context: who talked to the bench, where
        self.idempotent: dict[str, dict] = {}        # idempotency_key -> first HardwareReply (as dict)
        self.approval_ttl_s = 15 * 60
        self._event_id = 0
        self._events_path = self.dir / "events.jsonl"
        self._load()

    # ------------------------------------------------------------------ persistence
    def _load(self) -> None:
        if self._events_path.exists():
            for line in self._events_path.read_text().splitlines()[-self.events.maxlen:]:
                try:
                    ev = Event.model_validate_json(line)
                except Exception:  # noqa: BLE001
                    continue
                self.events.append(ev)
                self._event_id = max(self._event_id, ev.id)
        p = self.dir / "people.json"
        if p.exists():
            try:
                self.people = json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                self.people = {}
        self.load_history()

    def load_history(self) -> None:
        out: list[RunSummary] = []
        for p in sorted(OUT_DIR.glob("run_*.json"), reverse=True):
            try:
                d = json.loads(p.read_text())
                sim = d.get("sim_state") or {}
                out.append(RunSummary(
                    run_id=p.stem.replace("run_", ""), backend=d.get("backend", "sim"),
                    started_at=d.get("started_at"), outcome=d.get("outcome", "?"),
                    recipe=Recipe(**d["recipe"]) if d.get("recipe") else None,
                    doses=_doses(d.get("doses", {})), faults=d.get("faults", []),
                    foam_h_mm=sim.get("foam_mm"), bench_seconds=float(d.get("sim_seconds", 0.0))))
            except Exception:  # noqa: BLE001
                continue
        with self.lock:
            self.history = out[:50]
            self._bump()

    def save_people(self) -> None:
        (self.dir / "people.json").write_text(json.dumps(self.people, indent=1))

    # ------------------------------------------------------------------ core
    def _bump(self) -> None:
        self.version += 1
        self.state.ts = now_iso()
        self.cond.notify_all()

    def update(self, fn: Callable[[ExperimentState], None]) -> None:
        with self.lock:
            fn(self.state)
            self._bump()

    def wait(self, version: int, timeout: float = 15.0) -> int:
        with self.lock:
            self.cond.wait_for(lambda: self.version != version, timeout)
            return self.version

    def snapshot(self) -> ExperimentState:
        self.expire_approvals()
        with self.lock:
            s = self.state.model_copy(deep=True)
            s.alerts = [a for a in self.alerts.values() if not a.resolved]
            s.pending_approvals = [a for a in self.approvals.values() if a.status == "pending"]
            s.recent_events = list(self.events)[-50:]
            s.history = self.history[:20]
            s.health.open_alerts = len(s.alerts)
            return s

    # ------------------------------------------------------------------ events
    def event(self, kind: EventKind, message: str, *, level: str = "info", source: Source = "backend",
              run_id: str | None = None, step: str | None = None, bench_t: float | None = None,
              data: dict | None = None) -> Event:
        with self.lock:
            self._event_id += 1
            if run_id is None and self.state.run is not None:
                run_id = self.state.run.run_id
            ev = Event(id=self._event_id, kind=kind, message=message, level=level, source=source,
                       run_id=run_id, step=step, bench_t=self.state.bench_t if bench_t is None else bench_t,
                       data=data or {})
            self.events.append(ev)
            with self._events_path.open("a") as f:
                f.write(ev.model_dump_json() + "\n")
            self._bump()
            return ev

    def events_since(self, since_id: int = 0, limit: int = 200, kinds: Iterable[str] | None = None) -> list[Event]:
        with self.lock:
            ks = set(kinds) if kinds else None
            out = [e for e in self.events if e.id > since_id and (ks is None or e.kind in ks)]
            return out[-limit:]

    def messages(self, person: str | None = None, space_id: str | None = None, limit: int = 50) -> list[Event]:
        """Chat messages (both directions) for a person and/or space, oldest first."""
        with self.lock:
            out = [e for e in self.events if e.kind == "message"
                   and (person is None or e.data.get("person") == person)
                   and (space_id is None or e.data.get("space_id") == space_id)]
            return out[-limit:]

    # ------------------------------------------------------------------ alerts
    def alert(self, code: str, severity: str, message: str, *, step: str | None = None,
              data: dict | None = None, dedupe: bool = True) -> Alert:
        with self.lock:
            run_id = self.state.run.run_id if self.state.run else None
            if dedupe:
                for a in self.alerts.values():
                    if not a.resolved and a.code == code and a.run_id == run_id:
                        return a
            a = Alert(id=uuid.uuid4().hex[:8], severity=severity, code=code, message=message,
                      run_id=run_id, step=step, data=data or {})
            self.alerts[a.id] = a
            self.event("alert", f"[{severity}] {code}: {message}", level="error" if severity == "critical" else "warning",
                       step=step, data={"alert_id": a.id, "code": code, "severity": severity})
            self._bump()
            return a

    def resolve_alerts(self, code: str | None = None, run_id: str | None = None) -> int:
        n = 0
        with self.lock:
            for a in self.alerts.values():
                if a.resolved:
                    continue
                if (code is None or a.code == code) and (run_id is None or a.run_id == run_id):
                    a.resolved = True
                    n += 1
            if n:
                self._bump()
        return n

    def ack_alert(self, alert_id: str, by: str) -> Alert | None:
        with self.lock:
            a = self.alerts.get(alert_id)
            if a is None:
                return None
            a.acknowledged_by, a.acknowledged_at = by, now_iso()
            if a.severity != "critical":
                a.resolved = True
            self.event("alert", f"{a.code} acknowledged by {by}", data={"alert_id": a.id})
            self._bump()
            return a

    def mark_notified(self, alert_id: str, channel: str) -> None:
        with self.lock:
            a = self.alerts.get(alert_id)
            if a and channel not in a.notified:
                a.notified.append(channel)
                self._bump()

    # ------------------------------------------------------------------ approvals
    def request_approval(self, kind: str, payload: dict, summary: str, requested_by: Source,
                         requires: list[str] | None = None, person: str = "") -> ApprovalRequest:
        with self.lock:
            exp = (datetime.now(timezone.utc) + timedelta(seconds=self.approval_ttl_s)).isoformat(timespec="seconds")
            r = ApprovalRequest(id=uuid.uuid4().hex[:8], kind=kind, payload=payload, summary=summary,
                                requested_by=requested_by, requested_by_person=person, requires=requires or [],
                                expires_at=exp, asked_of=[p["id"] for p in self.people.values() if p.get("role") == "operator"])
            self.approvals[r.id] = r
            self.event("approval", f"approval requested ({kind}): {summary}", source=requested_by,
                       data={"request_id": r.id})
            self._bump()
            return r

    def expire_approvals(self) -> list[ApprovalRequest]:
        """Pending requests past expires_at become 'expired' (the asker must re-request)."""
        now = now_iso()
        out = []
        with self.lock:
            for r in self.approvals.values():
                if r.status == "pending" and r.expires_at and r.expires_at < now:
                    r.status = "expired"
                    out.append(r)
                    self.event("approval", f"approval request {r.id} expired: {r.summary}", level="warning",
                               data={"request_id": r.id})
            if out and self.state.mode == "awaiting_approval" and not any(a.status == "pending" for a in self.approvals.values()):
                self.state.mode = "idle"
                self._bump()
        return out

    def snooze_approval(self, request_id: str, minutes: float) -> ApprovalRequest | None:
        with self.lock:
            r = self.approvals.get(request_id)
            if r is None or r.status != "pending":
                return None
            until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            r.snoozed_until = until.isoformat(timespec="seconds")
            if r.expires_at and r.expires_at < r.snoozed_until:
                r.expires_at = (until + timedelta(minutes=5)).isoformat(timespec="seconds")
            self.event("approval", f"approval {r.id} snoozed {minutes:.0f} min", data={"request_id": r.id})
            self._bump()
            return r

    def decide(self, request_id: str, decision: str, by: str) -> ApprovalRequest | None:
        self.expire_approvals()
        with self.lock:
            r = self.approvals.get(request_id)
            if r is None or r.status != "pending":
                return None
            r.status = "approved" if decision == "approve" else "rejected"
            r.decided_by, r.decided_at = by, now_iso()
            self.event("approval", f"{r.kind} {r.status} by {by}", data={"request_id": r.id})
            self._bump()
            return r

    # ------------------------------------------------------------------ people (shared context)
    def touch_person(self, person_id: str, **fields) -> dict:
        with self.lock:
            p = self.people.setdefault(person_id, {"id": person_id, "first_seen": now_iso(), "notes": []})
            p.update({k: v for k, v in fields.items() if v is not None})
            p["last_seen"] = now_iso()
            self.save_people()
            self._bump()
            return p


def _doses(d: dict) -> dict:
    from backend.schemas import Dose
    out = {}
    for k, v in d.items():
        if isinstance(v, dict) and "target" in v:
            out[k] = Dose(**{kk: vv for kk, vv in v.items() if kk in Dose.model_fields})
        elif isinstance(v, (int, float)):
            out[k] = float(v)
    return out
