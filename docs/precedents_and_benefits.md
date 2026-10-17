# Precedents and benefits: who has done this before, and what it buys you

Researched 2026-10-17. Companion to [motivation.md](motivation.md) (cost + prior art table) and
[manifesto.md](manifesto.md) (thesis + script). This file adds two things for the pitch: a **story
of people who automated the lab before us**, and **measured evidence for the benefits** (human
error, time, strain, reproducibility, access), plus (sections 6–10) **the ethical case, the risks
judges will raise with our answers, why-now evidence, and an ethics statement**. Same house rule: every number has a link, and
secondary/press figures are labelled.

---

## 1. The 30-second history hook (say this out loud)

> "In 2009 a robot called Adam became the first machine to discover new scientific knowledge on
> its own. Since then robot chemists have run 688 experiments in 8 days, made 41 new materials in
> 17 days, and taken plain-English instructions. But each of those labs cost tens of thousands to
> millions. Meanwhile, the companies that actually spread automation, like Opentrons, started in a
> Brooklyn community biolab with a $2,000 robot. We're taking the next step down that curve: two
> $120 open-source arms, a kitchen-grade scale, and ordinary beakers."

---

## 2. Timeline: people doing this in the past

| Year | Who / what | What it showed | Cost signal | Source |
|---|---|---|---|---|
| 2009 | **Adam** (Ross King, Aberystwyth + Cambridge) | First machine to form hypotheses and run its own experiments to discover new knowledge (yeast gene functions). Published in *Science*. "The novel thing is that Adam is able to formulate hypotheses on its own and test them." | Not public | [Cambridge news](https://www.cam.ac.uk/research/news/robot-scientist-becomes-first-machine-to-discover-new-scientific-knowledge) |
| 2014–15 | **Opentrons** founded out of Genspace, a Brooklyn community biolab; Kickstarter-funded OT-1 | The low-cost open robot is how lab automation actually spread. Later raised a $200M Series C (2021) | OT-1 shipped at **$2,000** | [Wikipedia](https://en.wikipedia.org/wiki/Opentrons) (secondary) |
| 2015 | **Eve** (King lab, Manchester/Cambridge) | Screened ~1,500 approved drugs and found one that hits the malaria target DHFR; >10,000 compounds/day. Authors' claim: "reduces the costs, uncertainty, and time involved in drug screening" | Not public | [Manchester news](https://www.manchester.ac.uk/discover/news/robot-scientist-eve-could-boost-search-for-new-drugs/); *J. R. Soc. Interface* 2015 |
| 2019 | **Chemputer** (Cronin, Glasgow) | Synthesis using **common glassware**, chosen "to lower the barrier for reproducing the setup" | <$10k modules, ~$30k full | see [motivation.md](motivation.md) |
| 2020 | **Liverpool mobile robot chemist** (Cooper) | 688 experiments in 8 days, found a photocatalyst ~6× better; uses equipment built for humans | £30–120k (estimate) | see [manifesto.md](manifesto.md) |
| 2020 | **Open-source COVID testing robots** (Opentrons at Mayo, Harvard, Stanford, MIT, BioNTech; ROBOCOV in Spain) | Cheap open robots scaled emergency testing when commercial handlers were back-ordered | Low-cost by design | [Wikipedia](https://en.wikipedia.org/wiki/Opentrons) (secondary); [ROBOCOV, bioRxiv](https://www.biorxiv.org/content/10.1101/2020.06.11.140285.full.pdf) |
| 2023 | **A-Lab** (Ceder, Berkeley) | 41 new inorganic materials in 17 days, *Nature*. **Caveat:** later critiques questioned how many were truly new, so cite as "speed", not "discovery count" | ~$2M (press) | [Ceder lab](https://ceder.berkeley.edu/news/a-lab-paper-published-in-nature-featured-in-news-story) |
| 2023 | **Coscientist** (Gomes, Carnegie Mellon) | LLM plans chemistry and robots execute it, *Nature*. Gomes: LLMs remove "one of the most significant barriers for using automated labs: the ability to code" | Uses commercial handlers | [Times Higher Ed](https://www.timeshighereducation.com/news/ai-lab-partner-designs-and-executes-its-own-experiments) |
| 2025 | **U of Toronto undergrads** (Kalashnikov, Hou; Hattrick-Simpers) | Self-driving electrochemistry lab from a 3D-printer gantry, aquarium pumps and a 2-servo gripper; now used in a course. Built for people "who don't have access to expensive tools" | **<$500** | [U of T News, Jul 2025](https://www.utoronto.ca/news/ai-and-robotics-u-t-students-build-self-driving-lab-less-500) |
| 2026 | **RoboChem Flex** (UvA), **RAINBOT** | Explicit "democratisation" builds at ~$5k and <$1,300 | ~$1–5k | see [motivation.md](motivation.md), [manifesto.md](manifesto.md) |
| **2026** | **Wet Lab Bench (us)** | Gravimetric pour + powder dose + combine with general-purpose $120 arms and ordinary beakers | ~$300 buy list + arms | [BOM_final.md](../bom/BOM_final.md) |

**The story arc for judges:** automation started as one-off, million-dollar research robots
(Adam, A-Lab), got proven useful at scale, and spread when someone made it cheap and open
(Opentrons, then student builds like U of T). The trend line is **cost dropping ~10× per step**,
and student/hackathon builds are where the next step usually starts.

---

## 3. Benefits, with evidence

### 3.1 Humans are inconsistent at measuring, even experts
- 2026 study of **108 lab personnel** (students, PhDs, clinical chemists, technicians):
  **22% failed the ISO accuracy limit at 100 µL, and 36% failed the precision limit at 10 µL.**
  "Even experienced personnel occasionally failed to meet ISO standards." Students were the most
  variable and slowest.
  [Özcan et al., *J. Appl. Lab. Med.* 2026, 11(3):460](https://pure.amsterdamumc.nl/en/publications/pipetting-performance-across-laboratory-personnel-a-comparative-s/)
- **Pitch use:** our bench closes the loop on a scale, so the dose depends on the sensor, not on
  who's holding the beaker. (Our ±2 g / ±0.7 g are still *targets* until measured.)

### 3.2 It eats researcher time
- Industry survey: **70% of lab professionals spend >1 hour/day on manual pipetting**; those with
  no automation average **>3 hours/day**. 62% named time spent on manual pipetting a key
  workflow challenge. [SPT Labtech, State of Automated Pipetting 2022](https://sptlabtech.com/blog/the-state-of-automated-pipetting-2022)
  (vendor survey; sample size not published, so label it as such).

### 3.3 It hurts people's bodies
- Survey of 83 biomedical scientists (Oman, 2020): **77% had musculoskeletal symptoms in the
  past year** (neck 51%, shoulders 49%, lower back 43%), and pipetting was significantly
  associated with shoulder and lower-back complaints.
  [medRxiv 2021.06.04.21258372](https://www.medrxiv.org/content/10.1101/2021.06.04.21258372.full.pdf)
  (preprint, single site; use as "evidence of", not "proof").

### 3.4 Science has a reproducibility problem
- *Nature* survey of 1,576 researchers: **>70% have failed to reproduce another scientist's
  experiment; >50% have failed to reproduce their own.**
  [Baker, *Nature* 533:452, 2016](https://bioblast.at/index.php/Baker_2016_Nature)
- 78% of lab professionals call accuracy, standardization and reproducibility a major challenge
  (SPT Labtech 2022, above).
- **Pitch use:** every dose on our bench is logged as target vs. actual mass, which is exactly
  the record a replication needs. (Logging is a planned feature, not in this checkout.)

### 3.5 Safety: removing hands from the transfer step
- Already sourced in [motivation.md](motivation.md) Claim 4: CSB counts 261 lab incidents and
  10 deaths (2001–2018); Sangji (UCLA) and Texas Tech injuries happened during manual
  transfer/handling; NIOSH ranks engineering controls above PPE.

### 3.6 Cheap + open is what actually spreads
- Opentrons started with a $2,000 robot from a community lab; a few years later its robots ran COVID testing at Mayo, Harvard, Stanford and MIT
  (secondary source). U of T's <$500 build went straight into a course. Cost is the
  barrier every SDL review names ([motivation.md](motivation.md) Claim 1, 5).

---

## 4. Lines you can say on stage

1. "The first robot scientist was in 2009. Fifteen years later, the cheapest
   mainstream liquid-handling robot still starts at $10,000. We built ours for about $300."
2. "In a 2026 study, more than a fifth of lab staff missed ISO accuracy limits pipetting by hand.
   Our bench doesn't trust hands or glassware. It trusts the scale."
3. "70% of lab workers spend over an hour a day on manual liquid handling. That's the hour we
   want back."
4. "Over 70% of scientists have failed to reproduce someone else's experiment. A robot that logs
   every gram is a replication you can re-run."
5. "Opentrons started in a Brooklyn community lab with a $2,000 robot. We think the next step
   down that curve starts at a hackathon."

## 5. Don't say

- That Adam/Eve/A-Lab used cheap hardware (they didn't, that's the contrast).
- "A-Lab discovered 41 new materials" as settled fact (disputed; say "made 41 targets in 17 days").
- That our bench fixes reproducibility or injuries. These are *motivations*; we have no measured
  outcome. Pipetting studies are µL pipettes, we pour grams; say "the same problem class".
- Opentrons' "$2,000 to $28 per test" COVID figure (Wikipedia, unverified).

---

## 6. The ethical case

The short version is that automation, safety, and reproducible wet-lab work are now mostly available to well-funded labs, and a ~$300 bench is priced for everyone else. Everything below is a motivation backed by evidence about the problem. **We have not measured outcomes from Wet Lab Bench itself.**

### 6.1 Access and equity: research capacity is concentrated, and equipment is a direct barrier
- **Global:** G20 countries account for 93.2% of research spending and 88.8% of researchers ([Science|Business summary of UNESCO Science Report 2021, secondary](https://sciencebusiness.net/news/number-scientists-worldwide-reaches-88m-global-research-spending-grows-faster-economy)). Sub-Saharan Africa accounts for about 0.42% of global R&D spending and about 0.7% of researchers ([NACOSTI summary of UNESCO SR 2021, secondary/government body](https://www.nacosti.go.ke/2021/06/21/countries-spend-less-than-1-of-gdp-on-research/)). *Verify against current UIS data before quoting, because these are 2014–2018 figures.*
- **US:** the top 20 universities account for 31% of academic R&D ([SSTI analysis of NSF HERD FY2024, secondary](https://ssti.org/node/90464)). HBCUs received 0.91% of federal higher-ed R&D in FY2023, although they are about 3.2% of four-year institutions ([Center for American Progress, think tank](https://www.americanprogress.org/press/release-new-data-reveal-disproportionately-low-rd-funds-awarded-to-hbcus/)).
- **Equipment cost:** a Brazilian researcher described a ~$1M confocal microscope as "almost impossible" to afford in low-income countries. In Chile, a team 3D-printed a fluorescence microscope for ~$250, against ≥$25,000 commercially ([Nature feature 2020, secondary](https://media.nature.com/original/magazine-assets/d41586-020-03193-5/d41586-020-03193-5.pdf)).
- **Savings from open hardware:** Pearce's review found average savings of 87% versus proprietary tools, rising to 94% for Arduino-plus-3D-printing builds, which is our stack ([Pearce's own summary, secondary](https://opensource.com/article/20/10/open-source-hardware-savings); [HardwareX 2020 paper, primary](https://pmc.ncbi.nlm.nih.gov/articles/PMC7480774)).
- **Policy backing:** UNESCO's 2021 Open Science Recommendation was the first policy instrument to include open hardware ([The Turing Way, secondary](https://book.the-turing-way.org/reproducible-research/open/open-hardware); [UNESCO, primary](https://en.unesco.org/science-sustainable-future/open-science/recommendation)). GOSH set the goal of making open science hardware "ubiquitous by 2025" ([GOSH Roadmap, primary](https://openhardware.science/global-open-science-hardware-roadmap/)). *Verify the exact UNESCO wording before quoting it.*
- **Local repair is the lesson that transfers:** OpenFlexure microscopes are built in Tanzania so that "when it breaks, there's someone local who's able to fix it" ([Nature 2020, secondary](https://media.nature.com/original/magazine-assets/d41586-020-03193-5/d41586-020-03193-5.pdf)). Physics World reports a WHO estimate that about 70% of donated medical equipment in sub-Saharan Africa sits unused ([Physics World citing WHO, secondary](https://physicsworld.com/a/high-spec-open-source-microscopy-for-all/)). *Do not quote 70% without checking the WHO source, because other WHO figures put it nearer 40%.*
- **Honest limit:** we found no study of open-automation deployments at US community colleges or MSIs. Low cost also does not mean zero barrier: a team still needs a 3D printer, maker skills, and a safety review.

### 6.2 Accessibility for disabled scientists
- People with disabilities make up about 3% of the STEM workforce ([NSF NCSES 2023, primary/government](https://ncses.nsf.gov/pubs/nsf23315/report/the-stem-workforce)), against about 27% of US adults ([ACS Central Science, Vasquez 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11046470/)). NCSES reports the share was "unchanged" from 2011 to 2021.
- The documented bench barriers are reach, height, fine motor tasks, and standing-only equipment. Benches and fume hoods are too high for seated users, and talking scales and electronic pipettes are named accommodations ([Vasquez 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11046470/)). An RSC survey of 400+ respondents found that more than half of disabled respondents had delays getting adjustments, and some left wet-lab work ([Lab Manager summary of RSC report, secondary](https://www.labmanager.com/royal-society-of-chemistry-report-finds-chemistry-labs-still-exclude-disabled-scientists-34708)).
- **How the bench fits:** a seated operator loads the reagents while the arms do the pouring and mixing. The load-cell stream could be read aloud by text-to-speech, which would give the same function as a "talking scale". Published authors propose automated titration for students with disabilities ([Kosenkov & Kosenkov 2022, NSF PAR](https://par.nsf.gov/servlets/purl/10336803); [Lo et al. 2024, Digital Discovery](https://pubs.rsc.org/en/content/articlehtml/2024/dd/d3dd00223c)), but neither paper tested it with disabled users.
- **Honest limit:** this is a design hypothesis. We found no case study of a disabled researcher whose work was enabled by a robot arm. Co-designing the bench with disabled scientists would be the real test.

### 6.3 Worker safety and ergonomics (adds to Oman/CSB already in §1–5)
- The University of Hawaiʻi explosion in 2016 cost a postdoc her arm during a routine gas-mixing step, and she later received a ~£5M settlement ([Chemistry World, secondary](https://www.chemistryworld.com/news/researcher-severely-injured-in-2016-hawaii-lab-explosion-receives-5-million-settlement/4021833.article)). The investigation estimated ~$716k in infrastructure damage ([UCLA Chemistry summary](https://www.chemistry.ucla.edu/news/craig-merlic-leads-uccls-safety-investigation-university-hawaii-uh/)). The lesson is the same as in the CSB cases: a person was standing at the apparatus during the energetic step.
- Letting the arm initiate the reaction so the operator can stand back is an *engineering control*, which ranks above PPE in the hierarchy of controls.
- **Honest limit:** the best direct evidence comes from robotic chemotherapy compounding, and it is mixed. Robots "did not totally eliminate drug exposure," and pooled contamination rates were not significantly different ([US Pharmacist summary of meta-analysis, secondary](https://www.uspharmacist.com/article/time-for-robotic-compounding-of-cytotoxic-drugs)). The supportable claim is "reduces exposure and repetitive strain", not "eliminates hazard".

### 6.4 Reproducibility and open science
- Closed-loop gravimetric dosing records the mass that was *actually* dispensed, not the commanded amount. This answers the "verification is the bottleneck" theme of the 2026 community roadmap ([Ferreira da Silva et al., arXiv 2607.12113, preprint](https://arxiv.org/abs/2607.12113)).
- The weakness of open hardware is documentation: designs are often under-documented, and data are sometimes available only "on reasonable request" ([Miljković et al. 2021, arXiv preprint](https://arxiv.org/pdf/2109.06045v2)). **Commitment:** publish CAD, BOM, firmware, and calibration data, including dosing error and CV against an analytical balance.

### 6.5 Education
- Low-cost "frugal twin" self-driving labs cost from about $50 to $30k and are already used in courses at U of T, MIT, UChicago, and UH Mānoa ([Lo et al. 2024](https://pubs.rsc.org/en/content/articlehtml/2024/dd/d3dd00223c)). UBC funded an autonomous teaching lab starting April 2026 ([UBC TLEF, university page](https://tlef.ubc.ca/funded-proposals/entry/1034)). U of T students built a self-driving lab for under $500 for an AI course ([Acceleration Consortium, university](https://acceleration.utoronto.ca/news/low-cost-open-source-robotic-system-could-make-self-driving-labs-more-accessible-to-students-and-researchers)).
- **Honest limit:** the evidence on learning outcomes is a 10-student survey that its authors call "by no means statistically sound" ([Kosenkov 2022](https://par.nsf.gov/servlets/purl/10336803)). Present the bench as aligned with where curricula are going, not as proven to improve learning.

## 7. Risks judges will raise, and our answers

**"Won't this take technicians' jobs?"**
- BLS projects chemical technicians to grow 5% over 2025–35 ([BLS, government](https://www.bls.gov/ooh/life-physical-and-social-science/chemical-technicians.htm)) and biological technicians 7% ([BLS](https://www.bls.gov/ooh/life-physical-and-social-science/biological-technicians.htm)). Neither page cites automation as a drag on demand.
- Researchers surveyed about self-driving labs did voice concern for the human role, and some preferred partial automation ([ChemRxiv survey, n=102, preprint; authors not verified](https://chemrxiv.org/engage/chemrxiv/article-details/65e0ce79e9ebbb4db993d6fe)).
- **Answer:** a two-arm, one-recipe bench takes over repetitive weighing and pouring, not jobs. It is pitched for under-resourced labs that have no automation and often no technician, not for cutting headcount. Students who use it also gain automation skills.

**"Couldn't this be misused (dual use)?"**
- The canonical warning is Urbina et al. 2022, in which an inverted toxicity model proposed ~40,000 toxic candidates in under 6 hours ([Nature Machine Intelligence, PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9872092)). *Spot-check this before quoting; the paper was not re-fetched.* The National Academies treat AI plus automated or cloud labs as an emerging risk ([NASEM workshop page](https://www.nationalacademies.org/our-work/artificial-intelligence-and-automated-laboratories-for-biotechnology-leveraging-opportunities-and-mitigating-risks-a-workshop)).
- **Answer, current build:** a fixed, non-reprogrammable, gram-scale recipe using drugstore-class reagents gives no capability a person lacks by hand. The policy literature targets general-purpose, remote, reprogrammable automation.
- **Answer, future LLM feature:** this is where the concern genuinely applies, and we say so. The safeguards are:
  - an **allow-list** validator (deny-lists fail on the unanticipated), written in ordinary code outside the model;
  - human approval of the *compiled action list*, not only the prose protocol;
  - append-only logs;
  - small reservoirs;
  - no remote or unattended runs.

**"Is it physically safe?"**
- Under ISO 10218:2025, safety belongs to the *application* (robot, tool, task, and environment), and the integrator must assess it. No robot is "collaborative by itself" ([EVS vendor summary of the standard, secondary](https://www.evsint.com/?p=9433)). **Do not claim compliance.** Claim that the design is "informed by its risk-assessment approach."
- The chemistry is the main hazard, not the arms. The classic 30% H₂O₂ demo causes immediate burns, the reaction is strongly exothermic (ΔrH° = −196 kJ/mol), and the procedure says to stand back after initiation ([UC Davis/LibreTexts](https://chem.libretexts.org/Courses/University_of_California_Davis/UCDemos/Elephant_Toothpaste)). **Our 12% choice is deliberate safety-by-design.** ACS DCHAS publishes a job hazard analysis for this demo ([DCHAS JHA](https://dev.dchas.org/wp-content/uploads/2020/10/Sigmann-JHA-Elephant-Toothpaste.pdf)).
- The SO-101 arms run on wall adapters ([CNX Software, press](https://www.cnx-software.com/?p=149841)). Our carousel, stage and auger servos run on a 2S LiPo, behind a 10 A fuse and a hardware e-stop that cuts all three ([electrical.md](electrical.md)). Plug it in only with the e-stop pressed, and charge it in a bag, never unattended.
- The most likely real incident is a spill. Today's controls are the e-stop, gram-scale volumes, goggles and gloves. Cheap additions worth making before demo day are a secondary containment tray, a splash shield and a marked no-go zone.
- An e-stop only helps if someone notices the problem. Robotic-chemist research shows that unnoticed small anomalies propagate through a workflow ([PREVENT, arXiv 2510.21438, preprint](https://arxiv.org/abs/2510.21438)), so the load cell doubles as an anomaly sensor.

**"Won't people over-trust it?"**
- This is the best-evidenced risk. Automation bias hits experts and novices alike and "cannot be prevented by training or instructions" ([Parasuraman & Manzey 2010, Human Factors](https://doi.org/10.1177/0018720810376055)). Detectors that raise false positives get ignored ([PREVENT](https://arxiv.org/abs/2510.21438)).
- **Answer:** an approval click alone will become a rubber stamp, so the approval step is designed against complacency:
  - show the diff from the last approved run;
  - list each validator check rather than a green tick;
  - require re-approval whenever a parameter changes;
  - rely on the load cell's physical ground truth rather than the model's claim of success.

  *Note that the automation-bias evidence comes from aviation and medicine, not from labs.*

**"Isn't this more plastic and e-waste?"**
- Research labs produce an estimated ~5.5 Mt of plastic waste a year, a figure extrapolated from a single department ([Exeter release on 2015 Nature correspondence, secondary](https://news-archive.exeter.ac.uk/2015/december/title_488903_en.html)). State the method whenever you quote it.
- **Answer:** washable beakers and auger dosing mean there are no disposable tips per run. Validated tip reuse has cut tips 12-fold, which shows tips are the waste stream worth eliminating ([Berger et al. 2024, DOI](https://doi.org/10.1016/j.diagmicrobio.2024.116241)). Printable parts (~$35) make the bench repairable at component level ([SO-ARM101 repo](https://github.com/uofrobotics/SO-ARM101)).
- **Caveat:** washing glassware costs water and energy, and no life-cycle study compares the two approaches at this scale. The arms will themselves become e-waste eventually.

## 8. Why now: more pitch evidence

- **Market:** estimates put lab automation at roughly **$6–8B and growing 6–9% a year** ([ResearchAndMarkets via Business Wire, market research](https://www.businesswire.com/news/home/20250929897316/en): $6.5B in 2025 at 9.4% CAGR; [IMARC, market research](https://imarcgroup.com/laboratory-automation-market): $7.6B, with ~67% from pharma/biotech). Quote this as a range, because firms define the market differently. We found no public size for the academic or teaching segment.
- **Government momentum:**
  - **US:** Executive Order 14363 ("Genesis Mission", Nov 2025) directs DOE toward AI-directed robotic laboratories ([White House fact sheet, government](https://www.whitehouse.gov/fact-sheets/2025/11/launching-the-genesis-mission/)). DOE then awarded >$320M, including 14 robotics and automated-lab projects ([ExecutiveGov, press](https://www.executivegov.com/articles/doe-investment-genesis-mission-ai)); *confirm this on energy.gov.*
  - **NSF:** the PCL Test Bed offers up to $5M a year for 4 years per award ([UW–Madison research office](https://research.wisc.edu/competition/nsf-25-541-test-bed-toward-a-network-of-programmable-cloud-laboratories-pcl-test-bed)).
  - **UK:** ARIA funded 12 "AI scientist" teams at ~£500k each ([MIT Technology Review, press](https://www.technologyreview.com/2026/01/20/1131462/the-uk-government-is-backing-ai-scientists-that-can-run-their-own-experiments/)).
  - **Canada:** the Acceleration Consortium received $200M CFREF ([U of T Engineering](https://news.engineering.utoronto.ca/self-driving-labs-200-million-federal-grant-powers-ai-driven-materials-discovery-for-clean-energy-advanced-manufacturing-and-more/)).
  - **Contrast:** a single Ginkgo/PNNL autonomous lab costs $47M ([SynBioBeta, press](https://www.synbiobeta.com/read/ginkgo-joins-genesis-project-to-build-a-47-million-autonomous-robot-lab)), against $300 for our bench.
- **LeRobot momentum:**
  - The SO-101 launched in April 2025 from $100 per arm ([TechCrunch, press](https://techcrunch.com/2025/04/28/hugging-face-releases-a-3d-printed-robotic-arm-starting-at-100)).
  - The LeRobot repo has ~28k GitHub stars ([GitHub](https://github.com/huggingface/lerobot)).
  - The June 2025 worldwide hackathon drew >2,500 participants ([Univ. Lille CRIStAL](https://www.cristal.univ-lille.fr/en/news/2025-06-19-982/)).
  - NVIDIA publishes an SO-101 sim-to-real course ([NVIDIA docs](https://docs.nvidia.com/learning/physical-ai/sim-to-real-so-101/latest/04-lerobot.html)).
- **Value of powder dosing:**
  - At AstraZeneca, manual weighing took ~5–10 min per vial, while an entire automated run took under 30 min. Screens rose from ~20–30 to ~50–85 per quarter, and dosing deviation was <1% above 50 mg. AZ spent $1.8M on this equipment ([Trajan/CHRONECT summary of ACS Catalysis 2025, vendor](https://chronect.trajanscimed.com/news/high-throughput-experimentation-hte)). *Confirm against the ACS Catalysis paper.*
  - Open automation has mostly targeted liquids, so open solid dosing appears under-served. *We have not verified this with a review, so say "appears".*
  - **Do not claim sub-mg precision.** Pitch the bench for gram-scale and teaching use, and publish our measured tolerances.

## 9. Ethics statement for the pitch

**Spoken (~30 s):** "Lab automation today is a million-dollar tool for well-funded labs. Wet Lab Bench is about $300 of open parts, so a community college, an HBCU, or a lab in Dar es Salaam can build and repair it. It lets a seated scientist dose and pour, and it keeps hands away from the reaction. It is not built to replace people. It runs one fixed, low-concentration recipe, a human loads every reagent, and a hardware e-stop is always in reach. If we add an LLM later, it will only propose actions. Plain code checks every action against an allow-list, a human approves the exact action list, and the scale verifies what actually happened. These are motivations, not measured outcomes, and we'll publish our calibration data so others can check us."

**Responsible-build commitments (mapped to field guidance):**
1. **Application-level risk assessment** written and published, following the integrator duty in ISO 10218-2:2025 ([EVS summary](https://www.evsint.com/?p=9433)) and the DCHAS demo JHA ([DCHAS](https://dev.dchas.org/wp-content/uploads/2020/10/Sigmann-JHA-Elephant-Toothpaste.pdf)).
2. **Bounded energy and containment:** 12% H₂O₂, small volumes, a containment tray, a splash shield, and the e-stop.
3. **Closed-loop verification:** the load cell checks every dose, following the roadmap's verification priority ([arXiv 2607.12113](https://arxiv.org/abs/2607.12113)).
4. **Append-only logs** of the protocol, the approver, and the actuations, for reproducibility and accountability ([roadmap](https://arxiv.org/abs/2607.12113)).
5. **Allow-list validator outside the model, plus an approval step designed against complacency** (diffs, itemized checks), in response to Urbina et al. and Parasuraman & Manzey.
6. **No remote or unattended execution**, which addresses the main concern about cloud and automated labs ([NASEM](https://www.nationalacademies.org/our-work/artificial-intelligence-and-automated-laboratories-for-biotechnology-leveraging-opportunities-and-mitigating-risks-a-workshop)).
7. **Fully open release**: CAD, BOM, firmware, and calibration and CV data, to address the documentation gap in open hardware ([Miljković et al.](https://arxiv.org/pdf/2109.06045v2)).

## 10. Lines to say / don't say

| Say | Don't say |
|---|---|
| "Augments people; takes the repetitive weighing" | "Replaces lab techs" |
| "Designed to reduce exposure and strain" | "Eliminates lab accidents" / "makes chemistry safe" |
| "Informed by ISO 10218's risk-assessment approach" | "ISO-compliant" / "collaborative robot" |
| "Could help seated and mobility-impaired scientists; a design hypothesis" | "Proven accessible" |
| "Aligned with where SDL teaching is going (U of T, UBC)" | "Proven to improve learning" |
| "Open hardware typically saves 87–94% (Pearce)" | "99% cheaper than a Quantos" (no verified benchmark) |
| "Gram-scale, with published tolerances" | "Matches commercial sub-mg dosing" |
| "Fixed recipe; the LLM is future work behind an allow-list and human approval" | "An AI that runs any protocol" |
| "No disposable tips per run; repairable parts" | "Zero waste" |
| "Estimated ~5.5 Mt/yr lab plastic (2015 extrapolation)" | That figure stated as a measurement |
