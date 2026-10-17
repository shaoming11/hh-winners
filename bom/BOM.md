# Wet Lab Bench: bill of materials

Generated from `bom/BOM.csv` (CDR-23). The CSV is the source of truth; this page renders it by category. CDR item numbers in the notes point to `review/records/cdr_ruling.md`.

**Status values:** `owned`, `borrowed`, `ordered`, `to-order`, `to-source` (no verified link yet: the link column holds suggested search terms), `to-print`, `buy-in-Boston`, `dropped` (kept for the record, qty 0, do not buy).

> **Servo change, 2026-10-14:** the yeast auger is now driven by the owned **Feetech FB5311M-360** continuous-rotation servo with position feedback (`ELE-40`). The N20 gearmotors (`ELE-10`, `ELE-11`), the TB6612FNG (`ELE-09`), the N20 M1.6 screws (`FAS-15`) and the 1 A TB6612 fuse (`ELE-20`) are `dropped`; the N20 caps are removed from `ELE-33`. New: horn `ELE-41` (from the `ELE-31` pack), 3 A auger fuse `ELE-42`, M3 x 8 horn screws `FAS-19`, M3 x 12 ear screws `FAS-20`. `DH-01` and `DH-02` move to v3; `DH-02` is printed x2 at 100 % infill. Details: `docs/electrical.md` §11.

> **About `to-order` rows with an Amazon link:** they were on the README's Oct 13 "order today" list, which teammates handle. Nobody has confirmed those orders in the repo. Check with the ordering teammate before buying again, then change the status to `ordered`.

## Totals

- **144 rows** across 11 categories.
- Rows per category: printed 28, glassware 3, labware 5, fasteners 20, hardware 7, electrical 42, consumables 23, chemicals 4, tools 7, safety 3, calibration 2.
- Rows per status: borrowed 1, buy-in-Boston 9, dropped 5, owned 17, to-order 34, to-print 18, to-source 60.
- **Filament** (grams; slicer figures where the README has them, otherwise estimates marked `est.` in the material column):

| Material | All printed parts (required qty) | Still to print |
|---|---|---|
| PLA | ~1508 g | ~947 g |
| PETG | ~261 g | ~0 g |
| TPU 95A | ~71 g | ~71 g |

  Optional EL-02 print (~150 g PLA) and TL-01 handles (~30 g) are not included. Add a margin of about 30 % for supports, purge and failed prints. Re-slice the v2 parts for real figures. PLA includes `DH-02` v3 x2 at 100 % (~7 g each, estimated; servo change, 2026-10-14); `DH-01` v3 still carries the v2 estimate.
- **Known prices:** the `to-order` rows with a README price come to about **$400** (logged-out prices from Oct 13; check at checkout). That includes three M45CHWs at ~$45 each: the spare (`ELE-30`) and the pair in `ELE-29`, which you can skip if you already own two. It also included the TB6612 (`ELE-09`), now `dropped` (servo change, 2026-10-14), so the real figure is a little lower. `to-source` rows have no price yet.

## Order tonight (ship to Cambridge)

Per CDR-23. Ship to Cambridge so it arrives by Friday morning. Rows with no verified link are `to-source`: pick a listing that delivers by Friday.

