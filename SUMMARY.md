# Wet Lab Bench — short version

A ~$500 tabletop robotic wet lab. Built for HackHarvard, Oct 16–18 2026.
Full detail: [README.md](README.md) · Run video: [media/wet_lab_run.mp4](media/wet_lab_run.mp4)

**Status:** final design (2026-10-15). Layout verified (planner Update 13, all 8 arm steps pass with margin). Parts ordered and printing.

## The idea

AI can propose hundreds of experiments; a human still has to mix and measure each one. Automating that loop works — Liverpool's robot chemist ran 688 experiments in 8 days unattended and found a ~6× better photocatalyst ([Nature 2020](https://doi.org/10.1038/s41586-020-2442-2)) — but self-driving labs start at ~$100k, or $25k/month.

This bench runs the same loop for ~$500 and ordinary glassware:

1. An AI agent plans the experiment.
2. Two $120 open-source SO-101 arms run it **by weight** (closed-loop pours on a load cell, auger powder dosing).
3. A camera measures the result.
4. The agent decides what to try next.
5. Every step is logged.

Two side benefits: every dose is weighed and logged, so protocols are re-runnable (>70% of researchers have failed to reproduce someone else's work — [Nature 2016](https://doi.org/10.1038/533452a)); and the operator never handles the hazardous reagent.

**Demo:** elephant's toothpaste as a stand-in for catalyst screening — visible to a crowd. The agent varies catalyst (yeast) and oxidizer (12% peroxide), the bench runs each recipe, the camera measures foam height and rise speed, and the agent improves over 2–3 runs. Same loop fits buffers, coatings, crystallization, dose-response.

## The hardware

| Part | Spec |
|---|---|
| Frame | 2020 extrusion square, 8 × 400 mm rails, clamped to a 30 in table; 746 mm deep. Both arm rails sit 74 mm north of CAD. |
| Pourer arm (west) | Base axis (397.4, 599.7). Every pour — side grasp, wrist-roll. |
| Transfer arm (east) | Base axis (604.8, 599.7). Carousel ↔ scale only, top-down grasp. Carries are joint-space so beakers stay upright. |
| Scale | 1 kg load cell + HX711 on WS-01 v4, clamped to E6; pan at (620, 407). Liquid pours close the loop on it. |
| Carousel + auger | East of the frame, rotated 220.6°. TT-04 v4 ring, 4 pockets at r 84. Auger (FB5311M-360 servo, DH-01 v5 head, DH-02 v4 screw, PS-01 v2 post) doses yeast by revolutions. |
| Reagent rack | One-piece RK-03, bolted to the Y-left rail west-face slot, hooked at the rail's south end. |
| Stage | ST-13 crank + ST-14 rod move the ST-11 sled 100 mm along S1/S2, WORK → ERUPT. Crank dead centres are the end stops. |
| Beakers | EISCO 100 mL PP (56 × 74) throughout. |
| Fasteners | M4 frame-wide; M3 only at servo horns; M5 only at the stage pivot. Nothing threads into printed plastic. |
| Electrics | 2S LiPo → XT60 w/ 10 A fuse → 2200 µF → 2-NC e-stop → WAGO → 3 servos. Mega runs off laptop USB. |
| Placement | Printed jigs JG-01..06 set rail spacing, arm bases and scale. |

## Run order

1. P1 carousel → scale
2. Developer pour onto P1 → 39 g
3. P1 → funnel
4. P1 → carousel
5. Auger doses ~7 g yeast into P2
6. P2 → scale (verify)
7. Water onto P2 → +30 g
8. P2 → funnel (reaction starts)
9. P2 → carousel
10. Sled → ERUPT

Margins in [docs/demo_process.md](docs/demo_process.md).

## Safety

- Reagent is **12% H2O2** (40-volume developer): **causes serious eye damage.** Splash goggles + nitrile gloves when loading, handling the flask, or cleaning foam.
- 39 g releases ~1.7 L O2. Foam is warm and still contains peroxide.
- The operator loads beakers by hand — automation removes the person from measuring, transferring and mixing, not from all chemical contact.
- The e-stop cuts carousel, stage and auger servos. **Keep a hand near it.** No current sensing on the servos.
- LiPo: plug in only with the e-stop pressed; charge in a bag, never unattended.

## Where to look

| File | For |
|---|---|
| [docs/demo_process.md](docs/demo_process.md) | **Start here.** Walkthrough: layout, every arm step, sensing, margins, setup/run/reset checklists |
| [docs/motivation.md](docs/motivation.md) | Why it matters, prior art, sourced claims |
| [docs/electrical.md](docs/electrical.md) | Power path, e-stop, pin table, wiring, bring-up tests |
| [docs/print_list.md](docs/print_list.md) | Printed parts, files, status |
| [bom/BOM_final.md](bom/BOM_final.md) | What was bought (LEAN v4, ~$303 + M4 hardware and VHB) |
| [docs/BENCH_PLACEMENT_SHEET.txt](docs/BENCH_PLACEMENT_SHEET.txt) | One-page tape positions (rack lines predate RK-03 — see walkthrough §2.4) |
| [tools/layout/layout_final.md](tools/layout/layout_final.md) | Planner record; `layout_final.json` → `update13_final` |
| [tools/layout/auger_review.md](tools/layout/auger_review.md) | Auger print fixes and post-print steps |
| [docs/plan_36h.md](docs/plan_36h.md) · [docs/pitch.md](docs/pitch.md) | 36-hour build plan by person; pitch and judge Q&A |

Current STL/STEP: `exports/prints_v2/`. Fusion model: `exports/assembly/`. Older export folders are superseded — don't print from them.

Where an older file (`bom/BOM.*`, `bom/BOM_links.*`, `bom/delivery_check*`, `docs/electrical_block.svg`, `docs/software_architecture.md`, `review/`) disagrees with the docs above, the docs above win.

## Not committed: Jev as a decision layer

[Jev](https://pub.towardsai.net/what-is-jev-ai-a-practical-guide-to-system-one-and-executable-decisions-c289a750a3ae) returns typed decisions (bounded choice, ordinal score, yes/no + confidence) rather than chat. Possible fits: a scope/hazard gate alongside the hard-coded validator, run-time pour checks ("progressing / stalled / spilling"), and routing free text to recipe templates. Speed and cost claims are the vendor's; latency needs measuring before anything time-critical uses it. The deterministic validator and the hardware e-stop stay final authority.
