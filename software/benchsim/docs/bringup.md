# Hardware bring-up

How to take the real bench from a bare Mega to a first arm move, with the host commands for every test.
The electrical tests E1–E10 are those of [`docs/electrical.md` §10](../../../docs/electrical.md); this guide adds the
host side and the arm checks A1–A5. Record every measured value where the table says (bench_params.toml `[mega]`,
the firmware defaults, or your calibration JSON), then rerun `hw-check`.

## Rules

- **The default is simulation.** Nothing in benchsim touches hardware unless asked. A command that can drive the
  bench takes `--real --i-understand-this-moves-hardware` (live) or `--real --dry-run` (open and read only); `--real`
  alone is refused (`benchsim.backends.real.add_cli_arguments` / `bench_from_args`). From Python the same choice is
  `make_bench('real', allow_hardware=True, ..., dry_run=False)`; `dry_run=True` is the default.
- **Dry run first.** In dry run the Mega transport refuses every TT/ST/AUG line and the arms refuse every goal and
  torque write (`HardwareOutputDisabled`). Use it for every read-only step below.
- Press the e-stop before plugging in the pack and before flashing or resetting the Mega. Keep a hand near it
  during every powered test (electrical.md 2 and 7): no current sensing protects a stalled M45CHW.
- The flask stays empty until E10 has passed. Arms move only after A1–A4 pass, and only with an operator's explicit
  confirmation.

## 0. Before touching hardware

```bash
cd software/benchsim
uv pip install --python .venv/bin/python -e '.[dev,hardware]'     # pyserial and lerobot (only needed from here on)
.venv/bin/python -m benchsim hw-check                             # offline: must print hw-check: PASS
```

`hw-check` opens no port. It checks the imports, the calibration file schema (`--calibration your.json`), the
firmware constants against bench_params.toml, the firmware host test and protocol parity, and compiles the sketch
when `arduino-cli` is installed. Flash the sketch (firmware/mega/README.md) with the e-stop pressed.

Find the ports: `python -m serial.tools.list_ports -v`. Label the hub ports; the Mega, the pourer arm and the
transfer arm must not be confused (A2 below makes a swap refuse to run).

Snippets below start with:

```python
import time
import numpy as np
from benchsim.backends import real
from benchsim.interfaces import MegaError

PORT = '/dev/ttyUSB0'                       # Windows: 'COM5'
mega, t = real.open_mega(PORT)              # dry run: TT/ST/AUG are refused
# mega, t = real.open_mega(PORT, dry_run=False)   # live: only where a step says so

def raw(seconds=2.0):                       # print every line the Mega sends (do not mix with mega.* calls)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for line in t.read_lines(): print(line)
        time.sleep(0.01)
```

Hand-typed lines also work in a terminal that does not toggle DTR, e.g.
`python -m serial.tools.miniterm --dtr 0 --rts 0 /dev/ttyUSB0 250000`, then type `{"cmd":"PING","seq":1}` (the CRC
field is optional for hand-typed lines). The Arduino IDE serial monitor resets the board when it opens.

After any fault, `CLR` clears it in the firmware; also call `mega.faults.clear()`, because `MegaClient.motion()` raises
on any fault it has seen.

## Electrical tests

