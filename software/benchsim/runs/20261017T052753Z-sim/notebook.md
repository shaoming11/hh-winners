# Lab notebook: run 20261017T052753Z-sim

sim mode · started 2026-10-17T05:27:53Z · finished 2026-10-17T05:27:58Z

| item | value |
|---|---|
| schema | benchsim.runlog/1 |
| layout source | tools/layout/layout_final.json:update13_final |
| bench_params sha256 | `62c630552aa8327f6f60432fb84a5fbf45ce353076f6e634765750a02bea095a` |
| SO-101 model revision | `5f6d2b876a53a4872e405b991dd925556c9e38a4` |
| seed | 0 |
| steps passed / failed / skipped | 1 / 1 / 10 |
| faults | 0 |
| video | – |

## Protocol

| item | value |
|---|---|
| source | preset |
| validation | passed |
| approved by | operator (sim, preset) |
| approved at | 2026-10-17T05:27:54Z |

Approved plan:

| # | type | params | label |
|---|---|---|---|
| 1 | `TRANSFER` | beaker=P1, src=carousel_pick, dst=scale_pan | 1 P1 carousel -> scale |
| 2 | `POUR_TO_SCALE` | reagent=developer, beaker=P1, target_g=39.00, tol_g=2.00, relative=no | 2 developer onto P1 |
| 3 | `POUR_TO_FUNNEL` | beaker=P1 | 3 P1 -> funnel |
| 4 | `TRANSFER` | beaker=P1, src=scale_pan, dst=carousel_pick | 4 P1 -> carousel |
| 5 | `DOSE_YEAST` | beaker=P2, target_g=7.00, tol_g=0.70, max_topups=2 | 5 yeast dose into P2 |
| 6 | `TRANSFER` | beaker=P2, src=carousel_pick, dst=scale_pan | 6 P2 -> scale |
| 7 | `VERIFY_MASS` | beaker=P2, target_g=7.00, tol_g=0.70 | 6 verify yeast |
| 8 | `POUR_TO_SCALE` | reagent=water, beaker=P2, target_g=30.00, tol_g=2.00, relative=yes | 7 water onto P2 |
| 9 | `WAIT` | seconds=60.00, reason=yeast activation | 7 activate |
| 10 | `POUR_TO_FUNNEL` | beaker=P2 | 8 P2 -> funnel (reaction starts) |
| 11 | `TRANSFER` | beaker=P2, src=scale_pan, dst=carousel_pick | 9 P2 -> carousel |
| 12 | `STAGE` | position=ERUPT | 10 ERUPT |

## Steps

| # | step | type | status | reason | target | measured | measured − target | start s | end s |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 P1 carousel -> scale | `TRANSFER` | passed | grasp grasped |  | grasp_jaw_deg 23.12, scale [{'event': 'place', 'before_g': 0.04, 'after_g': 18.03}], scale_after_g 17.98, beaker_tare_g 17.98 |  | 0.5 | 12.0 |
| 2 | 2 developer onto P1 | `POUR_TO_SCALE` | **failed** | safe stop: operator stop during the developer pour |  |  |  | 12.0 | 33.2 |
| 3 | 3 P1 -> funnel | `POUR_TO_FUNNEL` | **skipped** | not run: safe stop: operator stop during the developer pour |  |  |  | – | – |
| 4 | 4 P1 -> carousel | `TRANSFER` | **skipped** | not run: safe stop: operator stop during the developer pour |  |  |  | – | – |
| 5 | 5 yeast dose into P2 | `DOSE_YEAST` | **skipped** | not run: safe stop: operator stop during the developer pour |  |  |  | – | – |
| 6 | 6 P2 -> scale | `TRANSFER` | **skipped** | not run: safe stop: operator stop during the developer pour |  |  |  | – | – |
| 7 | 6 verify yeast | `VERIFY_MASS` | **skipped** | not run: safe stop: operator stop during the developer pour |  |  |  | – | – |
| 8 | 7 water onto P2 | `POUR_TO_SCALE` | **skipped** | not run: safe stop: operator stop during the developer pour |  |  |  | – | – |
| 9 | 7 activate | `WAIT` | **skipped** | not run: safe stop: operator stop during the developer pour |  |  |  | – | – |
| 10 | 8 P2 -> funnel (reaction starts) | `POUR_TO_FUNNEL` | **skipped** | not run: safe stop: operator stop during the developer pour |  |  |  | – | – |
| 11 | 9 P2 -> carousel | `TRANSFER` | **skipped** | not run: safe stop: operator stop during the developer pour |  |  |  | – | – |
| 12 | 10 ERUPT | `STAGE` | **skipped** | not run: safe stop: operator stop during the developer pour |  |  |  | – | – |

