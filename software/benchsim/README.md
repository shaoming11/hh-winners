# benchsim: MuJoCo simulation of the Wet Lab Bench

A runnable MuJoCo model of the bench and its 10-step demo. Two articulated SO-101 arms (the official
upstream MJCF), the load-cell scale, the carousel, the auger, the reagent rack and the slider-crank stage
are built from the final layout (`tools/layout/layout_final.json`, key `update13_final`). Liquids, yeast
and foam are analytical models, not CFD.

The original CAD planner in `software/tools/planner/` and `tools/layout/` is left untouched as the comparison
implementation. Nothing here reads `~/fusion_bridge` or `~/so101`.

## Setup

Requires Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/) (plain `pip` also works).

```bash
cd software/benchsim
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e '.[dev]'       # exact versions: requirements.lock
.venv/bin/python -m benchsim fetch                          # pinned SO-101 model, SHA-256 verified
```

`fetch` downloads `Simulation/SO101/so101_new_calib.xml` and its meshes from
[TheRobotStudio/SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100) at revision
`5f6d2b876a53a4872e405b991dd925556c9e38a4` (2026-09-23) into `third_party/so101/` (git-ignored).
`assets.lock.json` holds the revision and the SHA-256 of every file, and a mismatch aborts. The upstream model
is Apache-2.0; its `LICENSE` is fetched alongside it.

## Run

```bash
.venv/bin/python -m benchsim view       # interactive viewer, both arms parked
.venv/bin/python -m benchsim build      # compile; writes runs/model/bench.xml and fidelity.json
.venv/bin/python -m benchsim render     # PNGs from the overview, top, bench and foam cameras -> runs/renders/
.venv/bin/python -m benchsim.layout     # station table and r/bearing cross-check against update13_final
.venv/bin/python -m benchsim.cadmap     # CAD as-built pose fit (writes benchsim/config/cad_asbuilt_fit.json)
```

## Verification

```bash
.venv/bin/python -m benchsim.verify_layout   # phase 2 gate -> reports/layout_report.{md,json}
.venv/bin/python -m benchsim.meshfit         # re-fit imported CAD mesh placements -> benchsim/config/mesh_fits.json
.venv/bin/python -m benchsim.verify_kinematics   # phase 3 -> reports/kinematics_report.{md,json}, reports/native_plans.json
.venv/bin/python -m pytest -q tests
```

### Kinematics (phase 3)

- **CAD → MJCF mapping: approximate, not calibrated.** `q_mj = o + s·q_cad`. The offsets `o` come from fitting the
  upstream arm to the CAD as-built joint axes; all signs `s = +1`. Of the 32 sign combinations this is the only one
  that keeps every recorded station frame in the joint limits, and it has the lowest error by a factor of three.
  Recorded station endpoints land 3.4–10.4 mm from the stations. The binding joint matches the planner every time,
  but margins differ by a constant 1.67°, so the wrist-flex zero is uncertain by about that much.
- **Recorded-path playback: pending.** Pours replay cleanly: the lip sits within ±3 mm of the planner's 45/65 mm
  design height and carried beakers stay within 1.1° of upright. Approach and pick frames collide by the size of
  the residuals, and the planner's top-down frame puts the beaker 13–14 mm into the fixed finger.
- **The simulator uses MuJoCo-native plans.** These are solved by IK, seeded from the mapped recorded poses, and saved
  with `origin: mujoco-native` in `reports/native_plans.json`. All 8 arm steps are contact-free (penetration
  ≤ 0.5 mm) with the other arm parked. Free-motion clearance is at least 3.1 mm.
- **Open rule issues.** In the MJCF model the pourer's side-grasp picks miss the 10° pick rule: rack 1 reaches
  9.0° (GRIP_H raised 40 → 44 mm) and the scale reaches 7.5° (GRIP_H 30 → 33 mm). The pour manifold limits how
  far GRIP_H can rise. The planner reported 11.6° and 10.4° on its CAD model. These are the poses
  `demo_process.md` §8 calls the tightest.
- The transfer arm can lift a top-down beaker only about 20 mm before wrist flex runs out of margin; the recorded
  paths do the same.

