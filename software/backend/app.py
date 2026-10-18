"""HTTP API for the frontend + the MCP mount for agents.

  uvicorn backend.app:app --port 8000            (from software/)
  python3 -m backend.app --backend sim --no-render

  GET  /api/state                 ExperimentState snapshot
  GET  /api/stream                SSE: `state` events (full snapshot) whenever anything changes, `ping` keepalives
  GET  /api/events?since=&limit=&kinds=a,b
  GET  /api/runs  /api/runs/{id}  history / one record (same JSON as out/run_<id>.json)
  GET  /api/alerts  POST /api/alerts/{id}/ack {by}  POST /api/alerts/{id}/notified {channel}
  GET  /api/approvals  POST /api/approvals/{id} {decision, by}
  POST /api/command               HardwareCommand -> HardwareReply (the only way anything moves)
  POST /api/plan/validate         Plan -> {ok, problems, summary}
  POST /api/plan/from_text        {text} -> Plan via Claude (falls back to the preset without a key)
  POST /api/messages              {channel, person, text, direction} - chat write-back for shared context
  GET  /api/people
  GET  /api/snapshot/{camera}.jpg   GET /api/stream.mjpg   GET /api/schemas/{name}
  /out/...                        notebook pages, stills, run videos
  /mcp                            MCP (streamable HTTP) for the Photon agent
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import os
import sys
import time
from pathlib import Path

SOFTWARE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOFTWARE / "benchsim"))     # before software/, or the namespace dir shadows benchsim
sys.path.insert(0, str(SOFTWARE))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, TypeAdapter

from backend.config import load
from backend import mcp_server
from backend.schemas import (ALL_SCHEMAS, HardwareCommand, HardwareReply, Plan)
from backend.runner import BenchRunner
from backend.store import Store

OUT_DIR = SOFTWARE / "out"
WEB = SOFTWARE / "benchsim" / "benchsim" / "dashboard" / "web"     # the dashboard page, served by the backend

BACKEND = os.environ.get("WLB_BACKEND", "sim")
RENDER = os.environ.get("WLB_RENDER", "1") != "0"
FX = os.environ.get("WLB_FX", "1") != "0"           # 0 = the bare MuJoCo scene (benchsim.dashboard --plain)
AUTOCONNECT = os.environ.get("WLB_AUTOCONNECT", "1") != "0"
REALTIME = float(os.environ.get("WLB_RT", "1"))      # 1 = pace runs to wall-clock (the demo default), 0 = flat out

cfg = load()
store = Store()
RUNS_DIR = store.dir / "runs"        # run folders live beside the store, so WLB_BACKEND_DIR moves both
runner = BenchRunner(store, cfg, backend=BACKEND, render=RENDER, realtime=REALTIME, out_root=RUNS_DIR, fx=FX)
mcp = mcp_server.build(store, runner)
mcp_app = mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    if AUTOCONNECT:
        await asyncio.get_running_loop().run_in_executor(None, _connect)
    async with mcp.session_manager.run():
        yield


def _connect() -> None:
    try:
        runner.connect()
    except Exception as e:  # noqa: BLE001
        store.event("fault", f"bench connect failed: {type(e).__name__}: {e}", level="error")
        store.update(lambda s: s.__setattr__("mode", "error"))


app = FastAPI(title="Wet Lab Bench backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
OUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/out", StaticFiles(directory=str(OUT_DIR)), name="out")
app.mount("/mcp", mcp_app)


# ---------------------------------------------------------------------------- read
def _json(model_or_list) -> Response:
    """pydantic's serializer turns NaN/inf into null; json.dumps (what FastAPI uses on a plain
    dict / model_dump(mode="json")) would raise on them.  Takes one model or a list of models."""
    if isinstance(model_or_list, list):
        body = "[" + ",".join(m.model_dump_json() for m in model_or_list) + "]"
    else:
        body = model_or_list.model_dump_json()
    return Response(body, media_type="application/json")


def _scrub(obj):
    """NaN/inf -> null in a raw dict loaded from a run record (json.loads accepts NaN tokens)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


@app.get("/api/state")
def get_state():
    return _json(store.snapshot())


@app.get("/api/stream")
async def stream(request: Request):
    async def gen():
        ver = -1
        loop = asyncio.get_running_loop()
        while True:
            if await request.is_disconnected():
                return
            nv = await loop.run_in_executor(None, store.wait, ver, 10.0)
            if nv != ver:
                ver = nv
                yield f"event: state\nid: {ver}\ndata: {store.snapshot().model_dump_json()}\n\n"
            else:
                yield "event: ping\ndata: {}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/api/events")
