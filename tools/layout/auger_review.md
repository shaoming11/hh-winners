# DH-01 / DH-02 yeast auger: will it work as printed?

Date: 2026-10-14. Sources: `dh_v3.py`; the STLs in `prints_v2/` (identical by MD5 to `wlb/exports/prints` and to `PRINT ALL FINAL/X2`); the plate G-code in `H2D-2_auger-head-v4.gcode.3mf` (identical to `PRINT ALL FINAL/H2D/2_DH-01-v4_auger-head_2h37.gcode.3mf`); `H2D-2b_auger-screw-v3x2.gcode.3mf`; `layout_final.py` / `layout_study.py`; and the horn model in `hw_funcs.py`. Fusion was not used.

## Verdict: NEEDS DESIGN CHANGE (DH-02), plus a print-setting change for DH-01

| # | Finding | Severity |
|---|---|---|
| A | **2 of the 4 M3x8 flange screws cannot be installed.** The first flight turn sits 0.7 mm above where the heads seat, and the other 2 screws are blocked while you insert them. | **Blocker. Needs a design change, or trim the flights by hand after printing** |
| B | The current DH-01 slice puts **9.5 m of tree-support extrusion inside the Ø14 bore**: 8.0 m in the roofed outlet end (Y348–378) and 1.3 m in Y307.5–312. Support also climbs up through the Ø10 outlet. | Fix: support blocker (re-sliced, below) |
| C | The nominal radial gap is **0.74 mm, not 1.0 mm**. The flight is a 12 × 3.6 rectangle, so its corners sit at r = 6.264. The worst-case stack at the screw tip goes negative. | Expect light rubbing. It won't stall. Ream the bore and true the flange |
| D | Torque margin is large. Steady friction plus a wedged granule needs ≤ 0.05 N·m, against 0.5 N·m usable. The only realistic way to jam it is a **PLA support fragment** left in the bore, at roughly 0.2–0.3 N·m. | OK once B is fixed |
| E | The outlet is centred over the 180° carousel pocket at (87, 370). It is a Ø10 hole with a 35 mm free fall to the rim of the 100 mL beaker. | OK |
| F | Yeast will back-fill the bell. It can then trickle past the flange (1.5 mm radial gap) toward the horn and servo. | Risk. Your call (see the options below) |
| G | The hopper slot (12 × 32 mm) will not bridge with dry, free-flowing instant yeast. It could with humid or caked yeast. | OK |

---

## 1. Supports in the bore (DH-01, H2D, tree(auto), threshold 30°)

Plate placement, taken from `3dmodel.model`: the part is rotated 180° about Z. G-code → STL is x = 220 − X, y = 225.5 − Y, then world = STL + (40, 250, 135). I checked this against the outer-wall extents, which come out at 0.21–89.79 × 0.21–130.79, i.e. the part bounds minus half a line width. Support moves (`; FEATURE: Support` / `Support interface`) were sampled every 0.5 mm.

| Region (world) | Original slice: support extruded | With blocker |
|---|---|---|
| Bore r < 7.6, Y307.5–378 | **9 455 mm** (Z147.6–162.4, i.e. from bore floor to crown) | **0** |
| — Y307.5–312 (roofed, beside the bell) | 1 327 mm | 0 |
| — Y312–344 (under the hopper slot) | 90 mm | 0 |
| — Y344–378 (roofed, outlet end) | 8 037 mm | 0 |
| Outlet Ø10, Z140–148 | 1 737 mm (columns growing up into the bore) | 63 mm, all below the tube underside (Z ≤ 144.6) |
| Bell r12.5, Y287–307.5 | 12 748 mm | 12 489 mm (kept on purpose) |
| Servo window and pocket | 10 431 mm | 10 383 mm (kept) |
| Under the tube and hopper overhangs (outside) | ~38 m | ~38 m (kept) |

