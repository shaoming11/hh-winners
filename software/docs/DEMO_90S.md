# The 90-second demo

A judging slot is shorter than the process.  This is the end-to-end pipeline — backend, dashboard,
Photon — compressed into one slot, with every number below **measured on this laptop**, not estimated.

Sources: the conversation and its expected replies are rows of [DEMO_SCRIPT.md](DEMO_SCRIPT.md) §1;
the chemistry and the step order are [docs/demo_process.md](../../docs/demo_process.md) §4; the speed
and subset controls are [backend/README.md](../backend/README.md); the recording fallback is
[benchsim/README.md](../benchsim/README.md) "Record and replay (demo-day insurance)".

## What fits, and what doesn't

Measured, rendering on, speed 4× requested (the sim actually delivers ~3× — benchsim/README.md says
the same: 8× reaches about 3.3×):

| Plan | Steps | Wall time | Fits 90 s |
|---|---|---|---|
| **Quick preset** (`recipe.quick=true`), 20 g / 5 g / 15 g, 10 s activation | 9 | **~70 s** | yes, 20 s spare |
| Preset, same quantities, 10 s activation | 11 | 99 s | no |
| Preset, demo_process recipe (39 g / 7 g / 30 g), 60 s activation | 11 | 114 s | no |

(Step counts are for the current protocol, where the eruption rides on the final pour rather than
being its own step.)

`quick` keeps both closed-loop pours, the auger dose, the funnel transfers and the eruption.  It drops
the yeast re-weigh (`VERIFY_MASS`, whose top-up loop is the slowest step) and putting the last beaker
back, which happens after the foam anyway.

**The trade-off, stated plainly:** without the re-weigh the auger dose is never corrected.  In the
measured run the yeast landed at **4.3 g against a 5 g target** — outside the ±0.7 g tolerance the
full plan would have topped up.  The liquids are still closed-loop and land inside tolerance.  If a
judge asks where the gravimetric check is, say that this is the one step the slot cost you, and either
show the scale trace on the dashboard or run the 12-step version (99 s) instead.

## Before the clock starts

```bash
cd software
WLB_RT=1 python3 -m uvicorn backend.app:app --port 8000     # camera on; dashboard at /
cd agent && OPERATOR_PHONES=<your phone> AGENT_BOOTSTRAP_CODE=bench-2026 npm run dev
```

Then, in this order:

1. `curl -s -X POST http://127.0.0.1:8000/api/speed/4` — or click 4× on the dashboard.
2. `curl -s http://127.0.0.1:8000/api/approvals | head -c 200` — **the queue must be empty.**  A
   request left over from a rehearsal is still shown on the page and in Photon's answers.
3. `curl -s -X POST http://127.0.0.1:8000/api/command -H 'content-type: application/json' -d '{"kind":"run_control","action":"reset"}'`
   — a finished bench must be reset before it runs again.
4. Dashboard on the projector at `http://127.0.0.1:8000/`, camera on `overview`.
5. Phone in hand, agent's line open (it is the project's shared iMessage line — Photon dashboard,
   iMessage section).

Never point the agent test suite at this backend: it presses the simulated e-stop
(DEMO_SCRIPT.md §2).

## The slot

The texts are DEMO_SCRIPT.md §1 rows 1 (bootstrap), 6 (approve) and 8 (camera); the request itself is
row 11's wording with the quick plan.  The run fills the middle — you keep talking while the arms
work, which is the whole point: the bench is a colleague you text, not a dashboard you watch.

| Clock | You | What the audience sees |
|---|---|---|
| 0:00 | `i want to run the elephant toothpaste experiment` | Photon writes the plan up in plain words — what goes in, in what order — and says nothing moves until you say go.  The request appears on the dashboard. |
| 0:08 | `operator bench-2026` | "you're an operator now" — the registry is the backend's, shared with the page |
| 0:14 | `ok go ahead` | "Approved under your name — it's running now."  **This is the clock below.** |
| 0:35 | `how does it look?` | one sentence plus a camera still, in the chat |
| 1:05 | *(nothing — let it erupt)* | foam column climbs on the flask camera |
| 1:25 | *(optional)* `what did it weigh out?` | doses read back from the run record |

Asking plainly for the experiment always goes through the gate, operator or not: the plan is written
up and waits.  Two words switch it off — **"run the quick demo"** starts immediately with the short
plan (20 g / 5 g / 15 g, 10 s activation) and tells you in one line what it is doing.  Use the long
form when you want the gate on screen, the quick form when the clock is against you.

If you have a second phone, better still: let a teammate or an audience member send the request and
approve it yourself.  Then have them text `approve` too — it is refused, by name.

Measured from the moment the run starts (t=0 is your `approve`):

| t | Step |
|---|---|
| 0:01 | P1 carousel → scale |
| 0:04 | developer onto P1 — closed-loop pour on the load cell |
| 0:15 | P1 → funnel (into the flask) |
| 0:25 | P1 → carousel |
| 0:28 | yeast dose into P2 — auger |
| 0:34 | P2 → scale |
| 0:38 | water onto P2 — relative to the live reading |
| 0:51 | activate (10 s) |
| 0:54 | P2 → funnel — **the reaction starts, and the sled carries the flask at the audience** |
| 1:10 | complete |

So: `approve` at 0:14 puts the eruption at about **1:18** and the finish at **1:24**, inside the slot
with a few seconds to spare.

What the run produced, measured: peroxide 19.8 g (target 20), yeast 4.3 g (target 5, uncorrected —
see the trade-off above), warm water 14.7 g (target 15), foam peak **167 mm**, **0 g spilled**, every
step passed.

## The three things worth saying out loud

1. **Nothing moves without a human.** Photon cannot approve its own request — the backend refuses a
   `by` value like "agent" outright.  Ask someone in the audience to text `approve` from their own
   phone and it is refused: only an operator can.
2. **One bench, two views.** The page and the chat are projections of the same poll, so they cannot
   disagree (backend/README.md, `project.py`).
3. **Weigh, don't measure.** The pours are closed-loop on a load cell; commercial gravimetric dosing
   costs tens of thousands (docs/demo_process.md §1, motivation.md).

## If it goes wrong

| Symptom | Do this |
|---|---|
| The sim stutters on the projector | Drop to 2× and narrate the conversation instead; or replay a recorded run: `cd software/benchsim && python3 -m benchsim.dashboard --replay runs/dashboard/<run_id>` (plays the video with the same overlay, no simulation — benchsim/README.md) |
| Photon doesn't answer | The backend is probably down: `curl -s http://127.0.0.1:8000/api` — the agent's fallback reply says so too |
| The bench won't start | `phase` is not `ready`: reset it (step 3 above) |
| A step faults | Say what the bench said; `safe_stop` holds torque with the grippers closed and is always allowed |
| Something actually spills | Text `stop`; goggles and gloves before touching anything (12 % peroxide, eye damage) |

## Known gaps, as of 2026-10-17

Voice is not wired (no SIP provider).  The hardware backend has never run on hardware.  Servo
temperature and current are not sensed — the field is null by design.  Inbound photos **do** work now:
text a picture of the bench and it is read (HEIC converted on macOS).
