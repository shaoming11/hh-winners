# Bench on iMessage: demo script and test suite

What to run, what to text, what should come back, and how we know it works.  The agent's words
vary (it is a model); the facts, the tool calls and the safety behaviour do not.

## 0. Start

```bash
cd software
WLB_RENDER=1 WLB_RT=1 python3 -m uvicorn backend.app:app --port 8000      # paced to real time, camera on
cd agent && npm run dev                                                   # iMessage + terminal
```

Env (repo-root `.env`): `ANTHROPIC_API_KEY`, `ANTHROPIC_WORKSPACE_ID` (org-level keys), `PHOTON_PROJECT_ID`,
`PHOTON_SECRET`; `AGENT_BOOTSTRAP_CODE=bench-2026` lets a phone promote itself to operator for the demo.
The agent's number is the project's shared iMessage line (Photon dashboard, iMessage section).

Seeded context: 20 past runs, teammate **Sam** (student) who loaded 70 g developer and 65 g water and asked
for a 20 g / 5 g batch that is waiting for an operator.  Dashboard: `http://127.0.0.1:8000/`.

## 1. The script

| # | You text | What happens underneath | Expected reply (shape) |
|---|---|---|---|
| 1 | `operator bench-2026` | bootstrap: `set_person_preferences(role=operator, notify_on=[all])` | "Got it, +1… is an operator now: you can approve runs and you'll get alerts here." |
| 2 | `what's the bench doing?` | `describe()` | Idle, nothing moving, a queued run from Sam (20 g developer, 5 g yeast, 30 g water) waiting for an operator, expires at HH:MM. |
| 3 | `what did Sam load?` | `get_thread_context(person=+16175550142)` | Developer 70 g and water 65 g in the rack, from his message. |
| 4 | `is it healthy?` | `qa_check()` | E-stop clear, scale 80 Hz, no open alerts; servo temperature not sensed on this bench. |
| 5 | `later, ask me in 5` | `snooze_approval(id, 5)` | "Snoozed, I'll bring it up again in 5 min; it now expires at HH:MM." Nothing else arrives for 5 min. |
| 6 | `ok approve Sam's run` | `decide_approval(id, approve, by=<you>)` | "Approved by <you>, run 2026… is going now." Run takes about 7 min at real-time pace. |
| 7 | `anything new?` (a minute later) | `get_delta(since=<last id>)` | Only the change: "P1 is on the scale, developer pour started" or "nothing new since I last told you". |
| 8 | `how does it look?` | `show_camera()` | One sentence plus a picture of the bench. |
| 9 | `text me only if something breaks` | `set_person_preferences(notify_on=[critical])` | "Will do: criticals only." The run-complete summary will NOT be sent to you. |
| 10 | `stop` | `run_control(safe_stop)` | ONE message: stopped, torque held, grippers closed, which step it was in. No "bench stopped itself", no second summary. |
| 11 | `reset and run the standard recipe` | `run_control(reset)`, `start_run(requested_by=<you>)`, `decide_approval(by=<you>)` | Reset, validated (39 g / 7 g / 30 g), started because you are an operator and said run. |
| 12 | `run it with 80 g of developer` | `start_run` -> VALIDATION with `suggested_fix` | "80 g is over the 45 g peroxide limit; want 45 g instead?" |
| 13 | send the same request twice (double-tap) | `start_run(idempotency_key=<message id>)` | One approval request, the second reply says it is the same request. |
| 14 | wait for a run to finish | alert watcher, `run_complete` | One summary with doses and foam height, only to people whose `notify_on` includes run_complete/all. |
| 15 | from a second phone (not operator): `approve` | `decide_approval` not called | "Only an operator can approve; <you> was asked." |

Group chat: add the agent to a group with Sam. Chatter ("grabbing coffee") gets silence; "Bench, how much developer went in?" gets an answer; "I'm heading out, text me if anything breaks" gets a half-sentence confirmation and `notify_on=[critical]` saved.

Unprompted messages you should see, and only these:
- a critical the bench raised itself (spill, e-stop, fault not requested by a person): one message with a camera still, to everyone with `critical`/`all`, regardless of quiet hours;
- warnings: batched, one message per 20 s window, to `warning`/`all`, not in quiet hours;
- a run finishing: one summary to `run_complete`/`all`; a safe-stop a person asked for is never announced to that person.

## 2. Testing suite

| Layer | Command | Covers |
|---|---|---|
| Backend contracts + store + watchdog + runner + HTTP + MCP | `cd software && python3 -m pytest tests/test_backend.py -q` | 31 tests: schema round-trips, NaN-safe JSON, event log persistence, alert dedupe/ack, approval request/decide, watchdog rules, approved/needs-approval/validator-rejected runs, pause/resume/safe-stop/reset, direct commands and their refusals, SSE, in-process MCP tools |
| Conversation UX | `python3 -m pytest tests/test_backend_ux.py -q` | describe() wording per mode, delta() change extraction, approval expiry + snooze, idempotent start_run, suggested_fix on VALIDATION, EXPIRED on decide, thread context, person preferences, the HTTP twins |
| Whole simulator suite | `python3 -m pytest tests -q` | the 13 original sim tests plus the above |
| Agent (no key needed) | `cd software/agent && BACKEND_URL=http://127.0.0.1:<scratch port> npm test` | MCP bridge and tool list, memory persistence and cap, alert watcher: critical at once with still, warning batching, no re-send, one summary per run, storm of state events -> one message, requested stop not announced to the requester, notify_on/quiet-hours filtering, backend client, SSE |
| Agent (live Claude) | same, with `ANTHROPIC_API_KEY` set | one real `think()` turn; `show_camera` attaches a picture |
| Types | `cd software/agent && npx tsc --noEmit` | |
| Live 4-turn conversation | `npx tsx <scratch>/live_think.mts` (see session notes) | DM answer from state; group chatter silent; non-operator request -> approval; operator "yes" -> run starts with the approver recorded |

Never run the agent suite against the demo backend: it presses the simulated e-stop.

### What each judged quality maps to

- **Context across time, channels, people**: people registry + message log are the backend's (shared with the frontend); `get_thread_context`, `lastEventId` per chat, `requested_by` on runs and in the notebook.
- **Doesn't demand attention**: `[silent]` in groups; `notify_on` / quiet hours; batching; one message per alert id; requester-aware suppression; snooze.
- **Safety and fallback**: validator + approval gate + operator role; `safe_stop` always allowed; EXPIRED requests; templated replies when the model or backend is down; e-stop rehearsal via `simulate_estop`.
- **Craft**: single bench thread, one GL thread, NaN-safe JSON, idempotent requests, 90+ automated tests.

## 3. Known gaps

Voice (SMS line + SIP provider) not wired; inbound photos ignored; hardware backend never run on hardware;
servo temperature/current not sensed (field is null by design).