| # | Host side | Pass |
|---|---|---|
| E1 | none: continuity with the pack unplugged | electrical.md §2–§3: + to − not shorted, exactly one Mega-GND wire, 10 A fuse fitted, capacitor polarity |
| E2 | USB only. Open the port, then press the Mega reset button: `raw(3)` | One line `{"boot":true,"cal_ok":true,"fw":"wlb-mega 0.1",...}` after the button. **No** boot line when the port is opened (DTR/RTS held low); if one appears, the driver pulses DTR on open. D6/D7/D8 read 0 V on a meter. `mega.command('PING')` returns `ok` with `sim: false` |
| E3 | E-stop pressed, plug in the pack. `mega.command('PING')` | No spark at the e-stop; servos unpowered; PING shows `"estop": true` and `faults` bit 0 set (an `ESTOP` fault line appeared) |
| E4 | none: meter at each arm barrel | Voltage matches the arm variant (electrical.md §8); centre positive |
| E5 | Release the e-stop; send nothing that moves. After 0.5 s: `mega.command('CLR')`, `mega.command('PING')` | Both M45CHW and the auger stay still and turn by hand (no pulses). PING: `estop` false, `faults` 0. If you turned them, re-home before E6 (below) |
| E6 | Live. Re-home, then a slow carousel move, and press the e-stop about 2 s in (snippet E6) | Motion stops at once (the D2 interrupt cuts all PWM); the host gets `MegaError` code `ESTOP`; no `done` for that move; afterwards every command except PING/STOP/CLR/HB and the scale commands (STREAM/TARE/CAL) answers `err ESTOP` until release + 0.5 s + `CLR` |
| E7 | Dry run is enough. 100 samples (snippet E7) | Mean sample interval 12.5 ms ± 1 ms (and PING `hx_ms` ≈ 12.5); after `TARE`, no-load noise std < 0.1 g over 100 samples. If the RATE mod failed: about 100 ms, then fall back to 10 SPS |
| E8 | Live. Auger feedback range, speeds, g/rev, stall rule (snippet E8) | A2 below 5 V on a meter before connecting; ADC min/max recorded; forward and reverse speeds within 10 %; g/rev recorded; a screw held by hand stops within 150 ms, reverses ¼ turn and retries (`done` with `stalls` ≥ 1); held for good → `AUGER_JAM` after 3 stalls |
| E9 | Live. A slow carousel move, then stop the heartbeat (snippet E9); then repeat by unplugging the Mega USB | PWM stops within 0.5 s: `WDT` fault line, servo limp, no `done`. Unplugged: the Mega is USB powered, so PWM stops with it; after replugging and reopening the port, PING shows `"tt": null` (interrupted move) |
| E10 | Live, flask empty. Commission the stage pulses, then WORK ↔ ERUPT (snippet E10) | At `ST 0` and `ST 150` the crank sits at its dead centres (gauge of software_architecture.md 7.4 before the crank is bolted); the sled reaches both ends with no binding, 3 full cycles; `done` each time |

### Homing (after any hand movement or interrupted move)

The firmware keeps the last rest angles in EEPROM and refuses TT/ST for an axis whose position it does not know
(`err STATE "position unknown..."`). With the e-stop released and the servos limp, turn the deck to its 0° mark and
push the stage to WORK by hand, then:

```python
mega.command('CLR', home=True)          # declares deck 0 deg and stage WORK; starts no pulses
print(mega.command('PING'))             # pos: "known", tt 0.0, st 0.0
```

### E6: e-stop during a slow carousel move

```python
mega, t = real.open_mega(PORT, dry_run=False)
mega.command('CLR', home=True)                          # after homing by hand
input('Hand on the e-stop. Press Enter to start a 45 deg move over 8 s, then press the e-stop at about 2 s.')
try:
    mega.motion('TT', done_timeout=12, deg=45.0, ms=8000)
    print('FAIL: the move finished')
except MegaError as e:
    print('stopped by', e.code)                          # pass: ESTOP
try: mega.command('STREAM', on=False)                   # a probe that moves nothing, even if the latch failed
except MegaError as e: print('while latched:', e.code)  # pass: ESTOP
# release the e-stop, home the deck by hand (the move was interrupted), wait 0.5 s:
mega.command('CLR', home=True); mega.faults.clear()     # MegaClient keeps old faults until cleared
```

### E7: HX711 rate and noise

```python
mega.command('STREAM', on=True); mega.command('TARE')
mega.take_samples(); s = []
while len(s) < 100: s += mega.take_samples(); time.sleep(0.02)   # keep reading: do not let the port buffer fill
s = s[:100]; dt = np.diff([x['t'] for x in s]); w = np.array([x['w'] for x in s])
print('interval %.2f ms, PING hx_ms %.2f, noise std %.3f g' % (dt.mean(), mega.command('PING')['hx_ms'], w.std()))
mega.command('STREAM', on=False)
```

Scale calibration then uses the 100 g class M2 weight: `counts_per_g = (raw with weight − raw tared) / 100`,
send it with `mega.command('CAL', counts_per_g=k)` and record it in bench_params.toml `[scale] counts_per_g` (and in
`default_config()` so the board boots with it).

