# Electrical design (final, simplified)

Status: final, 2026-10-15. This file is the single source for the bench electrics.

**What changed from the post-CDR design (v2, 2026-10-14).** The electrics were simplified to cut
cost. These are **dropped**:
- the relay (D25);
- the INA226 current/voltage monitor and its 10 mΩ shunt (D20/D21);
- the WORK/ERUPT Hall sensors and magnets (D26/D27);
- the A1 servo-bus divider;
- the three 3 A branch fuses and holders;
- the 470 µF capacitor at the stage plug.

The CDR-41/42/46 sections of `review/records/cdr_ruling.md` and the matching parts of
`docs/electrical_block.svg` and `docs/software_architecture.md` are superseded by this file.
**What stays:** the firmware stall detection on the auger feedback wire, plus timeouts.

How the electrics serve the run: [demo_process.md](demo_process.md). Parts and links:
[../bom/BOM_final.md](../bom/BOM_final.md).

---

## 1. Overview

| Domain | Source | Loads | Protection |
|---|---|---|---|
| Servo power | 2S LiPo → XT60 lead with 10 A blade fuse → 2200 µF → e-stop pole 1 → WAGO distribution | Carousel M45CHW, stage M45CHW, auger FB5311M-360 | 10 A main fuse (wiring), e-stop, firmware stall rule and timeouts |
| Bench logic | **Laptop USB** | Arduino Mega 2560 Pro, HX711 | Laptop USB port |
| Arms | Each SO-101 on its own power adapter (supplied with the arms) | 2 × SO-101 follower (6 × STS3215 each) | Adapter; host-side voltage check |

---

## 2. Power path

```
2S LiPo ─ XT60 lead with inline 10 A blade fuse ─┬─ e-stop pole 1 (NC) ─ + WAGO ─┬─ carousel M45CHW  (signal D6)
                                                  │                               ├─ stage M45CHW     (signal D7)
                                           2200 µF 16 V                           └─ auger FB5311M-360 (signal D8, feedback A2)
                                                  │
                                              − WAGO ─────────────── servo − (all three) ─── ONE wire ─── Mega GND
```

| # | Element | Spec | Why |
|---|---|---|---|
| 1 | Pack | 2S LiPo, 7.4 V nominal, 8.4 V full (owned). Standard 4.20 V/cell balance charge, never LiHV | Both servo types are rated to 8.4 V, so they run straight off the pack |
| 2 | XT60 lead with inline blade-fuse holder | **10 A** blade fuse | One part gives the pack connector and the main fuse. The fuse protects the wiring; it does not protect a stalled servo |
| 3 | Bulk capacitor | **2200 µF 16 V** across + and −, right after the fuse | Holds the bus up during servo current peaks so nothing browns out. It sits **upstream of the e-stop**, so the e-stop contacts never switch its inrush; the connect spark lands on the XT60 |
| 4 | E-stop | 22 mm latching mushroom with **2 NC contacts**, in the ABS project box | **Pole 1** is in series with servo +: pressing it cuts power to all three servos, whatever the firmware does. **Pole 2** goes to Mega **D2** |
| 5 | Distribution | **WAGO lever nuts**: one for +, one for − | No soldering. One 5-way + nut feeds the three servo leads |
| 6 | Servo leads | 100 cm servo extensions where a lead needs to reach | Twist each signal with its own − |

Use the heaviest owned wire (16 AWG or thicker preferred) from the pack through the fuse,
capacitor and e-stop to the + WAGO, and back on the − side.

### Behaviour without a relay

With the relay gone, **servo power is live whenever the pack is plugged in and the e-stop is
released**, including while the Mega boots or is being flashed. The firmware holds D6/D7/D8 LOW
at boot, so the servos get no pulse. Operating rule:
- **Press the e-stop in before plugging in the pack, and before flashing or resetting the Mega.**
- Release it only when the host has connected and the firmware has initialised the servo
  positions.
- At bring-up, confirm that each M45CHW stays limp when it is powered with no pulse (test E5).

---

## 3. Ground

- One − WAGO is the star. The LiPo −, the 2200 µF −, and all three servo − leads land on it.
- **Exactly one** wire goes from the − WAGO to Mega GND. Do not add a second one.
- On Mega GND only: the HX711 and e-stop pole 2.
- The auger feedback (A2) is read against Mega GND while the auger's current returns through the
  star, so a small offset appears under load. The stall rule uses angle **progress**, not absolute
  angle, so a steady offset doesn't matter.
