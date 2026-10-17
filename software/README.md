# Wet Lab Bench software: simulation + the demo

Everything the laptop runs for the bench, plus a MuJoCo digital twin of it. The **same demo
code runs in the simulator and on the hardware**; only the backend behind one interface changes.

```
software/
  bench/        the application (HAL, motion, process control, sequencer, AI layer)
  sim/          the MuJoCo bench: scene builder, physics world, chemistry model, viewer
  firmware/     Arduino Mega sketch implementing the JSON serial protocol
  scripts/      entry points: run_demo, verify_layout, fetch_so101, make_bench_config, try_step
  backend/      FastAPI service: state + log store, QA watchdog, HTTP/SSE API for the frontend, MCP for agents
  schemas/      JSON Schema of the backend contracts (HardwareCommand, ExperimentState, Event, ...)
  agent/        the Photon (iMessage/terminal) messaging agent, TypeScript, talks to backend/ over MCP
  tests/        pytest
  out/          generated: poses.json cache, run records, notebook pages, videos, backend/events.jsonl
```

Backend + agent: `backend/README.md` (API, contracts, rules) and `agent/README.md` (behaviour, setup).

**The backend runs the `benchsim` bench and serves its dashboard.** One process gives you the live
page, the HTTP/SSE API and the MCP tools over a single run, so the dashboard and the Photon agent
see the same bench. `bench/` + `sim/` below are the earlier, standalone stack (`scripts/run_demo.py`);
the backend does not use them.

```bash
cd benchsim && python3 -m benchsim.assets fetch   # once: the pinned SO-101 model (hash-checked)
python3 -m uvicorn backend.app:app --port 8000    # dashboard at /, state /api/state, SSE /api/stream, MCP /mcp
cd agent && npm install && npm run terminal       # chat with the bench locally
```

## Quick start (simulation)

```bash
pip install mujoco pyyaml numpy scipy imageio imageio-ffmpeg opencv-python pytest
bash software/scripts/fetch_so101.sh          # official SO-101 MJCF + meshes (gitignored, ~11 MB)
python3 software/scripts/make_bench_config.py # bench.yaml from layout_final.json#update13_final
python3 software/sim/build_scene.py           # bench.xml
python3 software/scripts/verify_layout.py     # margins + clearances of every planned pose
python3 software/scripts/run_demo.py --backend sim --record   # the full 10-step run -> out/run.mp4
mjpython scripts/run_demo.py --backend sim --approve --view   # the whole run, live in a window
mjpython -m sim.viewer                        # just the parked bench (run from software/)
python3 -m pytest software/tests -q
```

`--view` opens the MuJoCo viewer and paces the run to wall-clock time (`--rt 4` for 4x,
`--rt 0` flat out, `--camera overview`).  macOS needs `mjpython` for the passive viewer, so start
the whole script with it; `--approve` then matters, because under `mjpython` the script body runs
off the main thread and the interactive approval prompt is a bad place to be.  In the window:
SPACE pauses, `[` / `]` retime, `c` cycles cameras.  Closing the window mid-run is a safe stop -
the notebook and `out/run_<stamp>.json` are still written.  `--no-snap` skips the offscreen
camera renders if the live window and the offscreen renderer ever fight over GL.

`run_demo.py` runs the sequence of `docs/demo_process.md` 4 (precheck, P1 to the scale,
closed-loop developer pour to 39 g, funnel pour, auger dose, yeast verify, water pour to +30 g,
activation wait, funnel pour, ERUPT) and writes `out/run_<stamp>.json` with target vs actual for
every dose. `--only 1 2` runs a subset, `--speed 0.25` slows every arm motion.

## How the simulation replicates the bench

* **Geometry** comes from one generated file, `bench/bench.yaml`, built from
  `tools/layout/layout_final.json#update13_final` (the only passing layout) and the CAD scripts:
  arm base axes, rails, scale, carousel pockets at r 84, rack cups, auger outlet, funnel rim,
  stage crank-slider (97.3 mm travel at crank 150 deg). `sim/build_scene.py` turns it into MuJoCo.
* **Arms** are the official SO-101 MJCF (TheRobotStudio/SO-ARM100 `Simulation/SO101`, the model
  LeRobot calibrates against) with STS3215 servo dynamics, mounted so the shoulder-pan axes sit
  exactly on the documented base axes. The stock jaws are replaced by the printed fin-ray gripper
  (rigid boxes; fin-ray compliance is **not** modelled, so grasp success in sim is optimistic).
* **Joint angles** everywhere are LeRobot's "new calibration" degrees (= the MJCF zero). The
  repo's recorded CAD-angle plan (`tools/layout/anim_paths.json`) is convertible with
  `bench/motion/calib.py` (`q_mjcf = q_cad + [-2.94, -88.17, 88.69, 0.07, 2.81]`), recovered by
  fitting the six joint-axis lines of `kin_model.py` to the MJCF - no `kin.json` needed.
* **Station poses** are re-solved natively by IK (`bench/motion/stations.py`), cached in
  `out/poses.json`, and checked by `verify_layout.py` against the margin rules (>= 10 deg at
  picks/places/pours, >= 5 deg on carries, limits shrunk 5 deg). Pours are wrist-roll manifolds
  theta 55..105 deg with the lip held over the receiver (drift <= 25 mm), as designed.