**Why it supports the bore.** The "teardrop" cut in `dh_v3.py` (apex at AZ + 7.9) only rises above the r7 circle for |x| < 2 mm, and its flats slope 30.8°. So the crown is effectively the circle from 60° to 73° (a 30° to 17° slope) plus a 30.8° peak. Both are at or below the 30° support threshold.

**Removability in the original slice.** The Y344–378 section is a closed 34 mm tube. You can only reach it straight down the axis from the servo end (130 mm in), from the slot end, or through the Ø10 outlet. The branches stand on the bore floor and touch the crown with a 0.2 mm gap. You can get them out by pushing a rod or turning a Ø14 drill through from the −Y end, but:
- They leave a scar of about 0.2–0.4 mm on both the floor and the crown.
- The real danger is a broken-off chip staying in the 3 mm dead end past the outlet (Y375–378) or in the gap. A 1 × 1 mm PLA chip wedged between flight and wall needs about 30–50 N to shear, which is **0.2–0.3 N·m at r6.26**. That is the same order as the servo's usable torque.

**Fix: a support blocker.** I used a cylinder r8.2 along the bore (Y307.6–378.2) plus r5.4 through the outlet (Z144.2–155). r8.2 stays inside the tube wall (r10.5), so the supports under the tube are untouched.
- Without support, the crown will sag about 0.3–0.5 mm over a ±(17–30)° arc around top dead centre. Reaming takes this out (section 2).
- The re-sliced plate removes every support move inside the bore and outlet. The remaining supports are 100 % line-of-sight reachable by ray-cast in the bell, window and under-tube regions, and 99.4 % reachable in the rest (external pockets under the hopper block).
- The bell and window supports pull out toward −Y through the servo window. Pocket, window, bell and bore have a clear straight line along the axis: ray-cast hits nothing for r < 7 until Y378.

| Slice | Time | Filament | Supports in the bore |
|---|---|---|---|
| Original `2_DH-01-v4_auger-head_2h37` | 2 h 36 m 28 s | 82.57 g | 9.5 m |
| My control re-slice (same 3MF, no blocker) | 2 h 36 m 44 s | 82.59 g | 9.5 m (reproduces the original) |
| **Corrected: `prints_v2/H2D-2_DH-01-v4_auger-head_BORE-BLOCKER_2h33.gcode.3mf`** | **2 h 32 m 33 s** | **81.88 g** | **0** |

Everything else is unchanged: H2D 0.4, Bambu PLA Basic, 0.2 mm layers, 4 walls, 15 %, tree(auto) at 30°, Textured PEI, and the same placement. The blocker mesh is saved as `prints_v2/DH-01-v4_bore-support-blocker_modifier.stl`, in the DH-01 STL frame, if you want to add it in the GUI yourself.

I considered other orientations and rejected them:
- **Bore vertical** gives a perfect bore, but the part becomes a 131 mm tower on a 90 × 13 mm footprint (−Y end), or it stands on the Ø21 tube end. Bell, window and hopper would all need more support.
- **"Support on build plate only"** would also drop the bell and window supports. Those roofs are Ø25 and a 42 mm span, sitting 1.5 mm from the flange and the servo body, so they need the support.

## 2. Tolerance stack (radial, mm)

**Nominal values, measured on the STLs:**
- Bore: r7.00 (sections 6.97–7.00).
- Flight tip: r6.264 at the rectangle corners and r6.00 at the middle of the blade face.
- Hub: r4.0.
- Gap: **0.736** at the corners.

Where the hopper slot widens the bore (Y312–344), the closest material is still r7.0, at the corner (6.0, 3.6).

