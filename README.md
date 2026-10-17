# Wet Lab Bench

## Why this matters
**Experiments are now the bottleneck of science, and only rich labs can automate them.**

AI can propose hundreds of recipes, catalysts or formulations in minutes, but someone still has to mix and measure every one by hand. When that loop is automated, discovery speeds up dramatically. Liverpool's mobile robot chemist ran **688 experiments in 8 days on its own** and found a photocatalyst mix **about 6x more active** than its starting point ([Burger et al., *Nature* 2020](https://doi.org/10.1038/s41586-020-2442-2)). That speed is locked inside a few well-funded labs: self-driving labs and cloud labs cost from **$100k**, or **$25k a month** ([sources](docs/motivation.md)).

**Wet Lab Bench brings that loop down to about $500 and ordinary glassware.**
1. An AI agent plans the experiment.
2. Two **$120 open-source SO-101 arms** run it **by weight** (closed-loop pours on a load cell, auger powder dosing).
3. A **camera measures the result**.
4. The agent decides what to try next.
5. Every step is logged automatically.

That gives any lab with a good question machine-speed discovery, and it brings two more benefits for free:
- **Reproducible:** in a large survey, **over 70 % of researchers had failed to reproduce someone else's experiment** ([Baker, *Nature* 2016](https://doi.org/10.1038/533452a)). Every dose here is weighed and every mass logged, so a protocol becomes something anyone can re-run exactly.
- **Safe:** nearly half of surveyed researchers have been hurt in a lab ([sources](docs/motivation.md)). The person running the experiments never handles the hazardous reagent.

**The demo:** elephant's toothpaste is a stand-in for catalyst screening, chosen because a crowd can see it.
1. The agent varies the **catalyst (yeast)** and the **oxidizer (12 % peroxide)**.
2. The bench runs each recipe.
3. The camera measures **foam height and rise speed**.
4. The agent improves the recipe over 2 to 3 runs.

The same loop applies to buffer recipes, coatings, crystallization conditions and dose-response curves.

> *"Self-driving labs have shown they can find better materials in days instead of months, but only for the handful of labs that can spend $100k+. We're bringing that loop down to $500 and ordinary glassware: an AI plans the experiment, two open-source arms run it by weight, a camera measures the result, and every step is logged so anyone can reproduce it."*


A tabletop robotic wet lab built for HackHarvard (Oct 16–18, 2026). Two open-source SO-101
arms, a load-cell scale and a printed yeast auger make up an exact elephant-toothpaste recipe
from rough, hand-loaded amounts. They combine it in a flask, and a sled carries the flask toward
the audience for the eruption.

**Video of the run:** [media/wet_lab_run.mp4](media/wet_lab_run.mp4)

**Status: final design (2026-10-15).** The layout is verified: planner Update 13, all 8 arm steps
pass with margin. Parts are ordered and printing.

## Start here

| Read | For |
|---|---|
| [docs/demo_process.md](docs/demo_process.md) | **The walkthrough**: vision, bench layout and placement, every step with the arm, parts, sensing and verified margins, the setup, run and reset checklists, and the tightest spots to check first |
| [docs/motivation.md](docs/motivation.md) | Why it matters: cost of commercial lab automation, prior art, what we do and don't claim (all sourced) |
| [docs/electrical.md](docs/electrical.md) | Simplified electrics: power path, e-stop, pin table, wiring, stall detection, bring-up tests |
| [docs/print_list.md](docs/print_list.md) | Final printed parts, files and print status |
| [bom/BOM_final.md](bom/BOM_final.md) | What was bought (LEAN v4 order, about $303 + M4 hardware and VHB), with links |
| [docs/BENCH_PLACEMENT_SHEET.txt](docs/BENCH_PLACEMENT_SHEET.txt) | One-page tape positions (its rack lines predate the one-piece RK-03; see the walkthrough §2.4) |
| [tools/layout/layout_final.md](tools/layout/layout_final.md) | Planner record. Update 13 is the final layout; `layout_final.json` key `update13_final` has the numbers |
| [tools/layout/auger_review.md](tools/layout/auger_review.md) | Auger print fixes and post-print steps |

Where an older file (`bom/BOM.*`, `bom/BOM_links.*`, `bom/delivery_check*`,
`docs/electrical_block.svg`, `docs/software_architecture.md`, `review/`) disagrees with the
documents above, the documents above win.

## The design in one page

- **Frame:** 2020 extrusion square (8 × 400 mm rails total, including E5, E6 and the stage rails
  S1/S2), clamped to a 30 in table. The bench is 746 mm deep. The only change from the CAD as
  built: both arm rails move **74 mm north**.
- **Pourer arm (west)**, base axis (397.4, 599.7). It does **every pour**, with a side grasp and a
  wrist-roll pour.
- **Transfer arm (east)**, base axis (604.8, 599.7). It does **only carousel ↔ scale moves**, with a
  top-down grasp.
- **Carries** are joint-space, so the beaker stays upright.
- **Scale:** 1 kg load cell + HX711 on WS-01 v4, clamped on E6. The pan is at (620, 407). Liquid
  pours are closed loop on its reading.
