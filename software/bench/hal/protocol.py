"""JSON-line protocol between the laptop and the Arduino Mega (docs/plan_36h.md:35).

One JSON object per line, both directions, 250000 baud.  The sim backend and the firmware
in software/firmware/bench_mega implement exactly this.

Host -> Mega                                   Mega -> host
  {"id":n,"cmd":"ver"}                           {"id":n,"ok":true,"fw":"WLB-MEGA v1","hx_hz":80}
  {"id":n,"cmd":"weight"}                        {"id":n,"ok":true,"g":12.34,"ms":123456}
  {"id":n,"cmd":"stream","on":true}              {"id":n,"ok":true}   then {"w":[ms,g]} at 80 Hz
  {"id":n,"cmd":"carousel","deg":180,"ms":4000}  {"id":n,"ok":true}   then {"done":n}
  {"id":n,"cmd":"stage","deg":150,"ms":2500}     {"id":n,"ok":true}   then {"done":n}
  {"id":n,"cmd":"auger","rev":3.5,"dir":1}       {"id":n,"ok":true}   then {"done":n,"rev":3.5}
  {"id":n,"cmd":"status"}                        {"id":n,"ok":true,"estop":false,"fault":null,
                                                  "carousel_deg":..,"stage_deg":..,"auger_rev":..,
                                                  "busy":[...]}
  {"id":n,"cmd":"stop"}                          {"id":n,"ok":true}   (all PWM off, auger off)
  {"id":n,"cmd":"clr"}                           {"id":n,"ok":true}   (clear a latched fault)
  {"id":n,"cmd":"hb"}                            {"id":n,"ok":true}
Unsolicited:  {"f":"ESTOP"|"AUGER_JAM"|"WDT"|"HX_TIMEOUT"|"TIMEOUT"}   {"i":{"fw":..,"hx_hz":..}}
Errors:       {"id":n,"ok":false,"err":"RANGE"|"BUSY"|"STATE"|"UNKNOWN"|"ESTOP"}

Rules (software_architecture.md 7.3, electrical.md 7): out-of-range values are REJECTED with
RANGE, never clamped; the auger never runs during a carousel/stage move (BUSY); a weight sample
carries the Mega's own millis so the host can compute flow against a stable clock; all taring
is host-side - the Mega reports gross grams.
"""
from __future__ import annotations

import json
import itertools

LIMITS = {
    "carousel": {"deg": (-720.0, 720.0), "ms": (500, 60000)},
    "stage": {"deg": (0.0, 150.0), "ms": (1500, 20000)},
    "auger": {"rev": (-50.0, 50.0)},
}
FAULTS = ("ESTOP", "AUGER_JAM", "WDT", "HX_TIMEOUT", "TIMEOUT")

_ids = itertools.count(1)


def next_id() -> int:
    return next(_ids)


def encode(obj: dict) -> bytes:
    return (json.dumps(obj, separators=(",", ":")) + "\n").encode()


def decode(line: bytes | str) -> dict | None:
    if isinstance(line, bytes):
        line = line.decode(errors="replace")
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return {"junk": line}
    return obj if isinstance(obj, dict) else {"junk": line}


def validate(cmd: dict) -> str | None:
    """Return an error code for a host command, or None if it is acceptable."""
    c = cmd.get("cmd")
    if c in ("carousel", "stage"):
        lim = LIMITS[c]
        if not (lim["deg"][0] <= float(cmd.get("deg", 1e9)) <= lim["deg"][1]):
            return "RANGE"
        if not (lim["ms"][0] <= int(cmd.get("ms", 0)) <= lim["ms"][1]):
            return "RANGE"
    elif c == "auger":
        if not (LIMITS["auger"]["rev"][0] <= float(cmd.get("rev", 1e9)) <= LIMITS["auger"]["rev"][1]):
            return "RANGE"
    elif c not in ("ver", "weight", "stream", "status", "stop", "clr", "hb", "estop_test"):
        return "UNKNOWN"
    return None