Station centres in the compiled model are compared with update13_final (gate 1 mm). Because the scene is built
from the same JSON, that check guards the config → scene pipeline (unit conversion, frames). The independent
evidence that CAD and layout agree is the feature fit of part-local STLs: the RK-03 rack's three cup floors land
on the rack pockets to 0.000 mm, the TT-04 ring's four pocket bores on the r 84 pockets to 0.12 mm and its floor
on the recorded beaker-bottom Z 61.7, and the WS-02 pan floor on Z 63.7.

## Control interfaces (phase 4)

```bash
.venv/bin/python -m benchsim.exercise    # arms + every Mega mechanism + error/fault responses -> reports/exercise_report.json
```

- `benchsim/interfaces.py`: `Clock`, `ArmBackend` (positions, loads, rate-limited joint goals, torque enable) and
  `MegaTransport`, plus `MegaClient`, the host side of the Mega protocol. The process controller talks only to these.
- `benchsim/protocol.py`: one JSON-lines codec with CRC-8, shared by the simulated Mega and the serial firmware.
  Commands are `PING TT ST AUG TARE CAL STREAM STOP CLR HB`. Replies are ack/ok/done. Errors are
  `BADCMD RANGE BUSY STATE ESTOP CRC`, and out-of-range values are rejected, never clamped. Faults are `ESTOP AUGER_JAM
  HOPPER_EMPTY HX_TIMEOUT WDT TT_TIMEOUT ST_TIMEOUT AUG_TIMEOUT`. Scale samples (80 Hz) and auger progress are streamed.
- `benchsim/bench.py`: the only place a backend is chosen. `make_bench('sim')` is the default.
  `make_bench('real', allow_hardware=True)` is the hardware path.
- `benchsim/backends/sim.py`: the arm servos follow a rate-limited smoothstep through the upstream position actuators.
  `read_loads` approximates Feetech `Present_Load` as actuator force over the force limit, in per-mille; the real
  register is a duty estimate. The simulated Mega models the carousel and stage profiles with timeouts, auger
  revolutions with the electrical.md stall rule and a ¼-turn reverse, an HX711 at 80 SPS (counts, noise, quantisation)
  read from a slide-joint flexure, the 500 ms comm watchdog, the e-stop and busy states.

## Grasping and transfer (phase 5)

```bash
.venv/bin/python -m benchsim.grasp_demo      # carousel->scale, rack->scale, deliberate miss -> reports/grasp_demo/
mjpython -m benchsim view                    # (macOS) interactive viewer; the demo videos are in reports/grasp_demo/*.mp4
```

- **Holding model (simulator only).** The TPU fin-ray fingers are compliant, which rigid MuJoCo contacts cannot
  capture. A held beaker is therefore a weld constraint. It engages only when both finger contact boxes touch the
  same beaker while the jaw is driven closed. At that moment the jaw is mechanically stopped where it closed, and
  finger-to-beaker contact is switched off through the collision bits. The weld releases as soon as the jaw is
  commanded open.
- **Grasp classification (backend independent, `process/motion.py`).** The jaw is closed under its torque limit
  (0.6 N·m), 6° past contact, and classified from where it stopped: within 3° of the expected contact angle is a
  grasp, closing 2.5° past it is a miss, anything else is ambiguous. The side-grasp contact angle predicted from
  `gripper_design.json` is 7.72°, and simulated closes stop at 7.56–8.35°. The taught top-down angle is
  calibrated in simulation at 22.94° and must be re-taught on hardware.
- **Top-down technique.** Descend with the fixed finger 3 mm off the beaker (demo_process §3), move the hand 3 mm
  so the finger touches, then close. Reverse that at release, lift 20 mm and slide out along the finger channel.
  Closing straight onto the 3 mm gap pushes the beaker sideways against the TT-04 locating ribs, and the lift
  then binds.
- **Observed-state checks (`process/executor.py`).** The other arm must be parked. Every close is classified. The
  jaw must still be at contact after the lift. The scale must change by at least 8 g on a lift from the pan or a
  place onto it. Placements release 1.5 mm above the floor.
