# Design review brief — Wet Lab Bench v2 (CDR, 2026-10-14)

**Review type:** Critical Design Review, before the remaining parts are printed and the software is
written. Mechanical, electrical and software disciplines are reviewed separately by senior
reviewers. Each design owner answers each finding, the reviewer gets a rebuttal, and the chief
engineer rules on what is still disputed. Records live in `review/records/`.

## Product in one paragraph
A carry-on-portable automated wet lab for a hackathon demo (HackHarvard, 16–18 Oct 2026, on a
folding table). Two borrowed SO-101 robot arms bolt to a 2020-extrusion ladder frame. Arm B pours
reagents from a rack onto a load-cell scale until the target mass is reached. Arm A moves the
measuring beaker to a funnel over a 250 mL Erlenmeyer. A servo carousel indexes beakers. A
printed auger meters dry yeast. A servo four-bar stage carries the flask out for an
elephant-toothpaste eruption.

## Hard constraints
- **Travel:** everything goes in a carry-on. The frame is 4 of the owner's 8 × 400 mm 2020
  extrusions, with no cutting.
- **Printing:** every printed part is **PLA** on Bambu A1 / H2D / X2 printers, except the
  fin-ray fingers, which are **TPU 95A**. 0.4 mm nozzle, 4 walls, 15–30 % infill.
- **Arms:** borrowed from SIGRobotics. Don't drill or modify them. Swapping their printed jaws
  for our parts is allowed (`GR-01`/`GR-02` reuse the stock servo and wrist interfaces).
- **Actuators:** the arms do the manipulation. The only extra actuators are 2 × FlashHobby M45CHW
  servos (carousel, stage) and an N20 6 V gearmotor (auger).
- **Electrical:** a 2S LiPo powers the M45CHWs. An Arduino Mega 2560 Pro (USB to the laptop) runs
  the servos, the HX711 scale and the TB6612 auger driver. The arms use their own supplies.
- **Schedule:** the Tuesday plates are printed. Tonight the A1 prints `AG-01`, `WS-01`, `DH-01` and
  `DH-02`. Changing those parts now costs a reprint, which is fine if the reason is real. The team
  flies on Thursday 15 Oct at 10:20 AM and assembles on Friday.

## Where everything is
| What | Path |
|---|---|
| Build doc, BOM, fastener table, power/control, servo tables | `README.md` |
| Software plan (no code yet) | `docs/software_architecture.md` |
| Hand load cases | `analysis/load_cases.md`, `analysis/load_cases.py` |
| Every Fusion component: material, bbox, volume, fillet/chamfer radii, joints, user parameters | `review/design_data.json` |
| Print files (open the STLs with numpy to measure walls, posts and section areas) | `exports/prints/*.stl` |
| Renders | `exports/assembly/*.png` |
| Scripts that generated the geometry, as world-coordinate box/cylinder calls you can read directly | `C:\Users\User\fusion_bridge\*.py`: `auger_west.py` (AG-01, DH-01), `aug2.py` (DH-02), `rk3.py` (RK-02), `gripper_design.py` + `gripper_ops.py` (GR-01/02/03), `rails.py` (frame), `csk.py`, `hw_funcs.py` (hardware), `fillet_lib.py` (how fillets are applied: `process4(r_out, r_in, ch, r_top)`) |
| Motion planner (collision-checked against meshes from the CAD), kinematics, grasp model | `C:\Users\User\fusion_bridge\planner.py`, `plan3.py`, `kin_model.py`, `grasp_model.py` |

Coordinates are world mm. The table top is Z 0, +Y points toward the back edge of the table, and
the arm pan axes are at (330, 525) and (570, 525).

## What reviewers must produce
Concrete findings, each with evidence (a file, a number, a calculation) and a required change
with numbers ("base fillet R6 on the AG-01 post", not "consider stronger posts"). Severity:
- **BLOCKER:** the demo fails, someone gets hurt, or a part breaks.
- **MAJOR:** likely to cause trouble at the demo, or costs significant rework later.
- **MINOR:** quality or cleanup.