## Masses

Run summary:

| quantity | value |
|---|---|
| vessels | P1 developer 12.02, P2 , dev developer 48.27, water water 49.60, flask soap 15.45, dye 0.20, hopper yeast 30.00 |
| measured | 1 P1 carousel -> scale grasp_jaw_deg 23.12, scale [{'event': 'place', 'before_g': 0.04, 'after_g': 18.03}], scale_after_g 17.98, beaker_tare_g 17.98 |
| spilled_g | 0.03 |
| foam_peak_mm | 0.00 |

## Faults

No faults.

## Scale trace

![scale trace](scale_trace.svg)

## Camera frames

![start · overview · t 0.00 s](frames/0000.00_overview.png)

*start · overview · t 0.00 s*

![precheck · bench_cam · t 0.50 s](frames/0000.50_bench_cam.png)

*precheck · bench_cam · t 0.50 s*

![before pick P1 · bench_cam · t 0.50 s](frames/0000.50_bench_cam.png)

*before pick P1 · bench_cam · t 0.50 s*

![after 1 P1 carousel -> scale · bench_cam · t 11.96 s](frames/0011.96_bench_cam.png)

*after 1 P1 carousel -> scale · bench_cam · t 11.96 s*

![pour start 2 developer onto P1 · overview · t 22.99 s](frames/0022.99_overview.png)

*pour start 2 developer onto P1 · overview · t 22.99 s*

![foam t+0.5 s · foam_cam · t 34.89 s](frames/0034.89_foam_cam.png)

*foam t+0.5 s · foam_cam · t 34.89 s*

![foam t+2.5 s · foam_cam · t 36.89 s](frames/0036.89_foam_cam.png)

*foam t+2.5 s · foam_cam · t 36.89 s*

![foam t+4.5 s · foam_cam · t 38.89 s](frames/0038.89_foam_cam.png)

*foam t+4.5 s · foam_cam · t 38.89 s*

![foam t+6.5 s · foam_cam · t 40.89 s](frames/0040.89_foam_cam.png)

*foam t+6.5 s · foam_cam · t 40.89 s*

![foam t+8.5 s · foam_cam · t 42.89 s](frames/0042.89_foam_cam.png)

*foam t+8.5 s · foam_cam · t 42.89 s*

![foam t+10.5 s · foam_cam · t 44.89 s](frames/0044.89_foam_cam.png)

*foam t+10.5 s · foam_cam · t 44.89 s*

![foam t+12.5 s · foam_cam · t 46.89 s](frames/0046.89_foam_cam.png)

*foam t+12.5 s · foam_cam · t 46.89 s*

![foam t+14.5 s · foam_cam · t 48.89 s](frames/0048.89_foam_cam.png)

*foam t+14.5 s · foam_cam · t 48.89 s*

## Events

| kind | count |
|---|---|
| step_start | 2 |
| attach | 2 |
| grasp | 2 |
| safe_stop_hold | 2 |
| precheck | 1 |
| detach | 1 |
| release | 1 |
| step_done | 1 |
| stop_requested | 1 |
| safe_stop | 1 |
| safe_stop_untilt | 1 |

---
Generated by benchsim.notebook at 2026-10-17T05:27:58Z.
