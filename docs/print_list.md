# Printed parts: final list

Status: final design, 2026-10-15. Where each part goes and what it does:
[demo_process.md](demo_process.md).

- Current STLs/STEPs are in `exports/prints_v2/`. Sliced plates are in `~/fusion_bridge/prints_v2/`
  and the `Downloads/PRINT …` queue folders.
- `exports/prints/` holds older versions. **Don't print from it.**
- Material is PLA unless stated otherwise. GR-03 is TPU 95A.

**How the status was worked out.** It was reconstructed from the print-queue folders as of
01:30 Thu Oct 15 (`PRINT ALL FINAL`, `PRINT NOW 2`, `STAGE SET`, `PRINT REST`,
`PRINT NOW 3 (01-30)`). **Confirm it against what is actually on the bench.**
- **Printed:** released in an earlier queue and not re-queued since.
- **Printing / queued:** in the 01:30 `PRINT NOW 3` queue.
- **To export + print:** designed in CAD; no STL exported yet.

## Final parts

| ID | Version | Part | Qty | Material / settings | File (`exports/prints_v2/` unless noted) | Status |
|---|---|---|---|---|---|---|
| PS-01 | v2 (+25 mm) | Auger post on E5; raises the DH-01 underside to Z 160 | 1 | PLA, 30 %, 4 walls, no supports | `PS-01_auger-post-v2_qty1.stl`; plate `A1_PS-01-v2_FINAL_auger-post_30pct_2h24` | Printed |
| DH-01 | v5 | Yeast auger head: bore Ø15, 45° teardrop crown, 0.7 mm seal gap at the flange | 1 | PLA, 15 %, 4 walls, tree supports at 30°, **plus the bore and outlet support blocker** | `DH-01_yeast-auger-head-v5_qty1.stl`; plate `H2D_DH-01-v5_FINAL_auger-head_BORE-BLOCKER_2h35`; blocker `DH-01-v5_FINAL_bore-support-blocker_modifier.stl` | Printing / queued (H2D) |
| DH-02 | v4 | Auger screw: flights start at 16 mm, Ø3.2 flange holes for M3 × 6 | 2 (1 spare) | PLA, 99 %, 4 walls, tree supports, standing on the flange | `DH-02_auger-screw-v4_qty2.stl`; plate `X2_DH-02-v4_FINAL_…_1h43` (H2D profile: re-slice for the X2) | Printed |
| GR-01 | – | Fin-ray gripper body | 2 | PLA, 30 %, tree supports | `GR-01_gripper-body_qty2_SUPPORTS.stl` | Printing / queued (X2E, with GR-02) |
| GR-02 | – | Fin-ray moving jaw | 2 | PLA, 30 %, tree supports | `GR-02_moving-jaw_qty2_SUPPORTS.stl`; plate `GR-01x2_GR-02x2_gripper-bodies_RE-SLICE-FOR-X2E_5h05` | Printing / queued (X2E) |
| GR-03 | – | Fin-ray finger | 4 | **TPU 95A**, 30 %, base block 100 % | `GR-03_fin-ray-finger_qty4_TPU.stl`; plate `2_A1_TPU-95A_GR-03-fingers-x4_3h26` | Printed |
| ST-11 | – | Stage sled (rides on S1/S2) | 1 | PLA, supports | `ST-11_stage-sled_qty1_SUPPORTS.stl` | Printed (H2D stage set) |
| ST-12 | – | Stage servo bridge | 1 | PLA | `ST-12_servo-bridge_qty1.stl` | Printed (H2D stage set) |
| ST-13 | – | Stage crank, 50 mm | 1 | PLA | `ST-13_crank_qty1.stl` | Printed (H2D stage set) |
| ST-14 | – | Connecting rod, 80 mm (F625ZZ bearings) | 1 | PLA | `ST-14_connecting-rod_qty1.stl` | Printed (H2D stage set) |
| ST-15 | – | Pivot spacer | 2 | PLA | `ST-15_pivot-spacer_qty2.stl` | Printed (H2D stage set) |
| ST-08 | v2 | Bearing-race spacer | 6 | PLA, 25 % | `ST-08_bearing-race-spacer-v2_qty6.stl` | Printed (with WS-02 v3) |
| ST-05 | – | Flask collar (holds the Erlenmeyer in the catch well) | 1 | PLA, 0.28 mm layers | `ST-05_flask-collar_qty1.stl`; plate `1_NOW_WS-01v4_+_ST-05_2h37` | Printing / queued (A1, with WS-01 v4) |
| ST-07 | – | Catch well, Ø130 × 90 | 1 | PLA, **vase mode** | `ST-07_catch-well_qty1.stl`; plate `2_ST-07_catch-well_VASE_0h54` | Printing / queued (A1) |
| TT-01 | v2 | Turntable base (holds the carousel M45CHW and the lazy Susan) | 1 | PLA, 40 % | `TT-01_turntable-base-v2_qty1.stl` | Printed |
| TT-02 | – | Carousel deck, Ø236 | 1 | PLA, 20 % | `exports/prints/TT-02_carousel-deck_qty1.stl` | Printing / queued (H2D) |
| TT-03 | – | Horn spacer, Ø22 × 4 | 1 | PLA, 40 % | `exports/prints/TT-03_horn-spacer_qty1.stl` | Printing / queued (H2D) |
| TT-04 | v4 | Beaker ring: **4 pockets at r 84** for 100 mL beakers | 1 | PLA, 15 % | `TT-04_beaker-ring-v4-4x100mL_qty1.stl`; plate `3_TT-04-v4_carousel-ring_1h48` | Printing / queued (A1) |
| WS-01 | v4 | Scale base with **E6 notch** (clamps on E6) | 1 | PLA, 0.28 mm layers | `WS-01_scale-base-v4_E6-notch_qty1.stl`; plate `1_NOW_WS-01v4_+_ST-05_2h37` | Printing / queued (A1, printing now at 01:30) |
| WS-02 | v3 | Scale pan with a **100 mL locating ring** | 1 | PLA, 25 % | `WS-02_scale-pan-v3-100mL_qty1.stl` | Printed |
| CAL-02 | v2 | Calibration probe, Ø56 (stands in for a 100 mL beaker when teaching poses) | 1 | PLA, 15 % | `CAL-02_probe-v2-d56_qty1.stl` | Printed |
| RK-03 | one-piece | Reagent rack: 3 cups on a spine bolted to Y-left's west-face slot (2 × M4 × 10), hook on the rail's south end | 1 | PLA | CAD (`~/fusion_bridge/rack1.py`); **no STL yet**. The `RK-03_reagent-stand_qty3` and `RK-03_reagent-rack-freestanding` STLs are superseded | **To export + print** |
| TT tie plate | – | Ties the loose carousel + auger unit to the Y-right rail | 1 | PLA | CAD; **no STL yet** | **To export + print** |
| JG-01 | – | Gap block E6 → X-front, 122 mm | 2 | PLA | CAD (`~/fusion_bridge/jigs.py`); no STL yet | **To export + print** |
| JG-02 | – | Gap block X-front → X-back, 50 mm | 2 | PLA | CAD; no STL yet | **To export + print** |
| JG-03 | – | E6 locator from the Y-left south end | 1 | PLA | CAD; no STL yet | **To export + print** |
| JG-04 | – | Pourer base X locator | 1 | PLA | CAD; no STL yet | **To export + print** |
| JG-05 | – | Transfer base X locator | 1 | PLA | CAD; no STL yet | **To export + print** |
| JG-06 | – | Scale X gauge, 7 mm | 1 | PLA | CAD; no STL yet | **To export + print** |

