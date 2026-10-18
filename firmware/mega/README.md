# Mega firmware (`wlb_mega`)

Arduino Mega 2560 (Pro) firmware for the bench mechanisms: carousel and stage M45CHW servos, the FB5311M-360
auger with its feedback wire, the HX711 scale and the e-stop sense line. It speaks the JSON-lines protocol of
[`software/benchsim/benchsim/protocol.py`](../../software/benchsim/benchsim/protocol.py), so the host program
cannot tell it from the simulated Mega (`benchsim.backends.sim.SimMega`), apart from the differences listed below.

| File | Contents |
|---|---|
| `wlb_mega/wlb_mega.ino` | Platform layer only: pins, Timer4 PWM, HX711 bit-bang, A2 ADC, D2 interrupt, EEPROM |
| `wlb_mega/protocol_core.{h,cpp}` | Everything else, in plain C++11 with no Arduino headers: CRC-8, flat-JSON parser, `protocol.validate` logic, replies, faults, motion profiles, auger stall rule |
| `host_test/test_protocol_core.cpp` | Host test: built-in checks, a script interpreter driven by lines from `benchsim.protocol.encode`, `--dump-config`, `--live` (real-time loop over stdin/stdout) |

No external libraries. `EEPROM.h` is part of the Arduino AVR core.

## Build, test, flash

Host test (no Arduino tools needed; this is what `python -m benchsim hw-check` and
`tests/test_firmware_core.py` run):

```bash
cd software/benchsim
.venv/bin/python -m benchsim hw-check              # compiles the core with c++/clang++/g++ and runs the script
.venv/bin/python -m pytest -q tests/test_firmware_core.py
# by hand:
c++ -std=c++11 -Wall -Wextra -fsanitize=address,undefined -o /tmp/tpc \
    ../../firmware/mega/host_test/test_protocol_core.cpp ../../firmware/mega/wlb_mega/protocol_core.cpp
/tmp/tpc                                           # built-in checks only
/tmp/tpc --dump-config                             # compiled-in constants
```

Board build (not run in this checkout: `arduino-cli` and avr-gcc were not installed; `hw-check` records it as SKIP):

```bash
arduino-cli core install arduino:avr               # once, needs network
arduino-cli compile --fqbn arduino:avr:mega:cpu=atmega2560 firmware/mega/wlb_mega
arduino-cli upload  --fqbn arduino:avr:mega:cpu=atmega2560 -p /dev/ttyUSB0 firmware/mega/wlb_mega
```

**No e-stop (default).** The bench runs without an e-stop: D2 is ignored and unplugging the pack is the only
stop. To use one again, wire an NC contact from D2 to GND and build with the flag below; then an open D2 latches
`ESTOP` as described in electrical.md.

```bash
arduino-cli compile --fqbn arduino:avr:mega:cpu=atmega2560 --build-property "build.extra_flags=-DWLB_USE_ESTOP" \
    --build-path /tmp/wlb_estop firmware/mega/wlb_mega
```

**Unplug the pack before flashing or resetting the board**: without the relay, servo power is live whenever the
pack is plugged in.

## Pins and timers (electrical.md 4)

| Pin | AVR | Use |
|---|---|---|
| D2 | PE4 / INT4 | E-stop pole 2, `INPUT_PULLUP`, NC to GND. Rising edge: the interrupt disconnects all three compare outputs and drives D6/D7/D8 LOW at once; the core then latches `ESTOP` |
| D31 | PC6 | HX711 DOUT, read on `PINC` (moved D3 → D11 → D31 to fit the bench wiring) |
| D4 | PG5 | HX711 SCK on `PORTG`; 25 pulses (channel A, gain 128) with interrupts off for about 25 µs |
| D6 / D7 / D8 | PH3/OC4A, PH4/OC4B, PH5/OC4C | Carousel, stage, auger. Timer4 mode 14, prescaler 8, `ICR4 = 39999` (50 Hz), `OCR4x = 2 × µs`. No Servo library |
| A2 | PF2 / ADC2 | Auger feedback, AVcc reference |
| USB | CH340G | 250000 baud. The host opens it with `dtr=False`, `rts=False` |

Boot: D6/D7/D8 are driven LOW from `.init3` (before the C runtime and `setup()`), and again in `setup()`. Timer4
runs with its compare outputs disconnected. A compare output is connected only when the core asks for a pulse,
and only at the next frame start (`TIMER4_OVF`), so the first pulse is never truncated. Nothing pulses until the
host sends TT, ST or AUG. During the bootloader (before `.init3`) the pins are inputs; the e-stop rule covers that.

