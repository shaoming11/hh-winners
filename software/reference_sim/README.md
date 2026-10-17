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

## What is represented

- Both official SO-101 arms are loaded as articulated MuJoCo models at the two final base
  coordinates. Position actuators use the upstream MJCF joint limits and dynamics.
- The 2020 frame, rack pockets, scale, carousel, auger post, flask, funnel and stage use the final
  layout coordinates. Bench and accessory collision shapes are simplified primitives.
- The carousel is a MuJoCo hinge and the stage is a slider driven from the 50 mm crank / 80 mm rod
  relation, calibrated to the documented 97.3 mm travel at 150 degrees.
- Liquid delivery uses a tilted-cylinder volume calculation, a weir-flow equation, 120 ms stream
  delay, noisy 80 Hz scale readings and a ballistic landing estimate. Yeast dosing is a calibrated
  grams-per-revolution calculation.

## Limits

This first reference version does **not** yet simulate arm pick-and-place motion or a calibrated
CAD-to-MJCF trajectory bridge. Its 10-step process run checks the analytical chemistry targets
and the carousel/stage mechanisms, but arm actions in the log are process events, not physical
arm playback. The liquid model is not CFD. The current flow and auger constants are placeholders
until measured on the assembled bench. It is useful for comparing layout, dose and flow assumptions,
not for claiming that untested hardware code will work unchanged.
