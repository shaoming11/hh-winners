# Pitch: Wet Lab Bench

Audience: hardware-track judges who score **impact**. Our users are **small research labs** and anyone who handles **hazardous reagents**.
The sources for every number are in [motivation.md](motivation.md).

## One line
**"Type the protocol, step back: two $120 open-source robot arms weigh out every reagent, mix it in your own glassware, and write the lab-notebook entry for you."**

## The 60-second version
1. **The problem.** In most small labs, a person still weighs and pours every reagent by hand. That is slow and error-prone, and it puts a human next to the hazard. Nearly half of the researchers in a 2,400-person survey had been injured in a lab.
   - Automation that doses by weight exists, but it costs **$10k–$100k+** (Opentrons from $10k, Chemspeed-class powder dosing $100k+) and locks you into vendor consumables.
   - Cheap pumps only handle liquids, and every reagent needs its own plumbing.
2. **Our answer.** Wet Lab Bench uses **two open-source SO-101 arms (about $120 each in parts), a $10 load cell and the lab's own beakers**.
   - You type the protocol in plain English, e.g. "39 g of 12 % peroxide, 7 g of yeast, 30 g of warm water".
   - An LLM turns it into the bench's steps. A deterministic safety check limits it to supported actions, reagents and amounts.
   - The arms **pour by weight in a closed loop**, an auger **doses powder**, and a camera **checks each beaker is in place** before every pick.
   - Every actual mass, time and photo goes into an **automatic lab-notebook record**.
3. **Live demo.** We put rough amounts in, and the bench measures 12 % hydrogen peroxide (a serious eye hazard), yeast and water by weight, combines them, and pushes the flask out for the eruption. Nobody touches the reagents.
4. **Why it matters.**
   - **Safety:** the person is away from the hazard for the whole measure, transfer and mix.
   - **Reproducibility:** every dose is weighed and logged, not eyeballed against beaker markings that are only good to about ±5 %.
   - **Access:** a few hundred dollars instead of tens of thousands. It uses ordinary glassware, and the same hardware runs a new protocol from new text, with no re-plumbing.

## What is new (said honestly)
- Low-cost lab robots, standard-glassware automation, robotic pouring by weight and robotic powder weighing **each exist separately**.
- **What we combine:** general-purpose $120 open-source arms, gravimetric closed loop for liquids and powders, ordinary glassware, protocols written in natural language, and an automatic lab-notebook record.
- We found no published system that does all of this.

## Numbers to measure at the event (they make the pitch credible)
- **Pour accuracy:** 10 pours to a target, reporting the mean ± standard deviation in grams. Until we measure it, don't quote it.
- **Yeast dose accuracy:** g/rev calibration, then the error.
- **Full-run time.**
- **Cost:** about $300 in new parts plus two arms at about $122 each.

## Likely judge questions
- **"A $30 pump does liquids better."** Yes, for one liquid. A pump can't pick up glassware, dose a powder, or run a different protocol without re-plumbing. The arms do all three with one setup.
- **"How accurate is it?"** Give the measured mean ± SD from the event. The design target is ±2 g on 39 g, and the scale noise is 0.05–0.1 g.
- **"What are the limits?"**
  - 100 mL beakers of water-like liquids.
  - A fixed bench layout: stations are located by printed jigs.
  - Open vessels, with no fume containment.
  - Preprogrammed motions; the LLM chooses steps, it doesn't invent motions.
  - Limited speed.
- **"Is it safe to let an LLM run chemistry?"** The LLM only proposes a step list. A hard-coded validator checks each step against the bench's allowed reagents, amounts and stations, and the operator approves the plan before the arms move. There is a hardware e-stop.

## Don't say
- "first low-cost lab robot"
- "no human contact" (the operator loads the beakers)
- "self-driving lab" (it doesn't plan experiments)
- "burns skin" (say "serious eye damage")
- any accuracy number we haven't measured