### E8: auger

Feedback range (servo powered, no pulses: the e-stop released, nothing commanded). Turn the screw slowly by hand
through two full turns while polling:

```python
adc = []
end = time.monotonic() + 20
while time.monotonic() < end: adc.append(mega.command('PING')['adc']); time.sleep(0.05)
print('A2 min %d max %d' % (min(adc), max(adc)))       # the wrap point is where it jumps from max to min
```

Record `aug_fb_adc_min`/`aug_fb_adc_max` in bench_params.toml `[mega]` and in `default_config()`, rebuild, run
`hw-check`, reflash. Feedback that rises with the dosing direction gives `aug_fb_sign = 1`; if a dose counts
backwards (immediate stalls, `AUGER_JAM`), flip it.

Speeds and the stop centre. The firmware never sends the stop pulse; the output is off when the auger is idle. The
stop centre therefore only balances the two directions:

```python
mega, t = real.open_mega(PORT, dry_run=False)
for d in (1, -1):
    t0 = time.monotonic(); r = mega.motion('AUG', done_timeout=20, rev=2.0, dir=d)
    print('dir %+d: %.2f s for 2 rev + 1/4 reverse, stalls %d' % (d, time.monotonic() - t0, r['stalls']))
```

If the two times differ by more than 10 %, move `aug_us_stop` toward the slower direction by a few µs, rebuild, repeat.

g/rev: tare a cup under the outlet (on the scale pan), dose 10 rev three times, `g_per_rev = mean(grams) / 10`;
record it in bench_params.toml `[auger] g_per_rev_nominal`.

Stall rule, gently (the Ø8 PLA hub of DH-02 is the part being protected):

```python
# motion() keeps the heartbeat going while it waits; never block in input() during a dose (the watchdog fires)
input('Enter starts a 5 rev dose (6 s). Hold the screw by hand for about half a second, then let go.')
print(mega.motion('AUG', done_timeout=30, rev=5.0, dir=1))      # pass: stalls >= 1, rev ~5.0
input('Enter starts another dose. Hold the screw until the firmware gives up.')
try: mega.motion('AUG', done_timeout=30, rev=5.0, dir=1); print('FAIL: no jam')
except MegaError as e: print(e.code)                             # pass: AUGER_JAM after 3 stalls
mega.command('CLR'); mega.faults.clear()
```

### E9: host-link watchdog

```python
mega, t = real.open_mega(PORT, dry_run=False)
mega.keepalive = False                                  # MegaClient stops sending HB while it waits
seq = mega.send('TT', deg=30.0, ms=8000); mega.wait(seq, key=('ack',))
time.sleep(0.7); mega._pump()
print([f['fault'] for f in mega.faults])                # pass: ['WDT']; the deck stops and goes limp
mega.keepalive = True
```

The move was interrupted, so home the deck, then `mega.command('CLR', home=True); mega.faults.clear()` before the
next move.

### E10: stage

Before the crank is bolted, check the pulses with the printed gauge (software_architecture.md 7.4): `ST 0` and
`ST 150` must put the horn at the WORK and ERUPT marks. Adjust `st_us_at_zero`/`st_us_per_deg` in bench_params.toml
`[mega]` and `default_config()`, rebuild, `hw-check`, reflash. The carousel pockets get the same treatment at
`TT 0/90/180/270` (`tt_us_at_zero`/`tt_us_per_deg`). Then, with the crank bolted and the flask empty:

```python
mega, t = real.open_mega(PORT, dry_run=False)
mega.command('CLR', home=True)                          # stage at WORK, deck at 0, by hand
for _ in range(3):
    print(mega.motion('ST', done_timeout=8, deg=150.0, ms=2500))   # ERUPT
    print(mega.motion('ST', done_timeout=8, deg=0.0, ms=2500))     # WORK
```

## Arm checks

Each SO-101 follower is a LeRobot Feetech bus. benchsim reads and writes raw registers (`normalize=False`) and
maps ticks to the MJCF joint angles with the calibration JSON. Start from a copy of
`benchsim/config/hardware_calibration.example.json` (every value in it is a placeholder) and pass its path
everywhere below as `CAL`.

