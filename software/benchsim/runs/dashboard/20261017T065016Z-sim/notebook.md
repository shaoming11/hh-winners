# Lab notebook: run 20261017T065016Z-sim

sim mode · started 2026-10-17T06:50:16Z · finished 2026-10-17T06:50:52Z

| item | value |
|---|---|
| schema | benchsim.runlog/1 |
| layout source | tools/layout/layout_final.json:update13_final |
| bench_params sha256 | `f6cec6dedc96ab639d7358b41b1d82e8735c18112e582e65d055ce82b688b342` |
| SO-101 model revision | `5f6d2b876a53a4872e405b991dd925556c9e38a4` |
| seed | 0 |
| steps passed / failed / skipped | 2 / 1 / 9 |
| faults | 0 |
| video | – |

## Protocol

| item | value |
|---|---|
| source | preset |
| validation | passed |
| approved by | operator (dashboard) |
| approved at | 2026-10-17T06:50:17Z |

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
| 2 | 2 developer onto P1 | `POUR_TO_SCALE` | passed | OK: added 38.71 g (error -0.29) | added_g 39.00, tol_g 2.00 | added_g 38.71, content_g 38.71, outcome OK, theta_first_deg 64.53, theta_cut_deg 78.06, pour_time_s 17.70, topup_pulses 0, grip_h_mm 44.00, spilled_total_g 0.00, sim_truth_receiver_g 38.73 | added_g -0.29 (within ±2.00) | 12.0 | 54.2 |
| 3 | 3 P1 -> funnel | `POUR_TO_FUNNEL` | **failed** | safe stop: operator stop (dashboard) |  |  |  | 54.2 | 55.3 |
| 4 | 4 P1 -> carousel | `TRANSFER` | **skipped** | not run: safe stop: operator stop (dashboard) |  |  |  | – | – |
| 5 | 5 yeast dose into P2 | `DOSE_YEAST` | **skipped** | not run: safe stop: operator stop (dashboard) |  |  |  | – | – |
| 6 | 6 P2 -> scale | `TRANSFER` | **skipped** | not run: safe stop: operator stop (dashboard) |  |  |  | – | – |
| 7 | 6 verify yeast | `VERIFY_MASS` | **skipped** | not run: safe stop: operator stop (dashboard) |  |  |  | – | – |
| 8 | 7 water onto P2 | `POUR_TO_SCALE` | **skipped** | not run: safe stop: operator stop (dashboard) |  |  |  | – | – |
| 9 | 7 activate | `WAIT` | **skipped** | not run: safe stop: operator stop (dashboard) |  |  |  | – | – |
| 10 | 8 P2 -> funnel (reaction starts) | `POUR_TO_FUNNEL` | **skipped** | not run: safe stop: operator stop (dashboard) |  |  |  | – | – |
| 11 | 9 P2 -> carousel | `TRANSFER` | **skipped** | not run: safe stop: operator stop (dashboard) |  |  |  | – | – |
| 12 | 10 ERUPT | `STAGE` | **skipped** | not run: safe stop: operator stop (dashboard) |  |  |  | – | – |

## Masses

| # | step | quantity | target | measured | difference | tolerance | result |
|---|---|---|---|---|---|---|---|
| 2 | 2 developer onto P1 | added_g | 39.00 | 38.71 | -0.29 | 2.00 | within |

Run summary:

| quantity | value |
|---|---|
| vessels | P1 developer 38.73, P2 , dev developer 21.59, water water 49.60, flask soap 15.45, dye 0.20, hopper yeast 30.00 |
| measured | 1 P1 carousel -> scale grasp_jaw_deg 23.12, scale [{'event': 'place', 'before_g': 0.04, 'after_g': 18.03}], scale_after_g 17.98, beaker_tare_g 17.98, 2 developer onto P1 added_g 38.71, content_g 38.71, outcome OK, theta_first_deg 64.53, theta_cut_deg 78.06, pour_time_s 17.70, topup_pulses 0, grip_h_mm 44.00, spilled_total_g 0.00, sim_truth_receiver_g 38.73 |
| spilled_g | 0.00 |
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

![foam t+0.5 s · foam_cam · t 55.82 s](frames/0055.82_foam_cam.png)

*foam t+0.5 s · foam_cam · t 55.82 s*

![foam t+2.5 s · foam_cam · t 57.82 s](frames/0057.82_foam_cam.png)

*foam t+2.5 s · foam_cam · t 57.82 s*

![foam t+4.5 s · foam_cam · t 59.82 s](frames/0059.82_foam_cam.png)

*foam t+4.5 s · foam_cam · t 59.82 s*

![foam t+6.5 s · foam_cam · t 61.82 s](frames/0061.82_foam_cam.png)

*foam t+6.5 s · foam_cam · t 61.82 s*

![foam t+8.5 s · foam_cam · t 63.82 s](frames/0063.82_foam_cam.png)

*foam t+8.5 s · foam_cam · t 63.82 s*

![foam t+10.5 s · foam_cam · t 65.82 s](frames/0065.82_foam_cam.png)

*foam t+10.5 s · foam_cam · t 65.82 s*

![foam t+12.5 s · foam_cam · t 67.82 s](frames/0067.82_foam_cam.png)

*foam t+12.5 s · foam_cam · t 67.82 s*

![foam t+14.0 s · foam_cam · t 69.32 s](frames/0069.32_foam_cam.png)

*foam t+14.0 s · foam_cam · t 69.32 s*

## Events

| kind | count |
|---|---|
| step_start | 3 |
| attach | 2 |
| grasp | 2 |
| detach | 2 |
| release | 2 |
| step_done | 2 |
| stop_requested | 2 |
| safe_stop_hold | 2 |
| precheck | 1 |
| safe_stop | 1 |

---
Generated by benchsim.notebook at 2026-10-17T06:50:52Z.