* **Grasping**: a weld latches when the jaw closes on a beaker inside the finger capture region;
  the finger then physically stalls on it, so the gripper classifier sees the real signature
  (load high) and a close onto nothing reads as a miss.
* **Load cell** is a MuJoCo force sensor under the pan plus the tracked liquid mass, sampled at
  80 Hz with 0.05 g noise and HX711 quantisation; the fake Mega streams it exactly like the
  firmware (`{"w":[millis, grams]}`). Taring is host-side.
* **Chemistry** (`sim/chemistry.py`) is the plant model specified in
  `docs/software_architecture.md` 9.3: tilted-cylinder capacity, weir flow
  `q = 2/3 Cd sqrt(2g) w h^1.5`, 0.12 s fall delay, stream momentum on the pan, stream landing
  `dx = 250 mm/s * sqrt(2h/g)` deciding which vessel (or the table) receives it, auger grams per
  revolution with noise, and a foam column driven by the H2O2 and yeast masses in the flask.

* **Looks**: the printed parts are drawn with their real STLs from `exports/` (TT-01/02/03/04,
  WS-01/02, PS-01, DH-01/02, ST-05/07/11/12/13/14, RK-03 stands), the hobby servos with
  `Sandard-Servo.stl`, beakers as glass walls (`_beaker_wall/_beaker_floor.stl`), and the flask
  and funnel from generated meshes (`sim/assets/gen/`). Collision still uses the simple
  primitives (drawn invisible), so the physics is unchanged by the visuals. Liquid columns,
  pour streams and the foam are visual-only geoms driven by the chemistry model every step.
  Note for editing: MuJoCo recentres mesh assets but compensates the geom frame, so a mesh
  geom's `pos` is simply where the STL's own origin goes.

## The seam: `bench/hal/base.py`

```python
class ArmBus:   read_positions() read_load() write_goals() set_torque()   # degrees, LeRobot convention
class MegaLink: command(obj) -> reply ; samples() -> {"w":[ms,g]} / {"done":id} / {"f":code}
class Clock:    now() sleep()
```
`hal/sim.py` implements them over `sim/world.py`; `hal/real.py` implements them with LeRobot's
`SO101Follower` and pyserial. Time only advances when something waits on it, so the control
loops are identical on both.

## Moving to the hardware

1. Flash `firmware/bench_mega/bench_mega.ino` (edit the calibration constants at its top after
   `docs/electrical.md` tests E7/E8/E10: HX711 counts per gram, servo microsecond endpoints,
   auger stop pulse and feedback volts per revolution).
2. `pip install lerobot`; calibrate both arms with LeRobot; set `WLB_POURER_PORT`,
   `WLB_TRANSFER_PORT`, `WLB_MEGA_PORT`.
3. `python3 software/scripts/run_demo.py --backend real --only PRECHECK` - firmware version, scale
   rate, e-stop state, arm positions.
4. Teach/verify stations: the planned poses are a starting point; re-measure the gripper's
   contact and open angles (`bench/motion/gripper.py`, `hal/real.py` GRIPPER_DEG_TO_PCT) and
   store per-station offsets in `bench.yaml` `calibration.station_offsets_mm`.
5. First runs at `--speed 0.25` with empty beakers, then water, then the real reagents
   (`docs/demo_process.md` 5.2 checklist, goggles and gloves).

Pour constants to refit on real water pours: `calibration.weir_c`, `control.pour.cut_a_g`,
`control.pour.cut_b_s` (all in `bench.yaml`). Report pour accuracy as mean +- SD of 10 pours.

## What the simulator currently reports

Full 10-step run (`run_demo.py --backend sim --approve --record`), 409 s of bench time, ~4 min
wall: developer pour 38.75 g (target 39, -0.25), yeast 5.88 g then one top-up to 7.01 g,
water 29.67 g (-0.33), 38.77 g and 36.71 g poured into the flask, eruption with a ~180 mm foam
column. `pour_stats.py --n 10`: 38.71 +- 0.04 g (a -0.29 g bias from the cut law, which
`calibration.cut_a_g/cut_b_s` absorb on the real bench). `verify_layout.py`: all 22 planned
poses pass the margin/clearance rules; the transfer carry sits at 6 deg (recorded plan: 9.5),
the top-down grasps at 41 deg (recorded: 17.7) because the sim gripper keeps its finger faces
vertical. These are simulator numbers, not bench measurements.

Bench state the run assumes (docs/demo_process.md 5.2): P1 in the carousel pick pocket, P2 in
the next pocket (+90 deg); index +90 deg puts P2 under the auger and -90 deg brings it to the
pick pocket.

## What is and is not claimed

The simulation exercises the control logic, timing and geometry. It does not model fin-ray
compliance, liquid sloshing, or the real servo's torque curve; grasp margins and the 5.3 mm
beaker-funnel clearance still need the slow first runs on the bench. The AI layer (LLM protocol
-> validated step plan -> operator approval -> lab-notebook record) and the camera checks are
implemented here and run against the simulator; they are features of the software, not measured
properties of the assembled bench.