def get_events(since: int = 0, limit: int = 200, kinds: str | None = None):
    ks = kinds.split(",") if kinds else None
    return _json(store.events_since(since, limit, ks))


@app.get("/api/runs")
def list_runs():
    with store.lock:
        return _json(list(store.history))


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    s = store.snapshot()
    if s.run and s.run.run_id == run_id:
        return _json(s.run)
    p = OUT_DIR / f"run_{run_id}.json"
    if not p.exists():
        raise HTTPException(404, "no such run")
    return _scrub(json.loads(p.read_text()))


@app.get("/api/alerts")
def get_alerts(include_resolved: bool = False):
    with store.lock:
        return _json([a for a in store.alerts.values() if include_resolved or not a.resolved])


class By(BaseModel):
    by: str


class Channel(BaseModel):
    channel: str


@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: str, body: By):
    a = store.ack_alert(alert_id, body.by)
    if a is None:
        raise HTTPException(404, "no such alert")
    return a.model_dump(mode="json")


@app.post("/api/alerts/{alert_id}/notified")
def alert_notified(alert_id: str, body: Channel):
    with store.lock:
        if alert_id not in store.alerts:
            raise HTTPException(404, "no such alert")
    store.mark_notified(alert_id, body.channel)
    return {"ok": True}


@app.get("/api/approvals")
def get_approvals(include_decided: bool = False):
    with store.lock:
        return _json([a for a in store.approvals.values() if include_decided or a.status == "pending"])


class Decision(BaseModel):
    decision: str
    by: str


# "nothing moves without a human": the same rule the MCP tool enforces, so the HTTP path is not a
# way around it.  `by` is the person who decided, never the agent acting for itself.
NOT_A_HUMAN = {"agent", "bench", "claude", "bot", "backend", "system", ""}


@app.post("/api/approvals/{request_id}")
def decide(request_id: str, body: Decision):
    if body.by.strip().lower() in NOT_A_HUMAN:
        return JSONResponse(status_code=403, content={"id": f"apr-{request_id}", "ok": False, "err": "REJECTED",
                                                      "message": "approvals must name the human who decided",
                                                      "data": {}, "v": "0.1.0", "ts": ""})
    return runner.decide(request_id, body.decision, body.by).model_dump(mode="json")


# ---------------------------------------------------------------------------- write
@app.post("/api/command", response_model=HardwareReply)
async def command(body: dict):
    body.setdefault("id", f"http-{int(time.time() * 1000)}")
    try:
        cmd = TypeAdapter(HardwareCommand).validate_python(body)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=422, content={"id": body.get("id"), "ok": False, "err": "VALIDATION",
                                                      "message": str(e), "data": {}, "v": "0.1.0", "ts": ""})
    rep = await asyncio.get_running_loop().run_in_executor(None, runner.command, cmd)
    return rep


@app.post("/api/plan/validate")
def validate_plan(plan: Plan):
    """benchsim.process.steps.validate is the only gate; the runner imports it, never re-implements it"""
    v = runner.validate_plan(plan)
    return {"ok": v.ok, "problems": v.problems, "summary": v.summary}


class Text(BaseModel):
    text: str


@app.post("/api/plan/from_text")
def plan_from_text(body: Text):
    """benchsim.ai.pipeline: the model only proposes; a reply that leaves the vocabulary is rejected whole
    and the preset is used instead.  Validation still gates execution."""
    from benchsim.ai import pipeline
    from backend.schemas import PlanStep
    try:
        result = pipeline.run(body.text, approver=None)
        steps, notes, source = result.steps, getattr(result, "notes", ""), getattr(result, "source", "llm")
    except Exception as e:  # noqa: BLE001 - no key / no network / bad reply -> the preset
        store.event("log", f"plan_from_text fell back to the preset ({type(e).__name__}: {e})", level="warning")
        preset = runner.preset_plan()
        return preset.model_dump()
    return {"title": "from protocol text", "source": source, "notes": notes,
            "steps": [PlanStep(type=s.type, params=s.params, label=s.label).model_dump() for s in steps]}


class ChatMessage(BaseModel):
    channel: str
    person: str
    text: str
    direction: str = "inbound"
    person_name: str | None = None
    space_id: str | None = None