| Contributor | Root (Y307.5) | Tip (Y368) |
|---|---|---|
| Nominal gap | +0.736 | +0.736 |
| Bore width shrink (horizontal bore = slot in each layer; −0.2 to −0.4 on Ø) | −0.10 to −0.20 | −0.10 to −0.20 |
| Crown sag, top arc only (unsupported, blocker slice) | −0.3 to −0.5 | −0.3 to −0.5 |
| Elephant foot | 0 (bore is 13 mm above the bed; EF compensation 0.15) | 0 |
| Screw OD (vertical contour, no compensation; corners round off) | −0.05 to −0.10 | −0.05 to −0.10 |
| Support nubs at the blade tips (3.96 m of support per screw at r6.0–6.5 in the 2b slice) | 0 to −0.2 unless dressed | same |
| Servo position (4 ear bolts in Ø3.4 holes, ±0.2; case moulding ±0.1) | −0.2 to −0.3 | −0.2 to −0.3 |
| **Flange-to-horn centring: no pilot or spigot**, 4 × Ø3.4 holes for M3 | −0.1 to −0.2 | −0.1 to −0.2 |
| Angular: servo output tilt play, horn face wobble, flange squareness (≈0.2–0.5°) × 61–69 mm | ≈0 | −0.25 to −0.6 |
| Gravity droop (6.93 g, EI from the real sections, Ixx 232–567 mm⁴, E 3 GPa) | 0 | −0.002 |

- **Root, sides and floor:** RSS about +0.3. Worst-case arithmetic is about 0.0 to −0.1.
- **Tip, sides and floor:** RSS about +0.2. Worst case about −0.6.
- **Tip, crown, unreamed:** RSS about +0.1. Worst case about −1.0.

So the gap is **not guaranteed positive at the tip**, especially at the crown. The consequence is rubbing, not stalling. From the section properties, the cantilever tip stiffness is about 10 N/mm (beam only; the joint makes it softer). A 0.5 mm interference therefore gives about 5 N of contact and about 0.4 × 5 × 7 = 14 N·mm (0.014 N·m), which is 3 % of usable torque. What it does produce is PLA fines in the yeast. To avoid this:
1. **Ream the bore** with a hand-turned Ø14 drill pushed in from the −Y (servo) end. The axis line is clear from Y250 to Y378, so you need ≥ 130 mm of reach. This removes both shrink and sag. Or use a Ø14 dowel with sandpaper.
2. **Dress the flight tips** after removing the supports, then check that DH-02 spins freely in the bore by hand.
3. **True the flange.** With the 4 screws snug, spin the servo slowly and tap the flange until the tip runs true, then tighten. There is no centring feature, so this step is the concentricity.

**Axial gaps:**
- Free end of the screw: Y299 + 69 = **Y368**. Bore end: Y378, so 10 mm free. The outlet spans Y365–375, so the tip sits over its upstream third.
- The last 3 mm past the outlet (Y375–378, about 0.46 mL) is a dead pocket. It fills once and then stays.
- Bolt heads (Y303–306) to the bore step (Y307.5): 1.5 mm. Flights start at Y306.5.
- M3x8 tips stick out 2 mm behind the 2 mm Al horn disc, to Y295. That leaves 3.5 mm to the servo case and 2.5 mm to the spline boss. They clear, but **M3x6 is the right length**: full 2 mm engagement and no protrusion.
- The fillet at the hub root (R0.5) lifts the inner edge of the bolt heads about 0.05 mm. Negligible.

## 3. Torque vs yeast; outlet; height change

