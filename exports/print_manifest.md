# Wet lab bench — print manifest

Generated from the Fusion model `WET-LAB-BENCH` on 2026-10-13. Dimensions are in mm and volumes
in cm³, measured in each part's own print orientation (bed face at Z = 0, no supports). Times
come from the Bambu Studio CLI: 0.20 mm Standard, 4 walls, Textured PEI.

| ID | File | Bounding box | Volume | Material / infill | A1 | H2D | g |
|---|---|---|---|---|---|---|---|
| TT-01 | `TT-01_turntable-base_qty1` | 151.3 × 110 × 43 | 250.3 | PLA 40 % | 4:31 | 4:07 | 200 |
| TT-02 | `TT-02_carousel-deck_qty1` | 236 × 236 × 7 | 179.1 | PLA 20 % | 2:31 | 2:27 | 127 |
| TT-03 | `TT-03_horn-spacer_qty1` | 22 × 22 × 4.1 | 1.1 | PLA 40 % | 0:09 | 0:12 | 1 |
| ST-01 | `ST-01_stage-base_qty1` | 70 × 206.9 × 66 | 235.3 | PLA 40 % | 4:18 | 3:51 | 172 |
| ST-02 | `ST-02_crank_qty1` | 176 × 26 × 10 | 32.9 | PLA 40 % | 0:49 | 0:48 | 26 |
| ST-03 | `ST-03_follower-link_qty1` | 176 × 26 × 10 | 31.7 | PLA 40 % | 0:46 | 0:44 | 25 |
| ST-04 | `ST-04_tray_qty1_PETG` | 176 × 206 × 49 | 142.6 | PETG 20 % | 3:44 | 3:06 | 108 |
| ST-05 | `ST-05_flask-collar_qty1_PETG` | 126 × 126 × 23 | 47.9 | PETG 20 % | 1:32 | 1:16 | 44 |
| ST-07 | `ST-07_catch-well_qty1_PETG` | 130 × 130 × 90 | 97.3 | PETG 20 % | 3:35 | 2:31 | 109 |
| ST-08 | `ST-08_bearing-race-spacer_qty6` | 8 × 8 × 1 | 0.03 ea | PLA 100 % | ~0:10 (6 off) | ~0:10 | 1 |
| TC-01 | `TC-01_bearing-test-coupon_qty1` | 70 × 40 × 6 | 12.8 | PLA 20 % | 0:28 | 0:28 | 10 |
| TL-01 | `TL-01_stir-rod-handle_qty2` | 25 × 25 × 40 | 18.7 ea | PLA 20 % | – | – | – |

TL-01 is optional and unscheduled; print it only once the gripper opening is known.

## Changes from the board version

- **Stock SO-101s** (official STEP) bolt to the rails with 4 × M4 × 20 + M4 T-nuts each. The front rail moved to Y 508.5.
- **All printed parts are filleted and chamfered**: 2 mm inside, 1.5–2.5 mm outside vertical, 0.8–1.5 mm top edges, 0.5–0.6 mm bed chamfer. Fit features stay sharp.
- **ST-01 stop posts** are now Ø18 and webbed into the servo cradle (SF 3.0 at full stall vs about 0.3 before). Unused foot recesses were removed from TT-01 and ST-01.
- **Servo pocket and pilot planes** are now driven by `sv_ear_z`; they had been left 0.7 / 1.7 mm short.
- **ST-08** bearing race spacers added (the pivot stacks).

- **AR-01 arm risers dropped.** The SO-101 bases bolt straight onto two 2020 rails.
- **TT-01 and ST-01** each gained a rail saddle: a 20.6 × 20.2 channel with 2 × Ø5.5 holes for
  M5 × 12 into T-nuts. Their rubber-foot recesses are now unused.
- **Servo geometry set to the FlashHobby M45CHW:** case 40.5 tall, ear underside 27.3, spline top
  46.0, horn face 48.0 (estimate). Turntable box top 43.0, deck 54.6; ST-01 servo gap 3 mm, so
  the crank stays at Z 56.
- **Horn holes on TT-02 and ST-02** moved to a 14 mm bolt circle (25T aluminium disc horn).
- **TT-03 horn spacer** added (4.1 mm), so the deck underside stays flat for printing.
- **ST-05** re-socketed for an 85 mm Erlenmeyer base (86.5 ID, 20 mm tall wall).
- **ST-07** catch well (the old REF-WELL cup) is now a printed part.
- **ST-06** printed funnel dropped (the bought EISCO 4 in replaces it). EL-01 is not printed.