## Behaviour

- **Protocol.** As `protocol.py`: commands `PING TT ST AUG TARE CAL STREAM STOP CLR HB`; replies ack/ok/done/err; the
  same error codes and the same check order (`protocol.validate`, then the order of `SimMega.handle`). Out-of-range
  values are rejected, never clamped. Output lines are compact with sorted keys and the trailing CRC field; the
  host test checks that every line passes `protocol.decode`.
- **Boot line.** `{"boot":true,"cal_ok":...,"fw":"wlb-mega 0.1","pos":"known|unknown","st":..,"t":..,"tt":..}`.
  `MegaClient` ignores it; bring-up E2 looks for it.
- **Carousel and stage (TT/ST).** Smoothstep in microseconds from the rest pulse to the target pulse over `ms`.
  Pulse = `us_at_zero + us_per_deg × deg`. The M45CHW has no position feedback, so `done` is sent when the
  profile has ended plus `settle_ms`, and reports the commanded angle. After `done` the servo keeps its pulse
  (holds).
- **Position knowledge.** The rest angle of each axis is kept in EEPROM, with a moving flag set during a move.
  At boot with no valid record, or after a move was interrupted (e-stop, watchdog, timeout, reset), that axis is
  *unknown* and TT/ST answer `err STATE`. Recovery: put the deck at its 0° mark and the stage at WORK by hand, then
  send `{"cmd":"CLR","seq":n,"home":true}` (needs the e-stop released). Plain `CLR` does not home. `home` is an
  extra key that `protocol.validate` and `SimMega` ignore.
- **Auger timed mode (bench default since 2026-10-17).** The A2 feedback wire is not fitted, so `aug_timed = 1`: the
  firmware counts progress as `aug_rev_per_s` x driving time, credits `aug_coast_rev` (the coast after the stop pulse)
  at the start, and has no stall rule. Fitted on the bench by eye: turns = 0.37 x s + 0.19. The anti-dribble reverse
  is off (`reverse_rev = 0`). Set `aug_timed = false` in bench_params.toml and the firmware default to go back to the
  feedback mode below once the wire is fitted.
- **Auger (AUG).** Pulse `aug_us_stop ± aug_us_offset` (sign from `dir` and `aug_dir_sign`); D8 is off at all other
  times. Revolutions are counted by unwrapping the A2 angle. The dosed count is the high-water mark of net progress
  in the commanded direction. A reading that jumps more than `aug_fb_max_step_deg` between two loop passes is
  treated as a glitch and ignored; after `aug_fb_glitch_resync` glitches in a row the reading is taken as the new
  reference without counting. Stall rule (electrical.md 6): less than 5° of progress in 150 ms → reverse ¼ turn,
  retry; the 3rd stall → `AUGER_JAM`. After the target is reached: reverse ¼ turn, then `done` with `rev` and
  `stalls`. Progress `{"aug","seq","t"}` at 5 Hz while dosing. `AUG_TIMEOUT` after `dose_timeout_s`.
- **Scale.** The HX711 is polled every loop and read when DOUT goes LOW. While streaming, each conversion is sent as
  `{"raw","t","w"}`. TARE replies after the mean of the next 8 conversions. The ready interval is measured
  (exponential average) and reported as `hx_ms` in PING. `HX_TIMEOUT` when no conversion arrives within
  max(100 ms, 4 × measured interval) while streaming or taring.
- **Faults.** Latched until `CLR`. `ESTOP`, `WDT` and the motion timeouts switch every output off (servos limp).
  Every fault stops the auger. `AUGER_JAM` and `HX_TIMEOUT` leave a held carousel/stage pulse on. While any fault is
  latched, TT/ST/AUG answer `err STATE`; with `ESTOP` latched everything except PING, STOP, CLR, HB and the
  scale commands (STREAM, TARE, CAL, which move nothing) answers `err ESTOP`. `CLR` clears `ESTOP` only after D2 has read LOW for `estop_release_ms`. `HOPPER_EMPTY` is a host-side
  rule and is never raised here.
- **Comm watchdog.** During TT/ST/AUG, no valid line for 500 ms → `WDT`. While idle the servos keep holding.
- **PING** adds `adc` (last A2 reading), `estop` (D2 state), `faults` (bit mask in `protocol.FAULTS` order), `hx_ms`,
  `pos`, `tt`, `st` (null when unknown) for bring-up.

## Constants and calibration

