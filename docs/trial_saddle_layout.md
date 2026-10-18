# Trial saddle layout (branch `try-saddle-carousel`)

The carousel (TT-01) sits on a saddle over the **Y-right** rail instead of on Y-left, and the auger post (PS-01)
sits on its own **E5** extrusion bolted straight out from Y-right with two corner brackets. Coordinates live in
`tools/layout/layout_final.json` → `update13_final.carousel` (mount text starts with `TRIAL`).

## Measurements (mm, top view, audience at the front = low Y)

| What | Where |
|---|---|
| TT-01 saddle bolts | 2 × M4×12 into T-nuts in Y-right's top slot, **12 and 42 mm** from Y-right's front end (Y 282 / 312) |
| TT-01 centre | (755.7, 297.0): 70.7 outside Y-right's outer face, 27 behind its front end; base overhangs the rail end by 28 |
| Pick cup (pocket 0 at deck 0) | (718.2, 372.2), faces the transfer arm (r 254.2, bearing 26.5°) |
| Pocket ids | [116.5, 206.5, 296.5, 26.5] deg; P1 in pocket 0, **P2 in pocket 2 (opposite)** |
| E5 | Y 386–406, X 685–1085 (front face 116 behind Y-right's front end), one corner bracket each side |
| PS-01 post | inner face 161.5 out from Y-right's outer face (X 846.5–886.5, Y 386–438) |
| Auger outlet | (834.5, 326.0), over the cup circle, ~96° round from the pick |

## Build pages

| Step | Page |
|---|---|
| Top view with every number | `build_img/lego/saddle_topview.png` |
| 1. TT-01 saddle onto Y-right | `build_img/lego/saddle_1.png` |
| 2. Deck/ring orientation | `build_img/lego/saddle_2.png` |
| 3. E5 + corner brackets | `build_img/lego/saddle_3.png` |
| 4. Auger post on E5 | `build_img/lego/saddle_4.png` |
| Spout alignment (5 pages) | `build_img/spout/spout_1..5_*.png` |

Spout headings (clock face, seen from above, standing at the front): developer in rack_1 **4:20**, water in rack_3
**12:00**, P1 in pocket 0 **12:45**, P2 in pocket 2 **6:45** (turntable at 0), and P1/P2 should land on the scale at
**1:30**. Computed from `reports/native_plans.json` (pre-pour direction mapped back through each gripper grasp and
the carousel deck angle).

## Simulation status on this layout

`python -m benchsim.reproduce`: layout, kinematics, interfaces, grasping, pour trials, mechanisms, full demo,
safe stop, language layer and offline hw-check all PASS.

- The sim now models the real PS-01 post, DH-01 head and E5 rail as boxes at their CAD extents
  (`carousel.auger_post_box / auger_head_box / auger_rail_E5`). Closest approach over every planned arm pose:
  transfer finger to DH-01 head 37 mm, carried beaker to E5 42 mm, carried beaker to head 51 mm.
- Same 6 pourer `wrist_flex` margin issues (7.5–9.7° < 10° rule) as the original layout; the move does not touch the pourer.
- Tightest carousel clearance: carried beaker 11.7 mm over the pockets.
- The auger is not opposite the pick any more, so the mechanism checks visit each pocket's pick and auger deck angle
  separately; the deck turns to a different angle to dose (handled by `mechanisms.deck_for`).
- `bench_cam` moved to [850, 120, 380]: at the old spot the real-size DH-01 head blocked its view of the pick cup.
  On the real bench, the camera must not look at the pick cup through the auger head.
- Three `test_kinematics` tests compare against arm paths recorded in the original CAD layout; they skip while a
  `TRIAL` layout is active.
- TT-04 mesh fit regenerated for the new pocket ids (`python -m benchsim.meshfit`).

## Not covered by the sim

Re-zero the carousel after mounting (a cup exactly at the pick spot); arm calibration and hardware ladder L1–L3;
auger screw and E5 corner brackets are not modelled; beakers have no spout in the sim. Do one slow dry run with
empty beakers and watch the transfer arm carry a cup over the carousel (the 11.7 mm clearance).