- **Available:** FB5311M-360, about 1.47 N·m stall and 0.5 N·m usable. A continuous-rotation servo has less torque at low speed commands, so command ≥ 30–50 % speed and dose by time or revolutions.
- **Bulk friction:** hopper head about 45 mm gives σv ≤ 290 Pa, which is 0.4 N·mm over the slot. A packed barrel at 1–5 kPa against 3 080 mm² of wall is ≤ 0.05 N·m. That is ≤ 10 % of usable.
- **One granule wedged in the gap:** instant yeast is 0.2–0.5 mm, friable rods. At an assumed 0.5–2 N to crush, that is 3–13 N·mm, or ≤ 3 %.
- **Does the 0.74 mm gap jam or leak?** It leaks. The granules are smaller than the gap and pass through. The gap annulus (π(7² − 6.26²) = 31 mm²) is about 35 % of the free channel area (88 mm²). Expect a lot of slip and backflow, so calibrate grams per revolution on the real powder; the order of magnitude is ~0.4–0.7 g/rev. Jamming needs something hard in the gap, i.e. PLA debris (finding B).
- **Dribble when stopped:** the static pile runs from the downstream edge of the slot (Y344, crown z≈162) to the floor (z148). At a 35° angle of repose its toe ends at about Y364.7, and the outlet starts at Y365. At 30° it reaches Y369 and spills. It is borderline, and vibration makes it worse. **Reverse the auger ¼–½ turn after each dose.** The conveying direction depends on the twist sign, so check it on the first run.
- **Outlet path:** a Ø10 vertical hole through a 3.5 mm tube wall. The opening is 20–30 granule diameters, so no arching. Per `layout_study.py` (CC0 = (175, 370), R88) the 180° carousel pocket sits at **(87, 370), exactly under the outlet**. Carousel and auger stand move together under `car_c`.
- **Height change (PS-01 +25):**
  - DH-01 underside goes from z135 to 160, and the outlet exit from z144.5 to **169.5**.
  - EISCO 100 mL beaker (56 × 74) with its bottom at z60.2 has its rim at z134.2. Clearance under DH-01 is **25.8 mm** (was 0.8). The fall to the rim is **35.3 mm**, and 109 mm to the bottom.
  - Lateral drift is ≤ 3–6 mm at tip speeds of about 40 mm/s, against roughly 21 mm of radial margin inside a ~52 mm inner diameter. Yeast drops into the beaker.

## 4. Hopper: will it bridge?

The slot is 12 × 32 mm with vertical walls from Z150 to 161. Above that is a funnel with 60° walls (30° from vertical) in X, vertical end walls in Y312 and 348, and a capacity of about 50 mL (~30 g).
- **Mechanical arching:** the 12 mm width is 24–40 granule diameters, so no.
- **Cohesive arching (Jenike, plane flow, H ≈ 1):** B_crit ≈ f_c / (ρg). Dry instant yeast is free-flowing (ff_c > 10). At σ1 ≈ 300 Pa, f_c ≈ 30 Pa, so B_crit ≈ 5 mm, which is under 12 mm: OK. Humid or caked yeast (ff_c ≈ 4) gives B_crit ≈ 12 mm, which is borderline. Keep it sealed and dry.
- The screw runs under the whole slot, which actively shears the bottom layer. That is the standard anti-bridging layout.
- Minor: there is a 4 × 12 mm flat ledge at Y344–348, Z161, where the funnel extends past the slot. A little yeast will sit there dead.

## 5. Assembly

**Order.**
1. Fit the horn to the servo with its centre screw. DH-02 has no centre hole, so this must come first.
2. Bolt DH-02 to the horn.
3. Slide the servo and auger in along +Y from the open −Y end. The screw passes through the pocket, the window (flange r11 against window Z143.5–166.5, so 0.5 mm per side) and the bell into the bore.
4. Fit the ear bolts (M3x16 + nyloc on the open +Y wall face at X72.7 / 121.3, reachable).
5. Fit the M3x25 bolts to PS-01 (X45 / 65, outside the servo, reachable from the top).

Do this on the bench before the head goes on the post. Nothing in DH-01 blocks the order.

**But step 2 fails: finding A.** I swept each SHCS footprint against the DH-02 STL in 0.1 mm slices along its axis. The blade (r ≤ 6.26) overlaps the head (r4.25–9.75) by 2.0 mm radially and the shank (r5.5–8.5) by 0.76 mm.

