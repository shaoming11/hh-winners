"""Yeast auger dosing model for the simulated bench (analytic; not a granular-flow simulation).

``AugerModel`` hangs on ``SimMega.aug_hooks``: the simulated Mega calls it every physics step with the signed
revolutions the screw turned in that step. Approximations (parameters in bench_params.toml [auger], [auger_model]):

- Grams per revolution are constant within one revolution of new screw travel and drawn independently for each
  revolution from a normal distribution with mean ``g_per_rev_nominal * true_over_nominal`` and coefficient of
  variation ``g_per_rev_cv``, clipped at 0. The model has its own seeded RNG, so doses do not depend on the scale noise.
- Yeast leaves only on new forward travel. The model follows the net screw angle (``SimMega.aug_angle``) and dispenses
  past its high-water mark. A reverse returns nothing to the hopper; this covers the 1/4-turn anti-dribble reverse,
  the stall-rule reverse and an AUG with dir -1. The forward travel that re-covers a reverse dispenses nothing
  (``recover_dispenses = false``). With ``true``, every forward revolution dispenses.
- Never more than the hopper vessel holds (``ledger.take('hopper', g)``).
- Spilled yeast is buffered and passed to ``ledger.spill`` once per completed revolution and when the AUG ends (the
  ledger rounds each spill record to 0.1 mg, so per-step records would lose about 2 % of the spill).
- Landing: the yeast falls straight down from the 'auger_outlet' site instantly (the ~0.15 s fall is ignored). It lands
  in the beaker whose opening contains the whole outlet: the opening is a horizontal disc at the beaker's lip site,
  below the outlet, and the outlet's horizontal distance from the beaker axis must be < inner radius - outlet radius.
  Otherwise the yeast goes to ``ledger.spill``.
- Hopper empty (electrical.md 6): if the last ``hopper_window_rev`` forward revolutions dispensed less than
  ``hopper_empty_g_per_10rev`` (scaled to the window), the model raises the Mega fault HOPPER_EMPTY. The real Mega
  cannot weigh, so on the hardware the host applies this rule from scale readings (``mechanisms.Mechanisms.dose_yeast``
  also does).

    ledger = Ledger(bb.world)
    auger = AugerModel(bb.world, bb.mega_device, ledger, seed=0)
    auger.fill(40.0)                                 # grams of yeast into the hopper vessel
"""
import collections
import math

import numpy as np

from ..units import mm
from .vessels import BEAKERS

EPS_REV = 1e-9                  # revolutions; less travel than this is round-off of the integrated screw angle


