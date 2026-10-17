# Demo walkthrough: the final design, end to end

Status: final design, 2026-10-15. The layout is planner Update 13: all 8 arm steps PASS with
margin. The record is in [tools/layout/layout_final.md](../tools/layout/layout_final.md) (section
"Update 13") and `tools/layout/layout_final.json`, key `update13_final`. Where an older document
disagrees with this one, this one wins.

Related docs:
- [motivation.md](motivation.md): why this matters, with sources.
- [electrical.md](electrical.md): power, e-stop, pins, wiring.
- [print_list.md](print_list.md): every printed part and its status.
- [../bom/BOM_final.md](../bom/BOM_final.md): what was bought.
- [BENCH_PLACEMENT_SHEET.txt](BENCH_PLACEMENT_SHEET.txt): the one-page tape sheet. **Its rack lines
  are out of date**: the three loose stands are now the one-piece RK-03 (see §2.4).
- [../tools/layout/auger_review.md](../tools/layout/auger_review.md): auger print fixes and
  post-print steps.

---

## 1. The vision

The operator pours **rough, arbitrary amounts** of each liquid into its reagent beaker, fills the
yeast hopper and presses go. The bench then makes up an exact elephant-toothpaste recipe:
- **Liquids:** one arm pours them onto a load-cell scale, closed loop.
- **Yeast:** an auger doses it, and the scale checks the dose.
- **Mixing:** an arm pours each measured beaker into a flask through a funnel.
- **Eruption:** a sled carries the flask toward the audience, and the foam erupts.

The pitch is "weigh, don't measure". Commercial gravimetric dosing costs tens of thousands of
dollars or more. This bench does it with two open-source SO-101 arms, ordinary beakers and an
Erlenmeyer flask, for about $300 of new parts. The full argument, with sources and the claims we
do **not** make, is in [motivation.md](motivation.md).

**What "automated" means here.** The operator still loads the beakers and reagents by hand,
wearing goggles and gloves. The automation takes the person out of **measuring, transferring and
mixing**. It does **not** mean "no human contact" with the chemicals.

### Recipe

| Reagent | Target | Done by |
|---|---|---|
| 12 % H2O2 (40-volume clear developer) | **39 g** (design tolerance ±2 g), about 36 mL | Pourer arm, closed loop on the scale |
| Dish soap + food colouring | 15 mL + a few drops | **Pre-loaded in the flask by hand** before the run |
| Instant dry yeast | **about 7 g** (one packet), tolerance ±0.7 g | Auger, dosed by revolutions, then weighed |
| Warm water (about 40 °C) | **+30 g** on top of the yeast (±2 g) | Pourer arm, closed loop on the scale |

39 g of 12 % peroxide is 4.7 g of H2O2, which releases **about 1.7 L of O2** as it decomposes.
The ST-07 catch well holds the flask; the foam runs over it, so cover the table under the ERUPT
end.

**Hazard: 12 % H2O2 causes SERIOUS EYE DAMAGE** (EU CLP Eye Dam. 1, H318). It is not classified
as corrosive to skin at 12 %; it can whiten and irritate skin. **Wear splash goggles and nitrile
gloves** whenever you handle the developer, the reagent beaker, the flask or the foam. Rinse skin
contact with plenty of water.

---

## 2. Bench layout and placement

### 2.1 Coordinates and tape datums

World coordinates are in mm, with the table top at Z 0. **+X is east** (toward the Y-right rail)
and **+Y is north** (toward the arm rails). The audience is to the south.

For placing things by hand, use the **tape datums**:
- **Tape X** is measured from the **west (outer) face of the Y-left rail** (world X 245).
- **Tape Y** is measured from the **south face of E6**, the stage crossbar (world Y 430).

### 2.2 Frame

- Eight 400 mm 2020 extrusions: the frame square (X-front, X-back, Y-left, Y-right), E5 (auger
  post rail), E6 (stage crossbar, which also carries the scale), and S1/S2 (stage sled rails).
- **The only change from the CAD as built:** both X rails (the arm rails) move **74 mm north**.
  New centres: front Y 582.5, rear Y 652.3. Move the rear corner brackets to the south side of
  their joints.
- Y-left (Y 290–690), Y-right (Y 270–670), E6 (Y 430–450) and the stage stay as built.
- **Bench depth is 746 mm**, so it fits a 30 in (762 mm) table. Set it with the table's front
  edge about **20 mm in front of the stage rails**. Clamp the frame to the table with the two
  deep-reach C-clamps.
