# Independent reference simulator

This is a second, separate implementation for comparing simulation assumptions in this branch.
It reads the final layout from `tools/layout/layout_final.json` (`update13_final`) and fetches a
pinned copy of the SO-101 MuJoCo model on the first setup. It does not edit the source CAD or the
existing offline planner.

## Run it

From the repository root:

```sh
python3 -m venv software/reference_sim/.venv
software/reference_sim/.venv/bin/pip install -r software/reference_sim/requirements.txt
software/reference_sim/.venv/bin/python software/reference_sim/fetch_so101.py
software/reference_sim/.venv/bin/python software/reference_sim/build_scene.py
software/reference_sim/.venv/bin/python software/reference_sim/verify_layout.py
software/reference_sim/.venv/bin/python software/reference_sim/verify_motion.py
software/reference_sim/.venv/bin/python software/reference_sim/verify_transfer.py
software/reference_sim/.venv/bin/python software/reference_sim/viewer.py
```

Run the process and analytical pouring model with:

```sh
software/reference_sim/.venv/bin/python software/reference_sim/run_demo.py
```

The run writes `software/reference_sim/build/reference_run.json`. The fetched upstream mesh files,
virtual environment, generated MJCF and run output are local and gitignored. The source commit and
hashes are recorded in `assets/so101/manifest.json`.

Run the numerical acceptance checks with:

```sh
software/reference_sim/.venv/bin/python software/reference_sim/validate.py
```

The simulator also exposes shared control interfaces in `hal/base.py`. `hal/sim.py` implements
the SO-101 joint bus and an asynchronous Mega-like device. The demo routes tare, auger, carousel,
and stage commands through that device and the newline JSON codec. Arm joint goals are accepted in
degrees and actuated by the official MuJoCo position servos.

## What is represented

- Both official SO-101 arms are loaded as articulated MuJoCo models at the two final base
  coordinates. Position actuators use the upstream MJCF joint limits and dynamics.
- The 2020 frame, rack pockets, scale, carousel, auger post, flask, funnel and stage use the final
  layout coordinates. Bench and accessory collision shapes are simplified primitives.
- The scale's beaker locating ring has a 56.6 mm bore and collision geometry.
- The carousel is a MuJoCo hinge and the stage is a slider driven from the 50 mm crank / 80 mm rod
  relation, calibrated to the documented 97.3 mm travel at 150 degrees.
- Liquid delivery uses a tilted-cylinder volume calculation, a weir-flow equation, 120 ms stream
  delay, noisy 80 Hz scale readings and a ballistic landing estimate. Yeast dosing is a calibrated
  grams-per-revolution calculation.
- `verify_motion.py` checks joint-limited IK to a carousel beaker, a proximity-triggered weld grasp,
  a 40 mm lift, and a small wrist move while holding the beaker.
- `verify_transfer.py` executes the empty P1 carousel-to-scale transfer, including an outward
  escape, a lifted carry, release, and upright-placement measurement.

## Limits

The 10-step demo keeps process transfers as logical events. The standalone transfer check validates
one empty P1 move from the carousel to the scale; other station pairs and filled-beaker handling are
not yet validated. Grasping uses a proximity check and weld constraint; the stock SO-101 fingers
are excluded from beaker contacts because they do not reproduce the custom fin-ray geometry. Yeast
dosing is a calibrated grams-per-revolution equation, and the flow and auger constants are
placeholders until measured on the assembled bench. The liquid model is not CFD. The checks
compare geometry, dose, mechanism, and control-interface assumptions; they do not prove a hardware
run will work unchanged.