- **Carousel + auger unit:** outside the frame to the east, rotated 220.6°. TT-04 v4 ring with 4
  pockets at r 84. The auger (FB5311M-360 servo, DH-01 v5 head, DH-02 v4 screw on the PS-01 v2
  post) doses yeast by revolutions.
- **Reagent rack:** one-piece RK-03, bolted to the Y-left rail's west-face slot, with a hook on the
  rail's south end.
- **Stage:** the ST-13 crank and ST-14 connecting rod move the ST-11 sled 100 mm along S1/S2,
  from WORK to ERUPT. The crank's dead centres are the two end positions.
- **Placement:** printed alignment jigs JG-01..06 set the rail spacing, the arm bases and the
  scale.
- **Beakers:** EISCO 100 mL PP (56 × 74) everywhere.
- **Fasteners:** M4 on the whole frame, M3 only at servo horns, M5 only for the stage pivot.
  Nothing threads into printed plastic.
- **Electrics:** 2S LiPo → XT60 lead with 10 A fuse → 2200 µF → 2-NC e-stop → WAGO → 3 servos.
  The Mega runs on laptop USB.

### Run order

1. P1 carousel → scale.
2. Developer pour onto P1 to 39 g.
3. P1 → funnel.
4. P1 → carousel.
5. Auger doses about 7 g of yeast into P2.
6. P2 → scale (verify).
7. Water onto P2 to +30 g.
8. P2 → funnel (reaction starts).
9. P2 → carousel.
10. The sled moves to ERUPT.

Details and margins are in [docs/demo_process.md](docs/demo_process.md).

## Safety

- The reagent is **12 % H2O2** (40-volume developer). **It causes serious eye damage.** Wear splash
  goggles and nitrile gloves when loading reagents, handling the flask and cleaning up the foam.
- 39 g of it releases about 1.7 L of O2. The foam is warm and still contains peroxide.
- The operator loads the beakers by hand. The automation removes the person from measuring,
  transferring and mixing, not from all contact with the chemicals.
- The e-stop cuts power to the carousel, stage and auger servos. **Keep a hand near it.** There is
  no current sensing on the servos.
- LiPo: plug it in only with the e-stop pressed. Charge it in a bag and never leave it unattended.

## Repository layout

```
README.md                    this page
media/wet_lab_run.mp4        run video
docs/
  demo_process.md            walkthrough (start here)
  motivation.md              why it matters, with sources
  electrical.md              final simplified electrics
  print_list.md              final printed parts and status
  BENCH_PLACEMENT_SHEET.txt  one-page tape positions
  software_architecture.md   software plan (pre-simplification; electrical.md wins on pins/hardware)
bom/
  BOM_final.md               what was bought (LEAN v4)
  BOM.csv / BOM.md / BOM_links.* / delivery_check*   earlier full BOM, reference only
exports/
  prints_v2/                 current STL/STEP for every printed part
  prints/, plates/, print_final/   older versions; don't print from these
  assembly/                  Fusion model (wet-lab-bench_WORK.f3d) and renders
tools/
  layout/                    planner record (layout_final.md/.json), auger review
  cad/                       Fusion scripts that build and update the parts
software/tools/planner/      grasp and kinematics models
analysis/                    load cases and fastener-reach checks (pre-final geometry)
review/                      design brief and CDR records (history)
```

The previous, longer README (the post-CDR v2 design: four-bar stage, relay/INA226 electrics,
reagent rack on Y-right) is in git history at commit `644fa86`.

## Team plan and pitch
- [docs/plan_36h.md](docs/plan_36h.md): the 36-hour build plan by person (Nick, Nehal, Shao, Jerry), with go/no-go checkpoints and fallbacks
- [docs/pitch.md](docs/pitch.md): the pitch, judge Q&A, and what not to claim

## Possibility we may explore (not committed): Jev as a fast decision layer
[Jev](https://pub.towardsai.net/what-is-jev-ai-a-practical-guide-to-system-one-and-executable-decisions-c289a750a3ae) (TypeSafe AI, public since Sept 2026) is a *decision* model, not a chatbot.
- **How it works:** you give it context and a typed question, and it returns a bounded choice, an ordinal score, or a yes/no probability with confidence.
- **Where it might fit:** next to the LLM protocol step in [docs/pitch.md](docs/pitch.md), as a fast, structured judge.
  - **Scope / safety gate:** "Is this typed protocol within the bench's supported actions? yes/no + confidence" and "hazard level 1–5". This would sit alongside the hard-coded validator, never replacing it.
  - **Run-time checks:** "Given the last 2 s of scale readings, is the pour progressing / stalled / spilling?" and "Given the step log and camera check, continue / pause for the operator?"
  - **Routing:** map free-text requests to one of our recipe templates.
- **Caveats:** the speed and cost claims are the vendor's own. Latency over the network has to be measured before anything time-critical uses it. The deterministic validator and the hardware e-stop stay the final authority.