- **Evidence.** Carousel→scale grasps at 23.12° (expected 22.94°): the held beaker slips 0.01 mm and tilts 0.08°,
  and the scale rises 18.0 g on place. Rack→scale (pourer, GRIP_H 48) grasps at 8.09° (expected 7.72°) and the
  scale rises 19.3 g. With P1 removed, the jaw closes to 16.96°: a miss, so the step fails and the arm backs out.

## Liquid, pouring, auger, stage and foam (phases 6–7)

```bash
.venv/bin/python -m benchsim.pour_trials          # 10 closed-loop pours, spill cases, funnel pour -> reports/pour_report.md
.venv/bin/python -m benchsim.verify_mechanisms    # auger doses, carousel, stage, foam + camera -> reports/mechanisms_report.md
```

These are analytic models, not CFD. All coefficients are in `bench_params.toml` under `[liquid] [pour] [auger_model] [foam]`,
and the ones marked *assumed* have no measurement behind them.
- **Liquid** (`chem/liquid.py`): a tilted-cylinder volume and lip head for the held beaker, weir flow over the lip,
  stream delay plus ballistic landing, and material that misses the receiver opening goes to the spill tally. The
  liquid weight is applied to the beaker bodies, so the MuJoCo scale flexure and the HX711 model read it.
- **Pour controller** (`process/pour.py`, no MuJoCo): architecture §5. A line-fit flow estimate, feed-forward plus PI
  on flow, the cut law `a + b·q̂`, two-stage untilt, drip hold and bounded top-ups. Ki is 1.5 rather than the doc's
  0.3, because 0.3 failed the doc's own ±1 g/s tracking criterion on the synthetic plant. In simulation: **10/10
  pours within ±2 g (mean −0.28 g, SD 0.06 g, worst 0.38 g)**. Offsetting the receiver by 31–35 mm gives measured
  spills of 16.5 g and 40.5 g and a pause. The funnel pour delivers 38.58 of 39 g, landing at most 34 mm off-axis
  against the 40 mm limit.
- **Auger** (`chem/auger.py`, `mechanisms.py`): g/rev with a per-revolution spread; yeast lands in the beaker under the
  outlet; first pass at 85 %, scale check, at most 2 top-ups; stall rule, jam and hopper-empty faults. 10 doses of
  7 g: all within ±0.7 g, with a −0.18 g mean bias that comes from the assumed `recover_dispenses = false`.
- **Stage**: the MuJoCo slider-crank matches the analytic `s(θ)` within 0.0001 mm and gives **97.306 mm at 150°**.
- **Foam** (`chem/foam.py`): induction delay plus first-order H2O2 decomposition, with soap trapping O2 as foam.
  39 g of 12 % developer gives 1.68 L of O2 (demo_process: about 1.7 L). The foam column geom grows on the sled,
  and the `foam_cam` pixel count of foam colour rises 2362 → 30869.

## Full demo, run log and notebook (phases 8–9)

```bash
.venv/bin/python -m benchsim.demo_run                                   # 10-step demo -> runs/<id>/ (video, run_log.json, notebook)
.venv/bin/python -m benchsim.demo_run --stop-during-pour --no-video     # safe stop in the middle of the developer pour
.venv/bin/python -m benchsim.demo_run --protocol-text benchsim/ai/examples/elephant_toothpaste.txt --approve --no-video
.venv/bin/python -m benchsim.ai --text benchsim/ai/examples/elephant_toothpaste.txt   # proposal + validation + approval only
.venv/bin/python -m benchsim.collect_evidence runs/<id> demo_run        # copy a run into reports/
```

- **Sequencer** (`process/sequencer.py`, `process/skills.py`). Explicit states, per-step timeouts, and stop requests
  honoured at safe points. On safe stop the Mega gets STOP, a pouring arm untilts, both arms hold with torque on,
  and a gripper holding a beaker is never opened.