| Screw at | Blade over head footprint (z above the flange base; head seats at z4–7) | Blade over shank |
|---|---|---|
| (+4.95, +4.95) and (−4.95, −4.95) | **z7.7–11.3**, 15.7–19.3 | z8.3–10.7 |
| (−4.95, +4.95) and (+4.95, −4.95) | **z11.7–15.3**, 19.7–23.3 | z12.3–14.7 |

An M3x8 travels with its head between z15 (tip entering the flange) and z7 (seated), and it must be axial over the last 4–8 mm. So:
- **Screws 1 and 3 are physically impossible.** The blade sits right on the seated head.
- **Screws 2 and 4** collide while they enter. You might force them in with tilt and a ball-end key.

The CAD interference check passes only because it looks at the final position, not the insertion path.

**Options. These are design decisions, so tell me which you want:**
1. **CAD:** start the flights at **COL1 ≥ 16 mm (Y315)** instead of 7.5. That leaves 9 mm of headroom above the heads for M3x8 and a ball-end key, and only the rear 3 mm of the slot loses flight. Also switch to **M3x6**.
2. **No reprint:** after printing, cut the flights down to the Ø8 hub from the flange to Y315 (about the first ½ turn) with flush cutters or a file. Same result as option 1. Those flights are upstream of the slot (Y312) and do almost no conveying.
3. Fit only screws 2 and 4 (if they go in), plus adhesive. Two M3 take 0.5 N·m easily (about 36 N each), but you lose the 4-hole centring and it is not serviceable. Not recommended.

**Finding F (risk, your call).** The roofed tube Y307.5–312 fills from the slot, and its open end spills into the bell at the angle of repose. The bell floor (z142.5) is below the bore floor. The flange (r11) inside the bell (r12.5) leaves a 1.5 mm annulus, about 3–5 granule diameters, so granules can trickle behind the flange to the horn and the servo window. It is probably slow, but check it with a dry run. Possible mitigations: a felt or foam washer around the flange, or a closer-fitting flange.

## Post-print checklist
1. Print DH-01 from `prints_v2/H2D-2_DH-01-v4_auger-head_BORE-BLOCKER_2h33.gcode.3mf`.
2. Pull the bell and window supports out toward −Y, then ream the bore Ø14 from the −Y end.
3. DH-02: pick option 1 or 2. Remove the supports and file the flight tips. Check that it spins by hand in the bore.
4. Bolt DH-02 to the horn (M3x6), true it by spinning, then tighten.
5. Dry run with yeast: check conveying direction, grams per revolution, and dribble (reverse ¼ turn after each dose), and look for leakage into the bell.

---

# Update (v5 CAD): DH-01 v5, DH-02 v4, PS-01 v2

**Correction to section 1.** The first G-code parse drew the Bambu `G2/G3` arc moves as straight chords. After re-parsing with real arcs, the original v4 slice has **13.1 m** of support inside the bore, not 9.5 m: 11.3 m at Y344–378 and 1.75 m at Y307.5–312. The v4 blocker slice still has 0 m. None of the conclusions change. All figures below come from the arc-aware parser.

## Slices (all in `prints_v2/`)

| File | Printer / profile | Settings | Time | Filament |
|---|---|---|---|---|
| `H2D_DH-01-v5_auger-head_BORE-BLOCKER_2h35.gcode.3mf` | H2D 0.4, single nozzle (filament 1 only) | PLA Basic, 4 walls, 15 %, tree(auto) at 30°, bore and outlet blocker | **2 h 34 m 58 s** | **82.89 g** |
| (control: v5 without blocker, not saved) | same | same, no blocker | 2 h 38 m 01 s | 83.36 g |
| `X2_DH-02-v4_auger-screw-x2_99pct_tree-sup_SLICED-H2D-PROFILE_1h43.gcode.3mf` | H2D profile (no X2 profile here) | 4 walls, 99 %, tree(auto) at 30°, standing on the flange | **1 h 42 m 52 s** | **27.67 g** |
| `X2_DH-02-v4_..._NO-SUPPORT-option_..._0h52.gcode.3mf` | H2D profile | as above, no supports | 0 h 51 m 59 s | 13.45 g |
| `A1_PS-01-v2_auger-post_30pct_2h24.gcode.3mf` | A1 0.4 | PLA Basic, 4 walls, 30 %, no supports, rotated 90° about X as in `plates.py` (`rx90`) | **2 h 24 m 00 s** | **110.86 g** (old PS-01: 2 h 10 m 46 s, 95.24 g) |

