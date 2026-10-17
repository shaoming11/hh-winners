# Precedents and benefits: who has done this before, and what it buys you

Researched 2026-10-17. Companion to [motivation.md](motivation.md) (cost + prior art table) and
[manifesto.md](manifesto.md) (thesis + script). This file adds two things for the pitch: a **story
of people who automated the lab before us**, and **measured evidence for the benefits** (human
error, time, strain, reproducibility, access). Same house rule: every number has a link, and
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
