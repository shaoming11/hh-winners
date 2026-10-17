# CDR ruling (chief engineer) — Wet Lab Bench v2, 2026-10-14

Full record of findings, defense, rebuttals and final word: [cdr_record.json](cdr_record.json).

```text
CDR ruling, Wet Lab Bench v2, 2026-10-14. I chaired and ruled on all 75 findings (M-01..M-29, E-01..E-16, S-01..S-30). Nothing was rejected outright. Many items were narrowed: the rejected sub-requirements are listed under "rejected", tagged by finding ID.

Priority key:
- P0: must be done before the Thursday 09:45 carry-on drop. That covers CAD changes to anything that has not been printed yet (the A1 plate must not start, or must be stopped, until AG-01/WS-01/DH-01/DH-02 v2 are exported), purchases that have to ship to Cambridge, and the documents teammates need from tonight's push.
- P1: before the live demo, meaning Friday bring-up, assembly and implementation.
- P2: nice to have.

All README, BOM and docs/software_architecture.md text changes go into tonight's commit whatever their priority. Following the user's instruction, the software deliverable is the architecture document. Firmware and host code are not written as part of this CDR; the schedule in §9 is the team's recommendation.

Spot-checks I ran myself:

(1) M-04, escalated. I sliced exports/prints/ST-01_stage-base_qty1.stl at Z 7.3, 10, 20 and 34, scanning lines x = -8, -2.98 and +2. Material crosses only at y = -38.8 and y = -10.3, so it is continuous from the post, through the web and the 4 mm cradle wall, into the cradle. There is no air gap. At Z 36 the section is the Ø18 post alone (y -38.85..-20.4). The reviewer's Z5-root failure claim is therefore wrong, and the owner's final position stands: Z35.3 governs at about 10 MPa peak under 188-197 N, SF ≈1.0 against 10 MPa. ST-01 v2 with the fin is mandatory before the live demo.

(2) AG-01 v2 saddle against TT-01. The TT-01 body's east face is at X230.2 (for Y316-424). Its saddle at X≥240 spans Y340-400. The AG-01 saddle walls span X238.1-270. Extending the AG-01 saddle to Y290-335 therefore clears TT-01 by 7.9 mm in X, and the 30 x 16 bar (Y282-312) clears TT-01 (Y≥316.2) by 4.2 mm. Both are OK.

(3) WS-02 growth. Taking the Base_SO101 bbox (arm A X270.1-390.1, Y493.3-586.3) and offsetting +240 mm in X puts arm B's base at X510.1-630.1. The nearest corner (510.1, 493.3) is 45.9 mm from the pan centre (468, 475). The proposed Ø90 pan would leave about 0.9 mm, so I capped the pan at Ø80 with a deeper lip.

(4) Print state. README lines 106-109 show ST-04, ST-05 and ST-07 were scheduled in PETG, not PLA. M-16 and M-19 had both assumed PLA. The as-printed material must be confirmed before anyone renames files or changes the thermal case.

Cross-discipline conflicts I settled. In each case the later item wins:
- RESET capacitor: none (E-02 over S-05).
- Servo PWM: Timer4 hardware PWM on D6/D7 with no Servo library, plus a direct-port HX711 read (E-04 over S-17, and it also removes the S-05 writeMicroseconds/attach clamp trap).
- Pack voltage comes from INA226 VBUS. The A0 10k/4.7k divider is dropped (E-07 over S-19/S-23).
- Serial ports are identified by hub-port location plus an identity probe, not VID:PID/serial (E-16 over S-21, because the CH340G has no serial number).
- One auger stall rule (E-10 over M-09/S-23).
- Gripper closes against a torque limit, with grasp classification in raw ticks (M-11 + S-11 + S-13).
- Per-station jaw opening confirmed by audit (S-12 + M-13).
- Pour lip height 15-20 mm above the receiver rim (M-29 vs S-03).
- Stage crank clamp tightened from ±40° to ±39°, with ±1.5° commissioning. With the TPU sleeve the stop sits at 42.2°, so a ±40° clamp plus ±2° trim left 0.2°.
- Developer target 39 g ±2, so that 41 g ≤ the 40 mL thermal cap.
- Cork pad raises the flask by 3 mm, so the funnel rim moves to Z236 and arm A must retract to Z>336.
- Hall sensors go on top of the taped-down drop cloth.
- The 60 s idle relay-open applies only outside a run.
- Cable-tie height corrected to Z130, because the AG-01 post top is at Z135.
- ST-01 v2 carries the E-01 lead slot.

Schedule:
- A1 tonight: AG-01 v2 and WS-01 v2.
- H2D: DH-01 v2 and DH-02 v2 first, then ST-01 v2 (3 h 51).
- X2: GR-01/02/03 (one test fit first), TT-04, WS-02 v2, RK-02, CAL-01 x2 and CAL-02, ST-09 x2, ST-08 x6.
- If ST-01 v2 is not fitted by Friday, the lead signs the accepted-risk entry with the Z35.3 wording.

## CDR-01 mechanical P0-before-print  | AG-01, DH-01, hw occurrences (fusion_bridge), README fastener table, bom/BOM.csv, analysis/fastener_reach.md 
  DECISION: M-01 upheld; owner's M3x20 counter-proposal adopted (reviewer resolved). 
  CHANGE: Use SHCS M3 x 20 at (48,262.5) and (62,262.5) through the DH-01 bridge (Z148 head seat) into the unchanged AG-01 Ø2.5 x 10 pilots (Z125-135). Tip at Z128 gives 7.0 mm engagement (2.3d) with 3 mm spare. Torque snug, ≤0.5 N·m. Update both CAD fastener occurrences and README fastener rows 388/513. Add an export reach check that computes shank-to-thread overlap for every screw from meshes.json and fails <1.5d in PLA or <1.0d in steel/Al. Publish the output as analysis/fastener_reach.md; it also generates the README engagement column (CDR-24).
## CDR-02 mechanical P0-before-print REPRINT | DH-01 (auger_west.py), analysis/load_cases.md 
  DECISION: M-02 upheld. Owner's mechanism correction (bending runs along layers at Y=299) accepted; the joint is unacceptable either way. 
  CHANGE: auger_west.py: dh.box(79,299,135 → 95,350,152) as a JOIN before the bore and slot cuts. Explicit R3 fillets on the web-to-bridge, web-to-tube and web-to-hopper edges, not via process4. Outlet Ø10 at Y365-375 stays open. The web bottom at Z135 clears the carousel beaker rims (Z121.2) by 13.8 mm. It does not conflict with the encoder-N20 can volume (local Y11.5-21.5, world Y261.5-271.5). Acceptance by slicing the exported STL before slicing for print: ≥700 mm² continuous at Y=299.0 and ≥600 mm² at Y=320. Record both values in analysis/load_cases.md.
## CDR-03 mechanical P0-before-print REPRINT | AG-01 (auger_west.py, agfix2.py), README rows 387, bom/BOM.csv 
  DECISION: M-06 (partial), M-07, M-21 (AG-01 part) and the M-08 AG-01 radii, combined into AG-01 v2. The user's large-base-fillet rule for a 123 mm pillar is applied. Owner's stress correction accepted (post ~1 MPa; the soft direction is -Y rocking). 
  CHANGE: auger_west.py AG-01 v2:
- Foot box(20,235,0 → 110,315,12). Extended to X110 so the full 40 mm +X gusset root sits on the foot; TT-01 starts at X120, so 10 mm clear.
- Explicit R8 fillet at the post-to-foot junction on all four sides.
- Delete the 6 x 25 x 58 gusset. Add two 8 mm gussets on the +X and +Y post faces: 40 mm root, tapering to zero at Z100, R5 at both ends, R3 on the gusset-to-post edges.
- Bar 30 x 16 (Y282-312, Z0-16), X70→saddle. Verified 4.2 mm clear of TT-01 (Y≥316.2 at X≥230).
- Saddle Y290-335, channel Y289-336. Saddle walls stay at X238-270, verified 7.9 mm clear of the TT-01 east face at X230.2.
- Bolts at (255,300) and (255,322); T-nuts Y294.5-305.5 and Y316.5-327.5, fully under the rail lips.
- Ø10 x 1.5 mm counterbores in the saddle roof (M5x12 tip at Z14.5 ±0.35, 3.35-4.05 mm engagement, ≥0.25 mm above the 2020 core at 13.9).
- Update the agfix2 hardware positions.
Print on the A1 with the bar along bed Y. Interference check against TT-01 and the Y-left rail before export.
## CDR-04 mechanical P0-before-print REPRINT | DH-02 (aug2.py), analysis/load_cases.py 
  DECISION: M-09 upheld (owner accepted); M-25 screw length included. 
  CHANGE: aug2.py DH-02 v2:
- Ø9 collar from z=0 to z=12; the 8 mm D-bore then has 4 mm of solid beyond it.
- R2 fillet from collar to hub. Hub Ø7.
- Buttress flights, ≥1.6 mm normal thickness: flat face on the outlet side, 45° underside flank.
- Flight OD Ø12.0. Screw ends at Y368 (24 mm choke).
- Prints upright with no supports.
Add a load_cases row: 0.25 N·m jam, Ø7 hub, τ≈3.7 MPa x Kt 1.3 ≈ 4.8 MPa, SF ≈2 against 10 MPa. Drive and stall logic per CDR-49.
## CDR-05 mechanical P0-before-print REPRINT | DH-01 (auger_west.py), README auger section, print settings note 
  DECISION: M-10 (partial; tip pin rejected) and M-25 accepted. 
  CHANGE: auger_west.py DH-01 v2:
- Bore Ø14.0 with a 45° teardrop crown (peak 0.9 mm above the circle).
- Hopper: replace the flat floor with ±X walls at 60° from horizontal, converging to a 12 mm slot X81-93, shortened to Y312-344.
- Bambu Studio: support blocker over the bore and slot volume; tree supports only under the hopper overhangs.
- Post-print: hand-ream with a 14 mm drill.
- Before packing Thursday: 2 min at the compensated 6.0 V with real instant yeast. Pass = no rub or squeal and ±0.3 g repeatability over 3 x 10 rev. If it fails, open the bore to Ø14.5.
- README: replace '70 mL' with the CAD-computed live volume and add 'refill every 4 runs'.
## CDR-06 mechanical P0-before-print REPRINT | WS-01 generator, README fastener/assembly, bom/BOM.csv (M3x12 set screw), analysis/load_cases.py 
  DECISION: M-15 (partial), M-21 (WS-01 counterbore), M-08 (WS-01 R4) and E-05 (mount face kept clear), combined into WS-01 v2. 
  CHANGE: WS-01 v2:
- Ø10 boss under the WS-02 rim at (500,475) ±5 mm, ≥15 mm beyond the load-cell free end (X478.5). Ø2.5 x 10 pilot for an M3 x 12 set screw as an adjustable overload stop. If the base has no material there, add a 14 x 14 pad tied to the nearest cross-bar, R2 roots.
- Explicit R4 fillet at the pedestal-to-saddle root.
- Ø10 x 1.5 mm counterbores in the saddle roof.
- Keep the -Y face (world Y455, X397-426, Z4-38) flat and featureless for the VHB-mounted HX711.
Assembly: set the stop gap with two sheets of printer paper under a 500 g load (≈1.2-1.4x FS). Add a load_cases row: place force is limited by grip slip to ~3 N plus the beaker; the stop is at ≈1.3x FS.
## CDR-07 mechanical P1-before-demo REPRINT | ST-01 generator, exports/print_manifest.md, README, analysis/load_cases.py 
  DECISION: M-04 escalation resolved for the owner's final position. CE slices of ST-01 confirm the post, web and cradle wall are continuous from Z5 to Z35.3, so the Z5-root failure claim is rejected. The Z35.3 section governs at SF ≈1.0 against 10 MPa, which is not acceptable next to 12% H2O2. ST-01 v2 is mandatory before the live demo (not before powered bring-up behind the clamp). 
  CHANGE: ST-01 v2:
- Same Ø18 posts at the same positions, so the stop stays at 45.2° bare and 42.2° sleeved.
- Extend the existing 12-wide web from Z35.3 to Z54 as a fin at local y -14.5..-20.9, mirrored on +Y. It clears the servo case (|y|≤10.3) by 4.2 mm and the crank underside (Z56) by 2 mm.
- R3 fillet where the fin meets the post along its full height.
- R5 on the free sides of the Z5 post-plate root where the geometry allows. Grow the plate locally on ±Y so the post face sits ≥2 mm (up to 6 mm) inboard of the plate edge.
- Include the E-01 lead slot: 8 mm wide through the +X wall (local x30.3-45), from Z35.3 down to 2 mm below the grommet height measured tonight.
Acceptance: slice the v2 STL and show σ_peak ≤10 MPa at every Z from 5 to 66 under 197 N at Z61. Expected ≈3 MPa at the fin top. Print on the H2D after DH-01/DH-02 (3 h 51, ~172 g). Keep v1 as a spare; v1 needs the E-01 hand cut for bring-up.
Correct the 'SF 3.0' claim in exports/print_manifest.md line 28 and the README. If v2 is not fitted by Friday, the lead signs this accepted-risk entry: 'stop post may fracture at the Z35.3 web top (SF≈1.0 vs 10 MPa) under a servo stall at the stop; protection is the firmware clamp plus the TPU sleeve.'
## CDR-08 mechanical P0-before-print  | ST-09 (new), README print list, bom/BOM.csv 
  DECISION: M-04 owner bumper accepted; the reviewer's 3 mm sleeve is rejected because it would drop the stop to 31.5°, below the 36.87° that WORK/ERUPT require. 
  CHANGE: New part ST-09 x2: TPU 95A sleeve, ID 18.3, wall 1.2 mm (3 perimeters), 14 mm tall, covering Z54-68 on each stop post. Print on the GR-03 TPU plate. Wall must never exceed 1.5 mm. Add to the print list and bom/BOM.csv (filament grams).
## CDR-09 software P1-before-demo  | docs/software_architecture.md §7, README stage/commissioning, angle gauge (print list) 
  DECISION: CE cross-check of M-04, E-03 and S-18. With the sleeve the stop is at 42.2°. A ±40° clamp plus E-03's ±2° trim tolerance reaches 42.0°, a 0.2° margin, which is too thin. Clamp tightened. 
  CHANGE: docs/software_architecture.md §7 and README stage section:
- Firmware EEPROM LIM for the stage = the µs equivalent of ±39.0° crank angle, from the no-linkage µs/deg sweep (tools/calibrate_mega.py, S-18). Out-of-range TT/ST is answered with ERR <seq> RANGE, never silently clamped.
- Stage moves take ≥3 s with smoothstep.
- Commissioning before the crank is bolted (E-03): horn on the spline nearest α=0, then confirm with the printed 36.87/45° gauge that the crank sits within ±1.5° of ±36.87° at the WORK/ERUPT pulses. Worst case 40.5° against the 42.2° sleeve stop. Record the trim in config.yaml.
- Add the angle gauge to the print list.
## CDR-10 mechanical P1-before-demo  | README turntable stack + fastener row 520, assembly checklist 
  DECISION: M-03: over-constraint upheld. Owner's zero-reprint fix adopted (float the bottom plate). Spigot and PTFE sheet rejected. 
  CHANGE: Turntable stack:
- Lower VHB layer on the TT-01 corner pads with its red liner left on, so the lazy-Susan bottom plate rests on it unbonded.
- Upper VHB bonds the top plate to the deck underside.
- Deck bolted to the horn as before, 0.5 mm shim.
- Update the README stack line and fastener row 520.
- Friday check, servo unpowered: deck turns by hand through ±70° at ≤0.1 N·m, no visible tape shear, bottom plate stays centred on the pads.
## CDR-11 mechanical P0-before-print  | README lines 37-42, bom/BOM.csv, plan3.py keep-out, analysis/load_cases.py 
  DECISION: M-05 upheld for the countersink (it modifies the borrowed arm). M4x22 rejected: js15 tolerance against a 0.5 mm window would bottom some screws on the 2020 core. 
  CHANGE: Front row: 4 x ISO 7380 M4 x 20 button heads on the unmodified boss (head top Z38.4, 2.0 mm T-nut engagement). Back row: SHCS M4 x 20, unchanged. All 8 at 0.6 N·m with medium threadlock. Delete README lines 37-42 (countersink seat) and the CSK BOM row B082PZY652. Buy the ISO 7380 M4x20 tonight (bom/BOM.csv). Planner: shoulder-link keep-out ≥Z41.4 within 10 mm XY of the front-row holes, enforced in plan3 (CDR-31). Update the arm-base load case to 2.0 mm engagement with PLA-limited preload ~1 kN.
## CDR-12 mechanical P1-before-demo  | fillet_lib.py + all part scripts (fusion_bridge), analysis/fillet_report.md, analysis/load_cases.py 
  DECISION: M-08: process criticism upheld. Reprinting already-printed parts just for fillets rejected (ST-04 tray posts SF 2.0 accident / 4.1, stall-only). ST-01 is handled by CDR-07. 
  CHANGE: - Every part script carries an explicit fillet spec table (edge → radius), applied before process4.
- process4 handles cosmetic edges only and logs every 0.6r/0.35r fallback.
- Export gate: list every concave edge inside the load-path boxes with its as-built radius and FAIL below spec. Output to analysis/fillet_report.md.
- Radii on unprinted parts: AG-01 R8/R5/R3, WS-01 R4, DH-01 R3, DH-02 R2, TT-04 and RK-02 pocket roots R1.5 inside and out, GR-01/02 tongue roots R1.5 with a matching 1.5x45° GR-03 slot-mouth chamfer.
- Record as-built roots and Kt-adjusted SF for printed parts in load_cases.
## CDR-13 software P1-before-demo  | docs/software_architecture.md §3/§8, GR-03 contact faces, bom/BOM.csv, analysis/load_cases.py 
  DECISION: M-11, S-11 and S-13(b) merged. Close by force, not angle. CE cross-check: the S-11 'stall short of goal' classification only works if the goal lies beyond contact; the torque limit must sit under the EEPROM Max_Torque_Limit=500 that LeRobot writes. 
  CHANGE: docs/software_architecture.md §3 Gripper:
- teach.py first records raw stall ticks closing on the real 43 mm and 56 mm beakers and on air (jaw-on-jaw).
- Close command = jaw-on-jaw tick minus a 1° margin (≈ the old -70°), with the RAM Torque_Limit (addr 48) ≤ EEPROM Max_Torque_Limit 500. Calibrate to the lowest limit that gives axial pull-out ≥3.2 N on a water-filled 100 mL beaker with wet silicone-faced fingers. Store the limit and the end ticks in config.yaml.
- Classify 0.3 s after settle. Grasp = Present_Load ≥ L_grip and stalled ≥1° short of goal. Miss = within 0.5° of goal and load <8%. Otherwise retry once, then PAUSE.
- Lift 5 mm, hold 0.5 s, require drift <1 mm before every transfer. Cross-check every scale pick or place to ±2 g.
- Read Status register 65 every 0.5 s and fault on overload/overheat/voltage bits.
- Friday hold test: 90 g at 100° tilt for 30 s with no overload bit.
- Delete the 85% gripper-load rule.
Mechanical/BOM: 1 mm self-adhesive silicone strip 20 x 30 mm on all 4 fingers. Add a grip-friction load case.
## CDR-14 mechanical P0-before-print  | TT-04, RK-02, WS-02 generators, plan3.py 
  DECISION: M-12 partial: lower the grasp. Pocket spout notch rejected (the spout is 45-60 mm above any pocket wall); arrows adopted, with the reviewer's carousel-angle condition. 
  CHANGE: - plan3.py GRIP_H: 100 mL 52 → 40 (finger 23-57 mm).
- 50 mL: if TT-04 is not yet printed, cut its pocket walls 16 → 12 mm and use GRIP_H 34 (finger 17-51). If already printed, use GRIP_H 37.
- Engrave a 0.6 mm-deep spout arrow at every TT-04, RK-02 and WS-02 pocket. The direction points downhill for that station's fixed roll sign. For TT-04 it is computed at the carousel angle where that pocket is picked.
- The new GRIP_H feeds the S-03 pour manifolds and the CAL-02 grip band (CDR-31, CDR-33).
## CDR-15 mechanical P0-before-print  | TT-04, RK-02, WS-02 generators, config.yaml spec in docs/software_architecture.md §3, plan3.py 
  DECISION: M-13 and S-12 merged. Openings are per station, confirmed by audit. The carousel floor is set where neighbours permit. 
  CHANGE: - Add a 3 x 45° lead-in chamfer to every pocket rim on unprinted TT-04, RK-02 and WS-02. If TT-04 is already printed, hand-chamfer with a countersink bit.
- config.yaml (generated from gripper_design.json and the CDR-13 contact ticks): open = contact + 12° at scale, rack and funnel (floor +9° if the audit collides); carousel = the largest opening that clears the 67.4 mm-pitch neighbours, floor +7°.
- Approach target offset 2.9 mm toward the moving jaw.
- If the carousel cannot reach +7°, the operator loads the run so the pockets flanking the pick pocket are empty at that step, recorded in config.yaml.
- Friday acceptance: 20 consecutive picks per station per arm with no rim strike (descent load spike <10%) and ±1.5 mm grasp-centre repeatability.
## CDR-16 mechanical P0-before-print  | GR-01, GR-02, GR-03 (gripper_ops.py), bom/BOM.csv 
  DECISION: M-14 upheld (owner accepted). Chamfered roof plus clearance in place of a 10 mm gable. 
  CHANGE: gripper_ops.py:
- SL 0.15 → 0.25 per side (slot 5.5 x 20.5).
- 2x45° chamfers on both slot-roof long edges (bridge 16.5 mm), with matching 2x45° chamfers on the GR-01/02 tongue tops.
- 1x45° tongue-tip lead-in; R1.5 tongue roots.
- Re-export GR-02 with the hinge axis vertical, as GR-01.
Slicing: GR-03 base block u<0 at 100% infill via modifier, bridges ≤15 mm/s with 100% fan.
BOM: 8 x DIN 985 M3 nylon locknuts plus 8 x M3x16.
Print one GR-01 and one GR-03 and test-fit (slides in by hand, no gap at the clamp) before printing the remaining three fingers.
## CDR-17 mechanical P0-before-print REPRINT | WS-02 generator, README, docs/software_architecture.md §8 (host-hang residual risk text) 
  DECISION: M-15 pan growth, S-16 spill containment and E-05 drip protection combined. CE check: Ø90 leaves only ~0.9 mm to the arm-B base bbox corner (510.1,493.3), so the pan is capped at Ø80. The S-16 ≥80 mL tray is replaced by a lip sized to the real worst case: an 80 mL-line reagent into a 74 mL-brim beaker that already holds yeast overflows ≈13-18 mL. 
  CHANGE: WS-02 v2:
- Ø80 max, centred (468,475); 5.9 mm to the arm-B base bbox corner.
- 8 mm raised lip, inner Ø76, net ≈24 mL around the 43 mm beaker. No skirt.
- Existing Ø46 locator ring gets the 3x45° lead-in and the spout arrow.
- Interference check against the real arm-B Base_SO101 mesh, ≥3 mm, and against the arm sweep.
- Neutral-cure silicone on the load-cell lead exit and Kapton over the HX711.
If WS-02 v1 is already printed, reprint it (0 h 38).
## CDR-18 mechanical P0-before-print  | README materials/recipe, exports/prints names, analysis/load_cases.py, config recipe, bom/BOM.csv (cork) 
  DECISION: M-16 partial. ST-07 3.2 mm reprint rejected. CE cross-check: the README schedule shows ST-04/05/07 were queued in PETG, so the material is confirmed before renaming. The developer target is set so the +2 g tolerance stays under the 40 mL cap. 
  CHANGE: - Confirm from the printer logs which filament ST-04/05/07 were printed in.
  - If PETG: keep the _PETG names, record in README a BRIEF deviation for these hot-wetted parts (PETG HDT ~70 °C vs adiabatic 56 °C), and set PETG in CAD (CDR-22).
  - If PLA: rename to plain names and add the load_cases row '56 °C (40 mL) / 62 °C (50 mL) vs PLA HDT 55 °C, near-zero stress, check ST-07 roundness after each run'.
- 3 mm cork pad cut to Ø80 under the flask in ST-05 (flask +3 mm, neck Z165, funnel rim Z236).
- Charge cap 40 mL: config recipe developer target 39 g ±2 g (max 41 g = 39.4 mL). Delete 'up to 75 mL'.
- Cold-water rinse after each run.
## CDR-19 mechanical P1-before-demo  | README setup/containment, bom/BOM.csv, analysis/load_cases.py 
  DECISION: M-17 partial. The basin is rejected because it sits in the tray's travel path. Charge cap plus disposable containment adopted, with the reviewer's snag condition. CE interface ruling with E-07: Hall sensors go on top of the cloth. 
  CHANGE: - 1.2 x 2.4 m drop cloth taped flat and wrinkle-free over the whole stage strip before clamping.
- Absorbent pads ring the ERUPT footprint (X330-570, Y-60..250) but stay outside the tray and glide path.
- The E-07 Hall sensors are VHB'd on top of the taped cloth. Recheck tray running clearance ≥1.5 mm.
- Run 3 full WORK↔ERUPT cycles on the cloth before the flask goes on.
- Cling film over the ST-01 servo; stage lead routed above Z60 away from -Y.
- Optional bought clear PP container (OD ≤150, rim ≤Z160, floor ID ≥127).
- Load case: 40 mL → ≈1.9 L warm foam vs 0.65 L well annulus plus cloth.
## CDR-20 software P1-before-demo  | docs/software_architecture.md §4/§8, README run sequence 
  DECISION: M-18, S-15, S-24 and E-07 merged into one eruption-timing and interlock rule. CE cross-check: the cork pad raises the funnel rim to Z236, so the retract height is Z>336. 
  CHANGE: docs/software_architecture.md §4/§8:
- Sequence: B_POUR_WATER → WAIT_ACTIVATE → A_YEAST_TO_FLASK (pour, untilt, retreat to gripper Z>336 and outside the funnel zone) → STAGE_OUT → ERUPT. P2 is placed only after the stage is DONE at ERUPT.
- STAGE_OUT starts ≤1.0 s after arm A is clear and ≤1.5 s after the untilt completes. 3 s smoothstep move. Requires the D27 Hall within move time + 0.5 s, otherwise F STAGE_POS.
- Arm A's retreat is audited against the union of stage poses for crank 0-73.74°.
- T_foam (default 4 s, measured on Friday's first live run and recorded in the README) is a hard deadline. If the induction time is <6 s, shorten WAIT_ACTIVATE.
- Flask interlock on A_DEV_TO_FLASK and A_YEAST_TO_FLASK requires: D26 WORK Hall active, EEPROM last-DONE = WORK, and operator confirmation at PRECHECK ('flask seated, funnel in neck').
- SAFE_STOP stage policy: hold everywhere, except complete STAGE_OUT if the catalyst pour passed θ_first and arm A is verified clear by Present_Position. Delete 'stage home'.
- Document: after a hardware e-stop the stage cannot move and the foam stays at WORK.
## CDR-21 mechanical P2-nice  | FN-01 (new, optional), plan3 scene 
  DECISION: M-18 fixed funnel FN-01 accepted only as a gated option (reviewer resolved). 
  CHANGE: FN-01: saddle on the right Y-rail at Y318-372, post to Z200, beam to a ring holding the funnel cone at (450,282). Stem cut to 15 mm, tip at Z170 (5 mm above the cork-raised neck at Z165). Ships only if a plan3 re-run with FN-01 in the scene shows zero collisions and ≥10 mm clearance for both arms by Thursday 06:00. Fallback: loose funnel in the neck over the absorbent pads.
## CDR-22 mechanical P1-before-demo  | Fusion model, matfix3.py, review/design_data.json 
  DECISION: M-19 upheld in full: correct physical materials on everything, including glass. 
  CHANGE: matfix3.py:
- RK-02, TT-04, ST-08 → PLA (FDM); move ST-08 from HARDWARE to PRINT.
- ST-04/05/07 → the as-printed material per CDR-18.
- REF-ROD → borosilicate glass (ρ 2.23). REF-FLASK-250 confirmed borosilicate glass. Add the 100 mL glass graduated cylinder as a reference body or as a BOM-only row.
- REF-GLIDE-1..4 → PTFE (ρ 2.2).
- M45CHW → ABS case plus steel output proxy; horn Al 6061.
- Beakers and funnel → PP.
- Shell the mix, scale and three 100 mL beakers to 1.0 mm walls; split the x3 body into three.
- Move ANIM-*, AR-01, EL-01, REF-BOTTLE and REF-TABLE to a hidden NON-BOM component.
- Re-export review/design_data.json and check assembly mass (excluding arms and table) is within 10% of the BOM-weighted mass.
## CDR-23 mechanical P0-before-print  | bom/BOM.csv (new), README 'What you buy' 
  DECISION: M-20 and E-13 merged, plus every consumable introduced by this CDR. One machine-readable BOM in the repo, as the user requires (all glassware included). 
  CHANGE: Create bom/BOM.csv (columns: id, cad_component, description, material, qty_required, qty_to_buy, pack_size, source_link, status, notes) in tonight's push. README 'What you buy' becomes a summary plus a link. Hardware rows are generated from design_data with the masters excluded. Rows:
- Printed: every printed part with PLA, PETG (if applicable) and TPU grams, including v2 reprints, ST-09, ST-08 v2, CAL-01 x2, CAL-02, angle gauge, optional EL-02.
- Glassware: 2 x 250 mL borosilicate Erlenmeyer, 4 x glass stir rods 6.35 x 150, 100 mL graduated cylinder.
- PP labware: 50 mL beakers x11, 100 mL beakers x3 + 2 spare, EISCO 4 in funnel.
- Fasteners at corrected lengths: M3x20 x2, ISO7380 M4x20 x4, SHCS M4x20 x4, M3x12 x4 deck, M3x16 x8 + DIN985 M3 x8, M3x12 set screw, M5x12 saddles and rack, M5x20 pivots, 18 M5 + 8 M4 T-nuts, M5 inserts x3, F625ZZ x6.
- Electrical per E-13: 2S LiPo ≥2200 mAh XT60, charger, LiPo bag, cell alarm, powered 4-port hub, Mega cable, 20 AWG HD JR extensions 1.0/0.3 m + spare, 16/20/22 AWG wire, Wago 221-415 x4, ATO holders x3 with 3 A x4 / 1 A x2 / 10 A x2, 22 mm NC e-stop + box, 5 V relay with H/L jumper, INA226 + 10 mΩ 2512 metal-strip shunt, resistors and caps per E-13, A3144 x3, 6x2 N52 x4, encoder N20 6 V 60 rpm 7 PPR, screw-terminal shield, 2 Class II arm adapters ≥6.5 A, 1 spare M45CHW, switched strip.
- Consumables: 3M 4950 VHB, cork pad, silicone grip strip, cling film, drop cloth, absorbent pads, Kapton, neutral-cure silicone, medium threadlock, heat-shrink, zip ties, tie mounts x10, 80 mL fill-line marker.
- Calibration: 100 g class M2 weight.
- Tools (≤7 in): Pinecil, hex keys 2/2.5/3/4, 14 mm drill, countersink, multimeter, luggage scale, thermometer.
- Safety: glasses, nitrile gloves.
- Fallback 2 x 3-4 in C-clamps.
Order tonight, shipping to Cambridge: encoder N20, relay, e-stop, INA226, fuses, extensions, adapters, spare servo, ISO7380.
## CDR-24 mechanical P1-before-demo  | README fastener table, CAD occurrences, bom/BOM.csv 
  DECISION: M-21 partial. No reprint of TT-01/ST-01 (preload is PLA-roof-limited; SF ~1.5 at installation, >40 in service). The 2 mm counterbore is rejected on tolerance grounds; 1.5 mm used (in CDR-03/06). 
  CHANGE: Carousel deck screws SHCS M3x12 x4 (tip Z46.6, full 2.0 mm horn flange); update the CAD occurrence and README row 519. Torque specs in the README: M5 into printed saddles 1.5 N·m, M4 arm 0.6 N·m, M3 pilots snug. Add an engagement column (mm and threads) to the README fastener table, generated from analysis/fastener_reach.md.
## CDR-25 mechanical P1-before-demo  | ST-05 (CAD), README verification table 
  DECISION: M-22 upheld. 
  CHANGE: Thursday fit check: drop ST-05 into ST-07. If it does not seat freely, sand the ST-05 OD to 124.8-125.0 (bottom 1 mm, elephant's foot) with 120 grit on a block. CAD ST-05 OD → 124.8. The clearance check flags zero-gap contacts between parts meant to slide.
## CDR-26 mechanical P0-before-print REPRINT | ST-08, README pivot stack, bom/BOM.csv 
  DECISION: M-23 partial. Shield contact accepted. DIN 988 5x7 (non-standard) and 1.5 N·m preload rejected. 
  CHANGE: Reprint 6 x ST-08 at Ø7.2/Ø5.3 x 1.0, 100% infill, any printer (~10 min). Pivot M5x20 snug ≤0.5 N·m with medium threadlock; each link spins free with no axial play. Update the README pivot stack row.
## CDR-27 mechanical P2-nice  | rk3.py 
  DECISION: M-24 accepted: delete the rib, do not add a foot. 
  CHANGE: rk3.py: delete line 33 (rib box). Comment: '# no rib: 6 mm plate overhang 68 mm, 20 N place load → σ≈1 MPa, δ≈0.04 mm (CDR M-24)'. No reprint; the geometry is identical.
## CDR-28 mechanical P1-before-demo  | analysis/load_cases.py, analysis/load_cases.md 
  DECISION: M-26 upheld, with operational/accident categories. 
  CHANGE: Rewrite analysis/load_cases.py and regenerate load_cases.md.
Allowables: PLA across layers 10 MPa, along layers 30, bearing 50; VHB 0.3 MPa sustained. Operational SF ≥2. Accident: SF ≥1 against these and ≥2 against 20/40. Peterson Kt from measured roots (fillet_report).
Rows:
- Stop post: F = 4.41/√(r_c²-(10+r_post+t_sleeve)²) = 188 N bare / 197 N sleeved at 39°. Sections: Z7.3 composite (A662, Z 4008/2580, lever 53.7, Kt1.5), Z35.5 (Z577, lever 25.5, Kt1.2), v2 fin top.
- Impact at 3 s with crank compliance.
- DH-01 joint; AG-01 20 N ±X/±Y (≤0.5°); DH-02 jam; grip friction (≥3.2 N pull-out); cell overload; thermal (as-printed material); foam volume; fastener engagement per group; carousel radial (friction ~2 N); TT-04 wall; ear screws in shear/bearing.
## CDR-29 mechanical P0-before-print  | README.md, docs/software_architecture.md §1.1 
  DECISION: M-27, S-28 and E-12 (doc portion) merged: one README consistency pass in tonight's push. 
  CHANGE: README:
- PLA everywhere (TPU 95A for GR-03/ST-09; PETG deviation per CDR-18).
- Fin-ray is the gripper; stock jaw moved to 'Fallback: stock jaw' appendix.
- Joints table in contact ticks/angles from config.
- Rack: 3 pockets at (670,414) developer, (717,495) soap, (707,587) water; M5x12.
- Run step 1: arm A carries to the funnel.
- Yeast: open-loop by encoder revs, verified on the scale.
- Pour axis wrist roll.
- Serial commands TT/ST per §7.
- Run time ≤5 min (frames.json is 142 s and declared invalid).
- Charge cap 40 mL. Soap 15 mL hand-loaded in the flask.
- Delete lines 223-234 (PCA9685 / 6 V 10 A) and any '9-14 A', '1000-2200 µF', '70 % PWM' or 'USB-C' that is not verified; grep must return none.
- Add docs/ and bom/ to the repo layout.
- tools/gen_config.py spec: config.yaml generated from design_data.json, gripper_design.json and the recipe, and the only source for planner, exporter and runtime.
## CDR-30 mechanical P0-before-print  | README packing table + assembly notes, bom/BOM.csv 
  DECISION: M-28 partial. Clamp, packing and tools accepted. ST-01 saddle extension rejected: the preload friction (~1 kN) holds a fixed offset that teach absorbs. 
  CHANGE: - Measure the BESSEY CM34DR overall length. If >178 mm, check it in or leave it; fallback is 2 x 3-4 in C-clamps bought in Cambridge Friday (in BOM).
- README packing table with envelopes and nesting: TT-04 on TT-02 Ø236; ST-05 in ST-07; AG-01 v2 ~230 x 86 x 135; ST-04 176x206x49; 4 x 400 mm 2020; 2 arms; flasks, glass rods and graduated cylinder in clothes inside a rigid box; LiPo in its bag, carry-on only; hex keys ≤7 in.
- Assembly note: square ST-01 to the rail flank before torquing.
## CDR-31 software P1-before-demo  | docs/software_architecture.md, fusion_bridge plan3.py/planner.py, software/tools/planner/, analysis/plan3_audit.txt 
  DECISION: S-01, S-02, S-03, S-06, S-14, M-29 and M-05 (keep-out) upheld. CE ruling on the M-29 vs S-03 conflict: the lip sits 15-20 mm above the receiver rim for scale pours (target 18) and 20-30 mm above the funnel rim. The current frames.json is invalid. The planner is existing CAD tooling: requirements are written into the doc tonight and implemented by the team per §9. 
  CHANGE: docs/software_architecture.md §3/§3.1/§5. Required plan3/planner changes:
- Per-arm, per-joint JOINT_LIMITS from so101_new_calib.urdf mapped to CAD zero minus 5°, enforced in ik_grasp, grasp_solutions, make_ready, rrt_connect, edge_free and pour() at every 1.5° sample.
- Held beakers keep the grasp-time hinge_sign; axis within 10° of +Z outside pour segments; ≤250 mm/s and ≤1.5 m/s² at the beaker centre.
- Pour manifolds θ = 40..105° in 1° steps, lip within 8 mm (scale) or 30 mm (funnel) of the receiver axis at the heights above, Δq ≤2°/step, collision-checked.
- Every WARN raises PlanError.
- Exporter: raw-tick range [min+20, max-20], no >2048-tick jumps, re-audit at ≤1°/step against fin-ray meshes and the idle arm, SHA-256 provenance checked by player.py, gripper values stripped.
- Single-mover token; idle arm within 2° (3° on shoulder/elbow if logs justify).
- Shoulder keep-out ≥Z41.4 near the M-05 button heads.
- Scene updates: AG-01 v2, WS-02 v2, ST-01 v2, cork +3 mm, new GRIP_H, per-station openings, EL-02, optional FN-01.
- Commit analysis/plan3_audit.txt (frames, voxel, collisions=0, per-move minima arm-fixture and arm-arm, WARNs).
- Copy planner.py, plan3.py, kin_model.py, grasp_model.py, kin.json, gripper_design.json, grip_frames.json and meshes.npz (int16 0.1 mm) to software/tools/planner/.
- Delete README line 607.
- tests/test_export.py must reject frames 541-599.
## CDR-32 software P1-before-demo  | docs/software_architecture.md §4/§8 
  DECISION: S-04 upheld, with the reviewer's pre-first-flow rule. 
  CHANGE: docs/software_architecture.md §4/§8:
- SAFE_STOP per state. In a pour before first flow: go to θ=40°. After first flow: go to max(40°, θ_first-25°) at full speed, then hold torque. Carrying: decelerate to stop within 0.2 s and hold.
- main() in try/finally; SIGINT/SIGBREAK/atexit → safety.safe_stop().
- ArmDriver never calls SO101Follower.disconnect(); bus.disconnect(disable_torque=False) only in RESET with both grippers empty.
- Barrel-jack pull is a documented last resort that drops the beaker.
- tests/test_safe_stop.py: exception before and after first flow, assert θ < θ_first (or 40°) within 0.5 s with torque on.
## CDR-33 software P0-before-print  | CAL-01 x2, CAL-02 (new), bom/BOM.csv print list, docs/software_architecture.md §3/§3.1 
  DECISION: S-13 escalation resolved for the owner's final position. The roll-axis lever is ~9 mm, so roll is unobservable with the 4-cone grasp-centre fit; owner and reviewer agree. The rigid-probe datum on an arm-registered block is accepted over a slot on WS-01 or the TPU fingers. The WS-01 location is rejected because its T-nut placement error would enter tick0. 
  CHANGE: Print before the carry-on drop (X2/H2D, not the A1):
- CAL-01 x2 (mirrored): PLA block keyed into the X-front rail slot (rail centre Y508.5) and butted against that arm's base side face. ≥4 conical seats (90°, Ø8) spanning ≥80 mm in Z and ≥80 mm in X/Y. Base fillets ≥R3 on any tower. Removable.
- CAL-02 x1: Ø43.0 x 100 PLA probe, 60° tip on axis 80 mm below the grasp-centre band, with a flat for rotation.
docs/software_architecture.md §3.1 teach.py:
(0) raw ticks q = s·(tick-tick0)·2π/4096;
(a) +5° sign jog per joint against FK;
(b) gripper zero per CDR-13;
(c) grip CAL-02 at the taught squeeze, hand-guide the tip into ≥4 cones;
(d) LSQ tick0 for joints 1-5, accept RMS ≤3 mm AND σ_j = RMS·√diag((JᵀJ)⁻¹) ≤0.5° every joint, then a ±15° roll cross-check within 1.5 mm;
(e) confirm CAL-01 removed, record 6 fixtures via FK, >10 mm → 'reclamp', re-plan and audit;
(f) no runtime blending.
PRECHECK refuses to run without taught poses newer than the last assembly.
## CDR-34 software P1-before-demo  | docs/software_architecture.md §5, config.yaml spec 
  DECISION: S-07, S-08, S-09, S-26 and S-29 upheld (pour controller §5). 
  CHANGE: docs/software_architecture.md §5:
- Cut law m_f ≥ target-(a+b·q̂), starting a=0.3 g, b=0.15 s. Refit by LSQ on ≥10 Friday water pours (1-8 g/s) and after the first live run. T_air deleted.
- θ = θ_ff + θ_PI. Feed-forward from the tilted-cylinder table of the callipered beaker. Kp 0.15, Ki 0.3, conditional integration, integrator reset at first drop, 10°/s rate clamp. q* = clamp(0.6·err, 1, 8 or 5) g/s.
- Fill inferred from θ_first. Fast move to 40°, then 3°/s. 80 mL fill line confirmed at PRECHECK. PAUSE if θ_first > θ(1.2 x 38.5 mL = 46 mL) ≈65° (developer) or ≈68-69° (water), or at the 105° end.
- Cut-off untilt: δ_fast 5° (8° if q̂_cut >5 g/s) at full speed, then ≤60°/s to θ_cut-15°. 1.5 s drip hold. Top-up +0.5° every 0.6 s, PAUSE after 6.
- Tolerances (demo): developer 39 g ±2 (CDR-18), water = m_yeast + 30 ±2, yeast 7 ±0.7. Stretch set behind a flag. Dashboard shows target, actual and error.
## CDR-35 software P1-before-demo  | docs/software_architecture.md §2/§7 
  DECISION: S-19 and S-20 upheld, with reviewer additions (HB proves orchestrator liveness; goal-wake). CE harmonization: V messages come from the INA226, not A0. 
  CHANGE: docs/software_architecture.md §2/§7:
- 250000 baud; '<seq> <CMD> <args> *<CRC-8/ATM>'; ACK/DONE/ERR BUSY|RANGE|STATE|CRC.
- Commands INIT, TT, ST, AUG, CAL, LIM, VER, HB, STOP, CLR, RESET.
- Unsolicited: W <millis> <raw> <grams>; V <pack_mV from INA226> <bus_mV from A1> at 2 Hz; I <fw> <MCUSR> <hx_rate>; F codes.
- 500 ms comm watchdog → stop auger, hold, F WDT [AUG n], latched until CLR, never auto-resumed.
- MegaThread sends HB only if the orchestrator (and the pour controller, during pours) tick counter advanced.
- Threads: ArmThread A/B and MegaThread, 50 Hz perf_counter loops, timeBeginPeriod(1). ArmThread wakes on the goal-queue Condition and writes immediately.
- Budget: W-to-goal ≤20 ms p95; a run is invalid for tuning if >30 ms. Bounded writer thread (10k records), flushed on fault.
## CDR-36 software P1-before-demo  | docs/software_architecture.md §4/§8 
  DECISION: S-22 and S-27 upheld. 
  CHANGE: docs/software_architecture.md §4/§8:
- Recipe in config.yaml. Soap 15 mL hand-loaded in the flask and confirmed at PRECHECK; delete README step 2 and the §4 soap note.
- PAUSE(reason) with resume-at-state. RESET sequence: stage to WORK on operator command, P2 back to the carousel via a planned segment, operator checklist.
- Retreat = reverse replay of the executed prefix at ≤50% speed. Scale→carousel and scale→auger segments planned and audited.
- Timeouts: pour 45 s, grasp 5 s, carousel/stage duration+2 s, settle 5 s, auger 60 s, WAIT_ACTIVATE 60 s, T_foam.
- Host-side relative taring (empty-pan zero at PRECHECK, per-beaker empties).
- Load thresholds: 99.9th percentile of Friday logs + 15 points (70%/0.5 s interim). Tracking guard |goal-present| >4° for >0.3 s → stop, retreat, PAUSE (joints 0-3 only during pours).
## CDR-37 software P1-before-demo  | docs/software_architecture.md §9 
  DECISION: S-25 partial: schedule, simulator spec, STEP and DEGRADED modes and cutting the web page accepted. Per the user's explicit instruction, no software is written in this CDR. The pre-flight code list is recorded as the team's recommended schedule, not a CDR deliverable. 
  CHANGE: docs/software_architecture.md §9:
- Recommended order: firmware/MegaLink/exporter checks/planner-in-repo/pour_sim before the flight if the team chooses. pour_sim spec: tilted-cylinder V(θ), weir q = C·w·h^1.5, 0.12 s fall delay plus momentum, σ_m 0.05 g at the measured rate, production LSQ filter, 270°/s limit, 20 ms latency.
- STEP mode (Enter advances each state).
- DEGRADED pour mode: θ from S-09 table, 0.5 s pulses, scale verify, ±2 g.
- Web page cut.
- Friday order: Mega bring-up → scale calibration (100 g M2) → auger calibration → arm A teach + dry replay at 30% → arm B → 10 water pours (refit S-07, σ_m) → full water run → chemicals.
## CDR-38 software P1-before-demo  | docs/software_architecture.md §8/§9.3, requirements.lock spec 
  DECISION: S-30 partial. Logging, hashing and voltage gating accepted. Ubuntu pin rejected (Windows 11 + LeRobot 0.6.0 already installed). The 100 g M2 weight replaces nickels as primary. CE harmonization of the battery thresholds with E-07. 
  CHANGE: docs/software_architecture.md §8/§9.3:
- Per sample: raw counts, grams, Mega millis, host perf_counter. Per run: SHA-256 of config, trajectories and calibration; status registers at 2 Hz; pack and bus mV. Fsync on fault.
- Windows 11 with Python/LeRobot 0.6.0 frozen in requirements.lock; USB selective suspend off; sleep/lid actions off; CH340/CH343 drivers; pynput hook plus UI stop.
- Battery from INA226: warn 7.2 V; refuse moves <7.0 V resting (relay open or 2 s idle); fault <6.6 V under load for >1 s; F NO_PACK <5 V; warn >8.50 V at arm.
## CDR-40 electrical P0-before-print  | TT-01 (hand mod), ST-01 v1/v2, hw_funcs.py, TT-01/ST-01 generators, README assembly 
  DECISION: E-01 upheld as a BLOCKER, owner's L-relief adopted. CE cross-check: the grommet must be measured tonight so ST-01 v2 (CDR-07) carries the slot. 
  CHANGE: - Tonight: dry-fit one M45CHW and record the grommet face, Y and height. Feed it to the ST-01 v2 generator and to hw_funcs.servo() (grommet 8 x 3 x 6 plus a 3 x 1.2 lead).
- TT-01 (printed; hand cut before Friday assembly): end-wall relief at local X-34.3..-30.3, Y (grommet-5)..+12.3, Z (grommet bottom-2)..29.3, plus a +Y sleeve break-out X-32.3..-24. Exit through the west window (world X~121, Y383-394).
- ST-01 v1 (bring-up spare): 8 mm slot through the +X wall (world X701), Z35.3 down to 2 mm below the grommet.
- Deburr, line with Kapton, tie mount 15 mm outside each exit.
- Pass: servo seats flush on its ears with no force; lead moves ±2 mm freely.
- Add 'step 0' to README assembly. Re-run the interference check.
## CDR-41 electrical P1-before-demo  | docs/software_architecture.md §7, README Electrical/bring-up, bom/BOM.csv 
  DECISION: E-02 and S-05 merged. CE ruling: no RESET capacitor (relay gating makes a reset limp and safe; a cap that must be removed to flash is a trap). The Servo library is dropped per CDR-43, so S-05's writeMicroseconds-before-attach and its 544-2400 µs clamp issue are superseded. 
  CHANGE: Hardware: SRD-05VDC-SL-C module, H jumper, IN on D25 with 10 kΩ to GND, coil on USB 5 V, NO feeds the servo + bus.
Firmware boot: relay off, D6/D7 LOW, COM4A/B off, banner 'I BOOT <fw> <MCUSR> <hx_rate>'.
INIT <tt_us> <st_us>:
- ERR POS_UNKNOWN if the EEPROM differs by >20 µs, MOVING=1, or the stage Hall state disagrees with st_us.
- Otherwise close relay, wait 200 ms, load OCR4A/B, enable COM bits.
- Operator confirmation is required only after an unexpected reset (host latches F_UNEXPECTED_RESET on any I line after INIT), F fault or POS_UNKNOWN. Recovery: relay open, flask empty, push tray to WORK until D26, deck to painted home mark, 'INIT FORCE'.
- RELAY_WELD check (A1 >2 V) 1.5 s after the open command.
- pyserial dtr=False/rts=False set before open().
- 250 ms AVR WDT only after a WDT-reset test passes on this board's bootloader (reflash MegaCore/fixed stk500v2 if it loops).
- E-16 idle relay-open after 60 s applies only in IDLE/PAUSE, never mid-run; automatic re-arm if MOVING=0 and Halls agree.
Bring-up: flask empty until forced-reset re-arm is shown twice with no motion; confirm the M45CHW is limp when powered with no pulse.
## CDR-42 electrical P1-before-demo  | README Electrical, docs/software_architecture.md §6/§7, bom/BOM.csv 
  DECISION: E-03 upheld as resolved (3 A branch fuses, single INA226 with replaced shunt, measured I_trip). 
  CHANGE: - Keep the 10 A main ATO on 16 AWG.
- 3 A inline ATO on the carousel and stage + branches, 1 A on TB6612 VM, all downstream of the relay.
- INA226 0x40 on D20/D21 with a 10 mΩ 2512 2 W metal-strip shunt replacing R100, placed after the 10 A fuse and before the 2200 µF cap, e-stop and relay. 50 Hz.
- Trip on sum > I_trip for 300 ms, or ≥8.0 A immediately → PWM off, relay open, F STALL. I_trip defaults to 2.5 A; on Friday set it to 1.3 x the largest 300 ms-average over a dry run, clamped 2-4 A.
- Sequencer rule: the auger never runs during a servo move.
- Commissioning per CDR-09. Spare M45CHW in the BOM.
## CDR-43 electrical P1-before-demo  | docs/software_architecture.md §1/§7, README pin table 
  DECISION: E-04 and S-17 merged. CE ruling for E-04: Timer4 hardware PWM plus a direct-port HX711 read. S-17's keep-the-Servo-library-on-D9/D10 option and its Timer5 fallback are superseded. S-17's STBY, WDT and timeout items are retained. 
  CHANGE: Firmware spec, docs/software_architecture.md §7:
- No Servo library. Timer4 mode 14, prescaler 8, ICR4 39999, OCR4x = 2·µs; carousel D6 (OC4A), stage D7 (OC4B); setpoints once per frame.
- Timer1 mode 14, ICR1 799 → 20 kHz PWMA on D11.
- HX711 by direct PINE5 (D3 DT) / PORTG5 (D4 SCK), interrupts off only for the 25-27 clocks (<35 µs, SCK high <50 µs), started after DOUT goes LOW.
- setup() first drives STBY D24 and D11 LOW; 10 kΩ STBY pull-down in hardware.
- HX_TIMEOUT = max(100 ms, 4 x measured interval) → F HX_TIMEOUT, auger stop.
- Bench test: 10 min logic-analyser capture of D6/D7 while streaming at 80 Hz, ≤5 µs deviation.
Single pin table in README (CDR-51).
## CDR-44 electrical P1-before-demo  | README Electrical, docs/software_architecture.md §5.1/§7 
  DECISION: E-05 and S-10 merged (80 SPS, VHB mount on the WS-01 -Y face, LSQ flow estimator). 
  CHANGE: - Both HX711 boards: cut pin 15 from GND and bridge to pin 16. Pass = 12.5 ±1 ms ready interval, reported in the I banner and every 10 s. Host refuses pours below 70 Hz. 10 SPS fallback parameters documented.
- Mount on the WS-01 -Y face (Y455, X397-426, Z4-38) with VHB; wires soldered and Kaptoned.
- Twisted 4-core along the X-front then Y-left slots, ≥50 mm from servo/N20 leads, crossing at 90°.
- q̂ and m_f by 0.5 s rolling LSQ on Mega millis with a 5σ gate. First drop = q̂ >0.5 g/s for 3 samples AND Δm >0.3 g.
- Friday σ_m at 80 SPS with arm B still and slewing 10°/s. If >0.10 g: 0.8 s window and 5 g/s ceiling. No-load std <0.1 g over 100 samples.
## CDR-45 electrical P0-before-print  | bom/BOM.csv, README Electrical, docs/software_architecture.md §8 
  DECISION: E-06 and S-16 merged. Hardware e-stop required. CE note: Mega D2 = PE4/INT4 (attachInterrupt 0); E-06 and S-16 name the same pin. 
  CHANGE: - Buy tonight: 22 mm red latching mushroom with 2 NC blocks in a yellow box.
- Mount at the front table edge (Y-60..40, near X300).
- Pole 1 in 16 AWG: LiPo → XT60 → 10 A ATO → INA226 shunt → 2200 µF → pole 1 → relay COM/NO → + Wago → 3 A/3 A/1 A branches.
- Pole 2: D2 INPUT_PULLUP, NC to GND. HIGH latches F ESTOP, PWM off, relay open. Re-arm needs D2 LOW for 500 ms + host RESET + INIT.
- Host runs the CDR-32 untilt-and-hold on both arms.
- Arm adapters only on a switched strip labelled 'ARMS OFF' (last resort, drops the beaker).
- Document the host-hang-mid-pour residual risk (contained by the CDR-17 lip).
- Delete 'A hardware e-stop isn't feasible'.
- Bring-up test: press during a slow stage move → bus <1 V within 1 s and F ESTOP on the host.
## CDR-46 electrical P1-before-demo  | README Electrical/pin table, docs/software_architecture.md §8, bom/BOM.csv 
  DECISION: E-07 upheld (Halls on the tray, INA226 VBUS, A1 bus divider). CE ruling: this supersedes the S-23/S-19 A0 10k/4.7k divider and makes the Hall the hardware input for the S-24 interlock. 
  CHANGE: - 2 x A3144 lying flat, VHB'd on top of the taped drop cloth outside the glide tracks (≥5 mm margin): WORK → D26, ERUPT → D27, INPUT_PULLUP.
- 2 x 6x2 N52 magnets (S down) on the ST-04 underside; running clearance ≥1.5 mm (glides are 6.6 mm tall).
- Switching window measured by hand, ≤±3° about ±36.87°.
- Pack voltage from INA226 VBUS (thresholds per CDR-38).
- A1: 33k/10k + 100 nF downstream of the relay, AVcc reference. F SERVO_PWR if relay closed and <6.0 V; F RELAY_WELD per CDR-41.
- No deck Hall, no microswitches, no A0 divider. Remove 'OPEN' and the 10k/4.7k text from §8.
## CDR-47 electrical P1-before-demo  | README Electrical, docs/electrical_block.svg 
  DECISION: E-08 upheld. XT30 power split rejected; 20 AWG HD JR extensions instead. 
  CHANGE: - Minus star: 2 x Wago 221-415 joined by 50 mm of 16 AWG, beside the bulk cap in EL-02. Lands LiPo-, cap-, both servo- (20 AWG), TB6612 GND (own 22 AWG) and ONE 22 AWG to Mega GND. HX711, INA226, relay and A1-divider grounds go to Mega GND only.
- 16 AWG XT60 → fuse → shunt → e-stop → relay → + Wago.
- 20 AWG HD JR extensions: stage 1.0 m, carousel 0.3 m. Each signal twisted with its ground.
- Bring-up: stage JR plug within 0.3 V of the pack during a move.
- Class II arm adapters only. Laptop on battery during runs.
- Ground drawing in README Electrical.
## CDR-48 electrical P0-before-print  | EL-02 (CAD/BOM), README Electrical layout, plan3 scene 
  DECISION: E-09 upheld (electronics box in the 0%-overflown left-rear zone). 
  CHANGE: - EL-02 at world X25-225, Y602-692, Z0-60, with a lid. Buy an ABS project box ≤200 x 120 x 75 rather than spend printer time; print in PLA only if a printer is idle before the drop.
- Contents: Mega 2560 Pro on 4 x M3x8 standoffs, TB6612, relay, INA226, 3 ATO holders, Wagos, 2200 µF.
- Cable exits +Y / -X only.
- LiPo in its bag, Velcro'd at ~(130,650), 635 mm from (450,102).
- Add EL-02 (visible) to CAD, the BOM and the plan3 scene (confirmation run).
## CDR-49 electrical P0-before-print  | bom/BOM.csv, README Electrical, docs/software_architecture.md §6 
  DECISION: E-10, M-09 (drive) and S-23 merged into one auger drive spec. CE ruling: E-10's stall rule replaces M-09's 300 ms and S-23's 200 ms rules. INA226 supplies V_pack. 
  CHANGE: - Buy the encoder N20 tonight (6 V 60 rpm, 7 PPR, same gearbox): A → D18, B → D19, 5 V. Fits behind the motor in DH-01 local Y11.5-21.5 with no geometry change.
- Duty = min(1, 6.0 V/V_pack) at 20 kHz.
- Stall: <10% of expected edges in 100 ms at duty >30% → coast 30 ms, brake 20 ms, reverse ¼ rev, retry; 3 stalls → F AUGER_JAM.
- Dosing: 85% first pass, scale verify, fractional top-ups (0.1 rev), ≤2 top-ups. Hopper-empty fault if 10 rev <1 g.
- TIMED fallback if the encoder has not arrived: rpm(V) calibrated at 3 voltages, each AUG ≤3 rev of time, INA step >0.4 A for 200 ms = stall, scale verify each cycle.
- 1 A ATO on VM. 100 nF across the tabs plus 2 x 47 nF to the can, potted.
- Fix README line 429 and software §6.
## CDR-50 electrical P0-before-print  | bom/BOM.csv, README SO-101 arms, docs/software_architecture.md §8 
  DECISION: E-11 and S-16 (voltage part) merged. CE ruling: thresholds are relative to the measured V_idle (S-16) using E-11's warn/fault ratios; 200 ms debounce to avoid acceleration-sag false trips. 
  CHANGE: - As soon as SIGRobotics confirms the arm variant, buy 2 adapters ≥6.5 A (5 V 8 A or 12 V 8 A) with 5.5 x 2.1 mm centre-positive plugs. One voltage family only.
- Red/blue bands and 'ARM A/B <V>' labels; multimeter check at each barrel before first power-on.
- Software: V_idle per arm recorded at connect. Read present_voltage on all 6 servos at 10 Hz. Warn <0.92·V_idle; torque-hold + F ARM_SUPPLY <0.85·V_idle for >200 ms. Refuse start if V_idle is outside 4.6-5.5 V or 11.0-12.6 V unless an operator override names the supply (logged).
- Bus timeout/CRC → arm UNKNOWN → RECOVER.
## CDR-51 electrical P0-before-print  | README Electrical, docs/electrical_block.svg, docs/software_architecture.md §1 
  DECISION: E-12 upheld. The single pin table is authoritative across disciplines (in tonight's push). 
  CHANGE: README 'Electrical' replaces lines 223-234 and 425-430:
(a) docs/electrical_block.svg: LiPo → XT60 → 10 A → INA226 → 2200 µF → e-stop → relay (D25) → + Wago → 3 A carousel / 3 A stage (+470 µF at the stage plug) / 1 A TB6612; minus star; Mega on USB; HX711 at WS-01.
(b) Pin table: D2 e-stop, D3/D4 HX711, D6/D7 servos (Timer4), D11 PWMA (Timer1 20 kHz), D18/D19 encoder, D20/D21 INA226, D22/D23/D24 AIN1/AIN2/STBY (10 k pull-down), D25 relay, D26/D27 stage Halls, A1 bus divider.
(c) Harness table: from/to/gauge/length/connector/fuse.
(d) Currents at 8.4 V.
Software §1 references the table only. Replace 'USB-C' with the inspected connector.
## CDR-52 electrical P1-before-demo  | README Electrical 
  DECISION: E-14 partial. Charging to 4.15 V rejected; capacitor placement upgraded (upstream of both the e-stop and the relay). 
  CHANGE: - Standard 4.20 V/cell balance charge, never LiHV.
- 2200 µF 16 V directly after the shunt, upstream of the e-stop and relay.
- 470 µF 16 V low-ESR across the stage JR plug only.
- Plug the pack in only with the relay open (boot default).
- Firmware warns at VBUS >8.50 V at arm.
## CDR-53 electrical P1-before-demo  | README cable routing 
  DECISION: E-15 upheld, with geometry corrected. CE cross-check: the AG-01 post top is Z135 (DH-01 bridge above it), so the upper tie point moves from Z140 to Z130. 
  CHANGE: - Solder 22 AWG to the N20 tabs and pot them.
- Adhesive tie mounts on the AG-01 post (X40-70) at Z130 and Z20; run the lead along the AG-01 bar and the Y-left slot under a cover strip to EL-02.
- No lead below Z140 within 125 mm of (175,370).
- Stage lead: from ST-01 +X exit (X701, Y~142) north along the table edge to Y270, then Y-right slot, then X-back slot.
- Carousel lead from the TT-01 west window north to EL-02, taped.
- Arm cables clipped in the X-back slot with a 100 mm service loop; full pan sweep with no tension.
- Load-cell lead on the WS-01 underside with 2 tie mounts.
## CDR-54 electrical P1-before-demo  | docs/software_architecture.md §2/§3, README Electrical (d) 
  DECISION: E-16 and S-21 merged. CE ruling: port identity by hub-port location plus identity probe (E-16), because the CH340G has no serial number. The S-21 fingerprint, goal=present and 5°/tick clamp are retained. 
  CHANGE: - config.yaml maps devices by ListPortInfo.location on the labelled powered hub (A/B/MEGA).
- Startup: Mega must answer 'OK <seq> WLB-MEGA v1'; each arm bus answers Feetech pings on IDs 1-6 with Homing_Offset and Min/Max limits matching that arm's stored fingerprint; otherwise refuse torque.
- Goal_Position = Present_Position before every Torque_Enable=1. ArmDriver clamps goals to ≤5° from present per tick.
- Friday: per-servo holding current at 8.4 V recorded in README (feeds I_trip). 30 min hold in the pocket; case and pocket <45 °C.

REJECTED
M-03 (part) The Ø53 spigot on TT-01 (already printed: a 4 h 31 reprint) and the PTFE sheet are unnecessary. Floating the lazy-Susan bottom plate removes the redundant constraint at zero cost, and the reviewer accepted that.
M-04 (part) Ø22 posts with a 3 mm sleeve move the stop to 31.5°, below the 36.87° that WORK/ERUPT need. The Z5-root failure claim (air gap, 26 MPa) is disproved: CE slices of the ST-01 STL at Z 7.3-34 show material continuous from y -38.8 to -10.3. The 0.5 kN/58 MPa impact figure ignores crank compliance. Replaced by CDR-07/08/09.
M-05 (part) M4 x 22 rejected. ISO length tolerance (±0.42 mm) against a 0.5 mm window would bottom some screws on the 2020 core and unclamp the arm. M4 x 20 at 2.0 mm engagement is adequate because preload is limited by the borrowed PLA boss.
M-06 (part) Moving AG-01 off the A1 is rejected. With the 90 x 80 foot and 230 mm bar footprint the part is stable on a bed-slinger, and the move only adds schedule risk. The reviewer's 7.5 MPa/3.5° numbers were for the bar and a free-pivot model, not the post.
M-08 (part) Reprinting already-printed parts (ST-04, ST-01 idler, TT-01) only for fillets is rejected. They are stall-only accident cases with SF ≥2 against 10 MPa including Kt. ST-01 is covered by CDR-07.
M-10 (part) The Ø3 tip pin in a Ø3.4 bushing is rejected. A 0.2 mm journal at the outlet would pack with yeast and become the jam point, and free-end runout (≤0.5 mm) fits inside the new 1.0 mm radial clearance.
M-12 (part) The spout key notch in the pockets is rejected. The EISCO spout is a pinched lip 45-60 mm above any pocket wall, so a notch cannot index it. Engraved arrows (CDR-14) instead.
M-15 (part) The fixed 0.4 mm printed gap is rejected (print tolerance ±0.2 mm against a 0.2-0.3 mm full-scale deflection); an adjustable set-screw stop is used instead. The Ø90 pan and skirt are rejected by CE check: Ø90 leaves ~0.9 mm to the arm-B base bbox corner (510.1, 493.3). Capped at Ø80 with an 8 mm lip (CDR-17).
M-16 (part) Reprinting ST-07 with 3.2 mm walls is rejected. It carries kPa-level stress for minutes, roundness is checked each run, and it may already be PETG (CDR-18).
M-17 (part) The ≥6 L basin under ERUPT is rejected. It sits in the PTFE-glide tray's travel path (Y214-420 → Y34-240), so the tray cannot reach ERUPT. Replaced by the 40 mL cap plus drop cloth, pads and a cling-film-protected servo.
M-21 (part) Reprinting TT-01/ST-01 for counterbores is rejected (PLA-roof-limited preload, SF >40 in service). The 2 mm counterbore is rejected on M5x12 length tolerance (tip could reach Z13.65, below the core at 13.9); 1.5 mm used instead.
M-23 (part) 'DIN 988 5x7x1' is not a standard size (d5 shims are 5x10, which would hit the shield). The 1.5 N·m pivot torque would crush any PLA spacer (~90 MPa); a pivot pin needs no preload.
M-24 (part) The table-height foot is rejected. It would have to match the rail height exactly and would rock, and the plate is adequate on its own (σ≈1 MPa, δ≈0.04 mm).
M-28 (part) Extending the ST-01 saddle to Y330 is rejected (reprint). Two M5 at ~1.6 kN preload give ~1 kN of friction against ~10 N of reactions, so any yaw is a fixed offset absorbed by teach.
E-02 (part) / S-05 (part) The 10 µF RESET-GND capacitor is rejected. With servo power relay-gated (off at reset, in the bootloader and with USB unplugged), a reset only makes the servos limp, and a cap that must be removed before flashing is a trap for teammates. S-05's writeMicroseconds-before-attach sequence is superseded because the Servo library is dropped (Timer4 PWM, CDR-41/43).
E-03 (part) Per-branch INA219s are rejected. One INA226 on the bus sum identifies a single 6.8 A stall against a <2.5 A legitimate sum. The '≥8° clear of the stop' commissioning criterion is impossible against 8.13° of design clearance; replaced by ±1.5° (CDR-09).
E-05 (part) M2 pilots on WS-01 are rejected in favour of VHB on the -Y face, which needs no generator change. The -X face is about 5 mm from arm A's shoulder sweep. The printed drip skirt is replaced by the WS-02 lip (CDR-17).
E-07 (part) D2F-L lever microswitches are rejected (4.3 mm of stop overtravel would crush them, and they need features on the printed ST-01). The deck-home Hall is rejected (a carousel mis-index is not a hazard and the grasp check catches it). The INTERNAL 2.56 V reference is rejected (±9%); the INA226 is used instead.
E-08 (part) The XT30 split power connector per servo is rejected. It doubles mis-mate risk for unsupervised assembly, and 20 AWG HD JR extensions meet the <0.7 V drop target while the 300 ms INA trip bounds stall duration.
E-14 (part) Charging to 4.15 V/cell is rejected. The M45CHW HV rating (6.0-8.4 V) covers a standard 4.20 V/cell 2S charge, which sags within seconds under load. A firmware >8.50 V warning is added instead.
S-13 (part) An orientation slot on WS-01 is rejected. WS-01 is located by T-nuts that slide by hand, so its placement error would enter tick0. A slot seating the TPU fin-ray fingers would use the most compliant element as the datum. Replaced by arm-registered CAL-01 plus the rigid CAL-02 probe (CDR-33).
S-16 (part) A ≥80 mL spill tray under WS-02 is rejected as sized. With the 80 mL fill line, the worst-case host-hang overflow into a 74 mL-brim beaker is ≈13-18 mL, covered by the ~24 mL WS-02 v2 lip. The fixed 6.0/10.5 V thresholds are rejected because they would fault a healthy 5 V arm; relative thresholds are used (CDR-50).
S-17 (part) Keeping the Servo library on D9/D10 with bit-level critical sections, and the Timer5 D45/D46 fallback, are superseded by the E-04 Timer4 hardware-PWM design, which is immune to interrupt latency and also avoids USART RX overrun (CDR-43).
S-19 (part) Sourcing the 'V <mV>' message from an A0 divider is rejected; pack voltage comes from INA226 VBUS and bus presence from the A1 divider (CDR-35/46).
S-21 (part) Port resolution by USB VID:PID plus serial number is rejected. The CH340G reports no serial number and the CH340/CH343 bridges can share VID:PID. Hub-port location plus an identity probe is used (CDR-54).
S-23 (part) The mandatory A0 10k/4.7k battery divider is rejected; it is superseded by INA226 VBUS (±0.1%, no AVcc dependence). The separate 200 ms no-edge stall rule is replaced by the single E-10 rule (CDR-49).
S-24 (part) The microswitch in ST-05 is rejected for this event (reprint and wiring of a printed part). The interlock uses the E-07 WORK Hall, the EEPROM last-DONE and operator confirmation instead. 'Stage moves only on operator command' is rejected without the catalyst-in exception (CDR-20).
S-25 (part) Writing and committing firmware, MegaLink and the simulator as part of this CDR is rejected: the user directed that the software not be written beforehand, only structured in the repo. The pre-flight code list stays in §9 as the team's recommended schedule (CDR-37).
S-30 (part) Pinning to Ubuntu 22.04 is rejected (the demo laptop runs Windows 11 with LeRobot 0.6.0 installed; re-imaging two days before the flight is the bigger risk). 20 nickels as the primary calibration mass is rejected (±0.5% scatter); a 100 g class M2 weight is primary and the nickels are the logged backup.
M-29 (part) / S-03 (part) Neither the flat 20 mm pour clearance nor the 10-20 mm lip band is adopted as written. CE ruling: 15-20 mm above the receiver rim for scale pours (≥10 mm margin over post-teach arm error while keeping the stream short) and 20-30 mm above the funnel rim (CDR-31).
{'mechanical': 29, 'electrical': 16, 'software': 30}
```
