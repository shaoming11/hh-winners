# Manifesto: the cheap bench wins by being many

Written 2026-10-17. Companion to [motivation.md](motivation.md) (the sourced market case) and
[pitch.md](pitch.md) (claim discipline, judge Q&A). This document is the *why* that the pitch
speaks and the *why* that decides what we build after the hackathon.

Rule of the house, inherited from motivation.md: **every number has a source and a trust label.**
Where a figure came from a search snippet rather than the paper itself, it says so, and it does not
go on a slide until someone opens the paper.

---

## 0. One sentence

Lab automation is priced like a capital instrument, so labs own one of it; we are building the
version you own fifty of, by moving precision out of the mechanism and into the feedback loop.

---

## 1. The thesis: buy accuracy with feedback, not with tolerances

Every expensive liquid handler spends its money in the same place: mechanical and fluidic precision.
Ground leadscrews, calibrated plungers, matched tips, a validated dispense curve. You pay for
accuracy *as a property of the hardware*, and the vendor protects that accuracy by controlling the
consumable — which is why the tips, vials and dosing heads are theirs.

A scale breaks that trade. Weighing is the reference method used to calibrate volumetric devices in
the first place (ISO 8655-6 is gravimetric — [Mettler Toledo summary](https://mt.com/in/en/home/perm-lp/product-organizations/pipe/iso-8655-updates.html)).
If the loop closes on mass, the mechanism no longer has to be accurate. It has to be *repeatable
enough to be controlled*: pour slowly, watch the grams, cut early, let the control law absorb the
rest. A $10 load cell plus a cut law buys what a precision plunger buys.

That is the entire cost argument, and it is an engineering claim, not a marketing one:

> **Accuracy is a closed-loop property. Spend on the sensor and the loop, not on the tolerance
> stack.**

Our evidence, in simulation: 10 pours at 38.71 g against a 39 g target, SD 0.06 g, a systematic
−0.28 g bias that the calibration constants absorb (`software/benchsim/reports/pour_report.md`,
reproducible with `python -m benchsim.reproduce`). Simulator numbers, not bench measurements — the
real ones go in the table in §6 the night they exist.

Everything else in this manifesto follows from that one substitution, because once accuracy is
software, cost collapses — and once cost collapses, *you can have more than one*, which is where the
real win is.

---

## 2. Five principles

Each one states the claim, why we believe it, what would prove us wrong, and what it costs us.
A principle with no cost is a slogan.

### 1. Weigh, don't measure

**Claim.** Every dose on this bench is closed-loop on mass: liquids by weir-flow pour onto a 1 kg
load cell at 80 Hz, powder by auger revolutions verified on the same scale. Nothing is trusted
because a graduation said so.

**Why.** Beaker and flask graduations are good to about ±5%
([DWK/Duran](https://www.dwk.com/laboratory-products/beakers-amp-flasks/erlenmeyer-flasks)).
Gravimetry is the calibration reference. Weighing is what lets cheap, ungraduated labware hit a
real target, and it is also the audit trail: target vs actual for every dose, in the run record.

**Falsified if.** On the assembled bench, pour error is dominated by something the loop cannot see —
residual drip, foam on the pan, beaker lip wetting — and mean ± SD lands outside ±2 g on 39 g.

**Costs us.** Speed. A closed-loop pour is slower than a calibrated squirt. We will never win
throughput-per-unit, and we should stop pretending we want to.

### 2. Use the lab that already exists

**Claim.** 100 mL beakers, a 250 mL Erlenmeyer, a funnel, a grocery-store packet of yeast, and
hair-salon 12% peroxide. No vendor plate, no proprietary tip, no dosing head, no consumable with a
part number we own.

**Why.** It is the honest version of the lock-in argument. Commercial systems are not evil, they are
*built around formats*: Opentrons "can only guarantee performance of the Flex when using our Flex
pipette tips" ([Flex pipette FAQ](https://opentrons.com/catalog/flex-pipettes/faqs)); Quantos powder
dosing runs on proprietary heads at roughly $2.0–3.2k per 10-pack
([Fisher listing](https://www.fishersci.com/shop/products/quantos-dosing-heads/01910260), reseller).
Third-party tips do exist for some platforms, so the accurate claim is narrower and better: these
machines are built around plates and tips, **not around the glassware a teaching lab already owns.**
Deploying into existing glassware means the deployment cost of the *consumable chain* is zero.

**Falsified if.** Grasping real, wet, warm glassware with fin-ray fingers turns out to need
per-vessel tuning so fine that we have effectively invented a proprietary beaker.

**Costs us.** Containment and sterility. Open vessels, no fume path, no sealed tips. There are whole
categories of chemistry and all of biosafety that this principle locks us out of.

### 3. One seam, two backends — the twin is a deployment tool, not a demo

**Claim.** The same demo code runs against MuJoCo and against the hardware. The seam is three
classes (`ArmBus`, `MegaLink`, `Clock` in `software/bench/hal/base.py`); `hal/sim.py` is physics,
`hal/real.py` is LeRobot plus pyserial. Time only advances when something waits on it, so the
control loops are byte-identical on both sides. Layout is verified offline before a screw is turned:
13 station centres within 0.09 mm of the final layout, 8 arm steps planned contact-free
(`software/benchsim/reports/`).

**Why.** This is the mechanism behind "faster to deploy," and it is the part that is genuinely ours.
A new bench is a `bench.yaml` — arm base axes, station coordinates, pocket radius — and the twin
tells you whether that geometry is reachable with margin *before* anyone buys extrusion. Commercial
deployment goes the other way: verify the site meets vendor environmental requirements, take
delivery, then installation and operational qualification before the first real sample
([Tecan on IQ/OQ/PQ](https://www.tecan.com/blog/iq-oq-pq-for-instruments-and-pipette-tips-for-validated-liquid-handling);
[Lab Manager, operational essentials](https://www.labmanager.com/automated-liquid-handling-and-robotics-the-operational-essentials-for-lab-managers-35631)).
We are not claiming we skip validation — we are claiming the *geometry and the control logic are
validated in software*, so the hours on the bench go to calibration, not discovery.

**Falsified if.** The sim-verified poses do not survive first contact — the honest warning sign is
already in our own report: 6 pick/place rows miss the 10° margin rule, and the CAD-to-arm path
mapping is explicitly "approximate, not calibrated" with station endpoints 3.4–10.4 mm off. If
those gaps turn into re-teaching every station by hand, the twin bought us nothing.

**Costs us.** The simulator lies in specific, known ways: no fin-ray compliance, no sloshing, no
real servo torque curve. Sim grasp success is optimistic. We say so, every time.

### 4. The interface is a conversation, and a human holds the gate

**Claim.** The operator does not learn a UI. They text the bench. One backend process owns state,
the log and the run; the frontend and the messaging agent read the same state over HTTP/SSE and the
same MCP tools, so what one sees the other sees. Anyone may *ask* for a run; the plan goes through a
deterministic validator (peroxide ≤ 45 g, yeast ≤ 10 g, water ≤ 60 g, waits ≤ 10 min) and then sits
as an approval request until a person with the operator role says yes, recorded by name. `safe_stop`
is always accepted. The e-stop is wired, not modelled.

**Why.** Two reasons, and the second one is the better pitch.

The access reason: reviews of self-driving labs name the operating expertise — hardware, software,
optimisation, data science — as a barrier alongside cost
([Doloi et al., *Digital Discovery* 2025, 4, 1685](https://doi.org/10.1039/d4dd00411f);
[Lo et al. 2024](https://doi.org/10.1039/d3dd00223c)). A bench a sophomore can run by text has a
deployment time measured in minutes of training.

The convergence reason: **this is where the field is going, and a June 2026 paper says so in our
exact vocabulary.** *LAP: An Agent-to-Instrument Protocol for Autonomous Science*
([arXiv 2606.03755](https://arxiv.org/abs/2606.03755), Zhu et al., 2026-06-02) argues that MCP
covers agent-to-tool and A2A covers agent-to-agent, but nobody covers agent-to-*instrument*, which
needs statefulness, exclusive ownership, safety-criticality, physical embodiment and measurement
integrity. Its four primitives are: signed capability-and-physical-limit descriptions, first-class
exclusive reservation, an operator-confirmation handshake bound to the task parameters, and a
physically typed measurement result with calibration anchoring and uncertainty.

We built, independently and before reading it: JSON Schema contracts with hard physical limits in a
validator, "only one direct command executes at a time" plus `BUSY` during runs, an approval request
bound to the validated plan and decided by a named human, and per-dose target-vs-actual with
tolerance in the run record. That is four for four. We are not first and we should not claim to be —
we should claim we are *aligned with the protocol the field is converging on, at 1/100th of the
capital cost.* That is a far better line than "we have an AI agent."

**Falsified if.** The gate is theatre — i.e. in practice the operator approves everything without
reading, or the agent finds a path to motion that does not raise an approval.

**Costs us.** Latency and autonomy. Every run waits on a human. We are not a self-driving lab and
§7 says so.

### 5. Build it so there can be fifty

**Claim.** The unit is not the deliverable. The *replica* is. Printed alignment jigs (JG-01..06) set
rail spacing, arm bases and scale position so a second bench is built from the jigs, not from a tape
measure; nothing threads into printed plastic; a broken part is reprinted, not RMA'd; the BOM is
Amazon links with prices; the arms are the official open-source SO-101.

**Why.** Because the literature already made this argument for us and we should simply point at it.
The frugal-twin review puts open lab hardware at roughly **$100–2k against ~$10k general-purpose and
~$1M special-purpose**, and argues that low unit cost is what *enables duplication*: several linked
duplicates give decentralisation, higher aggregate throughput and batch optimisation, with the
explicit tradeoff that **if time is the limiting factor and cost is not, prioritise the parallel
approach** — accepting some per-unit accuracy loss to get it
([Lo et al., *Digital Discovery* 2024, 3, 842](https://doi.org/10.1039/d3dd00223c);
**these specific sentences and tiers came from a search snippet — open the
[open copy](https://par.nsf.gov/servlets/purl/10500964) and quote the real text before this goes on
a slide**).

And the demand side is now the loud half of the field. The bottleneck has moved from proposing
experiments to *doing* them: AI proposes faster than labs or review can validate, and the hard part
is "everything between a software decision and a trustworthy physical measurement"
([IFP, *Scaling Materials Discovery with Self-Driving Labs*, Yang, 2025-08-11](https://ifp.org/scaling-materials-discovery-with-self-driving-labs/);
*Compressing the Validation Bottleneck*, [arXiv 2607.04508](https://arxiv.org/abs/2607.04508),
2026-07-05). If the shortage is physical validation capacity, then **capacity per dollar is the
figure of merit, and capacity per dollar is maximised by cheap units in parallel, not by one good
one.** One A-Lab at a press-reported ~$2M ([PopSci 2023](https://www.popsci.com/technology/a-lab-materials-discovery/))
is 3,400 of these benches. Liverpool's mobile chemist found a ~6× better photocatalyst in 688
experiments over 8 days ([Burger et al., *Nature* 2020](https://doi.org/10.1038/s41586-020-2442-2))
at a build cost Cooper estimated at £30–120k for that class of robot
([*Nature* 2019](https://media.nature.com/original/magazine-assets/d41586-019-01246-y/d41586-019-01246-y.pdf)).
That is the comparison that matters: not "we are cheaper," but **"for one of those, a department gets
a hundred of these, and a hundred benches running a shared protocol is a different machine."**

**Falsified if.** Per-unit variance across replicas is so large that pooling their results is
statistically worthless — i.e. the fleet is not one instrument, it is a hundred anecdotes. This is
the single biggest open risk in the whole thesis and the first thing a second bench should measure.

**Costs us.** Every per-unit virtue. Fifty benches means fifty calibrations, fifty failure modes,
and a fleet-calibration problem we have not solved and should not pretend to have solved.

---

## 3. What the research says

New findings, 2026-10-17. The price ladder, the consumable-lock-in evidence, the injury data and the
"what we don't claim" list all live in [motivation.md](motivation.md) and are not repeated here.

### 3.1 Cost is the named barrier, by everyone, repeatedly

Not our framing — the field's. Doloi et al. (2025) call the price gap a "technological divide" and
name cost as the main barrier to SDL adoption. Armer et al. (2022) document cloud-lab entry costs of
$25k/month with a one-year minimum. Lo et al. (2024) propose frugal twins explicitly to democratise
access. The 2026 reviews add a second barrier in the same breath: the multidisciplinary expertise
needed to build and run one.

**Why it matters for us:** we do not have to argue that cost is a problem. We can spend that time
arguing that *our specific substitution* (feedback for tolerance) is the one that makes cheap work.

### 3.2 The cheapest credible SDLs are now ~$1–5k, and they got there the same way we did

| System | Cost | How | Source |
|---|---|---|---|
| RoboChem Flex | ~$5,000, down from >$50k for the original RoboChem — a reported ~90% cut | 3D-printed liquid sample collector; human-in-the-loop carries samples to *shared* analytical instruments instead of buying dedicated NMR/HPLC | [UvA HIMS, Apr 2026](https://hims.uva.nl/content/news/2026/04/robochem-flex-democratisation-of-the-autonomous-synthesis-robot.html); [Lab Manager](https://www.labmanager.com/how-self-driving-labs-can-cut-automation-costs-by-90-percent-35276); [Chemistry World](https://www.chemistryworld.com/news/human-in-the-loop-approach-could-cut-costs-of-robotic-labs-by-90/4023311.article) |
| RAINBOT | under $1,300, "roughly an order of magnitude below entry-level commercial handlers" | Converts a consumer Elegoo Neptune 4 Max 3D printer: pipette on the printer's own gantry, two linear actuators for plunger and tip eject, Python control. **Browser digital twin with bidirectional sync, remote monitoring and a web e-stop** | [arXiv 2607.20662](https://arxiv.org/abs/2607.20662), Ayeche et al., 2026-07-22 |
| Archerfish | ~$500, reported up to 250 unique compositions/min | cited in the frugal-twin review (**search snippet — verify**) | [Lo et al. 2024](https://doi.org/10.1039/d3dd00223c) |
| Jubilee | ~$1,350 excl. tools | open tool-changing gantry | [GitHub](https://github.com/machineagency/jubilee) |
| **Wet Lab Bench** | **$302.51 bought (LEAN v4) + 4 fastener/VHB add-ons; ~$580 all-in if both arms are purchased at the published $121.94 BOM** | general-purpose arms + load cell + printed auger + existing glassware | [bom/BOM_final.md](../bom/BOM_final.md); [SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100) |

Two things follow, and the second one is uncomfortable, so we say it first on stage rather than
waiting for a judge to say it.

**Uncomfortable:** "low-cost SDL with a digital twin" was published three months ago. RAINBOT is the
nearest thing to us in the literature and it beats us on remote supervision. We are not novel on
cost, not novel on 3D printing, not novel on digital twins, not novel on gravimetric pouring
(Yoshikawa et al., [arXiv 2212.09672](https://arxiv.org/abs/2212.09672), did it on a Franka), and
not novel on agent-gated instruments (LAP).

**Useful:** every one of those cheap platforms is a *fixed-function machine* — a gantry that
pipettes, a printer that pipettes, a flow rig that flows. Ours is the only one in that price band
built on **general-purpose arms operating human labware**, which is the thing that decides whether a
new protocol costs a new instrument or costs a plan file. That is the gap we actually occupy, and it
is a smaller, truer claim than "cheap self-driving lab."

### 3.3 The arm stopped being the expensive part

The workflows we copy were demonstrated on research arms: Yoshikawa et al. poured in closed loop on
a Franka Panda; the commercial CHRONECT XPR powder system is a UR3e plus a balance. Those arms price
in the mid-five figures — aggregator and reseller listings for a Franka Panda cluster around
$25–40k and for a UR3e around $23–33k (**reseller/aggregator pages, not vendor quotes; treat as
order-of-magnitude only**). The SO-101's published BOM is **$121.94 per follower arm**
([SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100), Apache-2.0), and assembled kits from
multiple vendors sit around $200–240 ([ThinkRobotics](https://thinkrobotics.com/products/so-arm101-hugging-face-lerobot),
[Hiwonder](https://www.hiwonder.com/products/lerobot-so-101), [Seeed wiki](https://wiki.seeedstudio.com/lerobot_so100m_new/)).

Two orders of magnitude on the same primitive — reach, grasp, pour — is not a procurement trick, it
is the consumer robotics cost curve arriving in the lab. **The pitch line:** the published papers
used the arm that existed when they were written; the arm changed, so the price of the whole category
changed, and almost nobody has gone back to redo the cheap version.

### 3.4 Deployment cost is mostly software integration, and that is where a $500 bench can actually be *better*

The 2026 framing of lab automation's hard problem is not mechanism, it is connectivity: instruments
ship without an open control interface, retrofitting means writing drivers, and the absence of
interface standardisation leads to "inflexible device setups and highly customized and expensive
software solutions" that make small, rapid, cost-efficient automation impractical
([LAPP framework, arXiv 2106.10129](https://arxiv.org/abs/2106.10129); see also
[the SiLA 2 Manager, *SoftwareX* 2022](https://www.sciencedirect.com/science/article/pii/S2352711022000103)
on cutting integration cost, and [SiLA 2's own standard](https://sila-standard.com/)).

A bench built from open hardware has no driver problem to solve: we wrote the firmware protocol, so
the instrument's interface is a JSON line, and the agent interface is MCP over the same state store.
The *capability* an integrator spends months buying — a typed, inspectable, safety-gated control
surface — we got for free by owning the whole stack. **A new workflow here is a plan file through a
validator; on a vendor platform it can be a driver.**

What we must not oversell: commercial systems carry installation and operational qualification,
documented performance, service contracts and enclosures. Site requirements are verified before
delivery; qualification happens before real samples. That work is real, and in a regulated lab it is
mandatory. We deploy fast partly because **nobody is holding us to it** — not because we solved it.

### 3.5 The demand side: the shortage is physical validation capacity

- AI proposes faster than labs can test. The named bottleneck in 2025–26 writing is experimental
  validation, not ideation ([IFP, Yang, 2025-08-11](https://ifp.org/scaling-materials-discovery-with-self-driving-labs/);
  [arXiv 2607.04508](https://arxiv.org/abs/2607.04508)).
- Public money is moving at the facility scale: IFP reports Canada investing over $500M in public and
  private SDL funding, against newer US programmes of $40M (ARPA-E, catalysts) and $100M (CHIPS R&D,
  semiconductors). Early platforms demonstrate "hundreds of experiments per day."
- The frugal-twin review's parallel-vs-sequential argument (§2.5) is the supply-side answer to that
  demand, already in print.

**The synthesis, and the actual pitch:** the field is spending its money on a small number of
expensive, centralised, high-utilisation machines, while the thing in shortage is total validation
capacity and the thing in surplus is proposed experiments. Capacity per dollar favours many small
units. Nobody is building the many-small-units version with general-purpose arms, because until
about eighteen months ago a capable arm cost $30k.

### 3.6 Source trust labels

| Trust | Sources used above |
|---|---|
| Primary, opened | SO-ARM100 README; arXiv abstracts 2606.03755, 2607.20662, 2607.04508, 2106.10129; our own repo reports |
| Primary, prior work in motivation.md | Nature 2020 (Liverpool), Nature 2019, Steiner 2019, Lo et al. 2024, Doloi 2025, Armer 2022, Opentrons/Fisher/Tecan vendor pages |
| Secondary / press | Lab Manager, Chemistry World, PopSci, IFP, UvA news |
| **Search snippet only — re-verify before quoting** | Lo et al. cost tiers ($100–2k / ~$10k / ~$1M), the parallel-vs-sequential sentences, Archerfish ($500, 250 compositions/min) |
| **Aggregator pricing, order-of-magnitude only** | Franka Panda $25–40k, UR3e $23–33k, SO-101 kits $200–240 |
| Avoided deliberately | AI-generated SEO pages on SDL markets and pricing; the "SiLA2 + MCP by 2027-28" prediction; the "10,000 pages of IQ/OQ/PQ" figure |

---

## 4. The pitch

### The 30-second version

> AI can propose more experiments than any lab can run — the bottleneck is now physical. Automating
> it works: a robot chemist in Liverpool ran 688 experiments in eight days and found a six-times
> better photocatalyst. But that class of robot costs £30–120k to build, a materials lab like
> Berkeley's A-Lab was reported at $2M, and a cloud lab starts at $25k a month.
>
> We built the same loop for about five hundred dollars, and the trick is one substitution: we don't
> buy precision, we close the loop on a scale. Two $120 open-source arms pour onto a load cell at
> 80 Hz until the grams are right, an auger doses powder and the same scale checks it, and it all
> runs in ordinary beakers from a teaching lab. The whole thing is driven by an agent you text, and
> nothing moves until a named human approves the plan.
>
> At that price the unit stops being the point. For one A-Lab you get three thousand of these.

### The 2-minute script

Beats, with what the bench and the screen are doing. The texts come from
[`software/docs/DEMO_SCRIPT.md`](../software/docs/DEMO_SCRIPT.md) — that file is the other script,
and these two must stay in sync.

| # | Say | Show |
|---|---|---|
| 1 | "AI can now propose more experiments than anyone can run. The bottleneck is hands." | Bench parked. Dashboard idle. |
| 2 | "Automating the loop works — Liverpool, 688 experiments in 8 days, 6× better catalyst. And it costs £30–120k, or $2M, or $25k a month." | One slide, the price ladder. |
| 3 | "Here's the same loop for about five hundred dollars." Text the bench: `run the standard recipe`. | Phone on screen. Agent validates: 39 g / 7 g / 30 g. **Approval request appears.** |
| 4 | "Anyone can ask. Only an operator can approve — and the bench records who." Tap approve. | Approval decided by name, run starts. |
| 5 | "The trick isn't the robot, it's where the accuracy lives. We don't buy a precision pump. We pour onto a scale at 80 Hz and cut when the grams are right." | Live scale trace climbing to 39 g, target vs actual on the dashboard. |
| 6 | "Which means it works in a teaching lab's own beakers. No proprietary tip, no dosing head, nothing with our part number on it." | Camera on the beaker and the funnel. Auger doses yeast; scale verifies. |
| 7 | "Every dose is logged against its target, so the protocol re-runs. That matters: most researchers have failed to reproduce someone else's work." | Notebook page from the last run. |
| 8 | *(eruption)* "And the operator never measured, transferred or mixed any of it." | Sled to ERUPT. Foam. |
| 9 | "The reason to care isn't that it's cheap. It's that at this price the unit isn't the point — a department buys a hundred. The literature's own argument: duplicate cheap platforms for parallel, decentralised throughput. We're the only one in this price band built on general-purpose arms and human glassware, so a new protocol is a plan file, not a new instrument." | One slide: 1 × $2M vs N × $500. |
| 10 | "What we don't claim: it's not a self-driving lab, it doesn't pick its own experiments, our accuracy numbers are from the simulator until tonight's runs, and the operator still pours the peroxide. Here's the sim, and here's what the first ten real pours measured." | The measured table (§6). |

Beat 10 is not modesty, it is the strongest beat. Judges have heard nine pitches that overclaimed.

### Five slides

1. **The gap.** Proposed experiments ↑, validation capacity flat.
2. **The price ladder.** $10k → $26k → $128k → $2M → $25k/mo, and one line at $500 (from
   motivation.md's table; keep the trust labels in the footnotes).
3. **The substitution.** Precision plunger vs load cell + cut law. One diagram, the scale trace.
4. **The fleet.** 1 × A-Lab = 3,400 benches. The parallel-vs-sequential argument, cited.
5. **What we don't claim.** Verbatim from [pitch.md](pitch.md).

### Lines to use

- "We don't buy precision, we close the loop on it."
- "Deploy into the glassware the lab already owns."
- "Anyone can ask the bench for a run. Only a named human can approve it."
- "For one of those, a department gets a hundred of these."
- "A new protocol is a plan file, not a new instrument."

### Lines to never use

Everything in [pitch.md](pitch.md) § "Avoid these claims", plus, from this document's research:

- "First low-cost self-driving lab." RoboChem Flex, RAINBOT, Archerfish, Jubilee, and a whole review
  table of them exist. Say "the cheapest *general-purpose-arm* bench we can find, and we looked."
- "No human touches the chemicals." The operator pours the 12% peroxide by hand.
- Any accuracy figure without the word "simulator" until the bench has been measured.
- "We invented agent-gated instrument control." LAP (June 2026) published the same primitives.
  Say "aligned with where the protocols are converging, at a hundredth of the capital cost."

---

## 5. The hard questions

Additions to [pitch.md](pitch.md)'s list, from this research.

**"RAINBOT did low-cost plus a digital twin in July. What's left?"**
They converted a 3D printer into a pipettor — a fixed-function machine with an excellent remote
interface, and theirs beats ours on remote supervision. We are two general-purpose arms handling
unmodified human labware, closing the loop on mass for both a liquid and a powder. The difference
shows up on the second protocol: changing what they do means changing the end effector; changing
what we do means changing a plan file. Also, we should steal their browser e-stop.

**"Isn't 'buy a hundred cheap ones' hand-waving? You have one, and it isn't finished."**
Yes. Today it is an argument, with two pieces of support: the frugal-twin review makes the
parallel-throughput case in print, and our build is jig-located so the geometry is reproducible
rather than hand-fitted. The thing that would make it real is a second bench reproducing the first
one's pour statistics, and that is the first milestone in §6. Until then we say "designed for
replication," not "replicated."

**"Where does a $500 bench lose?"**
Throughput per unit, accuracy, containment, sterility, service, and anything regulated. Our tolerance
is ±2 g on 39 g — about 5%, the same order as the beaker graduations we are replacing. The win is
hitting a mass target from an arbitrary starting amount, not out-measuring a Quantos.

**"Your own report says six poses miss the margin rule."**
It does, and we would rather tell you than have you find it. The 10° rule is our own conservative
gate, the misses are 7.5–9.7° on side grasps, and the CAD-to-arm mapping is uncalibrated by
3.4–10.4 mm. That is exactly why first runs go at 25% speed with empty beakers.

**"Why arms instead of a pump and a stepper for this one recipe?"**
For one recipe, a pump wins — say so. The arms buy the next recipe: they move vessels, pour, and
reach a station we add next week, with no new hardware. We are buying generality, and generality is
the only reason the fleet argument works.

---

## 6. What this implies for development

The principles are only worth writing down if they decide the next commits. They do.

### Gate 0 — before the pitch (today)

- [ ] **Measure ten real pours.** Mean ± SD on 39 g, then the yeast dose. This single table converts
      the whole deck from design to result. Everything else can slip.
- [ ] **Fix the stale status lines.** [README.md](../README.md) and [pitch.md](pitch.md) both say the
      repo contains no run-time application or firmware, and tell the presenter not to claim the AI
      layer, camera checks or notebook logging. `software/` now contains all of them, plus
      `firmware/bench_mega/`. Judges read the repo. Update those two headers to say what exists and
      what is still simulator-only.
- [ ] One `software/` vs `software/benchsim/` sentence in `software/README.md`: two simulation stacks
      exist; say which one's numbers we quote (benchsim's, because `reproduce` regenerates them).

### Gate 1 — the claim becomes a measurement (next two weeks)

- [ ] Refit `calibration.weir_c`, `control.pour.cut_a_g`, `cut_b_s` on real water; report the −0.28 g
      sim bias against the real one. **Principle 1 lives or dies here.**
- [ ] Re-teach the six out-of-margin stations and record per-station offsets in
      `bench.yaml.calibration.station_offsets_mm`; calibrate the CAD↔MJCF path mapping so the twin's
      poses are trustworthy rather than approximate. **Principle 3 lives or dies here.**
- [ ] Add the browser e-stop and remote state view RAINBOT demonstrates. We already serve SSE and
      MJPEG; this is small and it closes a real gap.

### Gate 2 — the fleet claim becomes testable (the version that matters)

- [ ] **A second bench, built only from the jigs, the BOM and the docs, by someone who did not build
      the first.** Deliverable: hours-to-first-validated-pour, and whether its pour distribution
      overlaps bench one's. This is the experiment that tests the manifesto. If the distributions do
      not overlap, Principle 5 is wrong and we say so.
- [ ] Fleet calibration: a per-bench calibration record, and a run record that carries it, so a
      pooled dataset is interpretable.
- [ ] A protocol library — three recipes that are plan files, not new hardware (a buffer series, a
      dose-response dilution, a crystallisation screen). This is the direct test of "a new protocol
      is a plan file."

### Gate 3 — align to the field instead of diverging from it

- [ ] Map our contracts onto LAP's four primitives
      ([arXiv 2606.03755](https://arxiv.org/abs/2606.03755)): publish an InstrumentCard-shaped
      capability + physical-limit document generated from `bench.yaml` and the validator; make the
      approval token explicitly bound to the validated plan hash; put calibration anchor and
      uncertainty on every dose in `RunSummary`. We have the semantics; this is naming and schema
      work, and it makes a $500 bench legible to the same agents as a $100k one.
- [ ] Publish the twin + BOM + jigs as a reproducible build, the way the UvA group published
      RoboChem Flex's guide. Replication is the product (Principle 5); an unpublished replica is not
      a replica.

### What would make us stop

Written down now, while it is cheap to be honest:

- Real pour error on 39 g is worse than ±5% after refitting → the feedback substitution does not hold
  at this hardware grade, and the cost argument collapses with it.
- Re-teaching stations by hand beats the twin → Principle 3 is a nice story about a tool we do not
  actually use.
- Two benches cannot be pooled → we have a toy, a good teaching toy, and we should pitch it as a
  teaching toy, which is an honourable thing to be and is the use case Lo et al. actually documents.

---

## 7. What this document does not claim

- **Not a self-driving lab.** No experiment selection, no optimisation loop. The agent plans and
  executes a validated recipe; a human approves it. The catalyst-screening story in
  [SUMMARY.md](../SUMMARY.md) is the roadmap, not this checkout.
- **Not novel.** Low-cost SDLs, 3D-printed lab hardware, digital twins of lab robots, gravimetric
  robotic pouring and agent-gated instruments are all published prior art, cited above. Our claim is
  a combination — general-purpose open-source arms, unmodified human labware, closed-loop mass dosing
  of both a liquid and a powder, one code path from twin to bench, at hobby cost — and we found no
  published system with all of it. That is an integration and cost claim, not a technique claim.
- **No measured accuracy, throughput, safety, access or teaching outcome.** Every number in §2 and
  §3.2 that describes *our* bench is from the simulator. The fleet argument is an argument.
- **No fleet.** One bench exists.
- **Prices are as of 2026-10-14/17**, and the rows marked "search snippet" or "aggregator" are not
  stage-ready until someone opens the source.
