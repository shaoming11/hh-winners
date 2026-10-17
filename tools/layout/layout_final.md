# Final layout re-solve: status at the deadline

**Status: partly solved.** Arm A's carousel ↔ scale transfers pass every requirement (≥10° joint margin, collision-free path). Arm B's pours are not yet collision-free.
- **Funnel pour:** almost clear. Of 22 tilt samples, only 2–3 at θ 40–43° collide: the L5 fixed jaw touches the funnel rim at 11–12 voxel points.
- **Scale pours:** fail. With the receiving beaker also 56 mm wide and the lip 15–20 mm above its rim, the fingers on the lip side go below the receiving beaker's rim. The fingers reach to 17 mm below the held beaker's rim (GRIP_H 40 + 17).

Code: `layout_final.py`. Data: `layout_final.json` (step records, coordinates, positions along each extrusion). Run with `python -W ignore layout_final.py out.json` (about 8 min).

## Rules used
- **Joint limits:** CDR-31 (URDF minus 5°), with ≥10° margin on every joint. All beakers are EISCO 100 mL, Ø56 × 74, gripped at GRIP_H 40.
- **Grasp centres:** carousel at Z 100.2 (bottom 60.2), scale at 103.7 (bottom 63.7), RK-03 at 100.2 (pocket floors raised so the bottom sits at 60.2).
- **Auger:** PS-01 raised +25 mm, so DH-01 spans Z 160–230. This is included in the voxel world.
- **Pours:**
  - θ runs 40→105°, with joint steps ≤2° per 1° of tilt.
  - The lip may drift up to ±25 mm along the pour direction, and must stay inside the receiver opening: within ±23 mm of the scale axis, ±43 mm of the funnel axis.
  - Lip height above the rim: funnel 40–48 mm, scale 17.5–19.5 mm.
