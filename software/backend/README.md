# Bench backend: state, logs, API, MCP, and the dashboard

One Python process owns the bench, keeps the experiment state and the append-only log, **serves the
benchsim dashboard**, and exposes the same state and the same gated control path to agents over MCP.
The dashboard and the Photon agent therefore share one context: what one does, the other sees.

**The bench is `benchsim`.** The backend runs `benchsim.process.sequencer` over
`benchsim.bench.make_bench`, and the live view is `benchsim.dashboard.feed.Feed` - the very feed the
dashboard has always rendered. Every feed poll is also projected into `ExperimentState`
(`project.py`) and written to the Store, so the two views are two projections of one poll and cannot
drift.  The earlier standalone `bench/` + `sim/` stack has been retired; benchsim is the bench.

```
software/backend/
  schemas.py        the contracts (Pydantic) -> software/schemas/*.json via export_schemas.py
  config.py         bench constants, read from benchsim's bench_params.toml (dotted-path `cfg.at(...)`)
  project.py        benchsim.feed/1 snapshot -> ExperimentState (arms, mega, scale, vessels, chemistry)
  store.py          state + events (out/backend/events.jsonl) + alerts + approvals + people + run history
  runner.py         one bench thread: the run, direct commands and the idle nudge; pause/safe-stop
  watchdog.py       QA rules -> Health + Alerts (spill, e-stop, fault, overruns, dose error, scale rate ...)
  mcp_server.py     MCP tools for agents (mounted at /mcp)
  app.py            FastAPI routes, SSE, MJPEG, the dashboard page, static /out and /runs
```

**One bench, one thread.** Everything that steps the world happens on a single bench thread, because
benchsim renders the camera from a world frame hook and MuJoCo's GL context deadlocks the moment a
second thread renders. HTTP threads queue a job and wait, or raise a flag (pause / stop). A direct
command is therefore refused while a run is active *or paused* - even a Mega `ping` needs the world
to advance, and a paused run is suspended inside a frame hook.

## Run

```bash
pip install fastapi uvicorn "mcp[cli]" sse-starlette      # plus the sim deps from software/README.md
cd software/benchsim && python3 -m benchsim.assets fetch  # once: the pinned SO-101 model (hash-checked)
cd software
python3 -m uvicorn backend.app:app --port 8000            # the dashboard at /, paced to wall clock
WLB_RENDER=0 python3 -m uvicorn backend.app:app --port 8000   # headless (no offscreen GL, no camera)
WLB_RT=0 ...                                              # run flat out instead of real time (tests)
open http://127.0.0.1:8000/          # the dashboard
open http://127.0.0.1:8000/docs      # the API
```

## The three contracts (`schemas.py`, JSON Schema in `software/schemas/`)

1. **HardwareCommand -> HardwareReply** (`POST /api/command`). Discriminated on `kind`:
   `carousel` `stage` `auger` `mega` `stream` `tare` | `arm_goals` `arm_torque` `gripper` `arm_station` |
   `run_plan` `run_control` `approval`.  Every command carries `id`, `source`
   (frontend|agent|operator|backend) and `note`.  Replies carry `ok`, `err`
   (RANGE|BUSY|STATE|UNKNOWN|ESTOP|REJECTED|NOT_CONNECTED|NEEDS_APPROVAL|VALIDATION|TIMEOUT|INTERNAL)
   and `data` (e.g. `request_id`, `run_id`).  Will change as the hardware comes up; `v` is the version.
2. **ExperimentState** (`GET /api/state`, SSE `/api/stream`, MCP `get_state`): `mode`, `run`
   (plan, validation, per-step status + `type`, doses, faults, progress), `arms` (with `goal_deg`
   and the `twin`), `mega`, `scale`, `vessels` (benchsim's ledger keys: `dev` `water` `hopper` `P1`
   `P2` `flask`), `chemistry` (foam height, peak, O2, H2O2 left), `health`, open `alerts`,
   `pending_approvals`, `recent_events`, `media`, `history`.
3. **Event / Alert / ApprovalRequest**: the log.  `Event.kind` in
   log|step|dose|fault|alert|command|reply|approval|camera|message|state|note.  `message` events are
   what people said to the agent (and what it answered), so the frontend can show the conversation.

## Rules the backend enforces

