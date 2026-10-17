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
.venv/bin/python -m pytest -q tests
```

Station centres in the compiled model are compared with update13_final (gate 1 mm). Because the scene is built
from the same JSON, that check guards the config → scene pipeline (unit conversion, frames). The independent
evidence that CAD and layout agree is the feature fit of part-local STLs: the RK-03 rack's three cup floors land
on the rack pockets to 0.000 mm, the TT-04 ring's four pocket bores on the r 84 pockets to 0.12 mm and its floor
on the recorded beaker-bottom Z 61.7, and the WS-02 pan floor on Z 63.7.

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