The DH-02 files are sliced with the H2D printer profile. An X2 cannot run that G-code. Open the 3MF in Bambu Studio, switch the printer to the X2 and re-slice.

## DH-01 v5: is the blocker still needed? Yes

The v5 bore is r7.5 with 45° flanks and a 3.2 mm flat at r9. Without a blocker, the slicer still puts **7.9 m** of support in the bore (Z146.6–163.8, Y307–377, holding up the r9 flat and its edges) and **2.0 m** up through the outlet. The flat is a horizontal surface, so the 30° threshold catches it.

With the blocker (r9.6 along Y307.6–378.2, plus r5.4 through the outlet at Z143.7–155; the tube is now r11.5) the G-code shows:
- Support path length inside the bore (r < 9.2) is **0.0 mm**, and inside the outlet above the tube underside it is **0.0 mm**.
- 44 zero-length un-retract moves sit at feature boundaries. They deposit no path.
- The remaining supports are reachable by line of sight: bell 99.9 %, window 100 %, under the tube 100 %.

If the r9 flat sags without support, nothing is lost. It is 1.5 mm outside the r7.5 circle, and the 45° flanks are tangent to the circle and print cleanly.

## DH-02 v4: holes and supports

- **Ø3.1 holes print open and round.** All 8 holes, every layer z0.2–4.0, are drawn as `G3` arc loops. The nearest toolpath centreline is at r1.733–1.745, which means a printed hole of about Ø3.05–3.07 before real-world shrink. There is no fill or support inside any hole.
- An as-printed hole of about Ø2.9–3.05 against an M3 major diameter of 2.86–2.98 is a near-zero-clearance fit. **Run a Ø3.1 drill through each hole by hand**, so the screws don't cut threads into PLA.
- **Supports are needed.** The flight starts as a flat rectangle at z16, so its 2.26 mm wings off the hub cantilever horizontally. The blade underside slopes 23° at r6 and 32° at r4. The slicer adds 75.8 m of support per screw:
  - 2.6 m of it touches near the blade tips (r6.0–6.5).
  - About 0.9 m stands on the top face of the flange (r8–11) between z4.3 and 9, under the outer rim of the bolt heads.
  - Remove all of it and dress the flange top and the flight tips before fitting the screws.
- The no-support variant is there if you want to try it. Expect drooping wings at z16 and curled blade tips.

## Tolerance stack, v5 (radial, mm)

**Flight tip to bore.** Bore r7.50 against flight r6.264 gives a nominal gap of **1.236**. The crown is no longer a problem: the 45° flanks keep the bore surface at r7.5.

| Contributor | Worst-case allowance (mm) |
|---|---|
| Horizontal-bore width shrink | 0.20 |
| Floor stair-step | 0.05 |
| Screw OD oversize | 0.10 |
| Undressed support nubs | 0.10 |
| Servo float in Ø3.4 ear holes | 0.17 |
| Case moulding | 0.10 |
| Spline / bearing radial play | 0.05 |
| Flange on horn with Ø3.1 holes | 0.10 |
| Mounting squareness 0.1° × 69 mm | 0.12 |
| **Static sum** | **0.99** |

- **Worst case static:** 1.236 − 0.99 = **+0.25 mm at the tip**. The root is larger.
- **Add servo output-shaft tilt play** (0.2–0.5°, 69 mm lever, 0.24–0.60 mm): the worst case becomes **+0.01 to −0.35**.
- **RSS:** **+0.54**.

