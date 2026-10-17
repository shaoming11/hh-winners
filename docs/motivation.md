# Why it matters: motivation for the Wet Lab Bench

Researched 2026-10-14. Every number below has a link. Where a figure is a reseller price, comes from a
secondary source, or is our own arithmetic, it says so. Where we could not find a source, we say that
too and make no claim.

## Elevator pitch (3 sentences)

Commercial lab automation that weighs and doses reagents costs tens to hundreds of thousands of
dollars. It also tends to lock you into the vendor's tips, vials or dosing heads. Wet Lab Bench
makes up an exact recipe from rough, operator-loaded amounts, with closed-loop gravimetric
pouring by two open-source SO-101 arms, auger powder dosing checked on a scale, and ordinary
beakers and an Erlenmeyer flask, for a few hundred dollars of parts, and no one touches the
reagents during the run.

---

## Claims, with evidence

### Claim 1: Commercial liquid handling, powder dosing and self-driving labs cost from about $10k to millions

- **Liquid handlers.**
  - Opentrons is the cheapest mainstream vendor. Its OT-2 page is titled "from $10,000" ([opentrons.com/robots/ot-2](https://opentrons.com/robots/ot-2)), and Flex "configurations [start] at $26,400" ([opentrons.com/robots/flex](https://opentrons.com/robots/flex)). Both were checked 2026-10-14.
  - Tecan Fluent parts in a reseller's catalogue: base units are $46,530 to $124,589, and an 8-channel pipetting arm adds $81,058 to $94,802 ([GovSci catalogue](https://www.govsci.com/searching/supplier/Tecan/), reseller list price). A Fluent 480 base plus one arm therefore comes to about $128k (our sum).
- **Powder dosing.** A 2024 review says autonomous powder dispensers such as Trajan's CHRONECT "cost significantly more (USD 100k+) than liquid handlers of similar resolution" ([Lo et al., *Digital Discovery* 2024, 3, 842](https://doi.org/10.1039/d3dd00223c), §6.1; [open copy](https://par.nsf.gov/servlets/purl/10500964)).
- **Synthesis robots and SDLs.**
  - Cronin's Chemputer: robotic-module parts are under $10,000 per system, rising to $30,000 with stirrers, evaporator and chiller ([Steiner et al., *Science* 2019, 363, eaav2211](https://www.chem.gla.ac.uk/cronin/images/pubs/387-Steiner-ScienceJan19.full.pdf)). *Nature* reported £25,000–30,000 (US$33,000–39,500) each, including associated kit. In the same 2019 article, Cooper estimated mobile robots like Liverpool's cost £30,000–120,000 to build, and Imperial's automated-chemistry facility cost more than £4.5 million ([Sanderson, *Nature* 568, 25 Apr 2019](https://media.nature.com/original/magazine-assets/d41586-019-01246-y/d41586-019-01246-y.pdf)).
  - Berkeley A-Lab: "$2 million" ([Popular Science, 28 Apr 2023](https://www.popsci.com/technology/a-lab-materials-discovery/); a press figure, not an official budget).
  - The CMU/Emerald Cloud Lab facility is a USD 40 million facility (Lo et al. 2024, citing press).
  - The original RoboChem cost over $50,000, excluding NMR ([UvA HIMS news, Apr 2026](https://hims.uva.nl/content/news/2026/04/robochem-flex-democratisation-of-the-autonomous-synthesis-robot.html)).
- **Cloud labs.**
  - Emerald Cloud Lab's all-inclusive tier was "$25k/month, with a 1 year minimum commitment, for a total entry cost of $300k".
  - Strateos assay contracts were around $10k/month for a one-year minimum.
  - Both figures come from [Armer et al. 2022, "Barriers to Academic Use of Commercial Cloud Labs"](https://irispublishers.com/ojrat/fulltext/barriers-to-academic-use-of-commercial-cloud-labs.ID.000511.php). They are 2022 figures and may have changed.
- **Review-level statement.** Doloi et al. name cost as the main barrier to SDL adoption: commercial systems range from tens to hundreds of thousands of dollars, which limits access mainly to well-funded institutions ([*Digital Discovery* 2025, 4, 1685](https://doi.org/10.1039/d4dd00411f); paraphrased from the abstract, full text not opened).

### Claim 2: Commercial systems tie you to vendor consumables; ordinary glassware is approximate, which is why weighing matters

- **Vendor consumables.**
  - Opentrons: "Opentrons can only guarantee performance of the Flex when using our Flex pipette tips". Its guides say Flex pipettes are "not recommended" with tips from other manufacturers, and OT-2 tips are not compatible with Flex at all ([Opentrons Flex pipette FAQ / quick-start guides](https://opentrons.com/catalog/flex-pipettes/faqs)).
  - Mettler Toledo Quantos powder dosing uses proprietary dosing heads, sold in packs of 10 for about US$2,000–3,200 on Fisher's US site ([Fisher Scientific listing](https://www.fishersci.com/shop/products/quantos-dosing-heads/01910260); reseller price, from search results).
- **Be precise here: lock-in is not universal.**
  - Opentrons labware is SBS/ANSI plate format, and many third-party plates are supported.
  - Third-party "CO-RE-style" tips exist for Hamilton (e.g. [Axygen](https://cdn.thomassci.com/p/axygen-300l-hamilton-co-re-style-tips)).
  - So the accurate claim is that these systems are built around microplate- and tip-format consumables, and sometimes vendor-specific ones. They are not built around beakers and flasks.
- **Ordinary glassware is not a measuring device.**
  - Beaker and Erlenmeyer graduations are good to about ±5% ([DWK/Duran FAQ](https://www.dwk.com/laboratory-products/beakers-amp-flasks/erlenmeyer-flasks); [Harper College](https://dept.harpercollege.edu/chemistry/chm/100/dgodambe/thedisk/labtech/volume.htm)).
  - Weighing is the reference method used to calibrate volumetric devices themselves (ISO 8655-6, gravimetric; see [Mettler Toledo summary](https://mt.com/in/en/home/perm-lp/product-organizations/pipe/iso-8655-updates.html)).
  - Measuring by weight on a scale is what lets us use cheap, ungraduated-quality labware and still hit a mass target.

### Claim 3: The core workflows (gravimetric liquid transfer, powder dosing by weight, combining in a flask) can be done with hobby-grade open hardware and regular labware

- **Arm cost.** The SO-101 follower arm's published bill of materials is $121.94 per arm, or $229.88 for a leader and follower pair ([TheRobotStudio/SO-ARM100 README](https://github.com/TheRobotStudio/SO-ARM100), Apache-2.0).
- **Our BOM.**
  - Priced new purchases come to about $400 as of 2026-10-13. Some items are still unpriced, and the figure includes optional spares ([bom/BOM.md](../bom/BOM.md)).
  - The two arms are borrowed, and the Arduino Mega, frame and servos are already owned.
- **What the bench does** (design intent, see [demo_process.md](demo_process.md)):
  - pours to a mass target in closed loop on a 1 kg load cell at 80 Hz;
  - doses yeast by auger and verifies it by weight;
  - combines the reagents in a 250 mL Erlenmeyer through a funnel.
- **Design tolerances** are ±2 g on 39 g of peroxide, ±2 g on water and ±0.7 g on yeast. **These are targets, not measured results.** Report the measured error from real runs before using any accuracy number.

### Claim 4: Taking the person out of the dispensing step is a recognised way to reduce exposure, and academic labs do have a real injury problem

- **Injury data.**
  - In a 2012 survey of about 2,400 researchers, just under half reported a lab injury. 30% had witnessed a "major" injury needing medical attention, and more than a quarter of junior researchers had an injury they did not report. The sample was non-random ([Van Noorden, *Nature* 2013, via *Sci. Am.*](https://www.scientificamerican.com/article/safety-survey-reveals-lab-risks/)).
  - The U.S. CSB's laboratory dataset lists **261 incidents, 10 fatalities and 489 injuries** in U.S. public and private labs, Jan 2001 to Jul 2018. The CSB says this is incomplete ([CSB Laboratory Incident Data](https://www.csb.gov/assets/1/6/CSB_Laboratory_Incident_Data.pdf); our tally of its table). About 141 of those rows are universities or colleges (our keyword count).
- **Named cases.**
  - Sheri Sangji died after a t-butyllithium fire during a syringe transfer at UCLA in Dec 2008 ([summary](https://en.wikipedia.org/wiki/Sheri_Sangji_case); see the Cal/OSHA and criminal case refs there).
  - At Texas Tech in Jan 2010, a student lost three fingers grinding an energetic compound by hand. The CSB found "no comprehensive guidance for conducting hazard evaluations" in academic labs ([CSB, 19 Oct 2011](https://www.csb.gov/csb-releases-investigation-into-2010-texas-tech-laboratory-accident-case-study-identifies-systemic-deficiencies-in-university-safety-management-practices/)).
  - Both injuries happened during **manual transfer or handling steps**, the kind of step automation replaces. Note that neither was a dispensing-by-weight task like ours.
- **Why automation helps.**
  - NIOSH's hierarchy of controls ranks engineering controls, which "reduce or prevent hazards from coming into contact with workers", above PPE ([NIOSH, 2024](https://www.cdc.gov/niosh/hierarchy-of-controls/about/index.html)). A bench that measures and pours behind a physical boundary is an engineering control. Gloves and goggles are PPE.
- **Hazard of the demo reagent.**
  - Under EU CLP, hydrogen peroxide at 8–50% is classified **Eye Dam. 1 (H318, serious eye damage)**. At 12% it is *not* classified as a skin corrodent; that starts at 50% ([harmonised specific concentration limits as reproduced in supplier SDSs, e.g. Chemos](https://www.chemos.de/import/data/msds/GB_en/7722-84-1-A0272345-GB-en.pdf)).
  - IPCS says H2O2 is irritant to skin with "blistering and whitening; solutions >10% may cause burns" ([INCHEM PIM 946](https://inchem.org/documents/pims/chemical/pim946.htm)).
- **Honest caveats.**
  - We found no study that *measures* reduced exposure from lab automation.
  - SDL safety papers stress that robots add their own hazards, such as spills, broken glassware and battery fires ([PREVENT, arXiv 2510.21438](https://arxiv.org/pdf/2510.21438)).
  - In our bench **the operator still loads the peroxide by hand** (with gloves and goggles). What is automated is the measuring, transferring and mixing.

### Claim 5: Low cost widens access, and this is an argued goal in the field

- Lo et al. (2024) propose "frugal twins": low-cost SDLs for teaching, prototyping and "democratizing" access. Many educational SDLs are under USD 1,000, and their Table 1 lists builds from $50 to $15,000.
- Doloi et al. (2025) call the price gap a "technological divide".
- Armer et al. (2022) document cost and minimum-commitment barriers to academic use of cloud labs.
- **What we can honestly say:** a bench at this price is within reach of a teaching-lab or student-club budget. We have **no** data on adoption, learning outcomes or compliance benefits.

---

## Price comparison

| System | What it does | Price | Source | Date | Note |
|---|---|---|---|---|---|
| Opentrons OT-2 | Pipetting liquid handler (plates/tips) | from $10,000 | [opentrons.com](https://opentrons.com/robots/ot-2) | checked 2026-10-14 | Vendor page title. A July 2026 third-party guide lists $15,950 ([grabarobot](https://grabarobot.com/blog/opentrons-lab-automation-robot-price-guide-2026/), unverified) |
| Opentrons Flex | Pipetting liquid handler + gripper | from $26,400 | [opentrons.com](https://opentrons.com/robots/flex) | checked 2026-10-14 | Vendor |
| Tecan Fluent 480 | Liquid handler | $46,530 base + $81–95k per 8-ch arm (≈$128k+) | [GovSci](https://www.govsci.com/searching/supplier/Tecan/) | checked 2026-10-14 | **Reseller list price**; the total is our sum |
| Hamilton Microlab STAR, Beckman Biomek i7 | Liquid handlers | Quote only | Vendor sites | 2026 | Used-market asking prices seen in search were tens of thousands to >$100k. **Not verified; do not quote a number** |
| Mettler Toledo Quantos | Gravimetric powder dosing | System: quote only. Dosing heads: ~$2.0–3.2k per 10-pack | [Fisher](https://www.fishersci.com/shop/products/quantos-dosing-heads/01910260) | 2026 | **Reseller**; consumable price only |
| Trajan/Mettler CHRONECT XPR | Automated powder + liquid dosing | USD 100k+ | Lo et al. 2024 | 2024 | Review estimate |
| Chemspeed, Unchained Labs (incl. ex-Freeslate) | Automated synthesis/formulation | Quote only; no public price found | — | — | Do not quote a number |
| Chemputer (Cronin) | Modular organic synthesis, standard glassware | <$10k modules; ~$30k with stirrers/evaporator/chiller; £25–30k each per *Nature* | [Steiner 2019](https://www.chem.gla.ac.uk/cronin/images/pubs/387-Steiner-ScienceJan19.full.pdf); [Nature 2019](https://media.nature.com/original/magazine-assets/d41586-019-01246-y/d41586-019-01246-y.pdf) | 2019 | Authors' figures |
| Liverpool mobile robotic chemist (Burger et al., *Nature* 2020) | Mobile arm using human lab equipment | £30k–120k to build (Cooper's estimate for this class of robot) | [Nature 2019](https://media.nature.com/original/magazine-assets/d41586-019-01246-y/d41586-019-01246-y.pdf) | 2019 | **Estimate.** A 2020 quote of "£50k–150k" circulates but we could not open its source |
| Berkeley A-Lab | Autonomous solid-state synthesis | ~$2 million | [PopSci](https://www.popsci.com/technology/a-lab-materials-discovery/) | 2023 | Press figure |
| Emerald Cloud Lab | Remote cloud lab | $25k/month, 1-year minimum ($300k entry) | [Armer et al.](https://irispublishers.com/ojrat/fulltext/barriers-to-academic-use-of-commercial-cloud-labs.ID.000511.php) | 2022 | Secondary; may be outdated |
| Strateos | Cloud lab (pivoted to on-site in 2023) | ~$10k/month, 1-year minimum | Armer et al. | 2022 | Secondary |
| RoboChem Flex | Low-cost flow-chemistry SDL | ~$5,000 (original RoboChem >$50k) | [UvA](https://hims.uva.nl/content/news/2026/04/robochem-flex-democratisation-of-the-autonomous-synthesis-robot.html) | 2026 | Authors' estimate |
| Jubilee | Open-source tool-changing gantry | ~$1,350 per unit, excluding tools | [GitHub](https://github.com/machineagency/jubilee) | current | Project estimate |
| **Wet Lab Bench** | Gravimetric pour + powder dose + combine, standard labware | ~$400 new parts (priced rows) + 2 × ~$122 arm BOM | [BOM](../bom/BOM.md); [SO-ARM100](https://github.com/TheRobotStudio/SO-ARM100) | 2026-10 | Arms borrowed. Excludes 3D printer, filament and tools |

**These are not like-for-like comparisons.** Commercial systems give validated accuracy, throughput,
software, service and enclosures. Our bench does one recipe at hackathon quality.

---

## Prior art, and how we differ

- **Low-cost SDLs and "frugal twins" are well established** (Lo et al. 2024, Table 1: $50–$15k builds, e.g. CLSLab:Light ~$50, BOB ~$200, a "cheap automated synthesis platform" ~$450). So "low-cost lab automation" is **not new**.
- **Standard glassware in automation is not new.**
  - The Chemputer chose "common laboratory glassware rather than a jacketed reactor vessel … to lower the barrier for reproducing the setup" (Steiner et al. 2019).
  - Liverpool's mobile chemist "can work with equipment designed for human operation" ([Liverpool news, 2020](https://news.liverpool.ac.uk/2020/07/08/experiment-too-big-hire-a-mobile-robot-scientist/)).
- **Robotic pouring with scale feedback is not new.** [Yoshikawa et al. (arXiv 2212.09672)](https://arxiv.org/abs/2212.09672) pour in closed loop on scale readings in a chemistry setting, using a Franka Panda, which is a much more expensive arm.
- **Robotic powder weighing is not new.** Examples include spoon-based weighing learned in simulation ([Kadokawa et al. 2023, OMRON SINIC X](https://www.omron.com/global/en/media/2023/10/c1023_2.html)), dual-arm spatula weighing (Jiang et al., cited in [arXiv 2512.07091](https://arxiv.org/abs/2512.07091)), and a commercial UR3e-plus-balance system (CHRONECT XPR).
- **SO-101 arms in a lab.**
  - [Lambda-Biolab/so101-biolab-automation](https://github.com/Lambda-Biolab/so101-biolab-automation) uses dual SO-101 arms for 96-well pipetting. It describes itself as an untested prototype, and has no scale or powder dosing.
  - We found no published work using SO-100/101 arms for gravimetric pouring or powder dosing in standard glassware. We searched arXiv, GitHub and the web on 2026-10-14; that is not an exhaustive search.
- **What is new in our combination:**
  - general-purpose open-source arms at roughly $120 each in parts;
  - un-modified consumer and lab beakers and an Erlenmeyer, not plates or tips;
  - closed-loop gravimetric dosing of **both** liquids and a powder from arbitrary starting amounts;
  - all at hobby cost.
- It is an integration and cost demonstration, not a new technique.

---

## What we do NOT claim

- **We do not claim our accuracy matches commercial systems.** Our tolerances (±2 g, ±0.7 g) are design targets until measured, and ±2 g on 39 g is about 5%, the same order as beaker graduations. The win is hitting a mass target from arbitrary input amounts, not beating a Quantos.
- **We do not claim to be the first** low-cost SDL, the first to use standard glassware, or the first robot to pour by weight.
- **We do not claim "no human contact with hazardous chemicals."** The operator pours the 12% peroxide (consumer "40-volume" hair developer) into the reagent beaker by hand.
- **We do not claim 12% H2O2 is a severe hazard.** Its main formal classification is serious eye damage. "Burns skin" is supported only as "may cause burns" above 10% (IPCS).
- **We do not claim measured safety, access, or teaching benefits.** These are motivations, not results.
- **We do not claim a self-driving lab.** There is no closed-loop experiment planning or optimisation; it executes a fixed recipe.
- **We do not claim commercial systems *require* proprietary glassware.** They use plate/tip/vial formats, some vendor-specific, and third-party tips exist.
- **We do not quote prices for Chemspeed, Unchained Labs, Hamilton or Biomek.** None is publicly listed.
- **We do not quote the "£50k–150k" figure for the Liverpool robot.** Use the sourced "£30k–120k" estimate (*Nature* 2019) or none.
- **Our cost excludes** borrowed arms, 3D printer time, tools and labour.

---

## Poster or pitch one-liners

1. "Exact recipes from rough pours: gravimetric lab automation with $120 open-source arms and ordinary beakers."
2. "Dosing by weight, the kind of workflow commercial systems sell for $26k–$100k+, prototyped for a few hundred dollars with no hands on the reagents during the run."
3. "Weigh, don't measure: closed-loop pouring and powder dosing that turns approximate glassware into precise recipes."