@app.post("/api/messages")
def post_message(m: ChatMessage):
    store.touch_person(m.person, name=m.person_name, channel=m.channel, space_id=m.space_id)
    ev = store.event("message", m.text, source="agent",
                     data={"channel": m.channel, "person": m.person, "direction": m.direction, "space_id": m.space_id})
    return {"event_id": ev.id}


@app.get("/api/people")
def people():
    with store.lock:
        return dict(store.people)


@app.get("/api/schemas/{name}")
def schema(name: str):
    if name not in ALL_SCHEMAS:
        raise HTTPException(404, f"one of {list(ALL_SCHEMAS)}")
    return TypeAdapter(ALL_SCHEMAS[name]).json_schema()


# ---------------------------------------------------------------------------- media
@app.get("/api/snapshot/{camera}.jpg")
async def snapshot(camera: str):
    jpg = await asyncio.get_running_loop().run_in_executor(None, runner.snapshot_jpeg, camera)
    if not jpg:
        raise HTTPException(404, "no frame")
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/api/stream.mjpg")
async def mjpeg(request: Request, camera: str = "overview"):
    async def gen():
        ver = -1
        loop = asyncio.get_running_loop()
        while not await request.is_disconnected():
            def wait():
                return runner.hub.wait("jpeg", ver, timeout=5.0)
            nv, jpg = await loop.run_in_executor(None, wait)
            if jpg and nv != ver:
                ver = nv
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n"
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api")
def api_index():
    return {"service": "wet-lab-bench backend", "state": "/api/state", "stream": "/api/stream", "mcp": "/mcp",
            "docs": "/docs", "dashboard": "/", "schemas": [f"/api/schemas/{n}" for n in ALL_SCHEMAS]}


from backend import routes_ux  # noqa: E402
routes_ux.register(app, store)      # /api/describe, /api/delta, /api/messages, snooze, PATCH people

# ---------------------------------------------------------------------------- the dashboard
# The page is benchsim's, unchanged: it reads `benchsim.feed/1` from /events and the camera from
# /stream.mjpg, and POSTs its control verbs to /api/<cmd>.  Serving it here is what puts the dashboard
# and the agents on one bench - the same Feed poll fills both views.
@app.get("/events")
async def feed_events(request: Request):
    async def gen():
        ver = -1
        loop = asyncio.get_running_loop()
        while not await request.is_disconnected():
            nv, snap = await loop.run_in_executor(None, runner.hub.wait, "snap", ver, 10.0)
            if nv != ver and snap is not None:
                ver = nv
                yield "data: " + snap + "\n\n"
            else:
                yield ": keepalive\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/stream.mjpg")
async def feed_mjpeg(request: Request):
    return await mjpeg(request)


class View(BaseModel):
    azimuth: float | None = None
    elevation: float | None = None
    distance: float | None = None
    lookat: list[float] | None = None


@app.post("/api/view")
async def set_view(v: View):
    """the dashboard's mouse orbit: absolute free-camera pose.  MUST stay above the /api/{cmd:path}
    catch-all below, which would otherwise swallow it as a control verb."""
    rep = await asyncio.get_running_loop().run_in_executor(
        None, lambda: runner.set_view(v.azimuth, v.elevation, v.distance, v.lookat))
    return JSONResponse(json.loads(rep.model_dump_json()), status_code=200 if rep.ok else 409)


@app.post("/api/{cmd:path}")
async def feed_command(cmd: str, request: Request):
    """the dashboard's verbs: start | stop | reset | speed/<x> | camera/<name>"""
    ok, msg = await asyncio.get_running_loop().run_in_executor(None, runner.feed_control, cmd)
    return JSONResponse({"ok": ok, "message": msg}, status_code=200 if ok else 409)


@app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
def mcp_no_slash():
    """An MCP client configured without the trailing slash falls past the /mcp mount into the static
    mount below (404 on GET, 405 on POST).  307 keeps the method and the body, so the client's
    initialize POST survives the hop and the connection just works."""
    return RedirectResponse("/mcp/", status_code=307)


@app.get("/")
def dashboard_page():
    return Response((WEB / "index.html").read_text(), media_type="text/html; charset=utf-8")


app.mount("/runs", StaticFiles(directory=str(RUNS_DIR), check_dir=False), name="runs")
app.mount("/", StaticFiles(directory=str(WEB)), name="web")


def main() -> None:
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    uvicorn.run("backend.app:app", host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
