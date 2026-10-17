# Pour simulation

`software/sim/pour_sim.py` is an exploratory software-in-the-loop model for the proposed
scale-controlled pour. It is the first runnable liquid and scale simulation in this repository.
It runs with Python 3 and the standard library; it does not need the robot or a simulator package.

From the repository root, run one nominal 39 g pour from a 65 mL source fill:

```sh
python3 software/sim/pour_sim.py
```

The simulator prints the target, settled delivered mass, error, cutoff estimate, elapsed time, and
liquid remaining in the source. Save the time series for plotting or inspection with:

```sh
python3 software/sim/pour_sim.py --csv /tmp/pour.csv
```

Vary the actual flow coefficient while keeping the controller's nominal coefficient unchanged:

```sh
python3 software/sim/pour_sim.py --sweep-weir-scales 0.75,1.0,1.25
```

Other useful options include `--fill-estimate-error-ml`, `--scale-noise-g`, `--scale-lag-ms`,
`--sensor-delay-ms`, and `--fall-delay-ms`. Run `python3 software/sim/pour_sim.py --help` for all
options.

## What it models

- A cylindrical source beaker with a quasi-static horizontal water surface as the beaker tilts.
- Outflow over the low rim using a rectangular-weir approximation, with an adjustable actual flow
  coefficient to represent model mismatch.
- Liquid travel time from the lip to the receiver, plus the apparent scale force from the falling
  stream.
- Scale lag, sample delay, and Gaussian measurement noise.
- A copy of the proposed approach, flow setpoint, feed-forward plus PI tilt correction, early
  cutoff, untilt, and settling logic.
- Tilt command delay, tilt speed limits, and a first-order response in the liquid flow.

The controller constants are seeded from the historical proposal in
[`software_architecture.md`](software_architecture.md). The simulator reimplements that proposal;
there is no deployed pour controller in this checkout to import or validate against.

## What it does not model

This is not a full robot or physics simulation. It does not simulate robot arms, collisions, grasping,
camera feedback, the receiver geometry, splashing, sloshing, surface tension, foaming, or detailed
fluid dynamics. The beaker dimensions and flow coefficient are illustrative starting values. Its
settled error is a result of these assumptions, not a prediction of the real bench's accuracy.

Use measured water pours to fit flow against tilt and fill volume, and measure the scale's noise,
lag, and delay. Then compare the model against those runs before using it to choose controller
settings. It can help expose software mistakes and explore sensitivity to delays and model mismatch;
it cannot replace dry runs, water-pour commissioning, or hardware safety checks.
