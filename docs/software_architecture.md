# Proposed runtime software architecture (historical plan)

**Status:** This is a design proposal, not a description of the software in this checkout. Some
offline planner code is included under `software/tools/planner/`, but the planned host application,
Arduino firmware, tests and generated runtime configuration are not present. The hardware design
was later simplified; [electrical.md](electrical.md) is authoritative for final wiring and pins.

Revision 2, after the CDR of 2026-10-14. Rulings: `review/records/cdr_ruling.md`; full reasoning:
`review/records/cdr_record.json`.

> **Servo change, 2026-10-14:** the yeast auger is now the owned Feetech FB5311M-360
> continuous-rotation servo with analog position feedback (PWM on D8, feedback on A2; pins in
> `docs/electrical.md` §5). The encoder N20, the TB6612 and the TIMED fallback are gone. §6, §7
> and §11 are updated.

This document sets **how the software will be structured** before anyone writes it. The team
splits the work from it on Friday, and the design review attacks the plan rather than a pile of
code. Every item is a decision with a short reason. Section 12 maps each CDR item to the section
that implements it. Section 11 lists the risks we accepted knowingly.

At the user's instruction, no firmware or host code is written as part of this CDR. Section 9.5
gives the order the team is recommended to write it in.

> **The current CAD planner output (`~/fusion_bridge/frames.json`, 1707 frames, 142 s) is
> invalid.** It exceeds the SO-101 joint ranges, carries open beakers tilted, and puts the pour
> stream outside the receiver. Do not export or fly it. A trajectory becomes flyable only after
> the CDR-31 planner changes (§3.2) and the export audit (§3.3). `tests/test_export.py` must
> reject frames 541-599 of the current file.

## 1. What the software has to do

The demo: the operator pours *any* amount (up to the 80 mL fill line) of developer and warm
water into their reagent beakers on `RK-02`, loads yeast into the auger hopper, and hand-loads
15 mL of soap and dye into the flask. The bench then meters the recipe, adds the catalyst and
moves the flask out to erupt. Nobody touches the bench during the run, which takes 5 min or less.

| Dose | Target (demo tolerance) | How |
|---|---|---|
| Developer (12 % H2O2) | 39 g ± 2 | Arm B pours on the scale, closed loop (§5) |
| Soap + dye | 15 mL | Hand-loaded in the flask, confirmed at PRECHECK |
| Yeast | 7.0 g ± 0.7 | Auger into a carousel beaker, verified on the scale (§6) |
| Water | m_yeast_actual + 30.0 g ± 2 | Arm B pours on the scale onto the yeast (§5) |

The developer target is 39 g so that the worst case (41 g = 39.4 mL) stays under the 40 mL
thermal charge cap. The tighter "stretch" tolerances (±1.0 / ±0.5 / ±0.3 g) sit behind a
config flag. The chemistry does not need them, and they force slow correction loops.

| Actor | Hardware | Link to the laptop |
|---|---|---|
| Arm A, arm B | SO-101 follower, 6 × Feetech STS3215, Waveshare bus board each | USB serial, 1 Mbaud Feetech protocol, LeRobot 0.6.0 `FeetechMotorsBus` |
| Bench controller | Arduino Mega 2560 Pro: carousel and stage M45CHW, HX711 scale, FB5311M-360 auger servo with position feedback (servo change, 2026-10-14), INA226, servo-power relay, stage Hall sensors, e-stop input | USB serial, 250000 baud, framed protocol (§7) |
| Operator | Laptop keyboard, terminal dashboard, hardware e-stop | local |

**Pins:** the single, authoritative pin table is in `docs/electrical.md` (CDR-51). This
document names a pin only where the software meaning depends on it. It never restates the
table, and if the two disagree, `docs/electrical.md` wins.

### 1.1 Single source of truth: `config.yaml` and `tools/gen_config.py`

`software/bench/config.yaml` is **generated, never hand-edited**. `tools/gen_config.py` builds
it from:

| Input | Provides |
|---|---|
| `review/design_data.json` (CAD export) | Station and fixture poses, beaker geometry, GRIP_H, pour receiver axes and rim heights, stage and carousel geometry |
| `software/tools/planner/gripper_design.json` | Jaw kinematics, contact and opening geometry per beaker size |
| `software/bench/recipe.yaml` | Targets, tolerance sets (demo/stretch), WAIT_ACTIVATE, T_foam |
| `software/bench/calibration/*.json` (written by the tools in §3.1, §6, §7) | Joint tick0 and signs, gripper ticks and torque limit, taught fixture poses, scale counts/g, auger g/rev, stop pulse and feedback range, Mega µs limits and trims, I_trip, load thresholds, cut-law constants, idle-arm tolerances |

The planner, the exporter and the runtime all read only `config.yaml`. The file header records
the SHA-256 of every input. The runtime refuses a config whose header does not match the files
on disk. Why: the review found that the README, the planner and this document gave different
gripper angles, recipes and command sets. One generated file removes that class of bug. The
README now points at `config.yaml` and at §4/§5/§7 instead of repeating values.

## 2. Process and thread model

One Python 3.11 process runs on the demo laptop (Windows 11). The single asyncio loop of
revision 1 is gone. LeRobot's bus calls block for 3-5 ms per arm, and one stalled call would
have frozen the scale stream and the pour loop together.

```
            ┌───────────── asyncio orchestrator (state machine §4, UI, operator input) ─────────────┐
            │      queue.Queue ↓ commands                  ↑ loop.call_soon_threadsafe(events)      │
   ArmThread(A)            ArmThread(B)                  MegaThread                    LogWriter
   port A, 50 Hz           port B, 50 Hz                 Mega port                     bounded 10k queue
   ▲ goal queue (1 slot)   ▲ goal queue (1 slot)         └─ pour controller runs on each W sample
```

- **ArmThread(A), ArmThread(B), MegaThread:** each owns exactly one serial port, so no locks
  sit on a bus. Arm threads run 50 Hz `time.perf_counter` deadline loops. Every tick:
  Present_Position sync-read. Every 4th tick (12.5 Hz): Present_Load, Status (addr 65) and
  Present_Voltage.
- **`timeBeginPeriod(1)`** is called via ctypes at startup and undone at exit. Without it,
  Windows sleeps are quantised to about 15.6 ms and a 20 ms loop cannot hold its deadline.
- **Goal queue with Condition:** each arm has a 1-slot overwrite goal queue guarded by a
  `threading.Condition`. The arm thread waits on it with timeout = the next read deadline, and
  writes a new goal **immediately** when signalled instead of waiting for the next tick. Without
  this, the queue adds up to 20 ms of latency and the budget below cannot be met.
- **Pour controller placement:** the controller runs inside MegaThread's callback on every
  `W` sample. It uses Mega `millis` for dt, so host jitter does not enter the flow estimate. It
  posts tilt goals to the pouring arm's queue.