Optional, for dry runs before the beakers arrive on Saturday: `DUMMY-BEAKER-100mL_56x74_qty4.stl`
(plate `9_OPTIONAL_A1_dummy-beakers-100mL_x4`).

## Post-print steps

- **DH-01 v5:** pull the bell and window supports out toward the servo end, and clean the scar off
  the seal-zone crown. Optionally ream the bore Ø15.
- **DH-02 v4:** remove the supports, dress the flight tips, and check it spins freely in the bore.
  Bolt it to the horn with M3 × 6 using a ball-end key at 10–25°. Spin-sand the flange rim
  (240-grit, about 0.2 mm) to true it.
- **GR-03:** push one finger onto a GR-01 tongue before fitting the rest. It should slide on by hand
  with no gap at the clamp.

Details: [../tools/layout/auger_review.md](../tools/layout/auger_review.md).

## Dropped: do not print

| ID | Why |
|---|---|
| CAL-01 | Calibration blocks no longer needed |
| FX-01 | E5 joiner plate: the carousel + auger unit no longer ties to Y-left |
| SF-01 | Scale foot: the scale clamps on E6 instead |
| RK-02 | Reagent rack replaced by RK-03 one-piece |
| AG-01 | Auger stand replaced by E5 + PS-01 |
| ST-01, ST-02, ST-03, ST-04 | Old four-bar stage, replaced by the ST-11..15 slider-crank |
| ST-09 | TPU stop-post sleeves for the old stage |
| Old v1 parts and superseded versions | DH-01 v2–v4, DH-02 v2–v3, PS-01 v1, TT-04 v2, WS-01 v1–v3, WS-02 v1–v2, CAL-02 v1, TT-01 v1, RK-03 stands / free-standing rack |