The compiled-in values are in `default_config()` in `protocol_core.cpp`. Each one mirrors
`software/benchsim/benchsim/config/bench_params.toml` (`[carousel] [stage] [auger] [scale]`, and `[mega]` for the
firmware-only values) or a constant of `protocol.validate`. `hw-check` and `tests/test_firmware_core.py` fail if
any differs. To change one, edit both, rebuild, run `hw-check`, reflash.

Values that are **assumed** until bring-up (see `[mega]` in bench_params.toml):

| Value | Default | Measured at |
|---|---|---|
| Carousel pulse `tt_us_at_zero`, `tt_us_per_deg` | 569.0 µs, 6.897 µs/° (deck range −10…280° over 500–2500 µs) | E10 / deck alignment |
| Stage pulse `st_us_at_zero`, `st_us_per_deg` | 944.4 µs, 7.407 µs/° (crank 75° at 1500 µs) | E10 / crank gauge (software_architecture.md 7.4) |
| Servo pulse range | 500–2500 µs | M45CHW datasheet check |
| `settle_ms` | 150 ms | E10 (time from profile end to standstill) |
| Auger stop centre and offset | 1500 ± 200 µs (software_architecture.md 6) | E8 |
| Auger signs, feedback ADC range | +1, +1, 0–1023 | E8 |
| Glitch gate | 45°, 20 passes | E8 (feedback dead band) |

If the deck range does not fit the servo's pulse range, `cal_ok` in the boot line is false and TT targets outside
the pulse range answer `err RANGE`.

## Differences from the simulated Mega

These are deliberate. The host test and `tests/test_firmware_core.py` hold both implementations to one shared
script; the lines below are the `fw`-only parts of it.

1. TT/ST are open loop: `done` comes `settle_ms` after the profile and reports the commanded angle. SimMega reports
   the measured angle once within 0.6°. `TT_TIMEOUT`/`ST_TIMEOUT` therefore cannot catch a stalled M45CHW here; the
   e-stop is the protection (electrical.md 7).
2. Position knowledge and `CLR home` (above). SimMega always knows where the deck and stage are.
3. After a limp fault and `CLR`, outputs stay off until the next TT/ST for that axis; SimMega re-enables both servos
   holding at `CLR`. An axis that was never commanded since boot gets no pulses at all.
4. Auger: the stall rule also applies while reversing; the count is the high-water mark of net progress. SimMega
   counts gross forward rotation, so after a stall-reverse it counts the re-covered quarter turn again and the net
   rotation at `done` is about 0.25 rev short per stall. The jam and hand-held-screw scenarios behave the same in
   both (3 stalls → `AUGER_JAM`; one held stall → `done` with `stalls` 1–2).
5. `TARE` while a tare is pending answers `err STATE` (SimMega replaces the pending tare and never answers the
   first). `HX_TIMEOUT` is also watched during a pending tare, which then gets `err STATE`.
6. `CLR` of `ESTOP` needs D2 LOW for 500 ms (SimMega: released at that moment).
7. Flat JSON only: at most 10 keys, keys and string values of at most 15 characters, lines of at most 160 characters,
   `seq` within int32. Nested values, `NaN`/`Infinity` and non-ASCII `\u` escapes answer `err BADCMD`. Python's
   `json` accepts some of these. An error reply to a non-integer `seq` carries `seq -1`; SimMega echoes the value.
8. Extra keys in replies (PING, the boot line). `MegaClient` ignores unknown keys.

## What has and has not been verified

Verified on the host (macOS, Apple clang, ASan/UBSan): the core compiles without warnings; 371 host-test checks
pass (CRC against `protocol.crc8`, 190 validation vectors against `protocol.decode/validate`, the shared scenarios,
the firmware-only cases above, safety invariants on every simulated millisecond). Every output line decodes with
`protocol.decode`. The sketch compiles against stub AVR registers and its register logic (boot state, Timer4 setup,
connect-at-frame-start, D2 cut-off, EEPROM record) passes a smoke test. `MegaClient` over `SerialTransport` works
against the core running in real time.

Not verified: an avr-gcc build, timing on the board (loop period, HX711 clocking, PWM jitter; take the 10 min
logic-analyser capture of software_architecture.md 7.1), the M45CHW and FB5311M-360 behaviour, the real A2 feedback
range and dead band, and EEPROM write blocking (about 3.4 ms per changed byte, so a few ms at the start and end of
each move). The AVR hardware watchdog is not enabled (software_architecture.md 7.6: only after a deliberate WDT
reset has been shown to work with this board's bootloader).