- **Orchestrator:** the asyncio loop runs the state machine and the dashboard. It talks to the
  threads only through `queue.Queue` (commands down) and `call_soon_threadsafe` (events up).
  It increments a tick counter every cycle. MegaThread sends `HB` only if that counter (and,
  during a pour, the pour controller's counter) advanced since the last HB. A hung orchestrator
  or pour loop therefore stops the heartbeat, and the Mega watchdog (§7.6) fires within 500 ms.
- **LogWriter:** a dedicated thread with a bounded queue (10 000 records). It is flushed and
  fsynced on any fault (§9.3).

### 2.1 Latency budget

| Quantity | Budget | Action if exceeded |
|---|---|---|
| Pour controller compute per W sample | ≤ 2 ms | logged |
| W sample timestamp → goal written on the arm bus | ≤ 20 ms p95 | the run is **invalid for tuning** if p95 > 30 ms |
| Arm loop overruns | counted per run | logged, shown on the dashboard |

The 20 ms figure is what the cut law (§5.4) and pour_sim (§9.1) assume. A run that misses it
can still be demonstrated, but its pour data must not be used to refit the constants.

### 2.2 Port identity and the arm fingerprint

The CH340G on the arm boards has no USB serial number, and CH340/CH343 bridges can share a
VID:PID. So ports are identified by **physical location plus an identity probe**, not by
VID:PID or serial.

1. `config.yaml` maps `ListPortInfo.location` on the labelled powered hub to `A`, `B` and `MEGA`.
2. **Mega probe:** the port is opened with `dtr=False` and `rts=False` set **before** `open()`,
   so opening the port does not reset the board. `VER` must answer `OK <seq> WLB-MEGA v1`.
3. **Arm probe and fingerprint:** each arm bus must answer Feetech pings on IDs 1-6. The six
   Homing_Offset and Min/Max_Position_Limit values must match that arm's stored fingerprint
   (recorded by `teach.py`). A mismatch or an A/B swap refuses torque and names the fault.
4. **Torque-enable rule:** Goal_Position = Present_Position is written before every
   Torque_Enable = 1, so enabling torque never snaps the arm.
5. **Step clamp:** ArmDriver clamps every goal to ≤ 5° from the last Present_Position per tick
   (≤ 250°/s at 50 Hz). `safe_stop()` goes through the same path.
6. **Disconnect rule:** ArmDriver never calls `SO101Follower.disconnect()`, because that disables
   torque and drops the beaker. `bus.disconnect(disable_torque=False)` is called only in RESET
   with both grippers open and empty.
7. A bus timeout or CRC error marks that arm `UNKNOWN` and sends it to `RECOVER`. No commands
   go to an UNKNOWN arm until a fresh Present_Position read succeeds.

### 2.3 Platform

- Windows 11 with Python 3.11 and LeRobot 0.6.0, frozen in `software/requirements.lock`. We
  rejected moving to Ubuntu: re-imaging the demo laptop two days before the flight is the larger
  risk.
- USB selective suspend off. Sleep and lid-close actions off on AC and battery. CH340/CH343
  drivers installed before Thursday.
- Laptop on battery during runs (ground isolation, CDR-47). Arm adapters are Class II only.
- Stop inputs: a global `pynput` keyboard hook (spacebar) plus the dashboard stop key, both
  calling `safety.safe_stop()`. The planned judges' web page is **cut**.

## 3. Motion: offline-planned, audited, replayed

**Decision:** the arms only replay trajectories that were planned and collision-checked
offline, then re-audited at export against the as-taught bench. There is no online planning
and **no runtime blending** toward taught poses. Blending would leave the verified corridor,
and was the reason revision 1 could not guarantee collision freedom.

The CAD planner (`plan3.py`, `planner.py`, `kin_model.py`, `grasp_model.py` and inputs) is
copied into `software/tools/planner/` together with `kin.json`, `gripper_design.json`,
`grip_frames.json` and `meshes.npz` (int16, 0.1 mm), so the repo can regenerate every
trajectory. The re-plan command and its measured run time are documented there.

### 3.1 `teach.py` calibration (CAL-01, CAL-02)

The fit uses **raw ticks**, not LeRobot's normalised degrees, because the planner's zero is the
CAD rest pose and LeRobot's normalisation hides offset and sign. Fixtures: **CAL-01** (×2,
mirrored) is a PLA block keyed into the X-front rail slot and butted against that arm's base
side face, with ≥ 4 conical seats (90°, Ø8) spanning ≥ 80 mm in Z and in X/Y. **CAL-02** is a
Ø43.0 × 100 rigid PLA probe with a 60° tip on axis, 80 mm below the grasp-centre band.

| Step | What | Why |
|---|---|---|
| (0) | Model: q_j = s_j · (tick_j − tick0_j) · 2π/4096 per joint | Raw ticks map directly to the planner's CAD-zero frame |
| (a) | +5° jog per joint, compared with the FK prediction. Flip s_j or abort before any fit | A wrong sign makes a least-squares fit converge to nonsense |
| (b) | Gripper zero per §3.5: stall ticks on the 43 mm and 56 mm beakers and on air | Commands and grasp classification are in raw ticks |
| (c) | Grip CAL-02 at the taught squeeze, torque off, hand-guide the tip into ≥ 4 cones on CAL-01 | The probe puts the grasp compliance inside the loop and gives a 70.9 mm roll lever. A virtual grasp centre cannot touch anything |
| (d) | LSQ for tick0 of joints 1-5. Accept only if RMS ≤ 3 mm **and** σ_j = RMS·√diag((JᵀJ)⁻¹) ≤ 0.5° for every joint. Then a ±15° roll cross-check with the tip in one cone must match the prediction within 1.5 mm | RMS alone passes an unobservable roll. σ_j proves each joint is observable |
| (e) | Operator confirms CAL-01 is removed. Record the 6 fixtures (carousel pick, scale, 3 rack pockets, funnel) by FK. Any fixture > 10 mm from CAD → "reclamp", or update the scene, then re-plan and re-audit | CAL-01 is not in the run-time world model. Fixture error must be fixed in the plan, not absorbed online |
| (f) | No runtime blending | See above |

Outputs go to `calibration/teach_<arm>.json` (tick0, s_j, fit statistics, fixture poses, bus
fingerprint), then through `gen_config.py`. **PRECHECK refuses to run** unless the taught poses
are newer than the last assembly timestamp.

### 3.2 Planner requirements (CDR-31; existing CAD tooling, changed by the team)