So the gap is positive in every case except a servo with more than about **0.21° of output tilt play**. Reaming the bore Ø15 raises that limit to about 0.41°. Gravity takes up that play toward the bore floor, which is the accurate surface.

Even if the tip does touch, it is a rub, not a stall. Tip stiffness is about 10 N/mm, so 0.3 mm of interference costs about 0.01 N·m against 0.5 N·m usable.

**Flange r11.0 in the seal zone, r11.4 over Y299–307.5.** Nominal gap is **0.40**. Tilt hardly matters here because the flange is 0–4 mm from the horn face.

| Contributor | Worst-case allowance (mm) |
|---|---|
| Horizontal-hole shrink | 0.20 |
| Crown support scar (the seal-zone crown is supported: 3.2 m of support there) | 0.30 |
| Flange OD oversize | 0.10 |
| Elephant foot on the horn-side edge of the flange | 0.10 |
| Servo float | 0.17 |
| Case moulding | 0.10 |
| Spline play | 0.05 |
| Flange holes | 0.10 |
| **Sum** | **1.12** |

- **Worst case:** **−0.72**. **RSS:** **−0.05**.
- **Yes, the flange will touch the seal lip in the worst case, and probably in a typical build too, at the crown scar.** The root is held stiffly by the servo, so the contact is hard rubbing. It does not flex away the way the tip does.
- **Fix with no reprint:**
  1. Clean the support scar off the seal-zone crown.
  2. Bolt DH-02 to the servo and spin it slowly.
  3. Hold 240-grit paper against the flange rim to take about 0.2–0.3 mm off the diameter. This trues the flange to the servo axis and removes the elephant foot.
  4. Check it spins freely in the bell before the final fit.
- Without a support scar and with a trued flange: 0.4 − 0.2 (shrink) − about 0.1 (servo float, root) gives about **+0.1**, with no rub.

**Can a 2.5 mm ball-end key reach all 4 screws with the flights starting at Y315 (z16)?** Yes. Checked by sweeping a hex body (circumscribed r1.44) along the socket axis, tilted outward, against the STL sections:

| Outward tilt | Minimum key-to-flight clearance (mm) |
|---|---|
| 0° (straight) | −0.69 (blocked: first blade over the key at z16.9 for screws 1 and 3, z20.9 for screws 2 and 4) |
| 5° | +0.20 / +0.54 |
| ≥ 10° | **≥ 1.08** |

- A ball-end key used at 10–25° reaches all four. A plain straight key or a screwdriver bit does not.
- The screws also go in straight now. The first blade over a head footprint is at z16.2 (screws 1 and 3) and z20.2 (screws 2 and 4). An M3x8's head top is at z15 when its tip enters the flange, so M3x8 fits, and M3x6 fits more easily.
- Use **M3x6**: it gives full engagement in the 2 mm horn with no tip sticking out.

## Verdict (v5)

**WILL WORK WITH THESE PRINT SETTINGS, PLUS 3 POST-PRINT STEPS.**

**Print settings:**
- DH-01 v5 needs the bore and outlet blocker (`H2D_DH-01-v5_..._BORE-BLOCKER_2h35`).
- DH-02 v4 needs tree supports.

**Post-print steps:**
1. Drill the flange holes Ø3.1.
2. Clean the bell crown scar and true or sand the flange rim about 0.2 mm.
3. Optionally ream the bore Ø15.

The remaining open risks are tip rubbing on a servo with more than 0.2° of output play, and dribble or back-fill. Mitigate them by reversing ¼ turn after each dose and doing a dry run.

---

# FINAL update (seal r11.7, flange holes Ø3.2, web fillet R2.2)