- Nothing moves without a human.  A `run_plan` or a motion command from `source: agent` creates an
  `ApprovalRequest`; `POST /api/approvals/{id} {decision, by}` (or MCP `decide_approval`) runs it.
  The frontend may pass `approved: true` when the operator at the bench clicked the button.
- Plans go through `benchsim.process.steps.validate` first - the only gate, imported and never
  re-implemented. It simulates where each beaker is and what it holds, so it refuses impossible
  orderings (pouring onto a beaker that is not on the scale, a pour over `max_pour_g`, anything but
  returning a beaker after ERUPT) as well as out-of-range quantities.
- A plan step is `{type, params, label}` from benchsim's vocabulary: `TRANSFER`, `POUR_TO_SCALE`,
  `POUR_TO_FUNNEL`, `CAROUSEL`, `DOSE_YEAST`, `VERIFY_MASS`, `WAIT`, `STAGE`.
- `only: ["1", "2"]` runs a subset; tokens resolve to whole labels first, so `"1"` never also
  selects `"10 ERUPT"`. The subset is validated like any other plan.
- Motion is refused (`BUSY`) while a run is active; `run_control safe_stop` is always accepted and
  holds torque with grippers closed (the sequencer's own SAFE_STOP path).
- `pause` blocks the physics at the next step; `resume` continues; `reset` (sim) rebuilds the world.
- Only one direct command executes at a time; range/busy errors from the Mega are passed through.

## Routes

| Route | For |
|---|---|
| `GET /api/state` | snapshot |
| `GET /api/stream` | SSE `state` events on every change (+ `ping`) |
| `GET /api/events?since=&limit=&kinds=` | log |
| `GET /api/runs`, `GET /api/runs/{id}` | history (same JSON as `out/run_<id>.json`) |
| `GET /api/alerts`, `POST /api/alerts/{id}/ack {by}`, `POST /api/alerts/{id}/notified {channel}` | QA |
| `GET /api/approvals`, `POST /api/approvals/{id} {decision, by}` | human gate |
| `POST /api/command` | HardwareCommand |
| `POST /api/plan/validate`, `POST /api/plan/from_text {text}` | plans |
| `POST /api/messages`, `GET /api/people` | shared conversation context |
| `GET /api/snapshot/{camera}.jpg`, `GET /api/stream.mjpg?camera=` | pictures (sim render / webcam) |
| `GET /api/schemas/{name}` | JSON Schema |
| `GET /` + `/app.js` `/style.css` | the benchsim dashboard, served unchanged |
| `GET /events` | SSE, one `benchsim.feed/1` snapshot per message (what the page reads) |
| `GET /stream.mjpg` | the sim camera |
| `POST /api/start` `stop` `reset` `speed/<x>` `camera/<name>` | the dashboard's control verbs |
| `GET /api` | the JSON service index |
| `/out/notebook/<stamp>_run.html` | lab notebook pages |
| `/mcp` | MCP streamable HTTP |

The dashboard needs no build step and no changes: it is benchsim's own page, and the backend serves
it at `/` and answers the URLs it already spoke. For a *different* frontend, read `ExperimentState`:
`const es = new EventSource("http://127.0.0.1:8000/api/stream"); es.addEventListener("state", e => render(JSON.parse(e.data)))`.
Types: `npx json-schema-to-typescript software/schemas/ExperimentState.json`.

## MCP tools

get_state, get_run, get_events, get_alerts, acknowledge_alert, mark_alert_notified, qa_check,
camera_snapshot, get_schema, validate_plan, preset_plan, start_run (-> approval), list_approvals,
decide_approval (by = the human's name), run_control, hardware_command, simulate_estop (sim),
record_message, get_people, update_person.  Resource `bench://state`.

## QA today, and what the hardware will add

The watchdog sees: e-stop, latched Mega faults, load-cell rate, spills (sim: grams that landed
outside a vessel; real: to be replaced by a webcam CV check), arm settle overruns (the precursor of
the fault that stopped run 004135), stalls / missed grasps, dose errors beyond `bench.yaml`
tolerances, a missing beaker in the scale camera before a pick, pending approvals.  Servo
temperature and current are `null`: this bench has no current sensing (the e-stop is the
protection) - the field exists so the firmware can fill it later.