- **Fasteners:** M4 everywhere on the frame, into M4 T-nuts. M3 only at the servo horns. M5 only
  for the stage pivot. **Nothing threads into printed plastic.** Details in §6.

### 2.3 Station table

| Station | World (X, Y) | Tape X / Y | How it is mounted |
|---|---|---|---|
| **Pourer arm** base axis (WEST) | (397.4, 599.7) | +152.4 / +169.7 | On the X rails, axis **132.4 mm from the X rails' west end**. Located by jig JG-04 |
| **Transfer arm** base axis (EAST) | (604.8, 599.7) | +359.8 / +169.7 | On the X rails, axis **339.8 mm from the west end**. Located by jig JG-05 |
| X rails | front centre Y 582.5, rear Y 652.3 | Y +152.5 / +222.3 | Moved +74 mm north. Spacing set by jigs JG-01 and JG-02 |
| **Scale** pan centre | (620.0, 407.0); beaker bottom Z 63.7 | +375.0 / −23.0 | WS-01 v4 clamps on **E6** (E6 notch), pan on the south side, pan centre 355 mm from E6's west end. Saddle spans X 547–664. Set by jig JG-06 |
| **Funnel** (in the flask on the sled, at WORK) | (450.0, 282.0); rim Z 233 | +205.0 / −148.0 | Stage, as built |
| **Carousel** centre | (807.9, 523.5) | +562.9 / +93.5 | Carousel + auger unit sits **outside the frame to the east**, rotated **220.6°**. VHB under TT-01, and the TT tie plate bolts it to the Y-right rail |
| Carousel **pick** pocket (faces the transfer arm) | (744.1, 468.8); beaker bottom Z 61.7 | +499.1 / +38.8 | TT-04 v4 pocket |
| Carousel **auger** pocket (opposite the pick) | (871.6, 578.2) | +626.6 / +148.2 | DH-01 outlet directly above it |
| Rack pocket 1: **developer** | (192.3, 394.6); beaker bottom Z 60.2 | −52.7 / −35.4 | RK-03 one-piece rack (§2.4) |
| Rack pocket 2: soap (spare pocket, not poured by an arm) | (134.6, 477.1) | −110.4 / +47.1 | RK-03 |
| Rack pocket 3: **water** | (108.5, 574.4) | −136.5 / +144.4 | RK-03 |

**Distances from each arm's base axis** (bearing measured from −Y, positive toward +X). Use these
as a check after placing:

| Arm | Station | r (mm) | Bearing |
|---|---|---|---|
| Pourer | rack pockets 1 / 2 / 3 | 290 | −45° / −65° / −85° |
| Pourer | scale | 294.4 | +47° |
| Pourer | funnel | 322.0 | +9° |
| Transfer | carousel pick pocket | 191.1 | +48° |
| Transfer | scale | 193.3 | −5° |

**Arm names.** Older files use letters that conflict: the placement sheet calls the pourer "B"
and the transfer arm "A", while the planner's model tags are the reverse. This document only uses
**pourer (west)** and **transfer (east)**.

### 2.4 Mounting details

- **Reagent rack RK-03 (one piece).** Three cups with webs between them and a spine along the
  **west face of the Y-left rail**. The spine bolts into the rail's west-face slot with 2 × M4 ×
  10 and M4 T-nuts at Y 330 and Y 560. A hook around the rail's **south end face** (Y 290) is the
  Y datum, so the cups land on the pocket positions above without measuring. It replaces the three
  loose RK-03 stands on the placement sheet.
- **Carousel + auger unit.** TT-01 base, lazy Susan, TT-02 deck, TT-03 horn spacer and the TT-04
  v4 ring, plus E5, PS-01 v2 post and the DH-01/DH-02 auger, all move as one unit rotated 220.6°.
  The auger outlet must sit over the auger pocket: the outlet is Ø10 inside a Ø56 beaker, so about
  ±20 mm is fine. VHB tape goes under TT-01, and the **TT tie plate** bolts the unit to the
  Y-right rail so it can't drift.
- **Scale.** WS-01 v4 clamps on E6 using its E6 notch. The 1 kg load cell is clamped to WS-01 at
  one end and carries the WS-02 v3 pan (100 mL locating ring) at the other, with M4 at both ends.
  Only the cell's metal ends touch plastic, so flex in the PLA does not change the reading.
- **Alignment jigs JG-01..06** (printed). Set every position with a jig, not a tape:

| Jig | Sets |
|---|---|
| JG-01 ×2 | Gap from E6's north face to the X-front rail's south face: 122 mm |
| JG-02 ×2 | Gap between the X-front and X-back rails: 50 mm |
| JG-03 | E6 position: hooks the Y-left south end and runs to E6's south face |
| JG-04 | Pourer base X: from Y-left's west face to the base's west edge |
| JG-05 | Transfer base X: from the base's east edge to Y-right's east face |
| JG-06 | Scale X: 7 mm gauge between S2's east face and WS-01's west face |

---

## 3. The arms

| | Pourer (west) | Transfer (east) |
|---|---|---|
| Base axis | (397.4, 599.7) | (604.8, 599.7) |
| Job | **Every pour**: developer and water onto the scale, and both beakers into the funnel | **Only carousel ↔ scale moves** |
| Grasp | **Side grasp**: the hand holds the beaker from the side | **Top-down grasp** |
| Pour | **Wrist-roll pour**: the wrist roll tilts the beaker through θ 40→105° along a planned, collision-checked path | Never pours |
| Grip height (GRIP_H, fingers above the beaker bottom) | 40 mm for the reagent pours onto the scale; 30 mm for the funnel pours | Top-down |

- **Carries are joint-space**, lifted to Z 300 (grasp centre), with roll and pitch held in sum
  so **the beaker stays upright** the whole way.
- While one arm works, the other is **parked** in a folded pose (shoulder 60°, elbow −150°).
- Gripper: TPU fin-ray fingers (GR-03) on printed bodies (GR-01 body, GR-02 moving jaw). The
  gripper closes to a torque limit, which also detects a missed grasp.
- **Teaching the top-down pick (transfer arm).** Centre the beaker so the **fixed** fin-ray finger
  clears the beaker wall by about **3 mm** (the beaker sits about 14 mm toward the moving jaw from the
  old side-grasp centre line), and **open the jaw wide before descending**; close the moving jaw onto
  the beaker only at the bottom. Leave the beaker sideways along the finger channel (lift ~20 mm,
  then slide out) rather than swinging away with the fingers still around it.
- **Stage crank limit.** The stage crank is limited to **150°** (not 180°): past about 155° the
  ST-13 crank's M3 × 8 screw heads hit the underside of the ST-11 sled. At 150° the sled travels
  97.3 mm instead of 100 mm.
- **Margin** below means degrees to the nearest joint limit, where the limit is the URDF limit
  minus 5°. The rule is ≥ 10° at picks, places and pours, and ≥ 5° on carries. **Clearance** is the
  true distance from the arm or held beaker to the nearest object along the whole path.

---

## 4. The run, step by step

Before step 1: P1 (empty) is in the carousel pick pocket; the arms are parked; the carousel turn
is verified at 31.8° margin (elbow) with parked arms 18.9 mm clear of the frame.