| # | BOM id | Item | Link |
|---|---|---|---|
| 1 | `ELE-24` | SRD-05VDC-SL-C relay module, H/L jumper | search: SRD-05VDC-SL-C relay module high low level trigger jumper |
| 2 | `ELE-23` | 22 mm latching mushroom e-stop, 2 NC, yellow box | search: 22mm emergency stop mushroom latching 2NC yellow box |
| 3 | `ELE-26` | INA226 module | search: INA226 module I2C |
| 4 | `ELE-27` | 10 mΩ 2512 shunt (goes with the INA226) | search: 0.01 ohm 2512 2W metal strip shunt resistor |
| 5 | `ELE-19` + `ELE-42` | ATO fuses 3 A x5 (carousel, stage, auger + 2 spare) | search: ATO blade fuse 3A |
| 6 | `ELE-21` | ATO fuses 10 A x2 | search: ATO blade fuse 10A |
| 7 | `ELE-18` | Inline ATO holders x3 (the fuses need them) | search: inline ATO blade fuse holder 16 AWG |
| 8 | `ELE-12` | 20 AWG HD JR extension 1.0 m x2 | search: 20AWG heavy duty JR servo extension 1m |
| 9 | `ELE-13` | 20 AWG HD JR extension 0.3 m x2 | search: 20AWG heavy duty JR servo extension 30cm |
| 10 | `ELE-37` | 2 Class II arm adapters ≥6.5 A (**voltage waits on SIGRobotics**) | search: 5V 8A (or 12V 8A) power adapter 5.5x2.1 Class II |
| 11 | `ELE-30` | Spare FlashHobby M45CHW | [B09VBFZ9KW](https://www.amazon.com/dp/B09VBFZ9KW) |
| 12 | `FAS-02` | ISO 7380 M4 x 20 button head x4 | search: ISO 7380 M4 x 20 button head socket screw |

Removed from this list by the servo change (2026-10-14): the encoder N20 (`ELE-10`) and the 1 A fuses (`ELE-20`). The auger servo (`ELE-40`) is owned.

Small `to-source` parts worth adding to the same order: DIN 985 M3 locknuts (`FAS-08`), the M3 x 12 set screw (`FAS-09`), the 470 µF low-ESR cap (`ELE-32`), A3144s and magnets (`ELE-34/35`) and the Wago 221-415s (`ELE-17`).

## Printed parts (28)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `PRT-01` | TT-01 turntable base + rail saddle | TT-01 | PLA 40%; 200 g/ea (slicer) | 1 | 0 | - | exports/prints/TT-01_turntable-base_qty1.stl | `owned` | Printed Tue night (README schedule). CDR-40: hand-cut servo-lead relief + west-window exit before Friday assembly. |
| `PRT-02` | TT-02 carousel deck, 236 dia | TT-02-deck | PLA 20%; 127 g/ea (slicer) | 1 | 0 | - | exports/prints/TT-02_carousel-deck_qty1.stl | `owned` | Printed Tue night (README schedule). |
| `PRT-03` | TT-03 horn spacer 22 dia x 4.1 | TT-03 horn spacer | PLA 40%; 1 g/ea (slicer) | 1 | 0 | - | exports/prints/TT-03_horn-spacer_qty1.stl | `owned` | Printed Tue night (README schedule). |
| `PRT-04` | TT-04 carousel beaker locator ring, 8 pockets | TT-04 beaker locator ring | PLA; ~62 g/ea (est. STL 77.6 cm3 x 0.8) | 1 | 1 | - | exports/prints/TT-04_beaker-locator-ring_qty1.stl | `to-print` | X2. CAD material says Polypropylene: wrong, PLA per CDR-22. If not yet printed: CDR-14 pocket walls 16->12 mm, CDR-15 3x45 lead-in, spout arrows, R1.5 roots (re-export first). VHB it to the deck. |
| `PRT-05` | ST-01 v1 stage base (bring-up spare) | ST-01 | PLA 40%; 172 g/ea (slicer) | 1 | 0 | - | exports/prints/ST-01_stage-base_qty1.stl | `owned` | Printed Tue night. Kept as spare per CDR-07; needs the CDR-40 8 mm lead slot hand-cut for bring-up. Stop post SF~1.0 at Z35.3. |
| `PRT-06` | ST-01 v2 stage base (fin to Z54, R3/R5 roots, E-01 lead slot) | ST-01 | PLA 40%; ~172 g/ea (ruling: 3 h 51, ~172 g) | 1 | 1 | - | not yet exported (ST-01 v2 generator, CDR-07) | `to-print` | CDR-07 mandatory before live demo. H2D after DH-01/DH-02. Needs grommet measurement (CDR-40) before export. |
| `PRT-07` | ST-02 crank | ST-02 | PLA 40%; 26 g/ea (slicer) | 1 | 0 | - | exports/prints/ST-02_crank_qty1.stl | `owned` | Printed Tue night. |
| `PRT-08` | ST-03 follower link | ST-03 | PLA 40%; 25 g/ea (slicer) | 1 | 0 | - | exports/prints/ST-03_follower-link_qty1.stl | `owned` | Printed Tue night. |
| `PRT-09` | ST-04 tray | ST-04 | PETG 20%; 108 g/ea (slicer) | 1 | 0 | - | exports/prints/ST-04_tray_qty1_PETG.stl | `owned` | Scheduled in PETG; confirm as-printed material from printer logs (CDR-18). 2 x N52 magnets on underside (CDR-46). |
| `PRT-10` | ST-05 flask collar (Erlenmeyer socket) | ST-05 | PETG 20%; 44 g/ea (slicer) | 1 | 0 | - | exports/prints/ST-05_flask-collar_qty1_PETG.stl | `owned` | Confirm material (CDR-18). CDR-25: sand OD to 124.8-125.0 if it will not seat in ST-07. |
| `PRT-11` | ST-07 catch well 130 dia x 90 | REF-WELL | PETG 20%; 109 g/ea (slicer) | 1 | 0 | - | exports/prints/ST-07_catch-well_qty1_PETG.stl | `owned` | CAD body is still named REF-WELL. Confirm material (CDR-18). |
| `PRT-12` | ST-08 v2 bearing race spacer, 7.2 / 5.3 x 1.0 | ST-08 bearing race spacer | PLA 100%; <0.1 g/ea | 6 | 6 | - | not yet exported (ST-08 v2, CDR-26) | `to-print` | CDR-26 reprint at 7.2 OD (v1 at 8 OD touches the shield; discard v1). Any printer, ~10 min. CAD has it under HARDWARE: move to PRINT (CDR-22). |
| `PRT-13` | ST-09 TPU stop-post sleeve, ID 18.3, wall 1.2, 14 tall | - | TPU 95A; ~1.3 g/ea (calc. from dims) | 2 | 2 | - | not yet modelled (CDR-08) | `to-print` | New part CDR-08. Print on the GR-03 TPU plate. Wall must never exceed 1.5 mm. |
| `PRT-14` | TC-01 bearing-bore test coupon | TC-01 | PLA 20%; 10 g/ea (slicer) | 1 | 0 | - | exports/prints/TC-01_bearing-test-coupon_qty1.stl | `owned` | Printed Tue night. |
| `PRT-15` | TL-01 stir-rod handle (optional) | TL-01 | PLA 20%; ~15 g/ea (est. STL 18.7 cm3 x 0.8) | 0 | 0 | - | exports/prints/TL-01_stir-rod-handle_qty2.stl | `to-print` | Optional, unscheduled (README). Print only if needed; qty 2 in file name. |
| `PRT-16` | AG-01 v2 auger stand (90x80 foot, R8 post root, 2 gussets, 30x16 bar, saddle Y290-335) | AG-01 auger stand | PLA; ~145 g/ea (est. from v1 STL 178.9 cm3 x 0.8; v2 is larger) | 1 | 1 | - | not yet exported (AG-01 v2, CDR-03) | `to-print` | A1 tonight, bar along bed Y. exports/prints STL is v1: do not print v1. Re-slice for grams. |
| `PRT-17` | WS-01 v2 scale base (overload-stop boss, R4 root, 1.5 mm counterbores) | WS-01 scale base | PLA; ~77 g/ea (est. from v1 STL 96.9 cm3 x 0.8) | 1 | 1 | - | not yet exported (WS-01 v2, CDR-06) | `to-print` | A1 tonight. exports/prints STL is v1: do not print v1. Keep -Y face flat for HX711 VHB. |
| `PRT-18` | WS-02 v2 scale pan, 80 dia max, 8 mm lip | WS-02 scale pan | PLA; ~25 g/ea (est. from v1 STL 27.8 cm3; v2 larger) | 1 | 1 | - | not yet exported (WS-02 v2, CDR-17) | `to-print` | X2. Reprint even if v1 printed (0 h 38). |
| `PRT-19` | DH-01 v3 yeast auger head (v2 bore/hopper/web + horizontal FB5311M-360 mounting wall, 4 x Ø2.5 ear pilots) | DH-01 yeast auger head | PLA; ~55 g/ea + supports (v2 est.; re-slice v3) | 1 | 1 | - | not yet exported (DH-01 v3, servo change, 2026-10-14) | `to-print` | Servo change, 2026-10-14: v3 replaces the N20 face with a mounting wall for the FB5311M-360 (body horizontal, 4 x M3x12 into Ø2.5 pilots through the ears, FAS-20). Do not print v2. H2D first. Tree supports under hopper only; blocker over bore/slot. Hand-ream with 14 mm drill (TOO-03). |
| `PRT-20` | DH-02 v3 auger screw (Ø22 x 4 horn flange, Ø8 hub, 3.6 mm flights, OD 12, pitch 16; no D-bore) | DH-02 auger screw | PLA 100%; ~7 g/ea (est. from dims, not sliced) | 2 | 2 | - | not yet exported (DH-02 v3, servo change, 2026-10-14) | `to-print` | Servo change, 2026-10-14: 1 + 1 spare, 100 % infill. 25T Al horn (ELE-41) bolts to the flange with 4 x M3x8 (FAS-19). At full servo stall (1.52 N.m at 6 V) the Ø8 hub sees ~15 MPa torsion vs ~10 MPa interlayer allowable, so firmware stall detection (A2 feedback, 150 ms) is mandatory. Do not print v2 (D-bore for the N20). |
| `PRT-21` | RK-02 reagent rack, 3 pockets for 100 mL beakers | RK-02 reagent rack | PLA; ~107 g/ea (est. STL 133.6 cm3 x 0.8) | 1 | 1 | - | exports/prints/RK-02_reagent-rack_qty1.stl | `to-print` | X2 (~1 h 50). CAD material says Steel: wrong, PLA per CDR-22. Add CDR-15 lead-in + arrows before export if unprinted. |
| `PRT-22` | GR-01 fin-ray gripper body | GR-01 gripper body (A); GR-01 gripper body (B) | PLA 30%, supports; ~39 g/ea (est. STL 48.4 cm3 x 0.8) | 2 | 2 | - | exports/prints/GR-01_gripper-body_qty2_SUPPORTS.stl | `to-print` | X2. CDR-16 slot/tongue changes need re-export. Test-fit one GR-01 + one GR-03 first. |
| `PRT-23` | GR-02 fin-ray moving jaw | GR-02 moving jaw (A); GR-02 moving jaw (B) | PLA 30%, supports; ~16 g/ea (est. STL 19.9 cm3 x 0.8) | 2 | 2 | - | exports/prints/GR-02_moving-jaw_qty2_SUPPORTS.stl | `to-print` | X2. Re-export with hinge axis vertical (CDR-16). |
| `PRT-24` | GR-03 fin-ray finger | GR-03 fin-ray finger TPU (A fixed); GR-03 fin-ray finger TPU (A moving); GR-03 fin-ray finger TPU (B fixed); GR-03 fin-ray finger TPU (B moving) | TPU 95A 30%; ~17 g/ea (est. STL 17.1 cm3) | 4 | 4 | - | exports/prints/GR-03_fin-ray-finger_qty4_TPU.stl | `to-print` | X2. Base block 100% via modifier; bridges <=15 mm/s. Silicone strip on contact face (CON-03). |
| `PRT-25` | CAL-01 arm-registered calibration block (mirrored pair) | - | PLA; ~50 g/ea (est., not yet modelled) | 2 | 2 | - | not yet modelled (CDR-33) | `to-print` | X2/H2D before carry-on drop, not the A1. >=4 conical seats, keyed into X-front slot. |
| `PRT-26` | CAL-02 rigid probe, 43.0 dia x 100, 60 deg tip | - | PLA; ~70 g/ea (est., not yet modelled) | 1 | 1 | - | not yet modelled (CDR-33) | `to-print` | X2/H2D before carry-on drop. |
| `PRT-27` | Stage angle gauge, 36.87 / 45 deg | - | PLA; ~10 g/ea (est., not yet modelled) | 1 | 1 | - | not yet modelled (CDR-09) | `to-print` | Used for crank commissioning within +/-1.5 deg. |
| `PRT-28` | EL-02 electronics box (printed alternative, optional) | - | PLA; ~150 g/ea (est., not yet modelled) | 0 | 0 | - | not yet modelled (CDR-48) | `to-print` | Optional: default is the bought ABS box HDW-08. Print only if a printer is idle before the drop. |

## Glassware (3)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `GLS-01` | Karter 250 mL narrow-mouth Erlenmeyer, borosilicate, 85 dia x 148 | REF-FLASK-250 | borosilicate glass | 2 | 2 | 1 | [B006VYY10Y](https://www.amazon.com/dp/B006VYY10Y) | `to-order` | 1 + 1 spare. Wrap in clothes, rigid box. Measure neck OD (~34). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `GLS-02` | Glass stir rods 6.35 x 150 | REF-ROD | borosilicate glass | 4 | 1 | 4 | [B099QK8PX8](https://www.amazon.com/dp/B099QK8PX8) | `to-order` | CAD REF-ROD material -> borosilicate (CDR-22). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `GLS-03` | 100 mL glass graduated cylinder | - | borosilicate glass | 1 | 1 | 1 | search: 100 mL borosilicate glass graduated cylinder | `to-source` | BOM-only row per CDR-22. Pack in clothes in the rigid box (CDR-30). |

## PP labware (5)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `LAB-01` | EISCO 50 mL PP beaker, 43 OD x 61 H | REF-BEAKER; REF-BEAKER-MIX; EISCO 50 mL beaker on scale; ANIM-beaker50 | polypropylene | 11 | 6 | unconfirmed (README buys 6 listings at $9.19) | [B00BHLE5AW](https://www.amazon.com/dp/B00BHLE5AW) | `to-order` | 8 carousel + 1 scale + 1 mix + 1 spare = 11. Count on hand after delivery; buy more if the listing is a single beaker. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `LAB-02` | EISCO 100 mL PP beaker, 56 dia x 74 | EISCO 100 mL PP beaker x3 (developer, soap+dye, warm water); ANIM-beaker100 | polypropylene | 5 | 1 | 12 | [B00BHLE5RU](https://www.amazon.com/dp/B00BHLE5RU) | `to-order` | 3 in rack + 2 spare. Mark 80 mL fill line (CON-13). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `LAB-03` | EISCO 4 in PP funnel, 102 mouth, 104 tall, 20 OD stem | REF-FUNNEL-EISCO4; ST-06 | polypropylene | 1 | 1 | 1 | [B017UYYKSQ](https://www.amazon.com/dp/B017UYYKSQ) | `to-order` | Replaces printed ST-06. Rim at Z236 with cork pad. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `LAB-04` | PP bin ~110 x 80 x 100 (waste / rinse) | REF-BIN | polypropylene | 1 | 1 | 1 | search: polypropylene storage bin 110 x 80 x 100 mm | `to-source` | Provisional: REF-BIN sits off the bench at X835-945 and its purpose is not documented. Confirm use or drop from CAD. |
| `LAB-05` | Clear PP container for flask overflow (optional) | - | polypropylene | 0 | 0 | 1 | search: clear polypropylene container 150 mm diameter | `to-source` | Optional per CDR-19: OD <=150, rim <=Z160, floor ID >=127. |

## Fasteners (20)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `FAS-01` | SHCS M3 x 20, DH-01 bridge -> AG-01 pilots | SHCS ISO 4762 M3x12 | steel | 2 | 0 | kit | [B0FG2BRXL3](https://www.amazon.com/dp/B0FG2BRXL3) | `to-order` | CDR-01 (was M3x12). Snug <=0.5 N.m. From the M3 SHCS kit (6-30 mm); check kit has 20 mm. CAD occurrences still M3x12. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-02` | ISO 7380 M4 x 20 button head, arm front row | CSK ISO 10642 M4x20 | steel | 4 | 4 | - | search: ISO 7380 M4 x 20 button head socket screw | `to-source` | ORDER TONIGHT (CDR-11). Replaces countersunk B082PZY652 (deleted). 0.6 N.m + medium threadlock. CAD still shows CSK. |
| `FAS-03` | SHCS M4 x 20 12.9, arm back row | SHCS ISO 4762 M4x20 | steel | 4 | 1 | 30 | [B017NENNVS](https://www.amazon.com/dp/B017NENNVS) | `to-order` | 0.6 N.m + medium threadlock. Found by search, not page-checked (README). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-04` | 2020 M4 drop-in T-nut | T-nut 2020 drop-in M4 | steel | 8 | 1 | 100 | [B0DJG8FFGS](https://www.amazon.com/dp/B0DJG8FFGS) | `to-order` | Alt https://www.amazon.com/dp/B09FSJXB15. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-05` | SHCS M3 x 12: deck -> horn x4 (CDR-24, was M3x10) + crank -> horn x4 | SHCS ISO 4762 M3x12; SHCS ISO 4762 M3x10 (deck) | steel | 8 | 1 | kit (6-30 mm + washers) | [B0FG2BRXL3](https://www.amazon.com/dp/B0FG2BRXL3) | `to-order` | This row carries the M3 SHCS kit purchase (also covers FAS-01/07/17). CAD deck occurrence still M3x10. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-06` | Servo ear screws (modelled as M3 x 12) | SHCS ISO 4762 M3x12 | steel | 8 | 0 | supplied | supplied with FlashHobby M45CHW | `to-order` | Come with the servos (ELE-29). |
| `FAS-07` | SHCS M3 x 16, GR-03 finger clamps | - | steel | 8 | 0 | kit | [B0FG2BRXL3](https://www.amazon.com/dp/B0FG2BRXL3) | `to-order` | From M3 SHCS kit (check 16 mm present). Not in CAD hardware yet. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-08` | DIN 985 M3 nylon-insert locknut, GR-03 finger clamps | - | steel | 8 | 1 | - | search: DIN 985 M3 nylon insert lock nut | `to-source` | CDR-16 (replaces plain hex nut). M3 kit has washers, not nuts. |
| `FAS-09` | M3 x 12 set screw (grub), WS-01 overload stop | - | steel | 1 | 1 | - | search: M3 x 12 set screw grub screw | `to-source` | CDR-06. Gap set with 2 sheets of paper under 500 g. |
| `FAS-10` | SHCS M5 x 12: TT-01 + ST-01 saddles x4, AG-01 x2, WS-01 x2, RK-02 x2 | SHCS ISO 4762 M5x12 | steel | 10 | 0 | kit | [B0DMCS8KW4](https://www.amazon.com/dp/B0DMCS8KW4) | `to-order` | Included with the T-nut pack (also in M5 kit). RK-02 is M5x12, not M5x10. 1.5 N.m into printed saddles. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-11` | SHCS M5 x 20, four-bar pivots | SHCS ISO 4762 M5x20 | steel | 3 | 1 | kit | [B0FGV561HZ](https://www.amazon.com/dp/B0FGV561HZ) | `to-order` | Snug <=0.5 N.m + medium threadlock (CDR-26). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-12` | SHCS M5 x 8, frame corner brackets | SHCS ISO 4762 M5x8 | steel | 8 | 0 | kit | [B0DMCS8KW4](https://www.amazon.com/dp/B0DMCS8KW4) | `to-order` | Included with the T-nut pack. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-13` | 2020 M5 drop-in T-nut | T-nut 2020 drop-in M5 | steel | 18 | 1 | 120 (+M5 screws) | [B0DMCS8KW4](https://www.amazon.com/dp/B0DMCS8KW4) | `to-order` | Saddles 4 + AG-01 2 + WS-01 2 + RK-02 2 + brackets 8 = 18 (README said 12). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-14` | SHCS M4 x 12: load cell x2 from below, pan x2 from above | SHCS ISO 4762 M4x12 | steel | 4 | 1 | kit | [B074TFLBFQ](https://www.amazon.com/dp/B074TFLBFQ) | `to-order` | Link is search-only in README (not page-checked). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-15` | M1.6 x 4 screws, N20 motor -> DH-01 face | - | steel | 0 | 0 | supplied | supplied with N20 motor | `dropped` | DROPPED (Servo change, 2026-10-14): DH-01 v3 has no N20 face. The FB5311M-360 ears take FAS-20. |
| `FAS-16` | ruthex M5 heat-set insert | Heat-set insert M5 ruthex RX-M5x9.5 | brass | 3 | 1 | 50 | [B07YSVXWS8](https://www.amazon.com/dp/B07YSVXWS8) | `to-order` | ST-01 idler post + 2 on ST-04. Needs soldering iron (TOO-01). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-17` | M3 washers, horn-gap shims | - | steel | 4 | 0 | kit | [B0FG2BRXL3](https://www.amazon.com/dp/B0FG2BRXL3) | `to-order` | In M3 SHCS kit (FAS-05). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `FAS-18` | M3 x 8 standoffs + M3 screws, Mega 2560 Pro in EL-02 | - | brass/steel | 4 | 1 | - | search: M3 x 8 brass standoff kit | `to-source` | CDR-48. |
| `FAS-19` | SHCS M3 x 8, 25T horn -> DH-02 v3 flange | - | steel | 4 | 0 | kit | [B0FG2BRXL3](https://www.amazon.com/dp/B0FG2BRXL3) | `to-order` | Servo change, 2026-10-14. From the M3 SHCS kit (FAS-05, M3x6-30). Through the Ø22 x 4 flange into the horn's tapped M3 holes (14 mm BC): 2.0 mm engagement, tip ~2 mm past the horn flange (same as the carousel stack). Check clearance to the servo case at assembly. Snug. |
| `FAS-20` | M3 x 12 self-tapping, FB5311M-360 ears -> DH-01 v3 wall | - | steel | 4 | 0 | kit | [B0FG2BRXL3](https://www.amazon.com/dp/B0FG2BRXL3) | `to-order` | Servo change, 2026-10-14. Into Ø2.5 pilots through the 4 ear holes. Use the servo's own ear screws if supplied; otherwise M3 x 12 from the FAS-05 kit thread-forms into the pilots (as FAS-06). Snug. |

## Hardware (7)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `HDW-01` | F625ZZ flanged bearing 5 x 16 x 5 | REF-BEARING-G1; REF-BEARING-G2; REF-BEARING-T11; REF-BEARING-T12; REF-BEARING-T21; REF-BEARING-T22 | steel | 6 | 1 | 10 | [B0G1B256ZS](https://www.amazon.com/dp/B0G1B256ZS) | `to-order` | 2 per link end. Test bores with TC-01. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `HDW-02` | 2020 inside-corner bracket | 2020 inside corner bracket | aluminium | 4 | 0 | - | [B09ZXG9B2X](https://www.amazon.com/dp/B09ZXG9B2X) | `owned` | README: own angle brackets; buy this pack only if short. ~$14.99. |
| `HDW-03` | 2020 extrusion x 400 mm | FRAME-2020 (bought, 4 x 400 mm) | aluminium 6061 | 4 | 0 | - | owned | `owned` | Bring 4 (+1 spare if it fits) of the owner's 8. |
| `HDW-04` | BESSEY CM34DR deep-reach C-clamp | BESSEY CM34DR C-clamp | steel | 2 | 1 | 2 | [B0CBZ9J74Y](https://www.amazon.com/dp/B0CBZ9J74Y) | `to-order` | README table listed 2 packs; 1 pack covers the 2 needed. Measure overall length: >178 mm (7 in) must be checked or left (CDR-30). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `HDW-05` | C-clamp 3-4 in (fallback table clamp) | - | steel | 2 | 2 | - | search: 4 inch C-clamp | `buy-in-Boston` | CDR-30 fallback if the BESSEY cannot fly. Buy in Cambridge Friday. |
| `HDW-06` | SO-101 follower arm, stock (TheRobotStudio) | Base_SO101 v13; Wrist_Roll_Follower_SO101 v10; Moving_Jaw_SO101 v3; Wrist_Roll_Pitch_SO100 v15 (1); (and all REF:1 arm bodies) | PLA + STS3215 | 2 | 0 | - | borrowed from SIGRobotics | `borrowed` | Do not drill or modify. Stock jaw/wrist-roll follower kept as fallback. Ask SIGRobotics about motor variant and adapters. |
| `HDW-07` | ABS project box with lid for EL-02, <=200 x 120 x 75 | - | ABS | 1 | 1 | 1 | search: ABS project box 200 x 120 x 75 mm with lid | `to-source` | CDR-48. CAD envelope is X25-225, Y602-692, Z0-60 (200 x 90 x 60): pick a box that fits it or re-check the plan3 scene. Cable exits +Y / -X. |

## Electrical (42)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `ELE-01` | 2S LiPo 7.4 V, >=2200 mAh, XT60 | - | - | 1 | 0 | - | owned | `owned` | README: owner is bringing a 2S pack. Confirm >=2200 mAh, XT60, <100 Wh. Carry-on only, terminals taped, in bag. |
| `ELE-02` | 2S LiPo balance charger (4.20 V/cell, never LiHV) | - | - | 1 | 1 | - | search: 2S LiPo balance charger XT60 | `to-source` | CDR-52. Skip if one comes with the pack. |
| `ELE-03` | LiPo safety bag | - | - | 1 | 1 | - | search: LiPo safe bag fireproof | `to-source` | Charge and fly in the bag. |
| `ELE-04` | LiPo cell voltage alarm (2S) | - | - | 1 | 1 | - | search: LiPo cell voltage checker alarm 1-8S | `to-source` | Stop at 3.5 V/cell. |
| `ELE-05` | Powered 4-port USB hub, ports labelled A / B / MEGA | - | - | 1 | 1 | - | search: powered USB 3.0 hub 4 port with power adapter | `to-source` | CDR-54: ports identified by hub-port location. |
| `ELE-06` | Arduino Mega 2560 Pro | - | - | 1 | 0 | - | owned | `owned` | README: owner is bringing it. |
| `ELE-07` | USB cable for Mega 2560 Pro (connector per inspection) | - | - | 1 | 1 | - | search: USB cable for Mega 2560 Pro (check micro-USB vs USB-C on the board) | `to-source` | CDR-51: replace 'USB-C' with the inspected connector. |
| `ELE-08` | ShangHJ 1 kg load cell + HX711, 2 sets | Load cell 1 kg (ShangHJ) 75x12.7x12.7 | aluminium | 1 | 1 | 2 sets | [B09K7G51KJ](https://www.amazon.com/dp/B09K7G51KJ) | `to-order` | Wire end bolts to WS-01. CDR-44: cut HX711 pin 15 from GND, bridge to 16 (80 SPS). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `ELE-09` | TB6612FNG motor driver | - | - | 0 | 0 | 3 | [B08J3S6G2N](https://www.amazon.com/dp/B08J3S6G2N) | `dropped` | DROPPED (Servo change, 2026-10-14): the auger is the Feetech FB5311M-360 (ELE-40), driven straight from Mega D8; no motor driver. Do not order. Was: 10 k STBY pull-down (ELE-25), on the README Oct 13 Amazon list. |
| `ELE-10` | N20 6 V 60 rpm gearmotor with encoder, 7 PPR, same gearbox | N20 6V 60rpm gearmotor | steel | 0 | 0 | 1 | search: N20 6V 60RPM gear motor encoder 7PPR | `dropped` | DROPPED (Servo change, 2026-10-14): replaced by the owned Feetech FB5311M-360 (ELE-40). Remove from the order-tonight list. Was: A->D18, B->D19, 5 V; TIMED fallback. |
| `ELE-11` | N20 6 V 60 rpm gearmotor, plain, 3 pcs | N20 6V 60rpm gearmotor | steel | 0 | 0 | 3 | [B0F83T7531](https://www.amazon.com/dp/B0F83T7531) | `dropped` | DROPPED (Servo change, 2026-10-14): already bought, now unused (no TIMED fallback any more). Replaced by ELE-40. |
| `ELE-12` | 20 AWG heavy-duty JR servo extension, 1.0 m (stage) | - | - | 1 | 2 | - | search: 20AWG heavy duty JR servo extension 1m | `to-source` | ORDER TONIGHT. 1 + 1 spare (CDR-47). |
| `ELE-13` | 20 AWG heavy-duty JR servo extension, 0.3 m (carousel) | - | - | 1 | 2 | - | search: 20AWG heavy duty JR servo extension 30cm | `to-source` | ORDER TONIGHT. 1 + 1 spare (CDR-47). |
| `ELE-14` | 16 AWG silicone wire, red + black | - | copper | 1 | 1 | - | search: 16 AWG silicone wire red black | `to-source` | Main path XT60 -> fuse -> shunt -> e-stop -> relay -> Wago; minus-star link. |
| `ELE-15` | 20 AWG silicone wire, red + black | - | copper | 1 | 1 | - | search: 20 AWG silicone wire red black | `to-source` | Servo minus to star; auger servo +/- from the 3 A branch to the FB5311M-360 lead (Servo change, 2026-10-14). |
| `ELE-16` | 22 AWG hook-up wire, assorted colours | - | copper | 1 | 1 | - | search: 22 AWG silicone hook up wire kit | `to-source` | Mega GND, auger servo signal (D8) and feedback (A2), signals. (Servo change, 2026-10-14: TB6612 GND and N20 leads deleted.) |
| `ELE-17` | Wago 221-415 lever connector (5-way) | - | - | 4 | 4 | - | search: Wago 221-415 | `to-source` | Minus star (2) + plus bus (CDR-47). |
| `ELE-18` | Inline ATO/ATC blade fuse holder | - | - | 3 | 3 | - | search: inline ATO blade fuse holder 16 AWG | `to-source` | 3 A carousel, 3 A stage, 3 A auger servo, downstream of relay (CDR-42). Servo change, 2026-10-14: the third holder now carries the 3 A auger branch (was 1 A TB6612 VM). Order with the fuses tonight. |
| `ELE-19` | ATO blade fuse 3 A | - | - | 2 | 4 | - | search: ATO blade fuse 3A | `to-source` | ORDER TONIGHT. 2 used + 2 spare. |
| `ELE-20` | ATO blade fuse 1 A | - | - | 0 | 0 | - | search: ATO blade fuse 1A | `dropped` | DROPPED (Servo change, 2026-10-14): the 1 A fuse only protected the TB6612 VM branch, which is deleted. The auger branch is 3 A (ELE-42). |
| `ELE-21` | ATO blade fuse 10 A | - | - | 1 | 2 | - | search: ATO blade fuse 10A | `to-source` | ORDER TONIGHT. Main fuse in ELE-22 + 1 spare. |
| `ELE-22` | XT60 lead with inline blade-fuse holder | - | - | 1 | 1 | 1 | [B0BZ7Y1DQY](https://www.amazon.com/dp/B0BZ7Y1DQY) | `to-order` | Holds the 10 A main fuse. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `ELE-23` | 22 mm red latching mushroom e-stop, 2 NC blocks, yellow box | - | - | 1 | 1 | 1 | search: 22mm emergency stop mushroom latching 2NC yellow box | `to-source` | ORDER TONIGHT (CDR-45). Front table edge near X300. Pole 1 power (16 AWG), pole 2 to D2. |
| `ELE-24` | SRD-05VDC-SL-C 1-ch 5 V relay module with H/L trigger jumper | - | - | 1 | 1 | - | search: SRD-05VDC-SL-C relay module high low level trigger jumper | `to-source` | ORDER TONIGHT (CDR-41). IN on D25, H jumper, NO feeds servo bus. |
| `ELE-25` | Resistors: 33 k x1, 10 k x2 (A1 divider + D25 pull-down) | - | - | 3 | 1 | kit | search: 1/4W metal film resistor kit | `to-source` | CDR-41/46. Servo change, 2026-10-14: the third 10 k (TB6612 STBY pull-down, CDR-43) is no longer needed. |
| `ELE-26` | INA226 current/voltage module (I2C 0x40) | - | - | 1 | 1 | - | search: INA226 module I2C | `to-source` | ORDER TONIGHT (CDR-42). D20/D21. Replace onboard R100 with ELE-27. |
| `ELE-27` | 10 mOhm 2512 2 W metal-strip shunt resistor | - | - | 1 | 3 | - | search: 0.01 ohm 2512 2W metal strip shunt resistor | `to-source` | Order with the INA226 tonight. Buy a few: easy to lose / damage when reworking. |
| `ELE-28` | 2200 uF 16 V electrolytic (bulk cap after shunt) | - | - | 1 | 1 | 1 | [B0FVGBGMW2](https://www.amazon.com/dp/B0FVGBGMW2) | `to-order` | Rubycon. Upstream of e-stop and relay (CDR-52). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `ELE-29` | FlashHobby M45CHW 45 kg 25T 270 deg servo | FlashHobby M45CHW + 25T disc horn | ABS case, steel output | 2 | 2 | 1 | [B09VBFZ9KW](https://www.amazon.com/dp/B09VBFZ9KW) | `to-order` | Carousel + stage. Skip if two already owned. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `ELE-30` | FlashHobby M45CHW, spare | FlashHobby M45CHW + 25T disc horn | ABS case, steel output | 1 | 1 | 1 | [B09VBFZ9KW](https://www.amazon.com/dp/B09VBFZ9KW) | `to-order` | ORDER TONIGHT, ship to Cambridge (CDR-42). |
| `ELE-31` | Treedix 25T aluminium disc horn, 20 dia, 14 mm BC, M3 | 25T Al disc horn (Treedix); REF-SERVO | aluminium 6061 | 2 | 1 | 10 | [B0875ZS9KF](https://www.amazon.com/dp/B0875ZS9KF) | `to-order` | Deck and crank drilled for the 14 mm BC. Servo change, 2026-10-14: a 3rd horn from this 10-pack goes on the FB5311M-360 (ELE-41); no extra purchase. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `ELE-32` | 470 uF 16 V low-ESR electrolytic (stage JR plug) | - | - | 1 | 2 | - | search: 470uF 16V low ESR capacitor | `to-source` | CDR-52. |
| `ELE-33` | Ceramic cap 100 nF x1 (A1 divider) | - | - | 1 | 1 | kit | search: ceramic capacitor kit 100nF 47nF | `to-source` | CDR-46. Servo change, 2026-10-14: the N20 suppression caps (100 nF across the tabs, 2 x 47 nF tab-to-can, CDR-49) are dropped with the N20. |
| `ELE-34` | A3144 Hall-effect sensor | - | - | 2 | 3 | - | search: A3144 hall effect sensor | `to-source` | WORK D26, ERUPT D27 + 1 spare (CDR-46). |
| `ELE-35` | 6 x 2 mm N52 neodymium disc magnet | - | NdFeB | 2 | 4 | - | search: 6x2mm N52 neodymium magnets | `to-source` | 2 on ST-04 underside (S down) + 2 spare. |
| `ELE-36` | Screw-terminal shield / breakout for Mega 2560 Pro | - | - | 1 | 1 | - | search: Mega 2560 Pro screw terminal shield | `to-source` |  |
| `ELE-37` | Class II arm power adapter >=6.5 A, 5.5 x 2.1 centre-positive (5 V 8 A or 12 V 8 A) | - | - | 2 | 2 | - | search: 5V 8A (or 12V 8A) power adapter 5.5x2.1 Class II | `to-source` | ORDER TONIGHT once SIGRobotics confirms motor variant (voltage TBD; one family only). README Facmogu B0711Q5B49 (12 V 5 A) / B087LY41PV (5 V 4 A) are below the CDR-50 6.5 A rating. |
| `ELE-38` | Switched power strip, labelled ARMS OFF | - | - | 1 | 1 | - | search: power strip with switch | `to-source` | CDR-45: arm adapters only on this strip. |
| `ELE-39` | 4-core twisted/shielded cable ~1 m, load cell to EL-02 | - | copper | 1 | 1 | - | search: 4 core shielded cable 26 AWG | `to-source` | CDR-44 routing along X-front then Y-left slots. Only if the HX711 sits in EL-02; skip if it stays on WS-01 -Y face with short leads. |
| `ELE-40` | Feetech FB5311M-360 15 kg continuous-rotation servo with analog position feedback (4-wire), 25T | Feetech FB5311M-360 | - | 1 | 0 | 1 | owned (RobotShop RB-Fit-126) | `owned` | Servo change, 2026-10-14: yeast auger drive, replaces the N20 + encoder + TB6612. 40.1 x 20.1 x 38.8, 4-8.4 V (runs on the 2S servo bus), 50 rpm / 15.5 kg.cm stall at 6 V, 1.7 A stall. PWM D8 (Timer4 OC4C), feedback A2, 3 A branch (ELE-42). |
| `ELE-41` | Treedix 25T aluminium disc horn for the FB5311M-360 (3rd horn) | 25T Al disc horn (Treedix) | aluminium 6061 | 1 | 0 | from ELE-31 | from ELE-31 pack (B0875ZS9KF) | `to-order` | Servo change, 2026-10-14. Covered by the ELE-31 10-pack (2 used on the M45CHWs): no extra purchase. Bolts to the DH-02 v3 flange with 4 x M3x8 (FAS-19). |
| `ELE-42` | ATO blade fuse 3 A, auger servo branch | - | - | 1 | 1 | - | search: ATO blade fuse 3A | `to-source` | Servo change, 2026-10-14: replaces the 1 A TB6612 branch fuse (ELE-20). Same part as ELE-19, buy together (a multi-pack covers it). Stall 1.7 A at 6 V is ~57 % of rating, so this fuse protects wiring only; firmware stall detection and the INA226 trip protect the servo. |

## Consumables (23)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `CON-01` | 3M 4950 VHB tape, 1 in x 5 yd | - | acrylic foam | 1 | 1 | 5 yd | [B007Y7GIKI](https://www.amazon.com/dp/B007Y7GIKI) | `to-order` | Lazy Susan (lower layer liner left on, CDR-10), TT-04, HX711, Hall sensors. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `CON-02` | Cork sheet 3 mm, cut to 80 dia (flask pad in ST-05) | - | cork | 1 | 1 | - | search: 3mm cork sheet | `to-source` | CDR-18. Raises flask 3 mm (neck Z165, funnel rim Z236). |
| `CON-03` | 1 mm self-adhesive silicone rubber strip, 20 x 30 per finger | - | silicone | 4 | 1 | - | search: 1mm self adhesive silicone rubber sheet | `to-source` | CDR-13, all 4 GR-03 contact faces. |
| `CON-04` | Cling film | - | PE | 1 | 1 | roll | store: CVS / grocery | `buy-in-Boston` | CDR-19: over the ST-01 servo. |
| `CON-05` | Drop cloth 1.2 x 2.4 m (4 x 8 ft) plastic | - | PE | 1 | 1 | - | search: plastic drop cloth 4 x 8 ft | `to-source` | CDR-19: taped flat over the stage strip before clamping. |
| `CON-06` | Absorbent pads | - | - | 1 | 1 | pack | search: absorbent spill pads | `to-source` | CDR-19: ring the ERUPT footprint, outside tray and glide path. |
| `CON-07` | Kapton tape | - | polyimide | 1 | 1 | roll | search: Kapton polyimide tape | `to-source` | HX711 cover, lead-exit liners. |
| `CON-08` | Neutral-cure silicone sealant | - | silicone | 1 | 1 | tube | search: neutral cure silicone sealant | `to-source` | Load-cell lead exit (CDR-17). (Servo change, 2026-10-14: N20 tab potting, CDR-49/53, no longer needed.) |
| `CON-09` | Medium-strength threadlocker (blue) | - | - | 1 | 1 | tube | search: medium strength threadlocker blue | `to-source` | Arm M4 bolts (CDR-11), pivot M5x20 (CDR-26). |
| `CON-10` | Heat-shrink tubing assortment | - | polyolefin | 1 | 1 | kit | search: heat shrink tubing kit | `to-source` |  |
| `CON-11` | Zip ties | - | nylon | 1 | 1 | pack | search: small zip ties | `to-source` |  |
| `CON-12` | Adhesive cable-tie mounts | - | - | 10 | 1 | pack | search: adhesive zip tie mounts | `to-source` | AG-01 post Z130/Z20, WS-01 underside x2, lead exits (CDR-40/53). |
| `CON-13` | Fine permanent marker (80 mL fill line on 100 mL beakers) | - | - | 1 | 1 | 1 | store: CVS | `buy-in-Boston` | CDR-34: 80 mL line confirmed at PRECHECK. |
| `CON-14` | PTFE adhesive glides 20 dia x 6 mm | REF-GLIDE-1; REF-GLIDE-2; REF-GLIDE-3; REF-GLIDE-4 | PTFE | 4 | 1 | - | [B08HWC3CSP](https://www.amazon.com/dp/B08HWC3CSP) | `to-order` | Under ST-04. CAD material -> PTFE (CDR-22). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `CON-15` | 3.7 in lazy Susan bearing, 9.4 mm thick | REF-LAZY-SUSAN | steel | 1 | 1 | 8 | [B08CY2P8KZ](https://www.amazon.com/dp/B08CY2P8KZ) | `to-order` | Taped, not screwed (CDR-10). On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `CON-16` | PLA filament, white | - | PLA | 1 | 0 | 1 kg spool | owned | `owned` | Covers remaining PLA prints (see totals in BOM.md). |
| `CON-17` | TPU 95A filament | - | TPU 95A | 1 | 1 | 1 kg spool | search: TPU 95A filament 1.75 mm | `to-source` | ~70 g needed (GR-03 x4 + ST-09 x2). Skip if a spool is on hand. |
| `CON-18` | Paper towels + heavy trash bags | - | - | 1 | 1 | 1 each | store: CVS (README Boston list) | `buy-in-Boston` |  |
| `CON-19` | Hook-and-loop (Velcro) strip, LiPo mount | - | - | 1 | 1 | - | search: adhesive hook and loop strips | `to-source` | CDR-48: LiPo bag at ~(130,650). |
| `CON-20` | Cable cover strip for 2020 slot | - | - | 1 | 1 | - | search: 2020 aluminum extrusion slot cover strip | `to-source` | CDR-53: auger servo lead along the Y-left slot (Servo change, 2026-10-14; was the N20 lead). |
| `CON-21` | Red + blue electrical tape and labels (ARM A/B <V>, ARMS OFF) | - | - | 1 | 1 | - | search: colored electrical tape | `to-source` | CDR-45/50. |
| `CON-22` | Solder (rosin core) + flux | - | - | 1 | 1 | - | search: rosin core solder 0.8 mm | `to-source` | HX711 mod, auger servo lead extension, wiring. (Servo change, 2026-10-14: no N20 tabs.) |
| `CON-23` | 120-grit sandpaper | - | - | 1 | 1 | sheet | search: 120 grit sandpaper | `to-source` | CDR-25 ST-05 OD; bearing-bore reaming. |

## Chemicals (4)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `CHM-01` | Salon Care 40 Volume CLEAR developer, 32 oz (12 % H2O2) | REF-BOTTLE | H2O2 12 % | 2 | 2 | 32 oz | [SBS-760625.html](https://www.sallybeauty.com/SBS-760625.html) | `buy-in-Boston` | Sally Beauty #10850, Cambridge; call first. Clear, not creme. ~$9.29. Keep upright, vented cap. |
| `CHM-02` | Dish soap (Dawn), small bottle | - | - | 1 | 1 | 1 | store: CVS (README Boston list) | `buy-in-Boston` | 15 mL per run, hand-loaded in flask. |
| `CHM-03` | Liquid food colouring | - | - | 1 | 1 | pack | store: CVS / grocery (README Boston list) | `buy-in-Boston` |  |
| `CHM-04` | Instant dry yeast, packets | - | - | 12 | 1 | 12-15 packets or 4 oz jar | store: CVS 6 JFK St, Harvard Sq or any grocery (README Boston list) | `buy-in-Boston` | Instant dissolves faster. Also needed Thursday for the CDR-05 auger test. |

## Tools (carry-on: 7 in max) (7)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `TOO-01` | Pinecil (or similar) soldering iron | - | - | 1 | 1 | 1 | search: Pinecil soldering iron | `to-source` | Heat-set inserts, wiring. Skip if owned. Carry-on OK. |
| `TOO-02` | Long hex keys 2 / 2.5 / 3 / 4 mm, <=7 in | - | steel | 1 | 1 | set | search: long arm hex key set metric | `to-source` | TSA: tools <=7 in. |
| `TOO-03` | 14 mm drill bit (hand-ream DH-01 bore) | - | HSS | 1 | 1 | 1 | search: 14mm HSS drill bit | `to-source` | CDR-05. Check length <=7 in. |
| `TOO-04` | Countersink bit | - | HSS | 1 | 1 | 1 | search: countersink bit hex shank | `to-source` | CDR-15 hand chamfer if TT-04 already printed. |
| `TOO-05` | Digital multimeter | - | - | 1 | 1 | 1 | search: digital multimeter | `to-source` | Barrel voltage check before arm power-on (CDR-50). Skip if owned. |
| `TOO-06` | Luggage scale | - | - | 1 | 1 | 1 | search: digital luggage scale | `to-source` | Carry-on weight check. |
| `TOO-07` | Kitchen thermometer (reads 40 C / 105 F) | - | - | 1 | 1 | 1 | store: CVS / grocery (README Boston list) | `buy-in-Boston` | Warm water ~40 C. |

## Safety (3)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `SAF-01` | Quest ANSI Z87.1 safety glasses, 2-pack | - | PC | 2 | 1 | 2 | [B0CZ7K4Q9S](https://www.amazon.com/dp/B0CZ7K4Q9S) | `to-order` | On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |
| `SAF-02` | Indirect-vent chemical splash goggles | - | PC | 2 | 2 | - | search: chemical splash goggles indirect vent ANSI Z87.1 | `to-source` | 12 % peroxide. README: CVS fallback if Amazon items are late. |
| `SAF-03` | Nitrile gloves, 100 | - | nitrile | 1 | 1 | 100 | [B0C9S5PMSD](https://www.amazon.com/dp/B0C9S5PMSD) | `to-order` | Pick size. On README Oct 13 Amazon list; confirm with the ordering teammate before buying again. |

## Calibration (2)

| id | Description | CAD component | Material | Need | Buy | Pack | Source | Status | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `CLB-01` | 100 g calibration weight, OIML class M2 | - | steel | 1 | 1 | 1 | search: 100g calibration weight class M2 | `to-source` | Primary scale calibration (CDR-38). Carry-on. |
| `CLB-02` | US nickels (5.000 g each), logged backup | - | Cu-Ni | 20 | 0 | - | owned | `owned` | Backup only (CDR-38). |

## Removed or superseded

- **CSK ISO 10642 M4 x 20 ([B082PZY652](https://www.amazon.com/dp/B082PZY652))**: deleted by CDR-11. Use ISO 7380 button heads (`FAS-02`) on the unmodified boss; do not countersink the borrowed arm.
- **inShareplus 6 V 10 A supply ([B01GHN2S7Q](https://www.amazon.com/dp/B01GHN2S7Q)) and HiLetgo PCA9685 ([B01D1D0CX2](https://www.amazon.com/dp/B01D1D0CX2))**: README already had them at qty 0, and CDR-29 deletes the text. The LiPo and Mega replace them.
- **Facmogu 12 V 5 A ([B0711Q5B49](https://www.amazon.com/dp/B0711Q5B49)) and 5 V 4 A ([B087LY41PV](https://www.amazon.com/dp/B087LY41PV)) arm adapters**: below the CDR-50 rating of 6.5 A or more. Replaced by `ELE-37`.
- **v1 prints of AG-01, WS-01, DH-01, DH-02, WS-02 and ST-08**: superseded by v2 (CDR-03/06/02/05/04/17/26). The STLs in `exports/prints/` are still v1 for these parts. Don't print them; wait for the v2 export.
- **N20 auger drive (servo change, 2026-10-14)**: encoder N20 (`ELE-10`), plain N20 3-pack (`ELE-11`), TB6612FNG ([B08J3S6G2N](https://www.amazon.com/dp/B08J3S6G2N), `ELE-09`), N20 M1.6 x 4 screws (`FAS-15`), the 1 A TB6612 fuse (`ELE-20`), the N20 suppression caps (from `ELE-33`), the TB6612 STBY pull-down (from `ELE-25`) and the TIMED fallback. Replaced by the owned Feetech FB5311M-360 (`ELE-40`) on Mega D8 / A2 with a 3 A branch fuse (`ELE-42`). `DH-01` v2 / `DH-02` v2 (N20 face, D-bore) are superseded by v3.
- **M3 x 10 deck screws**: changed to M3 x 12 (CDR-24). **M3 x 12 at DH-01**: changed to M3 x 20 (CDR-01). **M5 x 10 rack screws**: changed to M5 x 12. **Plain M3 hex nuts on GR-03**: changed to DIN 985 locknuts (CDR-16).

## CAD cross-check

Every body in `review/design_data.json` was checked against the `cad_component` column. The design_data hardware quantities include one HW-LIB master each, so for example M45CHW q3 is 2 real servos, M5 x 12 q11 is 10, and M5 T-nut q19 is 18. The BOM uses the counts with the master excluded.

Quantity and material discrepancies to fix in CAD (CDR-22/24/01/11/16):

- `CSK ISO 10642 M4x20` should become ISO 7380 M4 x 20. `SHCS ISO 4762 M3x10 (deck)` should become M3 x 12. The two DH-01 M3 x 12 occurrences should become M3 x 20.
- GR-03 uses M3 x 16 and DIN 985 nuts, but neither appears in the CAD hardware. Add them.
- `TT-04` is set to Polypropylene and `RK-02` to Steel; both should be PLA. `ST-08` sits under HARDWARE and should move to PRINT. `REF-ROD` should be glass, the `REF-GLIDE-*` bodies PTFE, and `REF-WELL` should be renamed ST-07.
- `SHCS ISO 4762 M4x12` is hidden in CAD.

**Excluded on purpose (NON-BOM):** `REF-TABLE`: venue folding table (NON-BOM per CDR-22); `AR-01 (DROPPED - arms bolt to rails)`: dropped part (NON-BOM per CDR-22); `EL-01`: old electronics placeholder; replaced by EL-02 (NON-BOM per CDR-22); `ANIM-foam`: animation body (NON-BOM per CDR-22); `REF-BOTTLE` is reference geometry for the developer bottle, which is bought as `CHM-01`; `ANIM-beaker50` and `ANIM-beaker100` are animation copies of the beakers in `LAB-01` and `LAB-02`.

**Hidden `REF:1` bodies (85 entries)** are the internals of the SO-101 reference assembly: STS3215 servo parts, the Waveshare bus board and its SMD parts, connectors, standoffs and screws. They come with the borrowed arms (`HDW-06`) and are not bought.

## Unmapped CAD components

These bodies have no BOM row. Each needs a decision:

- `REF-BIN` (PP, 110 x 80 x 100, off the bench at X835-945): **mapped provisionally** to `LAB-04`. The README and CDR give no purpose for it (waste or rinse bin?). Confirm and buy it, or delete it from CAD.
- **Hidden legacy custom-gripper and arm bodies:** `Parte6`, `Parte8`, `Base_08p v18`, `Parte12`, `Parte14`, `Parte16`, `gripper_rail_base v1`, `gripper_finger v1`, `gripper_base_plate v1`, `MG90_ldb`, `scritta_MG90s`, `MG90S 9g Micro Servo Medium Horn 12 holes`, `blocco_giunto_polso`, `gripper_spur_gear v2`, `dito1`, `AS 1420 - 1973 - M3 x 10`, `BS 4168 - M2,5 x 10(1)`, `AS 1427 - M2 x 12(5) I`, `disco120`. These look like the old REF-ARM-A/B custom-gripper geometry: an MG90 servo, spur gear, fingers, disc, and the M2/M2.5/M3 screws that hold them. The README says those arms are hidden and not built, so nothing is bought for them. Confirm, then move them to NON-BOM in CAD.
- **Not in CAD yet but in the BOM:** ST-09, CAL-01, CAL-02, the angle gauge, EL-02, M3 x 16, DIN 985 nuts, the M3 x 12 set screw, and all the electrical parts except the load cell and the servos (M45CHW x2 and, per the servo change of 2026-10-14, the FB5311M-360 on `DH-01` v3).
