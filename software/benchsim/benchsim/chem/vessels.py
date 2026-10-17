"""Mass ledger for every vessel, the in-flight stream and the spill tally (shared contract).

Species masses are grams. A vessel tied to a MuJoCo beaker body gets its contents' weight applied each physics
step as an external force at the beaker's axis (``xfrc_applied``), so the simulated scale and the arm loads feel
the liquid. The flask rides on the sled and is bookkept only. Nothing here moves material between vessels by
itself: the flow model (chem.liquid), the auger model (chem.auger) and the sequencer call ``add``/``take``.

Contract (keep stable):
    ledger = Ledger(world)              registers itself as a SimWorld plugin
    ledger.add(vessel, species, g)
    taken = ledger.take(vessel, g)      removes g proportionally to composition -> {species: g}
    ledger.put(vessel, parts)           adds a {species: g} dict
    ledger.mass(vessel) / volume_ml(vessel) / composition(vessel)
    ledger.spill(parts, where)          material that missed every receiver
    ledger.snapshot()                   JSON-able state for the run log
"""
import math

import numpy as np

SPECIES = ('developer', 'water', 'yeast', 'soap', 'dye')
DENSITY = {'developer': 1.04, 'water': 0.992, 'yeast': 0.60, 'soap': 1.03, 'dye': 1.0}      # g/mL (12 % H2O2 ~1.04)
BEAKERS = ('P1', 'P2', 'dev', 'water')


class Ledger:
    def __init__(self, world, apply_weight=True):
        self.w = world; self.apply_weight = apply_weight
        self.v = {name: {} for name in BEAKERS + ('flask', 'hopper')}
        self.spilled = []; self.g = 9.81
        self.body = {bk: world.m.body('beaker_' + bk).id for bk in BEAKERS}
        self.liquid_geom = {bk: world.m.geom('liquid_' + bk).id for bk in BEAKERS}
        self.inner_r = (world.P['beaker']['od'] / 2 - world.P['beaker']['wall']) / 1000.0
        self.floor = world.P['beaker']['floor'] / 1000.0
        world.add_plugin(self)

    # ------------------------------------------------------------- bookkeeping
    def add(self, vessel, species, g):
        if species not in SPECIES: raise ValueError('unknown species %s' % species)
        if g < 0: raise ValueError('negative mass')
        self.v[vessel][species] = self.v[vessel].get(species, 0.0) + float(g)

    def put(self, vessel, parts):
        for s, g in parts.items(): self.add(vessel, s, g)

    def take(self, vessel, g):
        tot = self.mass(vessel); g = min(float(g), tot)
        if tot <= 0 or g <= 0: return {}
        f = g / tot; out = {s: m * f for s, m in self.v[vessel].items()}
        for s in out: self.v[vessel][s] -= out[s]
        return out

    def spill(self, parts, where=''):
        if parts and sum(parts.values()) > 0:
            self.spilled.append(dict(t=round(self.w.time, 3), where=where, parts={k: round(v, 4) for k, v in parts.items()}))

    def spilled_mass(self):
        return sum(sum(s['parts'].values()) for s in self.spilled)

    def mass(self, vessel): return float(sum(self.v[vessel].values()))

    def composition(self, vessel): return {s: round(m, 4) for s, m in self.v[vessel].items() if m > 1e-9}

    def volume_ml(self, vessel):
        """liquid volume; dry yeast counts by bulk density until wetted (a slurry is approximated as additive)"""
        return float(sum(m / DENSITY[s] for s, m in self.v[vessel].items()))

    def snapshot(self):
        return dict(vessels={k: self.composition(k) for k in self.v}, spilled_g=round(self.spilled_mass(), 4), spills=self.spilled[-20:])

    # ------------------------------------------------------------- physics coupling
    def pre_step(self, w):
        if not self.apply_weight: return
        for bk, bid in self.body.items():
            w.d.xfrc_applied[bid, :] = 0.0
            m = self.mass(bk)
            if m > 0: w.d.xfrc_applied[bid, 2] = -m / 1000.0 * self.g        # applied at the body origin (beaker axis, bottom)

    def post_step(self, w):
        pass

    def update_visuals(self):
        """upright liquid column in each beaker (visual only); the flow model may override for tilted beakers"""
        for bk, gid in self.liquid_geom.items():
            vol = self.volume_ml(bk) * 1e-6
            h = vol / (math.pi * self.inner_r ** 2) if vol > 0 else 0.0
            self.w.m.geom_size[gid, 1] = max(h / 2, 1e-5)
            self.w.m.geom_pos[gid, 2] = self.floor + max(h / 2, 1e-5)
            self.w.m.geom_rgba[gid, 3] = 0.8 if vol > 0 else 0.0
