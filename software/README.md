# Wet Lab Bench software

Everything the laptop runs for the bench: a MuJoCo digital twin, the process control that drives it,
the backend that serves the dashboard and the agents, and the Photon messaging agent. The **same
process code runs in the simulator and on the hardware**; only the backend behind one interface
changes (`benchsim.bench.make_bench('sim' | 'real')`).

```
software/
  benchsim/     the bench: scene, physics, chemistry, kinematics, skills, sequencer,
                the AI layer (protocol text -> validated steps -> approval), and the live dashboard
  backend/      FastAPI service: runs benchsim, serves the dashboard, state + log store,
                QA watchdog, HTTP/SSE API, MCP for agents
  agent/        the Photon (iMessage/terminal) messaging agent, TypeScript, talks to backend/ over MCP
  schemas/      JSON Schema of the backend contracts (HardwareCommand, ExperimentState, Event, ...)
  tools/        CAD-side planners (gripper geometry, grasp model)
  docs/         demo script and notes
  tests/        pytest for backend/ (benchsim has its own suite in benchsim/tests)
  out/          generated: run records, notebook pages, videos, backend/events.jsonl
```

The firmware lives at the repository root in `firmware/mega/` (shared core, kept in parity with
`benchsim.protocol` and `benchsim.backends.sim`).

## Quick start

```bash
pip install fastapi uvicorn "mcp[cli]" sse-starlette mujoco numpy scipy imageio imageio-ffmpeg pillow pytest
cd software/benchsim && python3 -m benchsim.assets fetch   # once: the pinned SO-101 model, hash-checked (~11 MB, gitignored)
cd software && python3 -m uvicorn backend.app:app --port 8000
open http://127.0.0.1:8000/          # the live dashboard
open http://127.0.0.1:8000/docs      # the API
```

One process gives you the dashboard, the HTTP/SSE API and the MCP tools over a single run, so the
page and the agent always see the same bench. Then, for the chat agent:

```bash
cd software/agent && npm install && npm run terminal
```

Useful environment variables: `WLB_RENDER=0` (headless, no camera), `WLB_RT=0` (run flat out
instead of wall-clock pacing; the default is `1`), `WLB_BACKEND=real` (hardware).

## Running the bench without the backend

benchsim stands alone, and its README is the detailed reference for the simulation itself
(verification, kinematics, grasping, chemistry, fidelity, hardware handoff).

```bash
cd software/benchsim
python3 -m benchsim --help              # fetch, build, view, render, hw-check
python3 -m benchsim.demo_run            # the full demo headless, with video and a notebook page
python3 -m benchsim.dashboard           # the dashboard on its own simulator (no backend, no agents)
python3 -m pytest tests -q              # benchsim's own suite
```

`python3 -m benchsim.demo_run --protocol-text FILE` runs the language layer: a proposal is parsed
against the fixed step vocabulary, checked by `benchsim.process.steps.validate` (the only gate), and
only then approved and run.

## Tests

```bash
cd software && WLB_RENDER=0 WLB_RT=0 python3 -m pytest tests -q   # backend + UX
cd software/benchsim && python3 -m pytest tests -q                # the simulation
```

Never point the agent's suite at a backend that is running a live demo: it exercises the simulated
e-stop.

## Where to read next

| | |
|---|---|
| `benchsim/README.md` | the simulation: what it models, what is verified, what is assumed |
| `backend/README.md` | the contracts, the API, the rules ("nothing moves without a human") |
| `agent/README.md` | the Photon agent: behaviour, alerts, setup |
| `benchsim/docs/bringup.md` | hardware bring-up order |
| `docs/DEMO_SCRIPT.md` | the texting demo script and its test matrix |

## What is and is not claimed

The simulation exercises the control logic, timing and geometry. It does not model fin-ray
compliance, liquid sloshing, or the real servo's torque curve; grasp margins and the 5.3 mm
beaker-funnel clearance still need slow first runs on the bench. The AI layer (protocol text ->
validated step plan -> operator approval -> lab-notebook record) and the camera checks are
implemented here and run against the simulator; they are features of the software, not measured
properties of the assembled bench. The hardware backend and the firmware have been bench-tested at
the protocol level (`python3 -m benchsim hw-check`, and a first Mega bring-up), not run as a full
demo on the real bench.