- The arms are electrically separate from the pack. They share only the laptop's USB ground.

---

## 4. Pin table (Arduino Mega 2560 Pro)

| Pin | AVR | Function | Configuration |
|---|---|---|---|
| D2 | PE4 / INT4 | E-stop pole 2 sense | INPUT_PULLUP, interrupt. NC contact to GND. HIGH (pressed or wire broken) latches the e-stop fault and stops all PWM |
| D11 | PB5 | HX711 DT | Direct port read (moved from D3 on 2026-10-17 to fit the existing wiring) |
| D4 | PG5 | HX711 SCK | Direct port write; interrupts off only for the 25–27 clock pulses |
| D6 | PH3 / OC4A | Carousel servo PWM | Timer4, 50 Hz (ICR4 = 39999, prescaler 8), OCR4A = 2 × µs. No Servo library. LOW at boot |
| D7 | PH4 / OC4B | Stage servo PWM | Timer4, same frame. LOW at boot |
| D8 | PH5 / OC4C | Auger servo PWM (FB5311M-360) | Timer4, same frame. About 1500 µs = stop (measure the exact centre); speed and direction from the offset. LOW with the output off except while dosing |
| A2 | PF2 / ADC2 | Auger servo position feedback (4th wire) | ADC, AVcc reference. Analog angle over 360°, used to count revolutions and detect stalls. **Check that it stays below 5 V before connecting** |
| USB | CH340G | Host serial to the laptop | 250000 baud. Open with `dtr=False`, `rts=False` so opening the port doesn't reset the board |

Freed by the simplification: D20/D21 (INA226), D25 (relay), D26/D27 (Halls), A1 (bus divider).

---

## 5. Load cell and HX711

- **Hardware:** 1 kg aluminium bar load cell + HX711 board (bought as a set).
- **Mounting:** one end of the cell is clamped to WS-01 v4 and the WS-02 v3 pan sits on the other,
  M4 at both ends. Only the cell's ends touch plastic, so the thin middle section bends freely.
- **80 SPS mod:** cut the HX711's RATE pin (pin 15) from GND and tie it to pin 16. Check that the
  ready interval is about 12.5 ms. If the mod fails, fall back to 10 SPS with slower pours.
- **Wiring:** keep the HX711 cable at least 50 mm from the servo leads, and cross them at 90°.
- **Expected noise:** about 0.05–0.1 g at 80 SPS. The software tares before every measurement.

---

## 6. Auger drive and stall detection (kept)

- **Actuator:** Feetech FB5311M-360 (owned), continuous rotation with analog position feedback.
  It runs on 4–8.4 V, so it is fed straight from the servo bus. About 0.3–0.6 A running and 1.7 A
  at stall (datasheet, 6 V).
- **Mechanics:** 25T aluminium disc horn → DH-02 v4 screw flange (4 × M3 × 6) inside DH-01 v5, on
  the PS-01 v2 post.
- **Dosing:** by revolutions counted from the feedback, times a calibrated g/rev. A first pass of
  about 85 % of the target, then the scale verifies, then at most 2 small top-ups. Reverse ¼ turn
  after each dose so the yeast doesn't dribble.
- **Stall rule (mandatory):** while the auger is commanded to turn, if the feedback angle advances
  **less than 5° in 150 ms**: stop, reverse ¼ turn, retry. After **3 stalls**, fault (auger jam).
  Reason: at full stall the servo can twist the Ø8 PLA hub of DH-02.
- **Hopper empty:** if 10 revolutions add less than 1 g, fault.
- **Sequencing:** the auger never runs during a carousel or stage move.

---

## 7. Timeouts and faults (firmware and host)

With no current sensor, timeouts are the protection for the M45CHW servos.

| Check | Action |
|---|---|
| Auger stall (§6) | Stop, reverse, retry; 3 stalls → fault |
| Auger dose takes longer than its time limit | Stop the auger, fault |
| HX711 sends no data within max(100 ms, 4 × measured interval) | Stop the auger and any pour, fault |
| Host link silent for 500 ms (comm watchdog) | Stop all PWM (servos go limp) |
| E-stop pole 2 open (D2 HIGH) | Latch the e-stop fault and stop all PWM. To re-arm: release the e-stop, then reset from the host |
| Carousel or stage move: commanded time exceeded | Stop PWM, fault |

