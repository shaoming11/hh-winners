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
software/reference_sim/.venv/bin/python software/reference_sim/verify_rack_transfer.py
software/reference_sim/.venv/bin/python software/reference_sim/verify_pour.py
software/reference_sim/.venv/bin/python software/reference_sim/verify_carousel.py
software/reference_sim/.venv/bin/python software/reference_sim/verify_foam.py
software/reference_sim/.venv/bin/python software/reference_sim/run_demo.py --physical-p1-transfer
software/reference_sim/.venv/bin/python software/reference_sim/run_demo.py --physical-pour --record
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
  delay, noisy 80 Hz scale readings and a ballistic landing estimate. Recorded pours show a
  non-colliding capsule for that analytical stream. Yeast dosing is a calibrated grams-per-revolution
  calculation.
- The final stage move grows a non-colliding foam visual from peroxide and yeast masses. Its oxygen
  estimate is stoichiometric; the 4 s growth and 140 mm peak height are visual defaults.
- `verify_motion.py` checks joint-limited IK to a carousel beaker, a proximity-triggered weld grasp,
  a 40 mm lift, and a small wrist move while holding the beaker; it reports the soft weld's
  measured compliance.
- `verify_transfer.py` executes the empty P1 carousel-to-scale transfer, including an outward
  escape, a lifted carry, release, and upright-placement measurement.
- `verify_rack_transfer.py` checks an empty rack-beaker-to-scale transfer with the pourer arm.
- `verify_pour.py` moves P1 to the scale, carries a second beaker above it, and uses the actual
  MuJoCo beaker tilt to drive the analytical flow, stream-landing and simulated-scale loop. The
  tested path reaches about 70 degrees while retaining joint-limit margin.
- `verify_carousel.py` checks that all four dynamic beakers follow a 45 degree carousel index while
  staying on the 84 mm pocket radius and upright.
- `verify_foam.py` checks peroxide/yeast scaling, the growth profile and the MuJoCo visual update.
- `run_demo.py --physical-p1-transfer` runs that same arm transfer as step 1 of the analytical
  10-step scenario and records the motion metrics in `build/reference_run.json`.
- `run_demo.py --physical-pour` also performs step 2 with both SO-101 arms, tilts a held donor
  beaker, and reports the analytical stream and scale measurements. Remaining process transfers
  and pours are logical events. Add `--record` to save an overview MP4 beside the JSON output.

## Limits

The 10-step demo defaults to logical process transfers and pours. With `--physical-p1-transfer`,
step 1 moves empty P1 from the carousel to the scale. `--physical-pour` also runs the developer pour
with arm motion in step 2. `verify_pour.py` independently checks that same arm-driven pour; the
other filled-beaker transfers are not yet validated. Grasping uses a proximity
check and weld constraint. The custom GR-01/02/03 geometry is not yet modeled, and stock jaw
collisions with beakers are excluded because they do not reproduce the custom fin-ray fingers.
Contact checks currently report no arm-to-scene contact on the P1 transfer or pour tilt paths.
Yeast dosing is a calibrated grams-per-revolution equation, and the flow and auger constants are
placeholders until measured on the assembled bench. The stream capsule visualizes the calculated
path, not fluid particles. Foam is a timed visual model, not reaction kinetics or CFD. The checks
compare geometry, dose, mechanism, and control-interface assumptions;
they do not prove a hardware run will work unchanged.
