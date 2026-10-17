"""JSON-lines protocol shared by the simulated Mega and the Arduino Mega firmware (250000 baud, docs/electrical.md 4).

One JSON object per line, UTF-8, '\\n' terminated. The body is compact JSON with sorted keys; the CRC-8/ATM
(poly 0x07) of that exact body text is appended as a final field, so every line ends ``,"crc":"xx"}`` and a
receiver checks the CRC on the bytes it received (no re-serialisation; the firmware strips the last 13 characters
and appends '}'). The same codec is used by the simulator transport and the serial transport, so a host program
cannot tell them apart.

Host -> Mega commands (``cmd`` plus a host sequence number ``seq``):

    PING                              identity            -> {"seq", "ok": true, "fw": "...", "sim": bool}
    TT   {"deg": a, "ms": t}          carousel deck angle, smoothstep over t ms   (ack, then done)
    ST   {"deg": a, "ms": t}          stage crank angle (0 = WORK, 150 = ERUPT)   (ack, then done)
    AUG  {"rev": r, "dir": +-1}       auger revolutions counted on the feedback wire (ack, progress, done)
    TARE                              zero the scale at the current reading       (ok)
    CAL  {"counts_per_g": k}          scale calibration                           (ok)
    STREAM {"on": bool}               start / stop the 80 Hz scale sample stream  (ok)
    STOP                              stop the auger, hold both servos where they are (ok; always accepted)
    CLR                               clear latched faults; ESTOP only once the e-stop is released (ok | err STATE)
    HB                                heartbeat for the 500 ms comm watchdog      (no reply)

Mega -> host:

    {"seq", "ack": true}                                  command accepted
    {"seq", "ok": true, ...}                              immediate command done
    {"seq", "done": true, "cmd", ...}                     TT / ST / AUG finished
    {"seq", "err": CODE, "detail": "..."}                 rejected; codes below. Never silently clamped.
    {"w": grams, "raw": counts, "t": ms}                  scale sample (80 Hz while streaming)
    {"aug": revs_done, "seq", "t": ms}                    auger progress (5 Hz while dosing)
    {"fault": CODE, "t": ms, ...}                         latched fault; codes below

Error codes: BADCMD (unknown command or malformed), RANGE (value outside the firmware limits), BUSY (a carousel,
stage or auger motion is running; the auger never runs during a servo move), STATE (not allowed now), ESTOP (an
e-stop fault is latched), CRC.
Fault codes: ESTOP, AUGER_JAM, HOPPER_EMPTY, HX_TIMEOUT, WDT (comm watchdog), TT_TIMEOUT, ST_TIMEOUT, AUG_TIMEOUT.
"""
import json

ERR = ('BADCMD', 'RANGE', 'BUSY', 'STATE', 'ESTOP', 'CRC')
FAULTS = ('ESTOP', 'AUGER_JAM', 'HOPPER_EMPTY', 'HX_TIMEOUT', 'WDT', 'TT_TIMEOUT', 'ST_TIMEOUT', 'AUG_TIMEOUT')
MOTION = ('TT', 'ST', 'AUG')


class ProtocolError(ValueError):
    def __init__(self, code, detail=''):
        super().__init__('%s %s' % (code, detail)); self.code = code; self.detail = detail


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
        for _ in range(8): c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


CRC_TAIL = len(',"crc":"00"}')


def encode(msg: dict) -> str:
    body = json.dumps({k: v for k, v in msg.items() if k != 'crc'}, separators=(',', ':'), sort_keys=True)
    return body[:-1] + ',"crc":"%02x"}\n' % crc8(body.encode())


def decode(line: str) -> dict:
    line = line.strip()
    if line.endswith('"}') and line[-CRC_TAIL:].startswith(',"crc":"'):
        body = line[:-CRC_TAIL] + '}'; crc = line[-CRC_TAIL + 8:-2]
        if '%02x' % crc8(body.encode()) != crc.lower(): raise ProtocolError('CRC', 'got %s' % crc)
    else:
        body = line                                   # CRC is optional for hand-typed bench commands
    try: msg = json.loads(body)
    except json.JSONDecodeError as e: raise ProtocolError('BADCMD', 'not JSON: %s' % e)
    if not isinstance(msg, dict): raise ProtocolError('BADCMD', 'not an object')
    return msg


class Limits:
    """firmware motion limits; the simulator and firmware both load them from bench_params.toml values"""

    def __init__(self, params):
        C, S, A = params['carousel'], params['stage'], params['auger']
        self.tt_deg = tuple(C['deck_range_deg']); self.tt_ms_per_45 = C['min_s_per_45deg'] * 1000
        self.st_deg = (min(S['work_deg'], S['erupt_deg']) - 2.0, max(S['work_deg'], S['erupt_deg']) + 2.0)
        self.st_ms_min = 2000.0; self.aug_rev_max = A['max_revs']


def validate(cmd: dict, lim: Limits, current=None):
    """raise ProtocolError for a malformed or out-of-range command; ``current`` = dict(tt_deg, st_deg) for duration
    checks. Returns the command name."""
    name = cmd.get('cmd')
    if not isinstance(cmd.get('seq'), int): raise ProtocolError('BADCMD', 'missing integer seq')
    num = lambda k: isinstance(cmd.get(k), (int, float)) and not isinstance(cmd.get(k), bool)
    if name in ('PING', 'TARE', 'STOP', 'CLR', 'HB'): return name
    if name == 'STREAM':
        if not isinstance(cmd.get('on'), bool): raise ProtocolError('BADCMD', 'STREAM needs on: bool')
        return name
    if name == 'CAL':
        if not num('counts_per_g') or not 10 <= cmd['counts_per_g'] <= 10000: raise ProtocolError('RANGE', 'counts_per_g')
        return name
    if name in ('TT', 'ST'):
        if not (num('deg') and num('ms')): raise ProtocolError('BADCMD', '%s needs deg and ms' % name)
        lo, hi = lim.tt_deg if name == 'TT' else lim.st_deg
        if not lo <= cmd['deg'] <= hi: raise ProtocolError('RANGE', '%s deg %.1f outside [%.1f, %.1f]' % (name, cmd['deg'], lo, hi))
        if name == 'TT':
            span = abs(cmd['deg'] - (current or {}).get('tt_deg', cmd['deg']))
            need = lim.tt_ms_per_45 * span / 45.0
            if cmd['ms'] < need - 50: raise ProtocolError('RANGE', 'TT %.0f deg needs >= %.0f ms' % (span, need))
        elif cmd['ms'] < lim.st_ms_min: raise ProtocolError('RANGE', 'ST needs >= %.0f ms' % lim.st_ms_min)
        return name
    if name == 'AUG':
        if not num('rev') or cmd.get('dir') not in (1, -1): raise ProtocolError('BADCMD', 'AUG needs rev and dir +-1')
        if not 0 < cmd['rev'] <= lim.aug_rev_max: raise ProtocolError('RANGE', 'AUG rev %.2f outside (0, %.0f]' % (cmd['rev'], lim.aug_rev_max))
        return name
    raise ProtocolError('BADCMD', 'unknown command %r' % name)