| File (`prints_v2/`) | Profile | Time | Filament |
|---|---|---|---|
| `H2D_DH-01-v5_FINAL_auger-head_BORE-BLOCKER_2h35.gcode.3mf` | H2D 0.4, 15 %, 4 walls, tree(auto) at 30°, plus bore and outlet blocker | 2 h 34 m 52 s | 82.85 g |
| `X2_DH-02-v4_FINAL_auger-screw-x2_99pct_tree-sup_SLICED-H2D-PROFILE_1h43.gcode.3mf` | **H2D profile.** There is no X2 profile in `~/bbl` (only `m_a1` and `m_h2d`) and none in the Bambu Studio BBL machine folder, so re-slice it for the X2 in Bambu Studio. | 1 h 42 m 48 s | 27.63 g |
| `A1_PS-01-v2_FINAL_auger-post_30pct_2h24.gcode.3mf` | A1 0.4, 30 %, 4 walls, no supports, rotated as before | 2 h 23 m 59 s | 110.86 g |

**DH-01 bore.** The blocker slice has 0.0 mm of support path inside the bore (r < 9.2, Y307.5–378) and 0.0 mm inside the outlet above the tube underside. The only moves there are zero-length un-retracts. The remaining supports are in the bell (18.3 m) and under the tube and hopper.

**M3 in the Ø3.2 holes.**
- The STL holes are Ø3.19. The G-code draws all 8 holes as open arc loops on every layer from z0.2 to 4.0, with the toolpath centreline at r1.782–1.796. That gives a printed hole of about Ø3.14–3.17, or about Ø3.0–3.1 after the usual small-hole shrink.
- Against an M3 major diameter of 2.86–2.98, the diametral clearance is +0.02 to +0.31, so the screws fit without cutting threads. No drilling is needed; a Ø3.2 drill pass is optional if one is snug.
- The flange can float by up to about ±0.12 radially on the horn.

**Seal lip.** Measured r11.67–11.70 over Y299–307.4, against flange r11.0, so the nominal gap is **0.68–0.70**.

| Contributor | Worst-case allowance (mm) |
|---|---|
| Horizontal-hole shrink | 0.20 |
| Crown support scar | 0.30 |
| Flange OD oversize | 0.10 |
| Elephant foot | 0.10 |
| Servo float | 0.17 |
| Case moulding | 0.10 |
| Spline play | 0.05 |
| Flange holes | 0.12 |
| **Sum** | **1.14** |

| Condition | Worst case | RSS |
|---|---|---|
| As printed | **−0.46** (can still touch) | **+0.23** |
| Crown scar cleaned to ≤ 0.05 | −0.21 | +0.33 |
| Scar cleaned and flange rim trued on the servo (removes OD, elephant foot and all centring errors) | **+0.43** | — |

Recommendation: clean the support scar off the seal-zone crown, then spin-sand the flange rim on the servo. A light touch with 240-grit is enough now.

---

# H2D overnight plate

**File:** `prints_v2/H2D_OVERNIGHT_GR-01x2_GR-02x2_DH-01v5_FINAL_7h30.gcode.3mf`

The parts come out as **one plate**: **7 h 29 m 56 s, 204.28 g**. Starting at 22:00, it finishes at about 05:30.

| Parts | Settings |
|---|---|
| GR-01 ×2, GR-02 ×2 | Same as H2D-1: the 'best' orientation from `orient_best.py` (the staged STLs are MD5-identical to `~/bbl/plates/stl`), 30 %, 4 walls, tree(auto) at 30° |
| DH-01 v5 FINAL | **Per-object 15 % infill**, set in the 3MF object config, plus the bore and outlet support blocker |

The 15 % is confirmed in the G-code: DH-01's sparse infill is 151.5 m, against 152.1 m in the standalone 15 % slice.

**Bore check:** 0.0 mm of support path inside the DH-01 bore (r < 9.2, Y307.5–378) and 0.0 mm inside the outlet.

For reference, the same plate at 30 % on every part (no per-object override) takes 7 h 45 m and 217.12 g.