**What is no longer detected** (because the INA226 and Halls are gone):
- A stalled M45CHW is not seen by current. A stall can draw about 6.8 A. That is under the 10 A
  fuse, so the fuse will not save the servo. **Protection is the e-stop: keep a hand near it**
  during bring-up and demos.
- The stage end position is not sensed. The crank's dead centres put the sled exactly at WORK
  and ERUPT, so this only matters if the horn slips on its spline.
- Pack voltage is not monitored. Check the pack with the charger or a multimeter before each
  session; recharge below about 7.4 V resting (3.7 V/cell).

---

## 8. Arms

- Each SO-101 follower has 6 Feetech STS3215 servos on a bus-servo board with a 5.5 × 2.1 mm barrel
  jack. Use the power adapters supplied with the arms.
- **The adapter voltage must match the motor variant** (7.4 V motors on 5 V, 12 V motors on 12 V).
  Check each barrel with a multimeter before first power-on.
- The e-stop does **not** cut the arms. On an e-stop, the host stops the arms and holds the beaker
  upright. Unplugging an arm's adapter is the last resort: the arm goes limp and drops what it
  holds.
- Arm USB runs to the laptop. Leave a service loop at each base so the pan can sweep fully.

---

## 9. Wiring list

| # | From | To | Wire | Notes |
|---|---|---|---|---|
| W1 | LiPo | XT60 lead with 10 A fuse | As bought | Plug in only with the e-stop pressed |
| W2 | Fuse output (+) | 2200 µF + and e-stop pole 1 in | Heavy owned wire | Watch the capacitor polarity |
| W3 | E-stop pole 1 out | + WAGO | Heavy owned wire | |
| W4 | + WAGO | Carousel, stage, auger servo + | Servo lead / 100 cm extension | |
| W5 | Servo − (all three), LiPo −, 2200 µF − | − WAGO (star) | Heavy owned wire / servo lead | |
| W6 | − WAGO | Mega GND | One thin wire | **The only one** |
| W7 | Servo signals | D6 (carousel), D7 (stage), D8 (auger) | Servo lead | Twisted with its own − |
| W8 | Auger feedback | A2 | Servo lead | Twisted with the auger − |
| W9 | E-stop pole 2 | D2 and Mega GND | Twisted pair | |
| W10 | HX711 DT / SCK / VCC / GND | D11 / D4 / 5 V / GND | 4 wires, twisted | ≥ 50 mm from servo leads |
| W11 | Mega USB | Laptop | USB cable (owned) | Confirm the board's connector type |

The e-stop and the electronics sit in the ABS project box, which keeps foam and liquid off them.
Put the box where the operator can reach the e-stop.

---

## 10. Bring-up tests

Run in this order. Record measured values in `config.yaml`.

| # | Test | Pass |
|---|---|---|
| E1 | Continuity, pack unplugged: + to − not shorted, one Mega-GND wire, 10 A fuse fitted, capacitor polarity | As §2–§3 |
| E2 | USB only: Mega boots, D6/D7/D8 LOW | Boot banner seen |
| E3 | E-stop pressed, plug in the pack | No spark at the e-stop; servos unpowered |
| E4 | Arm adapters at the barrel | Voltage matches the arm variant; centre-positive |
| E5 | Release the e-stop with no pulses | Both M45CHW and the auger stay still and can be turned by hand |
| E6 | E-stop during a slow carousel move | Motion stops at once; host shows the e-stop fault |
| E7 | HX711 80 SPS | Ready interval about 12.5 ms; no-load noise < 0.1 g over 100 samples |
| E8 | Auger: stop centre, feedback range, g/rev, stall rule | Feedback max < 5 V; a screw held by hand stops within 150 ms, reverses ¼ turn and retries; 3 stalls → fault |
| E9 | Host-link watchdog: unplug USB during a slow move | PWM stops within 0.5 s |
| E10 | Stage: WORK ↔ ERUPT at the commissioning pulses | Sled reaches both ends at the crank dead centres; no binding |

---

## 11. LiPo handling

- Standard 4.20 V/cell balance charge, never LiHV. Charge in a LiPo bag and never unattended.
- Plug the pack in only with the e-stop pressed.
- Travel: under 100 Wh, terminals taped, carry-on only.