| # | What happens | Arm | Parts | Sensing / control | Verified margins (Update 13) |
|---|---|---|---|---|---|
| 1 | **P1: carousel → scale.** Pick the empty beaker P1 from the pick pocket and set it on the pan | Transfer, top-down | TT-04 v4 ring, WS-02 v3 pan | Gripper torque limit; the Mega **tares** the scale after the place | Pick 17.7°, place 17.3°, carry 9.5° (wrist flex). Clearance 7.9 mm (arm vs WS-02 pan). **PASS** |
| 2 | **Developer pour onto P1 to 39 g.** Pick the developer beaker from rack pocket 1, carry it upright, tilt in, pour onto P1 and return the beaker to the rack. **Grip 40, lip 45 mm above P1's rim** | Pourer, side grasp, wrist-roll pour | RK-03 rack, load cell + HX711, WS-02 | **Closed loop on the scale** at 80 Hz: feed-forward plus PI on flow, slows near the target, predicts the cut-off and snaps the beaker upright. Approaches from below only | Pick 11.6°, carry 11.6°, pour 35.7° (elbow), tilt-in 35.7°. Clearance 6.2 mm (arm vs rack). Stream lands 15.9 mm off centre (limit 20). **PASS** |
| 3 | **P1 → funnel pour.** Pick P1 off the scale, carry it to the funnel, pour it all into the flask (which already holds the soap), and bring P1 back to the scale. **Grip 30, lip 65 mm above the funnel rim** | Pourer | Funnel, 250 mL Erlenmeyer in ST-05 collar | Pour path from the planner; the scale reading after P1 returns confirms it is empty | Pick 10.4° (wrist flex), carry 10.4°, pour 74.9°, tilt-in 66.0°. **Clearance 5.3 mm (held beaker vs funnel).** Landing 7.2 mm (limit 40), lip drift 13.2 mm. **PASS** |
| 4 | **P1 → carousel.** Put empty P1 back in the pick pocket | Transfer | TT-04 v4 | Gripper | Pick 17.3°, place 17.7°, carry 9.5°. Clearance 7.9 mm. **PASS** |
| 5 | **Yeast dose.** The carousel turns P2's pocket to the auger station (180° from the pick), the auger doses **about 7 g by revolutions**, then the carousel turns P2 back to the pick pocket | – (arms parked) | Carousel M45CHW; FB5311M-360 → 25T horn → DH-02 v4 screw in DH-01 v5, on PS-01 v2 | Servo feedback wire counts revolutions × calibrated g/rev. Reverse ¼ turn after the dose to stop dribble. Stall rule stops and reverses on a jam | Parked arms: 31.8° (elbow), 18.9 mm. Outlet 169.5 above the table, about 34 mm above the beaker rim. **PASS** |
| 6 | **P2 → scale (verify yeast).** If the dose is short, P2 goes back for a top-up (at most 2) | Transfer | WS-02 | Scale checks the yeast weight (±0.7 g) | Same geometry as step 1: 17.7° / 17.3° / carry 9.5°, 7.9 mm. **PASS** |
| 7 | **Water pour onto P2 to +30 g.** Pick the water beaker from rack pocket 3, pour onto the yeast, return it. Grip 40, lip 45 mm | Pourer | RK-03, scale | Same closed-loop pour as step 2. Then wait about 60 s for the yeast slurry to activate | Pick 11.2° (wrist flex), pour 35.6° (elbow). Clearance 5.8 mm (arm vs rack). Landing 10.2 mm. **PASS** |
| 8 | **P2 → funnel. The reaction starts.** Pour the slurry into the flask, untilt and lift clear | Pourer | Funnel, flask | The stage must not move until the pourer is clear | Same as step 3: pick 10.4°, pour 74.9°, tilt-in 66.0°, 5.3 mm, landing 7.2 mm. **PASS** |
| 9 | **P2 → carousel** | Transfer | TT-04 v4 | Gripper | Same as step 4: 17.3° / 17.7° / 9.5°, 7.9 mm. **PASS** |
| 10 | **ERUPT.** The stage crank moves the sled **97.3 mm** toward the audience; the foam erupts | – | Stage M45CHW on ST-12 servo bridge; ST-13 crank (50 mm) and ST-14 connecting rod (80 mm, F625ZZ bearings, ST-15 spacers, M5 pivot) drive the ST-11 sled along S1/S2; flask in ST-05 collar inside the ST-07 catch well | WORK is the crank dead centre at 0°; ERUPT is the crank at 150° (past ~155° the M3x8 crank screws hit the sled). Smooth move of about 2.5 s | Not part of the arm planner; mechanical |

The carry margin of 9.5° (steps 1, 4, 6, 9) is below the 10° pick/place rule but above the 5°
rule for carries.

---

## 5. Checklists

### 5.1 Setup (once per venue)

1. **Frame.** Assemble the square with the X rails 74 mm north of the CAD position. Use JG-01 (E6
   → X-front, 122 mm) and JG-02 (X-front → X-back, 50 mm) to set the spacing, and JG-03 to locate
   E6. All frame joints are M4 into T-nuts.
2. **Table.** Set the bench with the table's front edge about 20 mm in front of the stage rails,
   then clamp it with the two C-clamps.
3. **Arms.** Bolt the pourer base at 132.4 mm and the transfer base at 339.8 mm from the X rails'
   west end. Set them with JG-04 and JG-05. 4 × M4 × 20 per base (2 button heads in the front row,
   2 socket heads in the back row), into M4 T-nuts.
4. **Scale.** Clamp WS-01 v4 on E6 with the pan on the south side. Set X with JG-06 (7 mm from S2's
   east face). Check pan centre at tape (+375, −23).
5. **Rack.** Hook RK-03 on the Y-left south end and bolt the spine into the west-face slot (2 × M4 ×
   10).
6. **Carousel + auger unit.** Place it at tape (+562.9, +93.5), rotated 220.6°, pick pocket facing
   the transfer arm. Check the auger outlet sits over the auger pocket. VHB under TT-01; bolt the
   TT tie plate to Y-right.
7. **Check distances** (tape measure from each base axis): rack pockets and scale 290–295 mm from
   the pourer; carousel pick and scale 191–193 mm from the transfer arm.
8. **Electrics** per [electrical.md](electrical.md): Mega on laptop USB, e-stop box within reach of
   the operator, servo power only through the e-stop.