- **Why the lip has to drift:** while the beaker passes horizontal, the arm loses one degree of freedom (the beaker axis lines up with the arm's parallel joint axes). A pour with the lip held fixed is impossible there, so the lip must move 8–25 mm.

## Coordinates (world mm, table top Z 0)
| Item | Value |
|---|---|
| Arm A base axis | (355.0, 599.7) |
| Arm B base axis | (592.0, 599.7) |
| X rails | front centre Y 582.5, rear centre Y 652.3 (both +74). Rear base edge at Y 699.7, table edge at 700 |
| Y-left rail | Y 242.3–642.3 (moved −47.7). Y-right rail unchanged (Y 270–670) |
| Carousel centre | (175.0, 326.3), moved 43.7 south |
| TT-04 v4 | 4 pockets at r 88. Pick at 0° = (263.0, 326.3); auger at 180° = (87.0, 326.3). Yeast moves 180°, so the servo needs ±90° about its index |
| Scale pan centre | (470.0, 320.0), on E6. E6 moves to Y 343.5–363.5 |
| Funnel axis / rim | (899.5, 440.0, Z 233) |
| WORK stage | rotated 180° about the funnel axis. ST-01 bolts on Y-right at (675, 424) and (675, 442). ERUPT is at Y 540 (+Y) |
| RK-03 pockets (bottom Z 60.2) | (581.4, 294.9), (665.8, 303.8), (744.5, 335.6): r 305 from arm B at bearings −2°, 14°, 30° |

## Step order, assignment and margins
| # | Step | Arm | Result |
|---|---|---|---|
| 1 | Carousel pick (P1 at 0°) → upright carry at Z 175 → scale place | A | **OK.** Pick 11.1° (wrist flex), place 17.2° (wrist flex), carry 11.1°. No collisions on approach, carry or retreat |
| 2 | Rack dev → pour onto scale → back to rack | B | **FAIL.** Manifold margin 35–37° (well clear of limits), but the fingers hit the receiving beaker at θ 40–70° |
| 3 | Rack water → pour onto scale → back | B | Fails the same way as step 2 |
| 4 | Scale → pour into funnel → back to scale | B | **Nearly OK.** Manifold margin 53°, drift −4..+10 mm. Only L5 vs funnel rim at θ 40–43° (11–12 points) |
| 5 | Scale → carousel place | A | **OK.** Pick 17.2°, place 11.1°, carry 11.1° |

The steps then repeat for the yeast beaker P2: auger at 180° → turn 180° → pick at 0°, then steps 1, 3, 4, 5. The soap pocket is evaluated too; it fails like step 2.

Arm A never pours; arm B does every pour. Park poses are folded with shoulder 60° and elbow −150°: pan −60° for A, +30° for B. Arm-vs-arm and frame checks were clear in every pose evaluated.

## Remaining fixes (not run yet)
1. **Scale pours.** Raise the scale-pour lip to about 25–30 mm above the rim (this breaks the 15–20 rule), or grip the reagent beakers lower (GRIP_H about 30, which puts the finger top 27 mm below the rim). The fingers are what collide; reach is not the problem.
2. **Funnel pour.** Use a 50 mm lip height or a −40 mm start offset; this is expected to clear the 2–3 rim samples. It needs one more run.
3. **RK-03 pocket 1** sits 50 mm from the scale's base footprint. Check its support.

## Physical change list
- **X rails:** both slide +74 mm in Y. Front rail centre goes 508.5 → 582.5, rear 578.3 → 652.3. Flip the rear corner brackets to the south side of the rear rail.
- **Arm bases:** A slides +25 mm in X (pan axis 90 mm from the X-rail west end). B slides +22 mm (327 mm from the west end).
- **Y-left rail:** slides −47.7 mm (now Y 242.3–642.3) and is re-clamped.
- **Carousel (TT-01):** bolts move to Y 311.3 and 341.3 (69 and 99 mm from the Y-left south end).
- **E5, PS-01, FX-01:** move −43.7 mm with the carousel. FX-01 bolts go to Y 247.3 and 265.3, which is the same E5 relation, only shifted along Y-left. **Flag:** check the FX-01 holes.
- **PS-01:** +25 mm taller (already decided).
- **E6:** moves from Y 440 to Y 353.5 (centre), 111.2 mm from the Y-left south end. The scale saddle goes on E6 with the pan 205 mm from E6's west end (X 265).
- **WORK stage:** rotated 180° and mounted on the outside of Y-right. Its bolts sit 154 and 172 mm from the Y-right south end. The 400 mm Y rails are reused; no extra extrusion is needed.
- **Clearances to check:**
  - ST-01 (X 649–719) clears arm B's base (X ≤ 647) by only 2 mm.
  - REF-BIN has to move out of X 803–980, Y 302–508.
- **Printed parts that change:** TT-04 v4, WS-02 ring (Ø56), RK-03 (pocket floors at 60.2), PS-01 (+25 mm). No other printed part changes, but fixes 1 and 2 above may be needed.

---
# Update 2: full end-to-end run with GRIP_H 30 (coordinator decisions 1–5) — RESULT: FAIL

**Changes since the first run**
- All 100 mL grasps use GRIP_H 30. The finger band spans 13–47 mm above the beaker bottom.
- Arm A's base axis moves to **(380.0, 599.7)** and arm B's to **(617.0, 599.7)**, to recover reach lost by the lower grasp. RK-03 pockets: (606.4, 294.9), (690.8, 303.8), (769.5, 335.6) at Z 60.2.
- ST-01 and REF-BIN are removed from the collision world. The auger head is at its new height (DH-01 underside Z 160).
- **Table:** 1830 × 760. With the table at X −200…1630 and Y −30…730, every base is ≥30 mm inside the edges. The bases' rear edge is at Y 699.7.
- **S1/S2 mounting:** in the rotated-stage layout, the sled rails run along Y east of Y-right, and **there is no free crossbar for them**. E6 now carries the scale. Two options:
  - rotate the stage 90° instead, so S1/S2 run along X and their west ends bolt to the outside face of Y-right with 2020 corner brackets (that rail then acts as the crossbar). This moves the funnel and eruption geometry, which has not been evaluated;
  - or keep E6 as the S1/S2 crossbar and put the scale on another extrusion. With all 8 in use, that needs a 9th 400 mm 2020.

**Per-step result** (margin = degrees to the nearest CDR-31 limit; clearance not reported because no step produced a valid path)

| Step | Arm | Min margin | Collision | Result |
|---|---|---|---|---|
| Carousel turns (arms parked) | – | 31.8° (elbow) | parked arms clear the frame by 18.9 / 19.0 mm | PASS |
| 1 P1 carousel → scale | A | 9.7–10.1° (wrist flex) at the carousel | L5/L6 fingers hit the TT-04 collar in the **old (v3) mesh**: fingers at Z 73.2 vs collar top 74.6 | FAIL |
| 2 developer → pour onto scale → back | B | pour 36–41° | held beaker and fingers enter the receiving beaker at θ 40–48°; clear from about θ 52° on. A 28 mm lip reduces but doesn't remove it | FAIL |
| 3 P1 → funnel pour → scale | B | pour 57–59° | 16–17 of 17 tilt samples hit the funnel (lip 49.5, start offset −40) | FAIL |
| 4 P1 scale → carousel | A | 9.8–10.2° at the scale grasp | same TT-04 collar contact at the carousel | FAIL |
| 5–8 | – | – | the yeast cycle repeats the geometry of steps 1–4 | FAIL (same reasons) |

**What it would take to pass**
1. **Carousel (A):** the TT-04 v4 collar top must be ≤ bottom + 9 mm (Z ≤ 69) so it clears fingers at bottom + 13. I need the v4 mesh to verify this. Margin at GRIP_H 30 is only ~10° (wrist flex). Arm A needs to be about 10 mm further from the pick pocket for margin; the Y-left rail length (400 mm) is what limits that.
2. **Scale pours (B):** with 56-into-56 beakers, the pour cannot start at θ 40° with the lip only 15–28 mm above the rim. The held beaker's wall slopes 50° below horizontal and drops into the receiving rim. Start the manifold at θ ≈ 52–55° (tilt in from above), or let the lip go above 35 mm until θ 50°.
3. **Funnel (B):** needs the collision part named (out of time) and a lip search above 50 mm.

Code: `layout_final.py`. JSON: `layout_final.json`. The background run that writes the JSON was still running at the deadline, so the JSON step records may be from the previous run.

## Update 3: TT-04 v4 geometry (pitch r 84, pocket ID 56.6, walls to Z 70.6, beaker bottom Z 61.7)
- **New positions:**
  - pick = carousel centre + 84 X = **(259.0, 326.3)**;
  - auger pocket = centre − 84 X = **(91.0, 326.3)**;
  - PS-01 slides **+4 mm along E5** (in addition to the −43.7 Y shift with the carousel).
- **Carousel pick (arm A, GRIP_H 30):**
  - The old v3 TT-04 mesh is replaced in the collision world by the v4 pocket walls.
  - r = 298.9 mm, best margin **11.3° (wrist flex)**.
  - The finger band starts at Z 74.7, which is 4.1 mm above the 70.6 pocket walls. The voxel check (2.5 mm dilation) still registers 3–4 touching L5 points, so call it a marginal PASS at about 4 mm clearance.
- **Scale grasp (arm A):** 10.2° (wrist flex), collision-free.
- **Still FAIL:**
  - B scale pours: the pour starts at θ 40°, and at a 15–28 mm lip the held beaker meets the receiving rim (θ 40–48°).
  - B funnel pour: collides at 16–17 of 17 tilt samples (lip 49.5, start offset −40).
  - Fixes are in Update 2.

---
# Update 4: coordinator round 3 (stage unrotated, E6 = S1/S2 crossbar, tilt-high-then-descend pours) — STOPPED at the 45-min mark: FAIL

**Layout used**
- **Arm bases:** A at (380.0, 599.7), B at (617.0, 599.7).
- **Stage and funnel:** exactly as in CAD, with E6 at Y 430–450 as the S1/S2 crossbar. Funnel at (450, 282), rim Z 233.
- **Scale:** WS-01 saddle on the **outside of Y-right**, rotated 90°. Pan centre (708.5, 330.0); saddle bolts on Y-right at Y 271.5 and 326.5, which is 1.5 and 56.5 mm from the rail's south end (Y 270).
  - Distance from arm A: 415 mm. Distance from arm B: 271 mm.
  - The pan's west edge (X 671) clears S1/S2 (X ≤ 669) by 2 mm.
  - A rail position is found, so no 9th extrusion is needed for the scale.
- **Carousel:** TT-04 v4, r 84; pick at (259.0, 326.3), auger at (91.0, 326.3). PS-01 slides +4 mm along E5. Beaker bottom at Z 61.7, pocket walls to Z 70.6.
- **RK-03:** pockets at r 300 from B, bearings 50°, 65° and 80°: (846.8, 407.0), (888.9, 473.1), (912.4, 547.6), beaker bottom at Z 60.2. RK-03 bolts to the outside face of Y-right and rests on the table (pads), since it sits off the extrusions.
- **Steps:**
  - A: P1 carousel → scale.
  - B: developer → pour onto the scale → rack.
  - A: scale → funnel pour → scale → carousel.
  - Repeat for P2 (yeast at the auger, then water).
- **Carries:**
  - A between carousel and scale goes at Z 255 via (300, 410) and (600, 410), clear of TL-01 and the funnel.
  - Scale pours: lip ≥ 40 mm above the rim while tilting to 55°, then down to 26–34 mm, pour 55–105°, landing within r 26.
  - Funnel pour: lip 50–90 mm above the rim, start offset 0 to −60 mm, landing within r 35.

**Per-step result** (margin = degrees to the nearest CDR-31 limit; clearance in mm only where a path completed)

| Step | Arm | Min margin | Min clearance | Result | What hits |
|---|---|---|---|---|---|
| Carousel turns (arms parked) | – | 31.8° (elbow) | 18.9 mm (A), 19.0 mm (B) to the frame | PASS | – |
| 1 / 5 P1/P2 carousel → scale | A | 11.3° at the carousel (wrist flex). Scale grasp ≥ 30° expected at r 415 | not computed (no complete path) | FAIL in the voxel check | fingers vs TT-04 v4 pocket wall: 3–4 points, geometric gap 4.1 mm (fingers from Z 74.7, wall top 70.6). This is below the voxel dilation (2.5 mm voxel + 1). Really a marginal PASS that needs a finer check |
| 2 / 6 reagent → pour onto scale | B | manifold 30.0° | – | FAIL | 22 manifolds tried, all hit at θ 55° with lip 26–34 mm: the fin-ray fingers wrapping the **underside** of the held beaker enter the receiving beaker (S) |
| 3 / 7 scale → funnel pour | A | manifold 79.7° | – | FAIL | 27 manifolds tried; first hit at θ 55°: **L5 (fixed jaw / GR-01 finger) vs REF-FUNNEL-EISCO4**, 22 points |
| 4 / 8 scale → carousel | A | as in step 1 | – | not reached before the stop | – |

**Why the pours fail.** The blocker is the gripper geometry, not reach or joint margin: pour margins are 30–80°.
- With GRIP_H 30 the fin-ray fingers wrap the lower half of the beaker.
- Once the beaker is tilted 55° or more, the fingers on its underside sit 15–35 mm below the lip.
- Scale: the lip is only 26–34 mm above the receiving rim, so those fingers are inside the receiving beaker's outline.
- Funnel: the L5 jaw reaches the funnel cone (Ø102 at the rim) even with the lip 50–90 mm up, because the jaw passes over and below the rim beside the beaker body.

**What would pass (needs your decision)**
1. **Hand roll during the pour.** Constrain the pour so the finger plane stays on the upper side of the tilt (no fingers under the beaker). The manifold search does not constrain this yet; it is a solver change, about 1 hour.
2. **Scale pour lip.** With the lip ≥ 45 mm above the receiving rim from θ 55° on, the underside fingers clear (estimated, not run). The stream then falls about 45 mm into a Ø52 mouth, so it lands within r 26 only with low drift.
3. **Funnel.** Name the exact contact (rim vs cone) with a finer explain run. If it is the cone wall, a higher lip will not help; a start offset that puts the jaw outside the funnel (≥ +60 mm, beaker body outside the rim) needs the stream-landing check.

The background run will finish steps 4–8 and rewrite `layout_final.json`; steps 5–8 repeat the geometry of 1–4.

---
# Update 5: pitch pour (tilt about the grasp axis, roll frozen) — NOT FEASIBLE on the SO-101

Solver: `pitch_pour.py`.
- Wrist roll is frozen at the upright-grasp value. The pitch chain plus pan pin the lip exactly.
- The beaker tilts outward, so the lip points away from the base.
- Path: upright with the lip 45 mm above the rim → tilt to 55° while high → descend to the pour lip → tilt 55–105°.
- Tested on arm B (identical to A, translated). Lip directly ahead and at 30° bearing; receiver distance 100–260 mm from the base axis; GRIP_H 30. Joint limits are not enforced in the solve; the margin is reported.

| Receiver | Lip above rim | r (mm from base axis) | Best min margin over the path |
|---|---|---|---|
| Scale (rim Z 137.7) | 30 mm | 100 / 120 / 140 | −55° / −63° / −72°, all wrist flex |
| Scale | 30 mm | 160–260 | no solution at all, even with limits ignored |
| Funnel (rim Z 233) | 28 mm | 100–260 | no solution except one at r 160: −123° (elbow) |

**Why.** In a pitch pour the hand points straight down at 90° tilt, so the wrist-flex axis must sit about 150 mm (grasp offset) + 28 mm (beaker radius) above the lip.
- **Scale:** lip at Z ≈ 168, so the wrist must be at Z ≈ 350. The upper arm + forearm is 251 mm from a shoulder at Z 139, so the wrist must be within about 140 mm of the shoulder radially. That forces the receiver close to the base (r ≤ ~150), where wrist flex is far past its limit (−55° or worse).
- **Funnel:** lip at Z ≥ 256, so the wrist must be at Z ≥ 434. That is out of reach (max about 390).

The inward variant (lip toward the base, hand pointing up) puts the gripper body under the held beaker, straight down through the receiver. So it fails the "never underneath" rule and collides.

**Conclusion.** With the hand gripping the beaker side-on (hinge vertical) at GRIP_H 30, the SO-101 can pour only by rolling the beaker sideways (Update 4). In that pour the fin-ray fingers end up under the beaker. The options left are:
- a roll pour with the finger plane constrained to the upper side (not yet run);
- a higher lip;
- a different grasp (e.g. hinge horizontal, gripping from above). That needs a gripper or cup change, which is outside the current rules.

Arm A transfers and the parked/carousel steps stay as in Update 4: carousel 11.3° (wrist flex), marginal 4 mm clearance to the TT-04 v4 wall.

---
# Update 6: top-down grasp feasibility map (`topdown.py`) — GO for picks, NO-GO for pours

**Model.** The hand points down along the beaker axis.
- The beaker axis is the fin-ray finger direction, through the D56 grasp line.
- The rim sits at the palm (47 mm from the jaw hinge), so the fingers wrap the upper part of the beaker.
- Pours: lip pinned exactly (the top-down grasp has no 90° singularity), θ 0→105°, joint steps checked. Margin = degrees to the nearest CDR-31 limit (URDF minus 5°).

**Top-down pick/place: best min margin vs radius from the base axis** (straight ahead and 45° give identical results)

| r (mm) | 100 | 120 | 140 | 160 | 180 | 200 | 220 | 240 | 260 | 280 | 300 | 320 | 340 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| carousel, bottom Z 61.7 | −15.9 | −6.1 | 2.6 | 9.8 | 15.4 | 19.2 | 21.4 | **22.1** | 21.3 | 18.9 | 14.4 | 5.5 | – |
| scale, bottom Z 63.7 | −16.2 | −6.6 | 2.0 | 9.1 | 14.6 | 18.4 | 20.6 | **21.2** | 20.4 | 18.0 | 13.5 | 4.1 | – |
| rack, bottom Z 26.2 | −12.4 | 1.7 | 14.2 | 23.9 | 30.7 | 34.9 | 37.0 | **37.3** | 36.2 | 33.7 | 29.6 | 23.2 | 9.8 |

The ≥10° window is **r 165–305** at the carousel and scale heights, and r 135–335 at rack Z 26.2. Top-down picks therefore fit about 100 mm closer to the base than the side grasp (which needs ≥ 283). The CAD station positions (r 132–150) still fail.

**Top-down pitch pour: best min margin over θ 40–105°, lip pinned exactly**

| Receiver | r 140 | 180 | 220 | 260 | 300–380 |
|---|---|---|---|---|---|
| Scale (rim 137.7, lip +30), lip toward the base | −128 (shoulder) | −52 (wrist flex) | −30 (wrist flex) | **−16 (wrist flex)** | no solution |
| Scale, lip away from the base | −86 (wrist flex) | no solution | no solution | no solution | no solution |
| Funnel (rim 233, lip +50/+60/+70) | no solution | no solution | no solution | no solution | no solution |

- Joint steps reach 2.3–7.9° per degree of tilt on several branches, above the 2° rule.
- If the lip is allowed to slide, the margin reaches +12 to +19°, but only with 140 mm of lip drift. That is not a pour.

**Verdict: NO-GO for top-down pours.** At 90° tilt the hand would have to hold the beaker horizontally from its end, with the wrist about 150 mm beyond the rim at lip height. On the scale this runs wrist flex to its limit (−16° at best). On the funnel (rim 233 plus 50) it is beyond the arm's reach.

**Feasible combination, if a regrasp is acceptable:** use top-down for every pick and place (r 165–305, margin up to 22°). Then set the beaker on a regrasp spot and re-pick it side-on for the roll pour. The side roll pour is still blocked by the fingers under the beaker (Update 4), unless the finger-plane-on-top constraint is solved. That has not been tried.

---
# Update 7: grasp-offset study (`offset_study.py`), kinematic margins only

**Geometry (arm B; arm A is identical)**
- Wrist-flex axis → jaw hinge (gripper joint axis): **94.6 mm**. This is fixed by the STS3215 wrist/jaw body, not by the printed fingers.
- Jaw hinge → D56 grasp centre: **71.0 mm along the finger, 24.2 mm sideways** (gripper_design.json centre2d).
- Total wrist-flex → grasp centre: **161.8 mm** (the "~150"). The printed GR-0x fin-ray parts contribute the 71 mm. Of that:
  - 47 mm is palm clearance (`clear_palm`: GR-01 block + fin-ray base);
  - the beaker radius (28) sets the rest.
- **Current D56 contact:** 40.4 mm out along the 65 mm fin-ray finger (`contact_u`).
  - Side grasp: a finger of about 50 mm still wraps the beaker (contact 40 + about 10 mm of finger beyond it). Shortening only the finger tips does **not** move the grasp centre; the palm clearance (47) and beaker radius do.
  - Top-down grasp: the offset is wrist-flex → hinge (94.6) + palm + the length of beaker that the fingers must wrap.

**Best min margin (deg to the URDF−5° limits) vs offset, best receiver radius in brackets.** Side pours: lip drift ≤ 25 mm. Top-down pours: lip pinned.

| Offset (wrist-flex → centre) | Centre moved toward hinge | (a) side roll → scale | (b) top-down pitch → scale | (c) top-down pitch → funnel (lip 50) | (d) side roll → funnel |
|---|---|---|---|---|---|
| 150 | 13.5 mm | 37.9 (elbow, r 300) | −77.6 (shoulder) | no solution | 78.7 (wrist flex, r 320) |
| **130** | 37 mm | 47.8 (wrist flex, r 300) | **10.2 (wrist flex, r 300)** | **28.7 (wrist flex, r 180)** | 79.2 (wrist flex, r 320) |
| 115 | 56 mm | 48.3 (wrist flex, r 300) | 19.1 (wrist flex, r 300) | 36.5 (wrist flex, r 180) | 73.4 (elbow, r 320) |
| 100 | 77 mm | 53.1 (wrist flex, r 300) | 30.3 (shoulder, r 300) | 43.0 (wrist flex, r 220) | 74.0 (elbow, r 260) |
| 85 (non-physical) | 103 mm, which puts the grasp centre 32 mm behind the jaw hinge | 58.1 (shoulder, r 300) | 24.2 (wrist flex, r 260) | 49.4 (wrist flex, r 220) | 77.7 (wrist flex, r 260) |

**Reading**
- **Side roll pours (a, d) have ample joint margin at every offset** (38–79°). Their blocker is finger-vs-receiver collision (Update 4), which this kinematic study does not test, and which shortening does not obviously fix.
- **Top-down pitch pours become feasible at an offset of about 130 mm or less.** That means the grasp centre must sit about 37 mm closer to the hinge: hinge → centre about 34 mm instead of 71.
  - Scale: ≥10° at 130 mm offset, 19° at 115, 30° at 100.
  - Funnel: 29–43° at 115–130 mm offset.
  - In a top-down grasp this means palm clearance of about 10 mm and the fin-ray wrapping the upper beaker body directly below the GR-01 jaw block. It is a GR-01/GR-02/GR-03 redesign (shorter block and shorter fingers), not just trimming the fingers.
  - These are kinematic margins only. Collisions and finger contact quality on a shorter top-down finger have not been checked.

---
# Update 8: Priority 1, side-grasp roll pours with a high lip (current gripper, offset 162 mm) — PASS

Script: `roll_pour_study.py`. Results: `roll_pour_study.json`.
- **Sweep:** GRIP_H 20/30/40; lip 35/45/55/70 mm above the scale rim (50/65/80/100 above the funnel rim); both roll directions; tilt azimuth every 5°; three lip start offsets.
- **Collision check:** full voxel world (1-voxel dilation, real fin-ray finger meshes) against the receiver beaker, scale, funnel, flask, frame and the parked other arm. Clearance is the true point-to-surface distance along the pour, θ 40–105°.
- **Stream landing:** the lip offset at its worst drift + 0.25 m/s × free-fall time over the lip height.
- **Accept if:** lip drift < 15 mm and landing within r20 (scale) / r40 (funnel).
- Layout as in Update 4: scale at (708.5, 330) on Y-right, funnel at (450, 282); arm A at (380, 599.7), arm B at (617, 599.7).

Margins are degrees to the URDF−5° limits.

| Case | Best: lip above rim / GRIP_H | Min margin | Min clearance | Landing offset | Lip drift | Result |
|---|---|---|---|---|---|---|
| Scale pour, arm B (r 284.8) | **70 mm / 40** (roll +, tilt azimuth −150°, start −23.9 mm) | **35.0° (elbow)** | **18.9 mm** (arm vs frame rail) | 19.2 mm (≤ 20) | 13.2 mm | **PASS** |
| Scale pour, alternative | 55 mm / 40 | 31.5° (elbow) | 11.3 mm (arm vs receiver) | 19.0 mm | 13.0 mm | PASS |
| Scale pour, alternative | 45 mm / 40 | 28.9° (elbow) | 7.0 mm (arm vs receiver) | 11.8 mm | 11.8 mm | PASS |
| Funnel pour, arm A (r 325.3) | **65 mm / 30** (roll −, tilt azimuth 0°, start −22.8 mm) | **77.8° (shoulder)** | **5.5 mm** (arm vs funnel) | 20.5 mm (≤ 40) | 14.5 mm | **PASS** |
| Funnel pour, alternative | 65 mm / 20 | 74.3° (shoulder) | 8.3 mm (arm vs funnel) | 11.3 mm | 11.3 mm | PASS |

**Notes**
- **Scale pour:** only GRIP_H 40 passes, so the reagent beakers must be gripped at 40. At GRIP_H 20 and 30 every candidate's fingers enter the receiving beaker (9 of 17 collision-checked candidates hit it).
- **Funnel pour:** GRIP_H 40 has no clear branch; 20 and 30 pass. GRIP_H 30 matches the arm-A transfers (carousel 11.3°, Update 4).
- **Not yet checked:** this verifies the pour manifold (θ 40→105°) only. The approach, tilt-in (from 40 mm higher) and carries still need the end-to-end run in `layout_final.py` with these pour parameters (scale: lip 70, GRIP_H 40; funnel: lip 65, GRIP_H 30).
- **Priority 2** (short gripper) is not needed for the pours.

---
# Update 9: end-to-end run with the final pour settings — PARTIAL at the hard stop

**Settings**
- Scale pours: arm B, grip 40, lip 45 mm (fallback 55).
- Funnel pour: arm A, grip 20, lip 65 mm.
- Carousel and scale transfers: arm A, grip 30.
- Scene collisions: real geometry, undilated voxels (2.5 mm). Clearance is the true point-to-surface distance on the completed paths.
- Other arm parked: shoulder 60°, elbow −150°.

**Final coordinates (world mm; table at X −200…1630, Y −30…730)**
- **Arm A base axis:** (430.0, 599.7) — on the X rails, 165 mm from their west end (X 265).
- **Arm B base axis:** (617.0, 599.7) — 352 mm from the west end.
- **Carousel centre:** (175.0, 326.3). TT-04 v4 pockets at r 84 at 0/90/180/270°. Pick (259.0, 326.3); auger (91.0, 326.3). Beaker bottom Z 61.7.
- **PS-01/E5:** move −43.7 mm in Y with the carousel, and PS-01 slides +4 mm along E5. DH-01 underside at Z 160 (PS-01 +25).
- **Scale (WS-01):** saddle on the **outside of Y-right**, rotated 90°. Pan centre (708.5, 330.0), beaker bottom Z 63.7. Saddle bolts at (675, 271.5) and (675, 326.5), i.e. 1.5 and 56.5 mm from the Y-right south end (Y 270).
- **RK-03 pockets** (beaker bottom Z 60.2): (846.8, 406.9), (888.9, 472.9), (912.4, 547.6). RK-03 bolts to the outside face of Y-right and rests on table pads.
- **Funnel / stage:** as built. Funnel (450, 282), rim Z 233; E6 at Y 430–450 is the S1/S2 crossbar.

**Frame changes**
1. Both X rails move +74 mm along Y: front centre 508.5 → 582.5, rear 578.3 → 652.3. Rear corner brackets flip to the south side of the rear rail.
2. Arm A's base slides +100 mm along the X rails. Arm B's slides +47 mm.
3. Y-left moves −47.7 mm along Y (now Y 242.3–642.3), re-clamped.
4. Carousel (TT-01) slides −43.7 mm along Y-left: bolts at Y 311.3 and 341.3, i.e. 69 and 99 mm from the Y-left south end. E5/FX-01 move with it; FX-01 uses the continuous T-slots.
5. The WS-01 saddle moves from the X-front rail to the outside of Y-right (rotated 90°). Y-right, E6 and the stage are unchanged.

**Per-step result** (margin = degrees to the nearest URDF−5° limit)

| Step | Arm | Min margin (binding) | Min clearance | Result |
|---|---|---|---|---|
| Carousel turns (arms parked) | – | 31.8° (elbow) | 18.9 / 19.0 mm (parked arms vs frame) | PASS |
| 1 P1 carousel → scale | A | pick 19.4° (wrist flex), place 42.9° (wrist flex), **carry 9.2° (shoulder)** | **0.6 mm** (arm vs TL-01) | **FAIL** — retreat from the carousel hits TL-01 (joint-interpolated retreat to park) and the carry dips below 10° |
| 2 developer → pour onto P1 → rack | B | **15.0° (rack pick, wrist flex)**; pour 31.3° (elbow); tilt-in + descent 31.3° | 4.9 mm (arm vs neighbouring rack beaker R1) | **PASS.** Landing 17.6 mm (limit 20), lip drift 11.6 mm |
| 3 P1 scale → funnel pour → scale | A | pour manifold 70.5° | – | **FAIL** — no upright carry from the scale (388 mm from A) to the funnel pre-pour pose; carry IK fails on all 4 candidates. The manifold itself is collision-free |
| 4–8 | – | not reached before the stop | – | steps 5–8 repeat the geometry of steps 1–4 |

**Arm A's scale pick at grip 20:** not extracted before the stop.

**Diagnosis.** Pours and the rack side are solved. The remaining problem is placement: the scale sits 388–425 mm from arm A, near the edge of its reach, and arm A has to reach past arm B and TL-01 to get there.
- The scale needs to be about 300 mm from A **and** about 285 mm from B. That spot is about (520, 330), inside the stage footprint (X 370–669, Y 103–450).
- No existing rail reaches it while E6 stays the S1/S2 crossbar.
- **Options:**
  - **(a)** a 9th 2020 rail across the frame for the scale, with the stage translated south about 120 mm on Y-right/E6 so the scale fits north of the tray. Re-check the funnel distance from A (it becomes about 430 mm, too far, so the funnel pour would move to arm B).
  - **(b)** let arm B do the scale → funnel pour as well. Arm B reaches the funnel at about 350 mm with a high lip, not yet run. Arm A then only does carousel ↔ scale, which is the step-1 problem, so the scale still has to move closer to A.

---
# Update 10: restructure (A top-down carousel ↔ scale only; B all pours) — no layout found under the rules; not run

**Reach windows (margin ≥ 10° to the URDF−5° limits)**
- A top-down pick/place at Z 61–64: r 165–305 (Update 6).
- B side-grasp pick of P1/reagents (Z 84–104): r ≥ ~285.
- B scale pour (grip 40, lip 45): validated at r 285.
- B funnel roll pour, high lip: r ≤ ~380.

**Fixed geometry**
- A and B base axes at Y 525.7 (original X rails) or 599.7 (Update 9); A on the west, B on the east, 220–287 mm apart along X.
- The stage translates only in Y, because E6 spans the Y rails. Funnel X = 450. The tray reaches funnel + 138 mm north, and E6 sits at funnel + 148…168.
- The scale has to sit on a rail. On E6's north face the base's south edge is at pan − 47.8; it must stay north of the tray, so funnel Y ≤ scale Y − 186.

**Conflict.** The scale must be ≥ 285 mm from B and ≤ 305 mm from A, and the funnel ≤ 380 mm from B.
- **Arms at Y 525.7, B at X 550, A at X 330:**
  - The funnel must be at Y ≥ 159, so the scale must be at Y ≥ 345.
  - The scale then needs X ≤ 330 to be 285 mm from B. Its base (X 257–374, Y 297–365) then overlaps the carousel TT-01 base (X ≤ 271) by 14 mm.
  - At X 345 (clear of the carousel), B's distance is only 273 mm: side-grasp margin about 7°, below 10°.
- **Arms at Y 599.7:** every distance from the arms to the stage grows by 74 mm, so the funnel becomes unreachable for B (> 440 mm).
- **Scale on Y-right outside (Update 9):** 285 mm from B but 448 mm from A, beyond the top-down window.

**Closest candidate (not run):**
- Arms on the original X rails (no X-rail move). A at X 330; B slid −20 to X 550.
- Stage + E6 translated −123 mm in Y: funnel (450, 159), E6 at Y 307–327.
- Scale on E6's north face, pan (345, 350.5).
- Expected margins:
  - A: top-down carousel pick (r 211.7) about 21°; scale (r 177) about 12°.
  - B: scale side-grasp pick (r 273) about 7° — **FAIL by about 3°**; scale pour about 30°; funnel pour (r 380) unknown, likely 10–40°.
- **One of these closes it:**
  - **(a)** B picks P1 at grip 40 instead of 20–30. Z 103.7 lowers the side-grasp radius needed to about 270 mm, which reaches 10° at r 273. Grip 40 hasn't been tested for the funnel pour (the study found no clear branch at 40).
  - **(b)** Move the carousel/TT-01 and E5 a further 15 mm west of Y-left. That is not possible: the carousel is bolted to Y-left.
  - **(c)** Add a short 9th 2020 crossbar for the scale at about (340, 350), so the base can overhang the carousel's east side. This only works if the TT-01 base (Z ≤ 43) and the WS-01 base (Z ≤ 45) don't overlap in X; they do by 14 mm, so it doesn't help.

**Recommendation:** run the closest candidate with option (a), B gripping P1 at 40 for both the scale pick and the funnel pour, plus the funnel-pour check at r 380 and grip 40. That is about 30 min; I stopped here for the time limit. The layout coordinates and frame changes of Update 9 remain the last fully specified set.

---
# Update 11: Update-10 candidate, full run — FAIL (hard stop)

**Layout**
- Arms on the original X rails: A at (330, 525.7), B at (550, 525.7).
- Stage + E6 at −123 mm in Y: funnel (450, 159), E6 at Y 307–327.
- Scale on E6's north face (rotated 180°): pan (345, 350.5).
- RK-03 at r 300 from B: (779.8, 332.9), (821.9, 398.9), (845.4, 473.6).
- Carousel/E5/PS-01 as in Update 9. TL-01 removed.
- Code: `layout_final.py` (the Update-9 version is saved as `layout_final_u9.py`).

| Step | Arm | Result |
|---|---|---|
| Carousel turns (arms parked) | – | PASS: 31.8° (elbow), 18.9 mm |
| 1/5, 4/8 carousel ↔ scale, top-down | A | **FAIL (margin).** Pick 20.7° (wrist flex), place 13.6° (wrist flex), no collisions, clearance 9.6 mm (held beaker vs TT-04 v4 wall) and 11.0 mm (vs WS-02 pan). But the carry (bottom at Z 82, straight line) dips to **6.5° (wrist flex)**; at a carry height of 145 it is −18°. The straight-line carry passes inside r 165 of A. A curved carry staying at r ≥ 180 was not tried |
| 2/6 reagent → scale pour (grip 40, lip 45) | B | **FAIL.** Only 1 in-margin pour manifold at r 273 (the Update-9 pass was at r 285), and no matching grasp branch |
| 3/7 P1 → funnel pour (grip 40, lip 65/80/100) | B | **FAIL.** No in-margin manifold at r 380 with grip 40 |

**Best state to apply to CAD.** Use **Update 9** (frame changes and jig offsets in `layout_final.json` under `coordinates_mm`, `stations_on_extrusions` and `frame_changes`).
- B's scale pour is a full PASS there: 15.0° at the rack pick, pour 31.3°, clearance 4.9 mm, landing 17.6 mm.
- Its open items are arm A's carousel ↔ scale carry (9.2°, TL-01 now removed) and the funnel pour carry. Both would need A's scale distance reduced: the scale sits 388 mm from A in Update 9.

---
# Update 12: candidate 1 (transfer arm east, top-down; pourer west, side grasp) with joint-space carries — PARTIAL at the hard stop

**Layout**
- X rails +74 in Y (base Y 599.7).
- **Transfer arm (model tag B):** (604.8, 599.7), 339.8 mm from the X-rail west end.
- **Pourer (model tag A):** (397.4, 599.7), 132.4 mm from the X-rail west end.
- **Stage:** as built; funnel (450, 282).
- **Scale (loose, rotated 180°):** (596.0, 395.3).
- **Carousel (loose, unit rotated 220.6°):** centre (807.9, 523.5); pick (744.1, 468.8); auger (871.6, 578.2).
- **RK-03 (loose), nudged** to r 290 from the pourer at bearings −15°, −37°, −59°: **(322.3, 319.6), (222.9, 368.1), (148.8, 450.3)**, beaker bottom Z 60.2.
- **Carries:** joint-space interpolation between configurations lifted to Z 300 (grasp centre), roll and pitch sum constant, so the beaker stays upright.

Margins are degrees to the URDF−5° limits.

| Step | Arm | Margin (binding) | Clearance | Result |
|---|---|---|---|---|
| Carousel turns (arms parked) | – | 31.8° (elbow) | 18.9 mm | PASS |
| 1 P1 carousel → scale, top-down | transfer (east) | pick 17.7°, place 19.0°, carry 9.5° (all wrist flex; carry limit 5°) | 7.9 mm (arm vs WS-02 pan) | **PASS** |
| 2 developer rack → pour onto P1 → rack (grip 40, lip 45) | pourer (west) | pick 11.2° (wrist flex), carry 11.2°, pour 32.3° (elbow), tilt-in/descent 32.3° | 5.8 mm (arm vs RK-03) | **PASS.** Landing 16.4 mm (≤ 20), drift 14.9 mm |
| 3 P1 scale → funnel → scale | pourer (west) | pour manifolds 66–75° | – | **FAIL** — see below |
| 4 P1 scale → carousel, top-down | transfer (east) | pick 19.0°, place 17.7°, carry 9.5° (wrist flex) | 7.9 mm | **PASS** |
| Carousel turns / auger dose | – | 31.8° | 18.9 mm | PASS |
| 5–8 | – | not reached before the stop | – | steps 5/6/8 repeat the geometry of 1/2/4 (expected PASS); 7 = step 3 |

**Step 3 detail.** The scale is 285 mm from the pourer.
- **Grip 20:** the side-grasp pick of P1 at the scale has no ≥10° solution (Z 83.7 needs r ≥ ~305).
- **Grip 30, lip 65:** in-margin manifolds exist (best 74.9°), but none gives a clean pick + carry chain. No reason was logged; the likely cause is the scale pick margin (~9–10° at Z 93.7).
- **Grip 30, lip 80 and grip 40, lip 65/80:** fail at the tilt-in/descent segment. That is the joint interpolation from the upright pre-pour pose to θ 55° (lip raised), which collides or drops below 10°.
- **Next fixes to try:**
  - **(a)** Move the scale (it's loose) about 20 mm further from the pourer, to r ≈ 305, so grip 30 picks at ≥10°. Re-check the transfer arm's scale distance, currently 205 mm (window 165–305).
  - **(b)** Replace the straight tilt-in with the lip_lift continuation from θ 0 (lip pinned high), not a joint jump.

---
# Update 13: candidate 1, final — ALL 8 STEPS PASS

Code: `layout_final.py` (Update-12 version saved as `layout_final_u12.py`). Run log: `layout_final_u13_run.json` (written when the run finishes).

**Rules applied**
- Margin = degrees to the URDF−5° limits; ≥10° at picks, places and pours, ≥5° on carries.
- Carries are joint-space, lifted to Z 300; tilt-in is stepwise with a pinned lip, or an upright pre-pour + joint segment.
- Scene collisions use real geometry with undilated voxels; clearance is the true distance.
- The other arm is parked. TL-01 removed.

| Step | Arm | Min margin (binding) | Min clearance | Result |
|---|---|---|---|---|
| Carousel turn, P1 to pick (arms parked) | – | 31.8° (elbow) | 18.9 mm (parked arms vs frame) | PASS |
| 1 P1 carousel → scale, top-down | transfer (east) | pick 17.7°, place 17.3°, carry 9.5° (wrist flex) | 7.9 mm (arm vs WS-02 pan) | **PASS** |
| 2 developer → pour onto P1 → rack (grip 40, lip 45) | pourer (west) | pick 11.6° (wrist flex), carry 11.6°, pour 35.7° (elbow), tilt-in 35.7° | 6.2 mm (arm vs rack stand) | **PASS.** Landing 15.9 mm (≤ 20) |
| 3 P1 scale → funnel pour → scale (grip 30, lip 65) | pourer (west) | pick 10.4° (wrist flex), carry 10.4°, pour 74.9°, tilt-in 66.0° | 5.3 mm (held beaker vs funnel) | **PASS.** Landing 7.2 mm (≤ 40), drift 13.2 mm |
| 4 P1 scale → carousel, top-down | transfer (east) | pick 17.3°, place 17.7°, carry 9.5° | 7.9 mm | **PASS** |
| Carousel turn, P2 to auger, dose (DH-01 underside Z 160), turn to pick | – | 31.8° | 18.9 mm | PASS |
| 5 P2 carousel → scale | transfer (east) | 17.7° / 17.3° / carry 9.5° | 7.9 mm | **PASS** |
| 6 water → pour onto P2 → rack (grip 40, lip 45) | pourer (west) | pick 11.2°, pour 35.6° (elbow) | 5.8 mm (arm vs rack stand) | **PASS.** Landing 10.2 mm |
| 7 P2 scale → funnel pour → scale | pourer (west) | pick 10.4°, pour 74.9°, tilt-in 66.0° | 5.3 mm (held beaker vs funnel) | **PASS.** Landing 7.2 mm |
| 8 P2 scale → carousel | transfer (east) | pick 17.3°, place 17.7°, carry 9.5° | 7.9 mm | **PASS** |

**Weakest points:** the pourer's side-grasp picks (rack 11.2–11.6°, scale 10.4°, wrist flex) and the 5.3 mm held-beaker-to-funnel clearance.

## Final coordinates (world mm; table top Z 0)
Tape datums: **X from the outer (west) face of Y-left (X 245); Y from the south face of E6 (Y 430).**

| Item | World (X, Y) | Tape: X from Y-left face / Y from E6 south face | Mount |
|---|---|---|---|
| Pourer base axis ("B", model tag A) | (397.4, 599.7) | +152.4 / +169.7 | X rails, **132.4 mm from the X-rail west end** (X 265) |
| Transfer base axis ("A", model tag B) | (604.8, 599.7) | +359.8 / +169.7 | X rails, **339.8 mm from the X-rail west end** |
| X rails | front centre Y 582.5, rear 652.3 | +152.5 / +222.3 (centres) | moved +74 in Y; rear corner brackets on the south side |
| Scale pan centre (WS-01 on E6, south side) | (620.0, 407.0), beaker bottom Z 63.7 | +375.0 / −23.0 | E6: pan 355 mm from the E6 west end (X 265); saddle spans X 547–664 |
| Funnel (stage as built, E6 unchanged) | (450.0, 282.0), rim Z 233 | +205.0 / −148.0 | stage |
| Carousel centre (loose; TT-01 + E5 + PS-01 + DH-01 unit rotated 220.6°) | (807.9, 523.5) | +562.9 / +93.5 | loose (feet/VHB) |
| Carousel pick pocket | (744.1, 468.8), beaker bottom Z 61.7 | +499.1 / +38.8 | – |
| Carousel auger pocket (DH-01 outlet over it) | (871.6, 578.2) | +626.6 / +148.2 | – |
| Rack stand 1 (developer) | (192.3, 394.6), beaker bottom Z 60.2 | −52.7 / −35.4 | loose; foot r38 clears Y-left by 14.7 mm |
| Rack stand 2 (soap) | (134.6, 477.1) | −110.4 / +47.1 | loose |
| Rack stand 3 (water) | (108.5, 574.4) | −136.5 / +144.4 | loose |

**Distances (r) and bearings from the arms** (bearing measured from −Y, + toward +X)

| Arm | Station | r (mm) | Bearing |
|---|---|---|---|
| Pourer | rack stands 1 / 2 / 3 | 290 | −45° / −65° / −85° |
| Pourer | scale | 294.4 | +47° |
| Pourer | funnel | 322.0 | +9° |
| Transfer | carousel pick | 191.1 | +48° |
| Transfer | scale | 193.3 | −5° |

**Frame changes:** only the X rails move, +74 mm along Y, with the arm bases at the offsets above. Y-left (Y 290–690), Y-right (Y 270–670), E6 (Y 430–450) and the stage stay as built. The carousel unit and the three rack stands stand loose. The scale mounts on E6.