- **Evidence run** (`reports/demo_run/`: `demo.mp4`, `run_log.json`, `notebook.md/.html`, scale, joint and pour traces,
  camera frames). All 12 step rows passed:
  - developer 38.71 g (−0.29)
  - yeast 6.85 g (−0.15) after 1 top-up
  - water +29.77 g (−0.23)
  - funnel pours left 0.46 g and 0.39 g in the beakers
  - spill 0.002 g, ERUPT reached
  - 344 s of sim time in 107 s wall with video; the run is deterministic
- **Safe stop during the pour** (`reports/demo_safe_stop/`). The beaker is upright 1.2 s after the stop, the pourer
  still holds it with torque on, and 0.03 g spills. Every later step is skipped with the reason.
- **Language layer** (`benchsim/ai/`). Protocol text is turned into steps from the fixed vocabulary only, then the
  deterministic validator (`process/steps.validate`) checks them and the operator must approve (type `approve`, or
  pass `--approve` on the command line). It never produces actuator commands. Without an API key it falls back to
  the preset; `reports/demo_ai_protocol/` is that path run through simulation and the notebook.
- **Process finding** (it depends on assumed foam parameters). In the documented order, step 9 (P2 back to the
  carousel) comes before ERUPT. With the assumed kinetics (2 s induction, about 8 s half-life) the foam reaches the
  flask neck 4.3 s after the slurry hits the peroxide, while the stage reaches ERUPT 35 s later, so the eruption
  happens at WORK. `--erupt-before-return` swaps steps 9 and 10, but the pourer's own return still takes about
  20 s. The real induction time needs measuring before relying on an eruption at the audience position.

## Conventions

- World: +X east, +Y north, table top at Z 0 (`docs/demo_process.md` §2.1).
- Configuration and reports use millimetres and degrees. `benchsim/units.py` is the only place that converts
  to metres for MuJoCo.
- Station centres come only from `update13_final`, whose status is checked on load (`ALL 8 STEPS PASS`).
  Dimensions that update13_final does not record are in `benchsim/config/bench_params.toml`, each with its source.
- Names: arm bodies, joints, sites and actuators are prefixed `pourer/` (west) and `transfer/` (east).

## Phase 1 audit (what the checkout contains)

| Item | Found | Used for |
|---|---|---|
| `tools/layout/layout_final.json` `update13_final` | yes, status `ALL 8 STEPS PASS` | every station centre |
| `tools/layout/anim_paths.json` | 5 recorded arm steps (T1, P_dev, P_fun, T2, P_wat) + park, CAD joint convention | audit and seed poses (phase 3) |
| `docs/demo_process.md`, `docs/electrical.md` | yes | step logic, pins, limits, timeouts |
| `software/tools/planner/*.py` | kin_model, grasp_model, planner, plan3 | comparison only; they import `~/fusion_bridge/kin.json` (absent) |
| `tools/layout/layout_final.py`, `topdown.py`, `urdf_limits.py` | yes | they import `layout_lib`, `layout_study` (absent) |
| `gripper_design.json`, `grip_frames.json` | yes | fin-ray finger geometry, grasp centres |
| `exports/prints_v2/*.stl` | 78 STLs | GR-01/02/03 are in assembly coordinates (arm A as built) and are imported; the rest are part-local |
| `exports/assembly/wet-lab-bench_WORK.f3d` | yes | not readable without Fusion |
| `~/fusion_bridge/{kin.json, meshes.json, layout_lib.py}`, `~/so101/*.urdf` | **absent** | not used |
| Run-time host app, Arduino firmware | **absent** (README says so) | written in later phases |

Known disagreements found so far (the JSON coordinates are authoritative):

| Check | Recomputed from update13_final | Recorded | Note |
|---|---|---|---|
| pourer → scale bearing | +49.1° | +47° | r agrees (294.4) |
| transfer → carousel pick bearing | +46.8° | +48° | r 191.2 vs 191.1 |
| transfer → scale bearing | +4.5° | −5° | sign error in the recorded table |
| CAD wrist-roll axis | 7.4 mm off the MJCF roll axis laterally | – | the other five axes fit within 1.1 mm (`cadmap`) |
| CAD park pose `[30, 60, −150, 30, 0]` | maps to a near-vertical arm in MJCF | demo_process calls it "folded" | clear of everything; kept as recorded |