| # | Check | Pass |
|---|---|---|
| A1 | LeRobot calibration of each follower, with LeRobot's own tool: `lerobot-calibrate --robot.type=so101_follower --robot.port=PORT --robot.id=wlb_pourer` (and `wlb_transfer`) | LeRobot finishes its range recording; the id is the calibration JSON's `lerobot_id` |
| A2 | Identity: read each arm's fingerprint in dry run and write it into `CAL` (snippet A2); then swap the two port names | Swapped ports raise `ArmIdentityError`; correct ports connect with no fingerprint warning |
| A3 | Read-only positions and loads with torque off: move each joint by hand (snippet A3) | Each joint's sign matches the simulator (`python -m benchsim view`); loads near 0 at rest, change sign with the push direction. Hold the arm in the MJCF zero pose and record each joint's raw `tick_at_zero`; gripper closed/open ticks |
| A4 | Limits: narrow `min_deg`/`max_deg` to the bench's safe range; `hw-check --calibration CAL` | `hw-check` PASS; the limits are inside the MJCF ranges |
| A5 | One slow joint move, only after the operator confirms (snippet A5) | Torque enables without a snap; the joint moves 5° at 10 % speed and back; `read_positions` within `goal_tolerance_deg` of the goal |

### A2: fingerprint

```python
import json
CAL = 'my_calibration.json'
bb = real.make_real_bench(port_pourer='/dev/ttyACM0', port_transfer='/dev/ttyACM1', calibration_path=CAL)   # dry run
cal = json.load(open(CAL))
for name, arm in bb.arms.items(): cal['arms'][name]['fingerprint'] = arm.read_fingerprint()
bb.close(); json.dump(cal, open(CAL, 'w'), indent=2)
```

### A3: read-only positions and loads

```python
bb = real.make_real_bench(port_pourer='/dev/ttyACM0', calibration_path=CAL)       # dry run: no writes at all
a = bb.arms['pourer']; print(a.torque_enabled(), bb.warnings)                     # torque should be off
for _ in range(100):
    print(np.round(np.degrees(a.read_positions()), 1), a.read_loads(), a.read_ticks()); time.sleep(0.1)
bb.close()
```

### A5: first move (live, one arm, operator confirmation)

```python
from benchsim.bench import make_bench
bb = make_bench('real', allow_hardware=True, port_pourer='/dev/ttyACM0', calibration_path=CAL, dry_run=False)
a = bb.arms['pourer']                                   # connect() left torque OFF: the arm is limp
q0 = a.read_positions(); goal = q0.copy(); goal[0] += np.radians(5.0)    # shoulder_pan +5 deg
a.check_goal(goal)                                      # ValueError if outside the calibrated limits
if input('Arm clear, hand on its power plug. Type MOVE to enable torque and move shoulder_pan 5 deg: ') == 'MOVE':
    a.set_torque(True)                                  # Goal_Position = Present_Position first: no snap
    a.set_goal(goal, speed_scale=0.1)
    while a.is_moving(): time.sleep(0.05)
    print('error %.2f deg' % np.degrees(abs(a.read_positions()[0] - goal[0])))
    a.set_goal(q0, speed_scale=0.1)
    while a.is_moving(): time.sleep(0.05)
input('Support the arm, then press Enter to disable torque')
a.set_torque(False); bb.close()                         # disconnect alone never disables torque
```

`disconnect()` deliberately leaves torque as it is, so an arm holding a beaker does not drop it
(software_architecture.md 2.2). Unplugging an arm's adapter is the last resort: the arm drops what it holds.

## Where things are recorded

| Value | Where |
|---|---|
| Mega pulses, auger stop/offset/signs/feedback range, settle time | bench_params.toml `[mega]` **and** `firmware/mega/wlb_mega/protocol_core.cpp` `default_config()`; `hw-check` fails if they differ |
| Scale counts/g, auger g/rev | bench_params.toml `[scale] counts_per_g`, `[auger] g_per_rev_nominal` (and the firmware default for counts/g) |
| Arm ticks, signs, limits, fingerprints, speeds | your copy of `hardware_calibration.example.json` (schema `benchsim.hardware_calibration/1`) |
