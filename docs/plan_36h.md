# 36-hour build plan

**Assumed window:** Fri 7 pm → Sun 7 am. If the real start differs, shift every time. Times are also given as hours from the start (H+x).

**Team:**

| Person | Main role | Focus |
|---|---|---|
| **Nick** | software | arms: SO-101 bring-up, calibration, motion playback |
| **Nehal** | software | bench firmware (Mega: scale, servos, e-stop) + AI layer (LLM protocol + lab notebook) |
| **Shao** | software / mechatronics | frame + station assembly first night, then the run sequencer + closed-loop pour |
| **Jerry** | hardware | gripper, auger, carousel, stage, wiring. **Away 7:30–11 pm Fri**, so the others start on the arms, firmware and frame. |

Read first: [demo_process.md](demo_process.md) (walkthrough), [print_list.md](print_list.md), [electrical.md](electrical.md), [pitch.md](pitch.md).

**Deliveries:** most of the Amazon order arrives Thursday. The **peroxide arrives Friday** and the **100 mL beakers Saturday**. Until the beakers arrive, use the printed dummy beakers (or borrowed ones).

---

## Fri 7–11 pm (H+0 → H+4): Jerry away; start where software people are strongest
**Nick: arms**
1. Install LeRobot. Set the servo IDs, then calibrate **both SO-101s** (pourer = west, transfer = east).
2. Check each joint's real range against `tools/layout/urdf_limits.py`. **Write down any joint that can't reach its range.**
3. Play back the verified joint paths (`tools/layout/anim_paths.json`, from the Update 13 plan) **in the air, slowly (25 % speed)**, with nothing on the table.

**Nehal: Mega firmware**
1. **Scale:**
   - HX711 + 1 kg load cell on the bench, tare, calibrate with **20 nickels = 100.0 g**.
   - Read at 80 Hz with a median filter; target noise ≤ 0.1 g.
2. **Servos:**
   - Drive the carousel M45CHW and the stage M45CHW with smooth S-curves.
   - Run the auger FB5311M-360 continuous, and count revolutions from its feedback wire.
3. **E-stop:** pole 2 into D2, latches a fault.
4. **Serial protocol** to the laptop: one JSON line per command and reply, e.g. `{"cmd":"tare"}`, `{"cmd":"weight"}` → `{"g":39.12}`, `{"cmd":"carousel","deg":90}`, `{"cmd":"auger","rev":3.5}`.

**Shao: frame and stations, using the printed jigs** (no tape measure; every part locates off the extrusions)
1. Build the frame with the corner brackets, X rails **+74 mm** north.
   - The gap blocks set the spacing: **JG-01** (E6 → front X rail, 122 mm) and **JG-02** (front → back X rail, 50 mm).
   - **JG-03** sets E6 and stage rail S1, and **JG-10** sets S2. **If the jigs weren't printed,** cut scrap to 122 mm and 50 mm, and use a 7 mm hex key as the S2/scale gauge.
2. Bolt the **arm bases** to the X rails. **JG-04** and **JG-05** set their position along the rail.
3. **Scale:** WS-01 saddle on **E6**, **JG-06 (7 mm)** from S2. Load cell and WS-02 pan on top, plus the stop screw.
4. **Rack:** **RK-04 tie plate** bolted into the Y-left rail's west slot. **JG-08** sets it from the rail's south end. Then drop the **3 RK-03 stands** into its rings.
5. **Carousel + auger unit:** **TT-05 tie plate** bolted into the Y-right rail's east slot, positioned with **JG-07**. TT-01 sits in its pocket and E5 in its slot.

**Go/no-go at 11 pm:** both arms calibrated and moving through the waypoints in the air; the scale reads grams; all 3 servos move on command; the frame is up.

## Fri 11 pm–Sat 3 am (H+4 → H+8): Jerry back, mechanical assembly
**Jerry:**
1. **Grippers:**
   - TPU fin-ray fingers onto the GR-01/GR-02 tongues, clamped with M3x16 + nuts + Loctite.
   - Mount them on both arms in place of the stock jaws.
2. **Auger:**
   - Drill the DH-02 flange holes to Ø3.2.
   - Clean the support mark at the top of the seal area in DH-01.
   - Fix the horn to DH-02 with **M3x6**, then sand the flange rim (240 grit) while spinning it on the servo.
   - Mount it on PS-01 (+25 mm post) and E5.
3. **Carousel:**
   - Lazy Susan bearing with VHB on both faces between TT-01 and TT-02.
   - TT-03 spacer to the horn with M3x12.
   - TT-04 ring onto the deck with 4 × M4x10 as locating pins.
4. **Stage:**
   - F625ZZ bearings pressed into ST-14.
   - Crank on the horn with M3x8; the sled pin is M5x25 + nut.
   - Test the slide by hand, and sand the sled tabs if it's tight.
