# Bench on Photon: the messaging agent

A colleague in the chat, not a dashboard.  It lives on an iMessage line (and a local terminal for
development), knows who it is talking to, answers questions about the experiment from the backend's
live state, asks an operator before anything moves, and speaks first only when the bench needs a
human: a spill, an e-stop, a fault, a finished run.

```
agent/src/
  index.ts    Spectrum message loop: record -> remember -> think -> reply (or stay silent)
  brain.ts    one Claude turn with the backend's MCP tools; group-chat judgment; safety rules
  mcp.ts      MCP client -> Anthropic tool runner tools (schemas pulled from the backend at startup)
  alerts.ts   SSE watcher: criticals at once (+ camera still), warnings batched, run summaries
  memory.ts   per-space conversation memory on disk (data/spaces/*.json)
  backend.ts  HTTP client (state, people, message write-back, alert bookkeeping)
  config.ts   env
```

## Run

```bash
cd software && WLB_RENDER=0 python3 -m uvicorn backend.app:app --port 8000     # the backend
cd software/agent && npm install && cp .env.example .env                         # fill in keys
npm run terminal          # local: a chat TUI, no phone needed (type /operator to be allowed to approve)
npm run dev               # iMessage + terminal (needs SPECTRUM_PROJECT_ID/SECRET from app.photon.codes)
```

Photon setup (hackathon beta): create a project on the dashboard, copy Project ID / Secret from
Settings, assign a shared iMessage line to the project (dashboard "iMessage" -> Add -> assign a
number from the shared pool).  `imessage.config()` discovers every line the project owns.  Put the
operators' phones in `OPERATOR_PHONES`; they are registered as operators in the backend's people
registry at startup and receive alerts.

## Behaviour worth knowing

- **Shared context.** Every inbound message and every reply is posted to `POST /api/messages`, so
  the frontend shows the conversation next to the run; the people registry (`/api/people`) is the
  backend's, so a person recognised on iMessage is the same person on the terminal or SMS.
- **Group chats.** It replies only when addressed ("Bench", "robot"), asked about the experiment,
  or asked to report; otherwise it returns `[silent]` and nothing is sent, but it still listens and
  saves facts ("I'm leaving, text me if anything happens" -> subscribed).
- **Authority.** Anyone can ask for a run: the agent builds the plan, calls `start_run` (which
  creates an approval request) and says it is waiting for an operator.  Only a person with role
  `operator` saying yes in the conversation gets `decide_approval(by=<their name>)`; the model is
  told never to put its own name in `by`, and the backend refuses `by` values like "agent".
- **Doesn't demand attention.** One message per alert (recorded on the alert as `agent:<channel>` so
  a second agent instance would not repeat it), warnings batched for 20 s, one summary per run,
  nothing during a normal run unless asked.
- **Fallbacks.** Backend down: it says so and points at the e-stop.  Model down: a templated reply
  with the backend's state.  Any doubt / spill / "stop": `run_control safe_stop` first.
- Model: `claude-opus-5`, adaptive thinking, effort medium (chat latency), prompt-cached system prompt.

## Not done yet

- Voice (SMS line + a SIP provider) - the hooks are there (`reach()` by phone) but no voice provider
  is configured.
- Reading images people send (a photo of the bench) - inbound attachments are ignored.
- The Photon beta's `PHOTON_*` REST path is not used; this is the Spectrum TS SDK.
