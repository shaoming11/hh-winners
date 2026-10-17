"""Carousel, stage and auger through the Mega link (electrical.md 6-7, software_architecture.md 7).

Each call sends one JSON command, then waits for the matching {"done": id} while keeping the
weight stream flowing (so the scale filter never goes stale), with the commanded duration + 2 s
as its timeout.  Faults raise BenchFault.
"""
from __future__ import annotations

import math

from bench.config import Config, load
from bench.hal.base import Bench, BenchFault
from bench.hal import protocol


class Mechanisms:
    def __init__(self, bench: Bench, cfg: Config | None = None, log=print):
        self.b = bench
        self.cfg = cfg or load()
        self.log = log
        self.pad = float(self.cfg.at("control.carousel.timeout_pad_s"))
        self.carousel_deg = 0.0
        self._stream = None

    # ---------------------------------------------------------------- plumbing
    def _send(self, obj: dict) -> int:
        obj = dict(obj, id=protocol.next_id())
        rep = self.b.mega.command(obj)
        if not rep.get("ok"):
            raise BenchFault(f"Mega rejected {obj['cmd']}: {rep.get('err')}")
        return obj["id"]

    def _wait_done(self, cid: int, timeout: float) -> dict:
        if self._stream is None:
            self._stream = self.b.mega.samples()
        t0 = self.b.clock.now()
        while self.b.clock.now() - t0 < timeout:
            msg = next(self._stream)
            if msg.get("done") == cid:
                return msg
            if "f" in msg:
                raise BenchFault(f"Mega fault {msg['f']}")
        self._send({"cmd": "stop"})
        raise BenchFault(f"Mega command {cid} did not complete in {timeout:.1f} s")

    def status(self) -> dict:
        return self.b.mega.command({"cmd": "status", "id": protocol.next_id()})

    # ---------------------------------------------------------------- carousel
    def carousel_to(self, deg: float) -> None:
        """Index the carousel to an absolute deck angle, at >= 2 s per 45 deg."""
        delta = abs((deg - self.carousel_deg + 180) % 360 - 180)
        ms = int(max(delta / 45.0 * self.cfg.at("control.carousel.min_s_per_45deg"), 0.8) * 1000)
        self.log(f"  carousel -> {deg:.0f} deg ({delta:.0f} deg, {ms/1000:.1f} s)")
        cid = self._send({"cmd": "carousel", "deg": float(deg), "ms": ms})
        self._wait_done(cid, ms / 1000 + self.pad)
        self.carousel_deg = deg

    # ---------------------------------------------------------------- stage
    def stage_to(self, position: str) -> None:
        deg = 0.0 if position == "WORK" else float(self.cfg.at("stations.stage.erupt_crank_deg"))
        ms = int(float(self.cfg.at("stations.stage.move_s")) * 1000)
        self.log(f"  stage -> {position} (crank {deg:.0f} deg, {ms/1000:.1f} s)")
        cid = self._send({"cmd": "stage", "deg": deg, "ms": ms})
        self._wait_done(cid, ms / 1000 + self.pad)

    # ---------------------------------------------------------------- auger
    def auger(self, revolutions: float) -> float:
        """Run the auger `revolutions` turns (negative = reverse). Returns turns done."""
        a = self.cfg.at("control.auger")
        if abs(revolutions) > a["max_rev"]:
            raise BenchFault(f"auger {revolutions} rev exceeds the {a['max_rev']} rev limit")
        d = 1 if revolutions >= 0 else -1
        cid = self._send({"cmd": "auger", "rev": abs(float(revolutions)), "dir": d})
        secs = abs(revolutions) / float(a["rev_per_s"])
        msg = self._wait_done(cid, min(secs + 3.0, float(a["dose_timeout_s"])))
        return float(msg.get("rev", abs(revolutions))) * d

    def stop(self) -> None:
        self._send({"cmd": "stop"})
