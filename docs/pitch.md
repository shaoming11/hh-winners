# Pitch: Wet Lab Bench

Audience: hardware-track judges interested in lab automation. Sources and qualifications for the
market claims are in [motivation.md](motivation.md).

**Status:** This is a pitch for the documented hardware design. The repository does not include
the run-time laptop application or Arduino firmware. Do not present AI protocol generation,
camera checks, automatic experiment selection or lab-notebook logging as working features of this
checkout. Report measured performance only after testing the assembled bench.

## One line

**A low-cost dual-arm bench designed to weigh and transfer a fixed chemistry recipe using ordinary
glassware.**

## The 60-second version

1. **The problem.** Small labs still do much measuring and transferring by hand. Automation can
   improve repeatability and reduce exposure during those steps, but commercial systems can cost
   tens of thousands of dollars and may use specialized labware. See [motivation.md](motivation.md)
   for sourced examples and limits to that comparison.
2. **The design.** Wet Lab Bench combines two open-source SO-101 arms, a load-cell scale, an auger
   for powder and common beakers. The west arm pours liquid onto the scale; the east arm moves
   beakers between the carousel and scale. The auger doses yeast, and the scale checks the dose.
3. **The demo recipe.** The operator loads rough amounts of 12 % hydrogen peroxide, warm water
   and dry yeast, and puts soap and dye in the flask. The bench is designed to weigh 39 g of
   developer, dose about 7 g of yeast, add 30 g of warm water, combine the contents in the flask,
   then move it toward the audience for the eruption.
4. **Why it matters.** The design explores whether weighing, transferring and combining reagents
   can be done with inexpensive arms and ordinary glassware. The dose tolerances in the design
   are targets, not measured results.

## What this project combines

- General-purpose open-source arms with ordinary labware.
- Closed-loop liquid pouring based on scale readings, as designed.
- Auger powder dosing followed by scale verification.
- Offline kinematic and collision planning for the fixed bench layout.

The current demo executes a fixed recipe. The broader idea of turning free-text protocols into
validated actions, measuring the reaction with a camera and keeping an automatic lab notebook is
future software work. The present design does not select experiments or optimize the recipe.

## Numbers to measure on the assembled bench

- **Pour accuracy:** run 10 pours to a target and report mean error and standard deviation.
- **Yeast dose accuracy:** calibrate grams per revolution, then report dose error over repeated
  runs.
- **Full-run time.**
- **Cost:** the final buy list is about $303 before M4 fasteners and VHB add-ons. The two arms are
  borrowed; the cited arm cost is about $122 each if purchased separately.

Until those measurements exist, describe ±2 g for liquids and ±0.7 g for yeast as design targets.

## Likely judge questions

- **"A pump is cheaper for liquids."** A pump may be a better choice for one liquid. This design
  also moves beakers and doses a powder using the same arms and scale.
- **"How accurate is it?"** Give the measured mean error and standard deviation from actual runs.
  If there are no measurements yet, say the target is ±2 g for liquid doses and ±0.7 g for yeast.
- **"What are the limits?"** The design uses 100 mL beakers, a fixed station layout, open vessels
  and preplanned motions. It has no fume containment and is intended for a narrow demonstration.
- **"Does it remove the operator from the chemicals?"** No. The operator loads the reagents and
  handles the flask and cleanup. Wear splash goggles and nitrile gloves for 12 % peroxide.
- **"Is it a self-driving lab?"** No. It runs a fixed demonstration recipe. Experiment selection
  and optimization are outside the current scope.

## Avoid these claims

- The system autonomously plans or optimizes experiments.
- A camera measures foam height or checks beaker placement.
- Every run is automatically logged in a lab notebook.
- The operator has no chemical contact.
- Accuracy figures that have not been measured on the assembled bench.
- "First low-cost lab robot" or "self-driving lab."