5. **Wiring** (see [electrical.md](electrical.md)): LiPo → XT60 lead with 10 A fuse → 2200 µF capacitor → e-stop pole 1 → Wago lever nuts → 3 servos. Mega powered from the laptop's USB.

**Shao:** help Jerry, then calibrate the station positions with **CAL-02** (the probe) in each arm's gripper. Record any offset per station.

**Nick:** with the stations in place, run **pick/place with dummy beakers**:
- transfer arm (east): carousel ↔ scale, gripping from the top
- pourer (west): rack → scale and scale → funnel, gripping from the side

Adjust station offsets by hand-jogging and save them as named poses.

**Nehal:** start the **AI layer** (see below).

**Go/no-go at 3 am:** every pick and place works with dummy beakers, and nothing collides.

## Sat 3 am–9 am (H+8 → H+14): sleep in shifts (2 people on, 2 off)
- Dry runs of the whole sequence with **water** in dummy or borrowed beakers. Check the **pour-stop logic** and the auger with dry yeast into an empty beaker.

## Sat 9 am–3 pm (H+14 → H+20): make it work, then measure it
**Shao + Nick: closed-loop pour**
- The pourer tilts at a set rate while the Mega streams weight.
- It slows within 5 g of the target, and stops by tilting back at the target minus the expected drip.
- Run **10 pours to 39 g** and record the mean ± SD. That's the pitch number.

**Jerry:** calibrate the **auger** (g per revolution with real yeast, 5 runs), add a ¼–½ turn reverse after each dose, and tidy the cables.

**Nehal:** LLM protocol + lab notebook + camera check working end to end with the bench.

**Go/no-go at 3 pm:** a full water run with **no human touches**, plus the pour-accuracy numbers.

## Sat 3 pm–10 pm (H+20 → H+27): real reagents
**When:** after the **beakers arrive Saturday**. Wear goggles and gloves.
- 2–3 **full runs with 12 % peroxide**. Record **backup video** of the best run.
- Fix whatever breaks. Keep a written list of failure modes and the fix for each.

## Sat 10 pm–Sun 4 am (H+27 → H+33): pitch and polish
- Slides: problem, solution, demo, numbers, impact, limits. Use [pitch.md](pitch.md).
- Demo script with a fixed order of operations, plus a reset checklist (rinse the flask, refill beakers, new yeast).
- Sleep in shifts.

## Sun 4–7 am (H+33 → H+36): rehearse
- Full run + pitch, timed, twice. Charge the LiPo. Stage the backup video.

---

## The AI layer (Nehal, with Nick helping)
Make it simple, reliable and visible to the judges:
1. **Protocol → steps (LLM).**
   - A text box takes e.g. "Make elephant toothpaste: 39 g of 12 % peroxide, 7 g yeast, 30 g warm water."
   - The Claude API (model `claude-sonnet-5-5`) returns **JSON using only our step vocabulary**: `dose_liquid(reagent, grams)`, `dose_powder(grams)`, `transfer(src, dst)`, `pour_into_funnel(beaker)`, `carousel_to(pocket)`, `run_stage()`.
2. **Validator (plain code, no AI).**
   - Rejects unknown reagents, out-of-range amounts (e.g. peroxide ≤ 45 g, yeast ≤ 10 g), and steps the bench can't do.
   - Shows the plan, and **the operator presses Approve** before anything moves.
3. **Camera check (OpenCV + a USB webcam).** Before each pick, check that a beaker is present in the target pocket (simple colour/contour test, or fill level if time allows). If one is missing, pause and ask.
4. **Lab-notebook record.** Each run writes a JSON + web page: the protocol text, the approved plan, the target vs **actual mass** of every dose, timestamps, camera snapshots and the operator. This is the reproducibility proof for judges.
5. **Fallback:** preset protocol buttons, if the API or Wi-Fi is down.

## If something fails (decide fast)

| Failure | Fallback |
|---|---|
| A pour keeps missing or spilling | Grip lower or higher (30/40 mm) and raise the lip; slow the tilt. Last resort: the arm places the reagent beaker and the operator pours while the scale stops them (still weighed and logged) |
| An arm dies | The other arm can't reach every station; run the steps it can reach live, and show the backup video for the rest |
| The auger jams | Clean the bore and reverse; pre-weighed yeast in P2 as a fallback |
| The stage binds | Sand the sled tabs or grease them; the eruption still works without the stage moving |
| The LLM or Wi-Fi is down | Preset buttons (the notebook still logs) |

## Safety (everyone)
- Goggles + nitrile gloves whenever peroxide is open.
- **Press the e-stop before plugging in the LiPo or flashing the Mega.**
- Keep the LiPo in its bag when charging.
- Have a hand on the e-stop during every run.