class AugerModel:
    def __init__(self, world, mega, ledger, seed=0, params=None):
        P = params or world.P; A = P['auger']; M = P['auger_model']; B = P['beaker']
        self.w = world; self.mega = mega; self.ledger = ledger; self.rng = np.random.default_rng(seed)
        self.g_per_rev = A['g_per_rev_nominal'] * M['true_over_nominal']; self.cv = A['g_per_rev_cv']
        self.recover_dispenses = bool(M['recover_dispenses'])
        self.window = int(M['hopper_window_rev']); self.empty_g = A['hopper_empty_g_per_10rev'] * self.window / 10.0
        self.open_r = B['od'] / 2 - B['wall'] - A['outlet_d'] / 2        # outlet axis must sit this close to the beaker axis
        self.outlet = world.m.site('auger_outlet').id
        self.lips = {bk: world.m.site('beaker_%s_lip' % bk).id for bk in BEAKERS}
        self.net = 0.0                                   # integrated hook revolutions (used if the Mega has no aug_angle)
        self.a0 = self._angle(); self.travel = 0.0       # dispensing travel (rev) past the start angle: high-water mark
        self.rev_k = None; self.g_k = 0.0; self.draws = []    # revolution index of the current g/rev draw, its value, all draws
        self.fwd_frac = 0.0; self.fwd_g = 0.0            # open forward revolution: fraction done, grams so far
        self.recent = collections.deque(maxlen=self.window); self.rev_grams = []   # grams per completed forward revolution
        self.forward_rev = 0.0; self.reverse_rev = 0.0
        self.delivered = collections.defaultdict(float); self.spilled_g = 0.0; self.spill_buf = {}
        mega.aug_hooks.append(self.on_revs); world.add_plugin(self)

    def _angle(self):
        a = getattr(self.mega, 'aug_angle', None)
        return a / 360.0 if a is not None else self.net

    def fill(self, g):
        """load yeast into the hopper; resets the hopper-empty window"""
        self.ledger.add('hopper', 'yeast', g); self.recent.clear()

    # ------------------------------------------------------------- plugin (flushes the spill buffer when the AUG ends)
    def pre_step(self, w): pass

    def post_step(self, w):
        if self.spill_buf and not (self.mega.motion and self.mega.motion['cmd'] == 'AUG'): self.flush()

    def idle(self, w, dt): self.post_step(w)

    def flush(self):
        if self.spill_buf: self.ledger.spill(self.spill_buf, 'auger outlet: no beaker opening under it'); self.spill_buf = {}

    # ------------------------------------------------------------- hook
    def on_revs(self, drev):
        """SimMega hook: signed revolutions turned in this step"""
        self.net += drev
        if drev > 0: self.forward_rev += drev
        else: self.reverse_rev -= drev
        old = self.travel
        if self.recover_dispenses: self.travel += max(drev, 0.0)
        else: self.travel = max(self.travel, self._angle() - self.a0)
        g = self._deliver(self._grams(old, self.travel)) if self.travel > old else 0.0
        if drev > 0: self._count(drev, g)

    def _grams(self, a, b):
        """grams for dispensing travel a -> b (rev): one g/rev draw per revolution of travel"""
        g = 0.0
        while b - a > EPS_REV:
            k = math.floor(a + EPS_REV); e = min(b, k + 1.0)
            if k != self.rev_k:
                self.rev_k = k; self.g_k = max(0.0, float(self.rng.normal(self.g_per_rev, self.cv * self.g_per_rev))); self.draws.append(self.g_k)
            g += (e - a) * self.g_k; a = e
        return g

    def _deliver(self, g):
        parts = self.ledger.take('hopper', g); got = sum(parts.values())
        if got <= 0: return 0.0
        bk = self.receiver()
        if bk is None:
            for s, v in parts.items(): self.spill_buf[s] = self.spill_buf.get(s, 0.0) + v
            self.spilled_g += got
        else: self.ledger.put(bk, parts); self.delivered[bk] += got
        return got

    def _count(self, drev, g):
        """grams per completed forward revolution (as the Mega counts them) and the hopper-empty rule over the last window"""
        f = g / drev
        while drev > EPS_REV:
            d = min(1.0 - self.fwd_frac, drev); self.fwd_frac += d; self.fwd_g += f * d; drev -= d
            if self.fwd_frac >= 1.0 - EPS_REV:
                self.recent.append(self.fwd_g); self.rev_grams.append(self.fwd_g); self.fwd_frac = 0.0; self.fwd_g = 0.0; self.flush()
                if len(self.recent) == self.window and sum(self.recent) < self.empty_g:
                    self.mega.fault('HOPPER_EMPTY', g_last=round(sum(self.recent), 3), revs=self.window)

    # ------------------------------------------------------------- geometry
    def receiver(self):
        """the beaker whose opening is under the outlet, or None"""
        d = self.w.d; o = mm(d.site_xpos[self.outlet])
        for bk, sid in self.lips.items():
            lip = mm(d.site_xpos[sid])
            if lip[2] < o[2] and math.hypot(o[0] - lip[0], o[1] - lip[1]) < self.open_r: return bk
        return None

    def totals(self):
        return dict(delivered_g={k: round(v, 4) for k, v in self.delivered.items()}, spilled_g=round(self.spilled_g, 4),
                    hopper_g=round(self.ledger.mass('hopper'), 4), forward_rev=round(self.forward_rev, 3), reverse_rev=round(self.reverse_rev, 3),
                    net_rev=round(self._angle() - self.a0, 3),
                    dispensing_rev=round(self.travel, 3), g_per_rev_true=self.g_per_rev, cv=self.cv)
