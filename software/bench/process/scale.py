"""Scale processing on the host (software_architecture.md 5.1, 4.4).

The Mega streams gross grams at 80 Hz with its own millis.  Everything else is here:
host-side tare, a 0.5 s rolling least-squares line fit giving the filtered mass m_f and the
flow estimate q_hat, a 5-sigma outlier gate, settle detection and first-drop detection.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from bench.config import Config, load
from bench.hal.base import Bench, BenchFault


@dataclass
class ScaleState:
    t_ms: int = 0
    raw_g: float = 0.0
    m_f: float = 0.0           # filtered net mass (g)
    q_hat: float = 0.0         # flow (g/s)
    sigma: float = 0.0         # residual std of the window (g)
    n: int = 0


class Scale:
    def __init__(self, bench: Bench, cfg: Config | None = None):
        self.b = bench
        self.cfg = cfg or load()
        c = self.cfg.at("control.scale")
        self.rate = float(c["rate_hz"])
        self.window_s = float(c["lsq_window_s"])
        self.gate = float(c["outlier_sigma"])
        self.settle_sigma = float(c["settle_sigma_g"])
        self.settle_window = float(c["settle_window_s"])
        self.tare_g = 0.0
        self.buf: deque[tuple[float, float]] = deque(maxlen=int(self.rate * 1.0) + 2)
        self.state = ScaleState()
        self._stream = None
        self.rejected = 0

    # ---------------------------------------------------------------- sampling
    def _iter(self):
        if self._stream is None:
            self._stream = self.b.mega.samples()
        return self._stream

    def next(self) -> ScaleState:
        """Block for the next weight sample (advancing sim time), fold it in, return state.
        Fault lines from the Mega raise BenchFault; completion notices are ignored here."""
        it = self._iter()
        while True:
            msg = next(it)
            if "w" in msg:
                ms, g = msg["w"]
                self._push(ms / 1000.0, float(g))
                return self.state
            if "f" in msg:
                raise BenchFault(f"Mega fault {msg['f']}")
            # {"done":..} or {"i":..}: not ours

    def _push(self, t: float, raw: float) -> None:
        net = raw - self.tare_g
        if len(self.buf) >= 8 and self.state.sigma > 1e-6:
            # gate on the current fit's prediction
            pred = self.state.m_f + self.state.q_hat * (t - self.buf[-1][0])
            if abs(net - pred) > self.gate * max(self.state.sigma, 0.05):
                self.rejected += 1
                if self.rejected < 4:           # a burst of "outliers" is a real step: let it in
                    return
                self.buf.clear()                # it was a step: restart the fit at the new level
        self.rejected = 0
        self.buf.append((t, net))
        self._fit(t)
        self.state.t_ms = int(t * 1000); self.state.raw_g = raw

    def _fit(self, t_now: float) -> None:
        pts = [(t, g) for t, g in self.buf if t_now - t <= self.window_s]
        self.state.n = len(pts)
        if len(pts) < 3:
            self.state.m_f = pts[-1][1] if pts else 0.0
            self.state.q_hat = 0.0
            return
        ts = np.array([p[0] for p in pts]) - t_now
        gs = np.array([p[1] for p in pts])
        A = np.vstack([ts, np.ones_like(ts)]).T
        (slope, icpt), *_ = np.linalg.lstsq(A, gs, rcond=None)
        resid = gs - (slope * ts + icpt)
        self.state.q_hat = float(slope)
        self.state.m_f = float(icpt)              # the fit evaluated at "now"
        self.state.sigma = float(np.std(resid))

    # ---------------------------------------------------------------- operations
    def tare(self, seconds: float = 0.5) -> float:
        """Host-side tare on a quiet pan: average `seconds` of raw samples.  The fit and its
        outlier gate are reset FIRST - the pan contents just changed, so the old fit would
        reject the new level as outliers and leak stale raw values into the average."""
        self.b.mega.flush()
        self.buf.clear(); self.state = ScaleState(); self.rejected = 0
        raws = []
        n = int(seconds * self.rate)
        for _ in range(n):
            s = self.next()
            raws.append(s.raw_g)
        self.tare_g = float(np.mean(raws))
        self.buf.clear(); self.state = ScaleState()
        return self.tare_g

    def wait_settled(self, timeout: float | None = None) -> float:
        """Wait until the window is quiet (sigma < 0.05 g over 0.5 s); return m_f."""
        timeout = timeout if timeout is not None else float(self.cfg.at("control.scale.settle_timeout_s"))
        self.b.mega.flush()
        self.buf.clear(); self.state = ScaleState(); self.rejected = 0
        t0 = self.b.clock.now()
        while self.b.clock.now() - t0 < timeout:
            s = self.next()
            if s.n >= int(self.settle_window * self.rate * 0.8) and s.sigma < self.settle_sigma \
                    and abs(s.q_hat) < 0.3:
                return s.m_f
        return self.state.m_f

    def read_settled(self, seconds: float = 0.6) -> float:
        """Average of a settled window - the number that goes in the notebook."""
        self.wait_settled()
        vals = [self.next().m_f for _ in range(int(seconds * self.rate))]
        return float(np.mean(vals))

    def reset_fit(self) -> None:
        self.b.mega.flush()
        self.buf.clear(); self.state = ScaleState(); self.rejected = 0