9. **Auger** (once, after printing): follow the post-print steps in §7 and the dry run with yeast.
10. **Cover the table** under the ERUPT end of the stage with something absorbent.

### 5.2 Before each run (operator, goggles and gloves on)

- [ ] **Flask:** 15 mL dish soap + food colouring in the 250 mL Erlenmeyer. Flask in the ST-05
  collar inside the ST-07 catch well, on the sled at **WORK**. Funnel in the neck.
- [ ] **Rack:** developer beaker (pocket 1) and warm-water beaker (pocket 3) filled with rough
  amounts. Anything above what the recipe needs is fine; stay well below the brim.
- [ ] **Hopper:** dry yeast in DH-01. Keep it dry; damp yeast can bridge.
- [ ] **Carousel:** two clean, empty 100 mL beakers. P1 in the pick pocket; P2 in its pocket.
  The ring has 4 pockets, so one load covers 2 runs.
- [ ] Both arms parked; nothing loose inside the arms' reach.
- [ ] Laptop on, Mega connected, e-stop **released**, someone's hand near it.
- [ ] Press go. The software prechecks servos, scale and taught poses before step 1.

### 5.3 Reset after a run

1. Wait for the foam to stop growing. **It is warm and still contains peroxide: gloves on.**
2. Slide the sled back to WORK (or command it).
3. Rinse the flask, funnel, collar and catch well with **cold water**. Wipe up the table.
4. Rinse P1 and P2, or load fresh beakers in the carousel.
5. Top up the reagent beakers and yeast hopper if needed. Reload the soap and dye in the flask.

---

## 6. Fasteners

| Size | Where | Notes |
|---|---|---|
| **M4** | Every frame joint, both arm bases, the scale clamp on E6, the RK-03 spine, the TT tie plate, load cell and pan | Owned M4 screws and T-nuts plus the ordered M4 T-nuts, M4 × 10, M4 kit and M4 × 20 SHCS/BHCS |
| **M3** | Servo horns (25T aluminium disc horns: carousel deck, stage crank, auger flange M3 × 6) | From the M3 kit (F-01). The order sheet also uses this kit for the gripper finger clamps and the auger head, all as through-bolts with nuts |
| **M5** | **Stage pivot only**: 1 × M5 × 25 + nut through the F625ZZ bearings | Blue Loctite instead of nylocs |

**No screw threads into printed plastic.** Fastening is through-bolt with a nut, a T-nut, or the
tapped aluminium horn.

---

## 7. Auger: post-print steps

From [auger_review.md](../tools/layout/auger_review.md), FINAL update:
1. Print DH-01 v5 from the **bore-blocker** slice (no support inside the Ø15 bore or the outlet).
2. Pull the bell and window supports out toward the servo end. Clean the support scar off the
   seal-zone crown.
3. DH-02 v4: remove the supports and dress the flight tips. Check it spins freely in the bore by
   hand. Flights start at 16 mm, so all 4 horn screws (M3 × 6) go in; use a ball-end key at
   10–25°.
4. Bolt DH-02 to the horn, spin it slowly on the servo, and touch 240-grit to the flange rim to true
   it (about 0.2 mm). Optionally ream the bore Ø15.
5. **Dry run with real yeast:** check the conveying direction, measure grams per revolution, check
   dribble (reverse ¼ turn after each dose) and look for yeast leaking back into the bell.

---

## 8. Tightest spots: check these first

1. **Pourer side-grasp picks, 10–12° margin.** Rack picks 11.2–11.6° and the scale pick 10.4°, all
   on wrist flex. These are the closest to a joint limit in the whole run. If an arm base, the
   rack or the scale is a few mm off, these fail first. Verify the pourer base (JG-04), the rack hook
   and the scale (JG-06) before anything else, and teach these poses carefully.
2. **5 mm beaker-to-funnel gap** (5.3 mm, held beaker vs funnel) during the funnel pours, steps 3
   and 8. Check that the funnel sits straight in the flask neck, the flask is seated in ST-05, and
   the sled is exactly at WORK. Run the funnel pour slowly with an empty beaker first.
3. Lower priority: the 5.8–6.2 mm arm-to-rack clearance on the reagent pours, the 7.9 mm arm-to-pan
   clearance on transfer places, and the 9.5° transfer carry margin.

**Beakers:** the EISCO 100 mL beakers arrive **Saturday**. Until then, do dry runs with the
printed 100 mL dummy beakers (`DUMMY-BEAKER-100mL_56x74`, 56 × 74).