- **Joint limits:** `JOINT_LIMITS[arm][j]` from `so101_new_calib.urdf`, mapped to the CAD zero
  and shrunk 5° per side, per arm (each arm's calibration differs). They are enforced in
  `ik_grasp`, `grasp_solutions`, `make_ready`, `rrt_connect` sampling, `edge_free` and `pour()`
  at every 1.5° sample. This replaces the ±2.8 rad placeholder. If a segment becomes infeasible,
  that goes to the mechanical owner as a fixture move; the limits are not relaxed.
- **Held-beaker constraints:** a held beaker keeps its grasp-time `hinge_sign`. Outside
  declared pour segments its axis stays within 10° of +Z, enforced in `edge_free`, the `go()`
  fallbacks and RRT extend (samples projected onto the upright submanifold). The beaker centre
  moves at ≤ 250 mm/s and ≤ 1.5 m/s². Why: the old plan carried filled open beakers tilted and
  upside down.
- **Pour manifolds:** `trajectories/<pour>_manifold.json` is a 1-D table θ = 40..105° in 1°
  steps → q[0..4]. At every θ: the lip is within 8 mm horizontally of the receiver axis and
  **15-20 mm above the receiver rim (target 18)** for scale pours; for funnel pours, within
  30 mm and 20-30 mm above the funnel rim. Also Δq ≤ 2° per joint between steps, the joint
  limits, and collision-free. The approach ends on the same manifold branch under the upright
  constraint. No continuous branch → the export fails and the geometry changes.
- **Every WARN raises `PlanError`.** Warnings were how the invalid frames.json got through.
- **Shoulder keep-out:** the shoulder link stays at Z ≥ 41.4 within 10 mm (XY) of the front-row
  ISO 7380 button heads (CDR-11).
- **Scene updates:** AG-01 v2, WS-02 v2 (Ø80, 8 mm lip), ST-01 v2, cork pad (+3 mm flask, funnel
  rim Z236), new GRIP_H (100 mL: 40; 50 mL: 34 if the TT-04 walls are cut, else 37), per-station
  jaw openings (§3.6), EL-02, and FN-01 if it ships.
- **Arm A retreat** after the catalyst pour is audited against the union of stage poses for
  crank 0-73.74° (the whole WORK→ERUPT sweep).
- **Audit record:** commit `analysis/plan3_audit.txt` with frame count, voxel size,
  collisions = 0, per-move minimum clearances (arm-fixture and arm-arm), and any WARNs.

### 3.3 Trajectory export and audit (`tools/export_trajectories.py`)

The exporter cuts the plan into named segments and refuses to write anything that fails:

1. **Raw-tick check:** convert every waypoint to raw ticks with that arm's calibration. Fail,
   naming joint, segment and frame, if a tick is outside [range_min + 20, range_max − 20] or
   consecutive ticks differ by > 2048 (a 0/4095 wrap would turn the servo the long way round).
2. **Re-audit** every segment at ≤ 1° max joint step against the fin-ray meshes, beakers, the
   idle arm at its planned pose, and the §3.2 limits, tilt, speed and acceleration constraints.
3. **Refuse on WARN** anywhere in the planner log.
4. **Provenance:** each trajectory file carries the SHA-256 of `meshes.npz`, `plan3.py`,
   `planner.py`, `kin.json`, `gripper_design.json` and `config.yaml`. `player.py` refuses a
   trajectory whose hashes do not match the files in use.
5. **Gripper values stripped:** jaw commands come only from `config.yaml` (§3.5, §3.6), so a
   stale plan cannot carry stale jaw angles.

No trajectory exported before the joint-limits commit may be flown.

### 3.4 Player, single-mover token and guards

- **`player.py`** replays time-parameterised segments through the ArmThread goal queue. The
  universal **retreat** primitive is reverse replay of the executed prefix of the current
  segment at ≤ 50 % speed. Reverse replay is the only motion already proven collision-free from
  the arm's current position.
- **Single-mover token:** exactly one arm moves at a time, enforced by a global motion token.
  Before a segment starts, the idle arm must be within tol_j of its planned pose on all 6 joints
  (2° by default; 3° on shoulder_lift and elbow_flex only if Friday's static logs show > 1.5°
  steady error). The idle arm is re-checked every 0.1 s during the segment, with a stop on
  violation. Why: the plan was checked only against the other arm's *planned* pose. Zone locks
  stay as a secondary check.
- **Guards** (`guard.py`): load and tracking thresholds, status register and supply supervision
  (§8.3, §8.4).

### 3.5 Gripper: close by torque limit, classify the grasp

Revision 1 closed to an angle and inferred a miss from the end angle. That cannot work with
compliant fin-ray fingers and LeRobot's EEPROM gripper limits. **Decision: close against a
torque limit, toward a goal beyond contact, and classify in raw ticks.**

- **Teach** (§3.1 b): close slowly on the real 43 mm and 56 mm beakers and once on air
  (jaw-on-jaw), recording the stall ticks.
- **Close command:** goal = jaw-on-jaw tick minus a 1° margin (about the old −70°). RAM
  Torque_Limit (addr 48) is set ≤ the EEPROM Max_Torque_Limit of 500 that LeRobot writes. Use
  the lowest limit that gives ≥ 3.2 N axial pull-out on a water-filled 100 mL beaker with wet,
  silicone-faced fingers. Because the goal lies past contact, a real grasp always stalls short
  of it, which is what makes classification possible.
- **Squeeze** is set from the Friday hold test (default contact + 4°). The limit, squeeze and
  end ticks are stored in calibration and generated into `config.yaml`.
- **Classification**, 0.3 s after the close settles:
  - Grasp = Present_Load ≥ L_grip (measured Friday) **and** stalled ≥ 1° short of goal.
  - Miss = within 0.5° of goal **and** load < 8 %.
  - Anything else: retry once, then PAUSE.
- **Lift check:** lift 5 mm, hold 0.5 s, require < 1 mm drift before every transfer.
- **Scale cross-check:** every pick from or place on the scale must change the reading by the
  expected beaker mass ± 2 g.
- Status register (addr 65) is read at least every 0.5 s per arm. Overload, overheat or voltage
  bits → fault. The gripper protection registers are logged at connect.
- Friday hold test: 90 g at 100° tilt for 30 s with no overload bit.
- The 85 % gripper-load rule is deleted.

### 3.6 Per-station jaw openings

The jaw opening is set per station, generated into `config.yaml` from `gripper_design.json`
and the §3.5 contact ticks, and confirmed by the §3.3 audit:

| Station | Open command | Floor if the audit collides |
|---|---|---|
| Scale, rack, funnel | contact + 12° | contact + 9° |
| Carousel pick | largest opening that clears the 67.4 mm-pitch neighbours | contact + 7° |

- The approach target is offset 2.9 mm toward the moving jaw, because only one jaw moves.
- If the carousel cannot reach +7°, the operator loads the run so that the pockets on either
  side of the pick pocket are empty at that step. This is recorded in `config.yaml` and shown
  in the PRECHECK checklist.
- Friday acceptance: 20 consecutive picks per station per arm with no rim strike (descent load
  spike < 10 %) and ± 1.5 mm grasp-centre repeatability.

## 4. The run state machine

`process/recipe.py`; the recipe values come from `config.yaml`. P1 is the 50 mL measuring
beaker for the developer. P2 is the 50 mL yeast beaker.

```
IDLE → PRECHECK → INDEX_P1 → A_P1_TO_SCALE → B_POUR_DEV(39 g) → A_DEV_TO_FLASK
     → A_P1_TO_CAROUSEL → INDEX_TO_AUGER → AUGER_DOSE(85 %) → INDEX_TO_PICK → A_YEAST_TO_SCALE
     → VERIFY_YEAST ─short─► A_P2_TO_CAROUSEL → INDEX_TO_AUGER → AUGER_TOPUP (≤2) → …
     → B_POUR_WATER(m_yeast + 30 g) → WAIT_ACTIVATE → A_YEAST_TO_FLASK → STAGE_OUT → ERUPT
     → A_P2_TO_CAROUSEL → DONE

any state ──PAUSE(reason)──► PAUSED ──resume (re-check preconditions)──► same state
any state ──fault──► SAFE_STOP (per state, §8.1) ──operator──► RESET
```

- **Soap** has no state. It is hand-loaded (15 mL with dye) and confirmed at PRECHECK. This
  saves about 50 s of run time and one pour that the chemistry does not need to be precise.
- Every state has an entry precondition and a timeout (§4.3). Failing either latches a fault
  with a human-readable reason.
- **Sequencer rules:** the auger never runs during a servo move (carousel or stage), because the
  shared bus current is what the I_trip supervision measures. Only one arm moves at a time
  (§3.4).

### 4.1 PRECHECK

Every item must pass, or the run does not start:
- Port identity and arm fingerprints (§2.2). V_idle per arm within the allowed band, and the
  pack resting voltage ≥ 7.0 V (§8.3).
- Taught poses newer than the last assembly (§3.1). `config.yaml` hashes match.
- Mega: `I` banner seen, HX711 rate ≥ 70 Hz, LIM CRC valid, no latched fault, INIT accepted.
- Empty-pan zero recorded (§4.4). The no-load std is < 0.1 g over 100 samples.
- Operator checklist, each item confirmed on the dashboard: flask seated in ST-05 with the
  funnel in the neck; 15 mL soap and dye in the flask; developer and water beakers at or below
  the 80 mL line; hopper loaded (refill every 4 runs); carousel pockets loaded as configured
  (including empty neighbours if §3.6 requires them); catch well and drop cloth in place.

### 4.2 PAUSE, RESET and retreat

- **PAUSE(reason)** stops at a safe point (arms holding, auger stopped), shows the reason
  (e.g. "refill developer", "grasp miss") and resumes **at the same state**, re-running that
  state's precondition checks. In IDLE/PAUSE only, the Mega may open the servo relay after
  60 s of idle; it is re-armed via INIT when the run resumes.
- **Retreat** is reverse replay of the executed prefix of the current segment at ≤ 50 % speed
  (§3.4). Tracking-guard and grasp faults retreat, then PAUSE.
- **RESET** (operator-initiated after SAFE_STOP or at the end): stage to WORK on operator
  command; P2 back to the carousel via a planned segment; both grippers open and empty; then
  the operator checklist again. The scale→carousel and scale→auger (P2 back to its pocket, index
  to the auger) segments are planned and audited like any other.

### 4.3 Timeouts

| State type | Timeout |
|---|---|
| Pour (scale or funnel) | 45 s |
| Grasp (close + classify) | 5 s |
| Carousel / stage move | commanded duration + 2 s |
| Scale settle | 5 s |
| Auger dose (per AUG cycle set) | 60 s |
| WAIT_ACTIVATE | 60 s (fixed; shortened per §4.5) |
| Catalyst untilt → STAGE_OUT start | T_foam (§4.5) |

### 4.4 Host-side taring

The Mega reports gross grams. **All taring is on the host.** PRECHECK records an empty-pan
zero. When a beaker is first placed on the scale, its empty mass is recorded, and every target
is relative to it. Why: the old Mega `TARE` hid the reference from the logs and could not
express "water = actual yeast + 30 g". `TARE` is removed from the protocol.

### 4.5 Eruption timing rule

The catalyst must not start foaming under arm A at WORK:

1. **A_YEAST_TO_FLASK:** pour P2 (yeast and water) through the funnel, untilt, then retreat
   until the gripper is at Z > 336 (the cork pad raises the funnel rim to Z236) and outside the
   funnel zone. Arm A keeps holding P2.
2. **STAGE_OUT** starts ≤ 1.0 s after arm A is verified clear by Present_Position, and ≤ 1.5 s
   after the untilt completes. It is a 3 s smoothstep move. The ERUPT Hall (D27) must go active
   within move time + 0.5 s, otherwise `F STAGE_POS`.
3. **ERUPT.** P2 is placed back on the carousel only after the stage reports DONE at ERUPT.
4. **T_foam** (default 4 s; measured on Friday's first live run and recorded in the README) is
   a hard deadline from catalyst untilt to STAGE_OUT start. If the measured induction time
   (catalyst in → foam at the neck) is < 6 s, shorten WAIT_ACTIVATE.

### 4.6 Interlocks

| Interlock | Condition |
|---|---|
| Flask interlock on A_DEV_TO_FLASK and A_YEAST_TO_FLASK | D26 WORK Hall active, **and** EEPROM last-DONE = WORK, **and** the PRECHECK operator confirmation "flask seated, funnel in neck" |
| Pour states | HX711 rate ≥ 70 Hz, scale stable 1 s, receiver beaker's empty mass recorded |
| Stage moves | Only from the sequencer, or by operator command. After a fault, the only automatic stage move is the §8.1 STAGE_OUT completion |
| Any arm move | Motion token held, idle arm within tol_j, arm supply and pack voltage in range (§8.3) |
| Auger | No servo move in progress |

## 5. Closed-loop pour (the core of the demo)

The pouring arm (B) holds the reagent beaker and moves **along the pour manifold** (§3.2),
parameterised by the single tilt θ, with the lip 15-20 mm above the measuring beaker's rim.
The scale is the only flow sensor.

### 5.1 Scale signal chain and flow estimate

- The HX711 runs at 80 SPS (hardware RATE mod). The firmware reports the measured ready
  interval (pass: 12.5 ± 1 ms) in the `I` banner and every 10 s. The host refuses closed-loop
  pour states below 70 Hz.
- **m_f and q̂** come from a 0.5 s rolling least-squares line fit on (Mega millis, grams), with
  a 5σ outlier gate. This replaces the old median + low-pass. A line fit gives mass and slope
  from the same window with a known lag, and it uses the Mega's clock rather than host
  arrival times.
- **First drop** = q̂ > 0.5 g/s for 3 consecutive samples **and** Δm_f > 0.3 g.
- Friday test: σ_m at 80 SPS with arm B still and slewing at 10°/s. If σ_m > 0.10 g, the window
  becomes 0.8 s and the flow ceiling 5 g/s (in `config.yaml`).

### 5.2 Fill inference and approach

The reagent fill is never weighed directly; it is **inferred from θ_first**, the tilt at first
flow:
- Fast move to θ = 40° (manifold start), then ramp at 3°/s until first drop.
- V_first = V_table(θ_first) + offset_reagent. V_table comes from the tilted-cylinder model of
  the callipered BOM beaker. The offset is measured from 3 weighed-fill water pours on Friday.
- **PAUSE("refill developer")** if θ_first > θ_table(1.2 × 38.5 mL = 46 mL) ≈ 65°.
  **PAUSE("refill water")** if θ_first > θ_table(1.2 × 30 mL = 36 mL) ≈ 68-69°.
  **PAUSE("low reagent")** if the 105° manifold end is reached short of target.
- The 80 mL fill line on each reagent beaker is confirmed at PRECHECK. It bounds the overfill
  case the WS-02 lip must contain.

### 5.3 Control law: feed-forward + PI

θ = θ_ff + θ_PI along the manifold.
- **Feed-forward:** dθ_ff/dt = (dθ/dV)(V_remaining) · q̂/ρ, from the tilted-cylinder table.
  It tracks the falling liquid level, which a PI loop on flow alone cannot follow.
- **PI on flow:** Kp = 0.15°/(g/s), Ki = 0.3°/s/(g/s), conditional integration, integrator
  reset at first drop. The tilt rate is clamped to 10°/s.
- **Set-point:** q* = clamp(0.6 · (target − m_f), 1, ceiling) g/s, with a ceiling of 8 g/s
  (5 g/s if σ_m forces it, §5.1). It slows automatically near the target.
- Simulator acceptance (§9.1): q* tracked within ± 1 g/s after 1.5 s for 1-8 g/s and
  46-80 mL fills, with no sustained oscillation.

### 5.4 Cut law, untilt and drip

- **Cut** when m_f ≥ target − (a + b · q̂), with a = 0.3 g and b = 0.15 s initially, per reagent
  in `config.yaml`. The old "T_air" term double-counted in-flight mass and is deleted.
  a and b are refit by least squares on ≥ 10 Friday water pours spanning 1-8 g/s (settled error
  3 s after the cut), and again after the first live run.
- **Untilt:** δ_fast = 5° at full speed (8° if q̂_cut > 5 g/s), then ≤ 60°/s down to
  θ_cut − 15°. The two-stage untilt stops the stream quickly without sloshing a wave over
  the lip. Friday check: q̂ < 0.3 g/s within 0.15 s of the cut command.
- **Drip hold:** 1.5 s at θ_cut − 15° over the receiver, with no forward re-tilt.

### 5.5 Top-ups and tolerances

- If the settled mass (σ < 0.05 g over 0.5 s, timeout 5 s) is short by more than the tolerance:
  ramp to θ_cut − 3° at 10°/s, then +0.5° every 0.6 s until q̂ > 0.3 g/s or the cut law fires.
  PAUSE after 6 pulses. Pulses never jump straight to the flow angle, which is what excited
  slosh in revision 1.
- The approach is one-sided: an overshoot is reported, not corrected.
- **Demo tolerances:** developer 39 g ± 2; water m_yeast + 30 ± 2; yeast 7 ± 0.7. The stretch
  set is behind a flag. The dashboard shows target, actual and error for every dose.

### 5.6 Funnel pours (arm A)

A_DEV_TO_FLASK and A_YEAST_TO_FLASK follow the funnel manifold (lip 20-30 mm above the funnel
rim, within 30 mm of its axis) on a fixed tilt profile with the same untilt and drip hold.
Nothing weighs the flask, so these pours are not closed-loop. θ_first for the SAFE_STOP rule
(§8.1) is the V_table prediction from the content mass that was measured on the scale.

## 6. Auger dosing (yeast)

The yeast lands in P2 on the carousel, under the auger and **not on the scale**, because the
auger sits outside the arm workspace. Dosing is open-loop by servo revolutions and verified on
the scale when arm A brings P2 over.

- **Drive (servo change, 2026-10-14):** Feetech FB5311M-360 continuous-rotation servo with
  analog position feedback, on the switched servo bus. PWM on D8 (Timer4 OC4C), feedback on A2.
  About 1500 µs = stop; the firmware commands a speed pulse such as 1500 ± 200 µs (offset and
  sign set speed and direction; the stop centre and dosing pulse are calibrated). The firmware
  counts revolutions by unwrapping the A2 feedback angle.
- **Stall rule** (the single rule): while the auger is commanded, feedback angle progress
  < 5° in 150 ms → stop (stop pulse), reverse ¼ rev, retry. 3 stalls → `F AUGER_JAM`. This rule is
  mandatory: at full stall the Ø8 PLA `DH-02` hub is overstressed (about 15 MPa against about
  10 MPa interlayer), so the firmware must stop the servo before the screw shears.
- **Dosing:** first pass 85 % of target by `g_per_rev` (from `calibrate_auger.py`, 3 × 10 rev
  into a tared cup) → VERIFY_YEAST on the scale → fractional top-ups of
  round((target − m)/g_per_rev, 0.1) rev, at most 2. Each top-up sends P2 back to its pocket and
  indexes it to the auger. **Hopper empty** if 10 rev add < 1 g.
- Tolerance ± 0.7 g. `AUG` > 50 rev is refused by the firmware with `RANGE`.
- `calibrate_auger.py` also records the stop-pulse centre (no feedback motion at the stop pulse)
  and the feedback range (minimum, maximum and wrap point of the A2 reading).
- The auger never runs during a servo move (§4).
- **Superseded (servo change, 2026-10-14):** the encoder N20 (edges on D18/D19), the TB6612 duty
  compensation, the edge-count stall rule and the TIMED fallback.

## 7. Mega firmware and protocol (`firmware/bench_mega/`)

### 7.1 Timers and I/O

- **No Servo library.** Timer4 mode 14, prescaler 8, ICR4 = 39999 (20 ms frame),
  OCR4x = 2 · µs. Carousel on D6 (OC4A), stage on D7 (OC4B). Setpoints are loaded once per frame.
  Hardware PWM is immune to interrupt latency from the HX711 read and the UART, and dropping the
  library removes the attach-time 1500 µs pulse and the 544-2400 µs clamp trap.
- **Auger servo** on D8 (OC4C), in the same Timer4 frame: OCR4C = 2 · µs. COM4C is connected
  only while dosing; otherwise D8 is LOW and the servo is limp. **A2** reads its position
  feedback (AVcc reference) every control tick for revolution counting and the stall rule (§6).
  Timer1 is unused (servo change, 2026-10-14; it used to drive the TB6612 PWMA on D11).
- **HX711 direct-port read:** DT on PINE5 (D3), SCK on PORTG5 (D4). Started only after DOUT goes
  LOW, polled from `loop()`, never blocking. Interrupts are off only for the 25-27 clocks
  (< 35 µs total, SCK high < 50 µs). HX_TIMEOUT = max(100 ms, 4 × measured interval) →
  `F HX_TIMEOUT` and auger stop.
- **INA226** at 0x40 on D20/D21, sampled at 50 Hz: pack voltage (VBUS) and bus current.
- **A1** reads the servo bus downstream of the relay through a divider (AVcc reference).
- Bench test: a 10 min logic-analyser capture of D6/D7 while streaming W at 80 Hz, with
  ≤ 5 µs deviation.

### 7.2 Boot, relay and INIT

A Mega reset must never move a servo. Servo power is gated by a relay that is open at boot, and
the PWM is only enabled once the host confirms where the servos are.

1. **`setup()` first:** relay off (D25), D6/D7/D8 driven LOW, COM4A/B/C disconnected (D8 per
   the servo change, 2026-10-14). Then the banner
   `I BOOT <fw> <MCUSR> <hx_rate>`.
2. **`INIT <tt_us> <st_us>`** is compared with the EEPROM copy of the last pulses, which is
   written on every DONE, with a MOVING flag set at move start and cleared at move end.
   `ERR <seq> POS_UNKNOWN` if either value differs by > 20 µs, MOVING = 1, or the stage Hall
   state disagrees with st_us (D26 for the WORK pulse, D27 for ERUPT). Otherwise: close the
   relay, wait 200 ms, load OCR4A/B, enable the COM bits. Shutdown is the reverse.
3. **Operator confirmation** before INIT is needed only after an unexpected reset (the host
   latches `F_UNEXPECTED_RESET` on any `I` line after INIT), an F fault, or POS_UNKNOWN.
   **POS_UNKNOWN recovery** (the only path): relay open, flask empty; push the tray by hand to
   WORK until D26 is active; turn the deck to the painted home mark; send `INIT FORCE`, which
   loads the WORK and home pulses.
4. **RELAY_WELD:** 1.5 s after the relay is commanded open, A1 > 2 V → `F RELAY_WELD`.
5. **Idle relay-open** after 60 s applies only in IDLE/PAUSE, never mid-run. Automatic re-arm
   only if MOVING = 0 and the Halls agree.
6. The host persists the last acknowledged pulses to `state/last_pulses.json` after every DONE.
7. No RESET capacitor. A reset only makes the servos limp, and a capacitor that must be removed
   before flashing is a trap for teammates.
8. Bring-up rule: the flask stays empty until a forced reset followed by re-arm has been shown
   twice with no motion. Confirm the M45CHW is limp when powered with no pulse.

### 7.3 Framing

- 250000 baud: 0 % baud error at 16 MHz, against 2.1 % at 115200.
- Host → Mega: `<seq> <CMD> <args> *<CRC-8/ATM hex>\n`. The CRC (poly 0x07) covers the bytes
  before `*`. Mega → host lines carry the same suffix so the host can drop corrupted W samples.
- Replies: `ACK <seq>` on accept; `DONE <seq>` when a TT/ST/AUG completes;
  `ERR <seq> BUSY|RANGE|STATE|CRC|POS_UNKNOWN`. Queries (`VER`) reply `OK <seq> <payload>`.
- Out-of-range values are **rejected** with `ERR <seq> RANGE`, never silently clamped.

### 7.4 Command set

| Command | Meaning |
|---|---|
| `INIT <tt_us> <st_us>` / `INIT FORCE` | Arm servo power per §7.2 |
| `TT <us> <ms>` | Carousel to pulse, smoothstep over ms. ≥ 2 s per 45°, ≥ 4 s per 135° |
| `ST <us> <ms>` | Stage to pulse, smoothstep, ≥ 3 s |
| `AUG <revs×10> <dir>` | Auger revolutions, counted by unwrapping the A2 feedback angle; > 50 rev → RANGE |
| `CAL <counts_per_g×1000>` | Scale calibration, from `calibrate_scale.py` with the 100 g class M2 weight |
| `LIM ...` | TT/ST min/max µs and RATE min_ms_per_100us, stored in EEPROM with a CRC |
| `VER` | Identity: `OK <seq> WLB-MEGA v1` |
| `HB` | Heartbeat (§7.6) |
| `STOP` | Stop the auger (stop pulse, then D8 off), hold both servos at the current frame setpoint |
| `CLR` | Clear latched faults other than ESTOP |
| `RESET` | Clear F ESTOP (only if D2 has been LOW ≥ 500 ms) and return to the pre-INIT state |

**Motion limits in firmware:** `tools/calibrate_mega.py` writes LIM from a no-linkage sweep
(crank against a printed protractor; deck stations 0-3). For the stage, LIM is the µs equivalent
of **± 39.0° crank angle**. With the TPU sleeve the stop sits at 42.2°; the old ± 40° clamp plus
± 2° trim left only 0.2°. TT/ST are refused while the LIM CRC is invalid, and so are too-short
durations. The protocol carries µs. The host's degree view is display only.

**Stage commissioning** (before the crank is bolted): horn on the spline nearest α = 0, then the
printed 36.87°/45° gauge must show the crank within ± 1.5° of ± 36.87° at the WORK/ERUPT pulses
(worst case 40.5° against the 42.2° sleeved stop). The trim is recorded in calibration.

### 7.5 Unsolicited messages

| Message | Content |
|---|---|
| `W <millis> <raw> <grams>` | Every HX711 sample (80 Hz) |
| `V <pack_mV> <bus_mV>` | 2 Hz. Pack from INA226 VBUS, bus from A1 |
| `I <fw> <MCUSR> <hx_rate>` | At boot (`I BOOT ...`) and the HX rate every 10 s |
| `F <code> [args]` | `WDT [AUG n]`, `ESTOP`, `STALL <A>`, `AUGER_JAM`, `HX_TIMEOUT`, `STAGE_POS`, `SERVO_PWR`, `RELAY_WELD`, `NO_PACK` |

### 7.6 Watchdogs

- **Comm watchdog, 500 ms:** if no valid line arrives for 500 ms, stop the auger, hold both
  servos, emit `F WDT [AUG n]` (revolutions done), **latched until CLR and never
  auto-resumed**. Holding instead of homing is deliberate: a stage moving with nobody in
  control is worse than one that stops. HB is sent every 100 ms from MegaThread, but only if the
  orchestrator advanced (§2), so the watchdog proves that the *orchestrator* is alive, not just
  the serial thread.
- **AVR WDT, 250 ms:** reset only from the control tick. It is enabled only after a deliberate
  WDT reset has been shown to work on this board's bootloader (otherwise reflash MegaCore or a
  fixed stk500v2). The relay stays open through the reset.

### 7.7 Current supervision (I_trip)

- One INA226 measures the summed bus current. Trip when the sum > I_trip for 300 ms, or
  ≥ 8.0 A at once → PWM off, relay open, `F STALL <A>`.
- I_trip defaults to 2.5 A. On Friday it is set to 1.3 × the largest 300 ms average over a full
  dry run, clamped to 2-4 A, using the per-servo holding currents recorded at 8.4 V.
- A single stalled M45CHW (about 6.8 A) is unambiguous against a legitimate sum below 2.5 A,
  which is why one sensor is enough.

## 8. Safety

### 8.1 SAFE_STOP per state

`safety.safe_stop()` is idempotent and reachable from every path: `main()` runs in
`try/finally`; SIGINT, SIGBREAK and `atexit` all call it; so do the spacebar hook, the dashboard
stop, every latched fault, and `F ESTOP`. Torque **stays on** and grippers **never open**. The
old rule "arms hold" left a pour running, and exiting the process dropped the beaker.

| State at the fault | Arms | Mega |
|---|---|---|
| Pour, before first flow | Pouring arm to θ = 40° (manifold start), hold | STOP |
| Pour, after first flow | Pouring arm to max(40°, θ_first − 25°) at full speed, then hold | STOP |
| Carrying a beaker | Decelerate to a stop within 0.2 s, hold (upright) | STOP |
| Carousel index / auger dose | Hold | STOP (auger stopped, servos hold) |
| STAGE_OUT, or a fault after the catalyst pour passed θ_first | Arm A holds | Stage **completes STAGE_OUT** only if arm A is verified clear by Present_Position (not UNKNOWN); otherwise hold |
| Any other stage position | Hold | Stage holds. Any later stage move needs an operator command. "Stage home" is deleted |
| Arm UNKNOWN | No commands until RECOVER | STOP |

`tests/test_safe_stop.py` injects an exception before and after first flow and asserts
θ < θ_first (or θ = 40°) within 0.5 s with torque still enabled.

### 8.2 Hardware e-stop interaction

- A latching 22 mm NC mushroom with two NC blocks at the front table edge. **Pole 1** is in
  series in the LiPo bus (the carousel, stage and auger supply). **Pole 2** goes to D2
  (`INPUT_PULLUP`, NC to GND). D2 HIGH → firmware latches `F ESTOP`, PWM off, relay open.
- On `F ESTOP` the host runs the §8.1 untilt-and-hold on **both arms**. The arms run from their
  own adapters, so the e-stop does not cut them. This keeps a pour from continuing while the
  beaker stays held.
- Re-arm: D2 LOW for 500 ms, then host `RESET`, then `INIT` (with operator confirmation).
- **After a hardware e-stop the stage cannot move. If the catalyst is in, the foam stays at
  WORK.** The cloth, pads and well (CDR-19) contain it.
- Last resort: the arm adapters are on a switched strip labelled "ARMS OFF". This drops any
  held beaker, and is documented as such.
- Bring-up test: press during a slow stage move → bus < 1 V within 1 s and `F ESTOP` on the host.

### 8.3 Supply supervision

**Pack (INA226 VBUS, 2S LiPo):**

| Condition | Action |
|---|---|
| < 7.2 V | Warn |
| < 7.0 V resting (relay open or 2 s idle) | Refuse new moves |
| < 6.6 V under load for > 1 s | Fault |
| < 5 V | `F NO_PACK` |
| > 8.50 V at the arm | Warn (standard 4.20 V/cell charge; never LiHV) |
| Relay closed and A1 bus < 6.0 V | `F SERVO_PWR` |

The pack is plugged in only with the relay open (the boot default). The A0 10k/4.7k divider is
dropped: the INA226 is ± 0.1 % and does not depend on AVcc.

**Arm supplies (servo Present_Voltage):** V_idle is recorded per arm at connect. All 6 servos
are read at ≥ 10 Hz.
- < 0.92 · V_idle → warn. < 0.85 · V_idle for > 200 ms → torque-hold and `F ARM_SUPPLY`. The
  200 ms debounce avoids false trips from acceleration sag.
- Refuse to start if V_idle is outside 4.6-5.5 V or 11.0-12.6 V, unless the operator overrides
  and names the supply (logged). Thresholds are relative so that a healthy 5 V arm is not
  faulted by fixed 6.0/10.5 V limits.

### 8.4 Servo protection

- **Load:** per joint, per arm, threshold = 99.9th percentile of |Present_Load| from Friday's
  water runs + 15 points, stored in calibration. Interim value: 70 % for 0.5 s.
- **Tracking guard:** |Goal − Present| > 4° for > 0.3 s on any body joint while moving → stop,
  reverse-replay retreat, PAUSE. During pours it applies to joints 0-3 only (the wrist is the
  control actuator). It catches the light collisions that load thresholds miss.
- **Status register** (addr 65): overload, overheat or voltage bits → fault (§3.5).

### 8.5 Liquid safety

12 % hydrogen peroxide. The developer charge is capped at 40 mL (39 g ± 2). Gloves and eye
protection for the operator. The pour states depend on the §4.6 flask interlock. The WS-02 v2
lip (about 24 mL net) contains the worst-case overflow of an 80 mL-line reagent into P2 (about
13-18 mL). The README has the chemical handling notes.

## 9. Testing, modes, logging and bring-up

### 9.1 Proposed tests and simulation

This architecture document is a historical proposal. The files listed here as future tests and
controller components are not implemented in this checkout. An exploratory liquid-and-scale model
now exists at `software/sim/pour_sim.py`; see [`pour_simulation.md`](pour_simulation.md) for run
instructions and limitations.

The prototype models tilted-cylinder volume, approximate weir flow, stream travel and momentum,
scale delay/noise, and a reimplementation of the proposed pour-control logic. It does not import a
production controller because no production pour controller exists here. Its dimensions and flow
parameters have not yet been fitted against water-pour measurements, and the proposed acceptance
criterion below has not been demonstrated.

The following remain proposed offline tests, not current files: `test_protocol.py` for CRC-8/ATM
framing and a simulated Mega; `test_export.py` for trajectory limits and provenance;
`test_safe_stop.py` for §8.1; and `test_recipe.py` for state timeouts, pause/resume, reset, and
interlocks. The proposed simulation acceptance criterion is the §5.3 tracking criterion and settled
error within the demo tolerance across 46-80 mL fills. Validate that criterion only after the model
has been calibrated and compared with measured water pours.

### 9.2 Run modes

- **NORMAL:** the full state machine.
- **STEP:** Enter advances each state. Used for every first run after a change.
- **DEGRADED pour:** if the closed loop misbehaves on Friday, θ comes from the §5.2 table, the
  arm pours in 0.5 s pulses, and the scale verifies after each one, to ± 2 g.

### 9.3 Logging and provenance

Every run writes `logs/<timestamp>/` through the bounded LogWriter, fsynced on fault:
- **Per scale sample:** raw counts, grams, Mega millis, host perf_counter.
- **Per arm tick:** goal and present position; load, status and voltage at their read rate.
- **Per run:** SHA-256 of `config.yaml`, every trajectory and every calibration JSON; firmware
  version and `I` banners; status registers at 2 Hz; pack and bus mV; latency statistics (§2.1);
  every state transition, PAUSE, fault and operator override.
- **Per pour:** θ, θ_ff, θ_PI, q̂, m_f, q*, cut time and settled error, which are the refit inputs
  for §5.4.

Calibration uses a 100 g class M2 weight. 20 nickels are a logged backup only (± 0.5 % scatter).

### 9.4 Friday bring-up order

1. Mega alone: boot/relay/INIT tests (§7.2), forced-reset re-arm × 2 with no motion, WDT reset
   test, e-stop test, logic-analyser PWM capture, HX711 rate.
2. Stage commissioning with the gauge (§7.4); 3 full WORK↔ERUPT cycles on the cloth before the
   flask goes on; stage JR plug within 0.3 V of the pack during a move.
3. Scale calibration (100 g M2), no-load std, σ_m test (§5.1).
4. Auger calibration: stop-pulse centre, feedback range, g/rev, stall-rule test with a held screw.
5. Per-servo holding current at 8.4 V; 30 min hold in the pocket (< 45 °C); I_trip from a dry run.
6. Arm A: fingerprint, teach (§3.1), gripper calibration and hold test, dry replay at 30 %
   speed, 20-pick acceptance per station.
7. Arm B: the same.
8. 10 water pours, 1-8 g/s: refit a, b, offset_reagent and σ_m; confirm δ_fast.
9. Full water run (STEP, then NORMAL); set the load thresholds from its logs.
10. Real chemicals; measure T_foam on the first live run.

### 9.5 Recommended code schedule (team's choice, not a CDR deliverable)

If the team chooses to start before the Thursday flight, write in this order: Mega firmware →
MegaLink → exporter checks (§3.3) → planner moved into the repo with the §3.2 changes →
pour_sim. Everything else is Friday, in bring-up order.

## 10. Repository layout (for the future code)

```
software/
  requirements.lock            # Python 3.11 + LeRobot 0.6.0, frozen from the demo laptop
  bench/
    config.yaml                # GENERATED by tools/gen_config.py; never hand-edited
    recipe.yaml                # targets, tolerance sets, WAIT_ACTIVATE, T_foam
    calibration/               # teach_A.json, teach_B.json, scale.json, auger.json, mega.json, guards.json, pour.json
    state/last_pulses.json     # last acknowledged carousel/stage pulses
    hal/
      ports.py                 # hub-location mapping + identity probes (§2.2)
      arm.py                   # ArmDriver + ArmThread: fingerprint, torque rule, 5°/tick clamp, goal Condition
      mega.py                  # MegaLink + MegaThread: framing, CRC, ACK/DONE, HB gating, W/V/I/F parsing
    motion/
      library.py               # loads trajectories + manifolds, verifies SHA-256 provenance
      player.py                # replay, reverse-replay retreat, single-mover token
      guard.py                 # load, tracking, status, idle-arm and supply guards
      gripper.py               # torque-limited close, grasp classification, lift check
    process/
      scale.py                 # LSQ m_f/q̂ estimator, first-drop detector, host taring
      pour.py                  # FF + PI pour controller, cut law, untilt, drip, top-ups (§5)
      dose_auger.py            # 85 % pass + top-ups, feedback rev count, stall rule (§6)
      recipe.py                # run state machine, PAUSE/RESET, timeouts, interlocks (§4)
    safety.py                  # safe_stop() per state, fault latching, signal handlers
    ui.py                      # terminal dashboard (rich), operator checklist, STEP mode
    log.py                     # LogWriter thread
    main.py                    # timeBeginPeriod, try/finally, thread start-up
  firmware/bench_mega/bench_mega.ino
  tools/
    gen_config.py
    export_trajectories.py
    teach.py
    calibrate_mega.py          # LIM sweep, trims
    calibrate_scale.py
    calibrate_auger.py
    planner/                   # plan3.py, planner.py, kin_model.py, grasp_model.py, kin.json,
                               # gripper_design.json, grip_frames.json, meshes.npz
  trajectories/                # exported segments + <pour>_manifold.json (with hashes)
  sim/pour_sim.py
  tests/                       # test_protocol, test_export, test_safe_stop, test_recipe, test_pour
logs/                          # git-ignored
analysis/plan3_audit.txt       # committed audit of the current plan
```

## 11. Accepted risks

| Risk | Why accepted | Mitigation |
|---|---|---|
| Host hangs mid-pour: arm B keeps its last tilt | No independent arm cut short of ARMS OFF | HB gating stops the Mega side within 500 ms; 80 mL fill line; WS-02 v2 lip contains about 13-18 mL against about 24 mL; operator uses ARMS OFF |
| After a hardware e-stop the stage cannot move; foam erupts at WORK | The e-stop must cut the stage | Drop cloth, absorbent pads, catch well, cling film over the servo |
| ARMS OFF / barrel-jack pull drops the held beaker | Last resort only | Documented; the e-stop and safe_stop() come first |
| ST-01 v1 still fitted on Friday | v2 is mandatory before the live demo; if it is not fitted the lead signs: "stop post may fracture at the Z35.3 web top (SF≈1.0 vs 10 MPa) under a servo stall at the stop; protection is the firmware clamp plus the TPU sleeve." | ± 39° LIM, I_trip, sleeve |
| Auger jam can break `DH-02` (servo change, 2026-10-14): full servo stall gives about 15 MPa in the Ø8 PLA hub against about 10 MPa allowed | The owned servo replaces three parts and adds position feedback, but its stall torque exceeds what the screw can carry | Mandatory 150 ms feedback stall rule (§6), `DH-02` v3 at 100 % infill, 1 spare printed |
| Carousel opening below +7° | Pocket pitch is fixed | Flanking pockets left empty at that step |
| Re-plan under the joint limits proves infeasible for a segment | Limits are not relaxed | Escalated as a fixture move to mechanical |
| No flask sensor (microswitch rejected) | Would need a reprint and wiring | D26 Hall + EEPROM last-DONE + operator confirmation |
| No carousel home sensor | A mis-index is not a hazard | Grasp classification and the scale cross-check catch it |
| No RESET capacitor | The relay makes a reset limp and safe | Unexpected-reset latch, operator confirmation, INIT checks |
| AVR WDT may stay disabled | Some bootloaders reboot-loop | Enabled only after a passing test; the comm watchdog still applies |
| Windows is not real-time | Platform fixed two days before the flight | timeBeginPeriod, the goal Condition, latency logging, invalid-for-tuning rule |
| Funnel pours are open-loop | Nothing weighs the flask | Contents measured before; manifold audited; drip hold |
| Demo tolerances (± 2 / ± 0.7 g) rather than stretch | The chemistry does not need more | Stretch set behind a flag |

## 12. Decision log

| CDR | Subject | Implemented in |
|---|---|---|
| CDR-09 | Stage clamp ± 39° in EEPROM LIM, RANGE errors, ≥ 3 s moves, ± 1.5° commissioning | §7.4 |
| CDR-11 | Shoulder keep-out Z ≥ 41.4 near the front-row button heads | §3.2 |
| CDR-13 | Gripper close by torque limit, grasp classification, lift check, status reads, hold test | §3.5, §8.4 |
| CDR-14 | New GRIP_H feeding the manifolds and CAL-02 | §3.2 |
| CDR-15 | Per-station jaw openings, 2.9 mm offset, 20-pick acceptance | §3.6 |
| CDR-17 | WS-02 v2 lip; host-hang residual risk | §8.5, §11 |
| CDR-18 | Developer 39 g ± 2, 40 mL cap, cork pad (funnel rim Z236) | §1, §4.5, §5.5 |
| CDR-20 | Eruption timing, Z > 336 retreat, D27 check, T_foam, flask interlock, SAFE_STOP stage policy | §4.5, §4.6, §8.1, §8.2 |
| CDR-29 | gen_config.py single source; README defers to this document | §1.1 |
| CDR-31 | Planner limits, held-beaker constraints, manifolds, PlanError, export checks, provenance, single-mover token, keep-out, audit file; frames.json invalid | §3 (banner), §3.2, §3.3, §3.4 |
| CDR-32 | SAFE_STOP per state, try/finally and signals, no disconnect(), test_safe_stop | §2.2, §8.1, §9.1 |
| CDR-33 | teach.py with CAL-01/CAL-02, steps 0, a-f; PRECHECK freshness check | §3.1, §4.1 |
| CDR-34 | Cut law, FF + PI, fill inference, untilt, drip, top-ups, tolerances | §5.2-§5.5 |
| CDR-35 | 250000 baud, CRC-8 framing, command set, unsolicited messages, watchdog, HB gating, threads, latency budget | §2, §2.1, §7.3-§7.6 |
| CDR-36 | Recipe in config, soap hand-loaded, PAUSE/RESET/retreat, timeouts, host taring, load and tracking guards | §4, §4.2-§4.4, §8.4 |
| CDR-37 | pour_sim spec, STEP and DEGRADED modes, web page cut, Friday order | §2.3, §9.1, §9.2, §9.4, §9.5 |
| CDR-38 | Logging, hashing, platform, battery thresholds, M2 weight | §2.3, §8.3, §9.3 |
| CDR-41 | Relay boot, INIT checks, POS_UNKNOWN recovery, RELAY_WELD, dtr/rts, AVR WDT gating, idle relay-open | §2.2, §4.2, §7.2, §7.6 |
| CDR-42 | INA226 bus current, I_trip, auger never with a servo move | §4, §7.7 |
| CDR-43 | Timer4 PWM (now also D8 for the auger), direct-port HX711, HX_TIMEOUT. Timer1 20 kHz and STBY first superseded by the servo change, 2026-10-14 | §7.1, §7.2 |
| CDR-44 | 80 SPS check, LSQ estimator, first-drop rule, σ_m test | §5.1, §4.1 |
| CDR-45 | Hardware e-stop, D2 latch, both-arm untilt, ARMS OFF, host-hang risk | §8.2, §11 |
| CDR-46 | D26/D27 Halls, INA226 VBUS, A1 bus divider, SERVO_PWR; A0 divider removed | §4.5, §4.6, §7.1, §8.3 |
| CDR-47 | Laptop on battery, Class II adapters | §2.3 |
| CDR-49 | Single stall rule and dosing, now on the FB5311M-360 feedback. Encoder N20, duty compensation and TIMED fallback superseded by the servo change, 2026-10-14 | §6 |
| CDR-50 | Arm supply supervision relative to V_idle; bus UNKNOWN → RECOVER | §2.2, §8.3 |
| CDR-51 | Single pin table in docs/electrical.md | §1 |
| CDR-52 | > 8.50 V warning, pack plugged in only with the relay open | §8.3 |
| CDR-54 | Hub-location port identity, identity probes, arm fingerprint, torque-enable rule, 5° clamp | §2.2 |
