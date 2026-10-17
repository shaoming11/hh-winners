"""Read-only views of the chemistry models for drawing (mm, world frame). Nothing here changes the models, the
Ledger, the MuJoCo model or the data: the look reads these every frame and draws into the scene copy.

    ctx = Context.from_world(world)      # finds the Ledger, LiquidModel, FoamModel and AugerModel among world.plugins
    ctx.streams(); ctx.drips(); ctx.levels(); ctx.flask(); ctx.funnel_flow(); ctx.foam(); ctx.auger(); ctx.spills()

Every view degrades to empty when its model is absent (a bare bench, the dashboard's quick dev run).
"""
import math

import numpy as np

from ..chem.liquid import G_MM_S2, capture_fraction, exit_speed_mm_s, fall_time_s
from ..chem.vessels import BEAKERS, DENSITY
from ..units import mm

TABLE_Z = 0.0                          # table top (scene.world: the table box ends at z = 0)


class Context:
    def __init__(self, world, ledger=None, liquid=None, foam=None, auger=None):
        self.w = world; self.L = ledger; self.LM = liquid; self.F = foam; self.A = auger; P = world.P
        B = P['beaker']; self.r_in = B['od'] / 2 - B['wall']; self.floor = B['floor']; self.h_beaker = B['height']
        Fl = P['flask']; S = P['stage']; Fu = P['funnel']
        self.flask_geo = dict(floor=S['sled_plate_z'][1] + 2.0, wall=(Fl['neck_od'] - Fl['neck_id']) / 2, base_r=Fl['base_od'] / 2,
                              neck_r=Fl['neck_od'] / 2, neck_rin=Fl['neck_id'] / 2, height=Fl['height'], neck_h=Fl['neck_h'],
                              well_rin=Fl['catch_well'][0] / 2 - 2.5, well_h=Fl['catch_well'][1], collar_h=Fl['collar'][1])
        self.funnel_geo = dict(rim_r=Fu['rim_d'] / 2, stem_r=Fu['stem_od'] / 2, cone_h=Fu['cone_h'], stem_h=Fu['stem_h'])
        m = world.m
        self.sid = {n: m.site(n).id for n in ('funnel_rim', 'flask_neck_top', 'auger_outlet')}
        self.bid = {bk: m.body('beaker_' + bk).id for bk in BEAKERS}; self.sled = m.body('sled').id
        self._flask_table = self._flask_volume_table()
        self._spill_seen = 0; self._spill_cells = {}       # spills() reads LM.landings incrementally

    @classmethod
    def from_world(cls, world):
        from ..chem.auger import AugerModel
        from ..chem.foam import FoamModel
        from ..chem.liquid import LiquidModel
        from ..chem.vessels import Ledger
        pick = lambda k: next((p for p in world.plugins if isinstance(p, k)), None)
        return cls(world, pick(Ledger), pick(LiquidModel), pick(FoamModel), pick(AugerModel))

    @property
    def t(self): return self.w.time

    # ------------------------------------------------------------------ geometry
    def site(self, name): return mm(self.w.d.site_xpos[self.sid[name]].copy())

    def beaker_frame(self, bk):
        d = self.w.d; b = self.bid[bk]; return mm(d.xpos[b].copy()), d.xmat[b].reshape(3, 3).copy()

    def sled_origin(self): return mm(self.w.d.xpos[self.sled].copy())

    def contents(self, vessel): return dict(self.L.v[vessel]) if self.L is not None else {}

    def volume_ml(self, vessel): return self.L.volume_ml(vessel) if self.L is not None else 0.0

    # ------------------------------------------------------------------ liquid in the beakers
    def levels(self):
        """per beaker: dict(name, pos, R, tilt_deg, volume_ml, height_mm (upright column), contents, held)"""
        if self.L is None: return []
        out = []; held = set(self.w.held.values())
        for bk in BEAKERS:
            p, R = self.beaker_frame(bk); v = self.L.volume_ml(bk)
            out.append(dict(name=bk, pos=p, R=R, tilt_deg=math.degrees(math.acos(float(np.clip(R[2, 2], -1, 1)))), volume_ml=v,
                            height_mm=v * 1000.0 / (math.pi * self.r_in ** 2), contents=self.contents(bk), held=bk in held))
        return out

    # ------------------------------------------------------------------ flask
    def _flask_volume_table(self):
        """inner flask volume (mL) below height z above its floor, tabulated: frustum body then the neck bore"""
        g = self.flask_geo; r0 = g['base_r'] - g['wall']; r1 = g['neck_rin']; hb = g['height'] - g['neck_h']
        z = np.linspace(0.0, g['height'], 300)
        r = np.where(z < hb, r0 + (r1 - r0) * z / hb, r1)
        dv = np.pi * r ** 2 * np.gradient(z) / 1000.0
        return z, np.cumsum(dv) - dv[0], r

    def flask_radius(self, z_rel, inner=True):
        """flask radius (mm) at z_rel above its floor; inner bore or outer glass surface"""
        g = self.flask_geo; hb = g['height'] - g['neck_h']; w = g['wall'] if inner else 0.0
        r0 = g['base_r'] - w; r1 = (g['neck_rin'] if inner else g['neck_r'])
        return r0 + (r1 - r0) * min(max(z_rel, 0.0), hb) / hb if z_rel < hb else r1

    def flask_height_of(self, v_ml):
        z, V, _ = self._flask_table; return float(np.interp(v_ml, V, z))

    def flask(self):
        """the flask on the sled: origin (sled frame origin, world mm), floor z (world), liquid height, foam-inside height"""
        if self.L is None: return None
        o = self.sled_origin(); g = self.flask_geo; v = self.L.volume_ml('flask')
        inside = self.F.inside_ml if self.F is not None else 0.0
        return dict(origin=o, floor_z=o[2] + g['floor'], volume_ml=v, liquid_h=self.flask_height_of(v),
                    foam_h=self.flask_height_of(v + inside), contents=self.contents('flask'), geo=g)

    # ------------------------------------------------------------------ pours
    def _landing(self, src, lip, v0, dh):
        """where a stream leaving ``lip`` with horizontal speed v0 along dh lands, as LiquidModel._release decides it:
        -> (receiver name, landing z (surface), receiver rim centre or None)"""
        LM = self.LM
        for name, vessel, rim, r_open, z_surf, bid in LM.receivers(src):
            tr = fall_time_s(lip[2], 0.0, rim[2])
            if tr is None: continue
            xy = lip[:2] + v0 * dh * tr
            if capture_fraction(float(np.linalg.norm(xy - rim[:2])), r_open, LM.cfg['jet_radius_mm']) > 1e-9:
                return name, (self._funnel_surface_z(lip, v0, dh, rim) if name == 'funnel' else z_surf), rim
        return 'table', TABLE_Z, None

    def _funnel_surface_z(self, lip, v0, dh, rim):
        """the stream crosses the funnel rim plane and meets the cone wall below it"""
        g = self.funnel_geo; z_top = rim[2]; z_stem = z_top - g['cone_h']
        for t in np.linspace(0.0, 0.5, 200):
            p = lip[:2] + v0 * dh * t; z = lip[2] - 0.5 * G_MM_S2 * t * t
            if z > z_top: continue
            r = float(np.linalg.norm(p - rim[:2])); zc = z_stem + (r - g['stem_r']) / (g['rim_r'] - g['stem_r']) * g['cone_h']
            if z <= zc or z <= z_stem: return max(z, z_stem)
        return z_stem

    def streams(self, n=26):
        """falling streams: dict(src, contents, q_ml_s, v0, points (n, 3) mm, speed (n,) mm/s, recv, rim)"""
        LM = self.LM
        if LM is None: return []
        out = []
        for bk, q in LM.q_ml_s.items():
            if q <= 0 or LM.head.get(bk) is None: continue
            lip, th, dh = LM.lip(bk)
            v0 = exit_speed_mm_s(LM.head[bk], LM.cfg['exit_velocity_coeff'], LM.flow.h_hold)
            recv, z_land, rim = self._landing(bk, lip, v0, dh)
            T = fall_time_s(lip[2], 0.0, z_land) or 0.0
            ts = np.linspace(0.0, T, n)
            pts = np.c_[lip[0] + v0 * dh[0] * ts, lip[1] + v0 * dh[1] * ts, lip[2] - 0.5 * G_MM_S2 * ts ** 2]
            speed = np.hypot(v0, G_MM_S2 * ts)
            out.append(dict(src=bk, contents=self.contents(bk), q_ml_s=q, v0=v0, dh=dh, theta=th, points=pts, speed=speed, recv=recv, rim=rim))
        return out

    def drips(self):
        """lip film draining after a stream stops: dict(src, lip, film_ml, land_z, contents)"""
        LM = self.LM
        if LM is None: return []
        out = []
        for bk, f in LM.film.items():
            if f <= 1e-4 or LM.q_ml_s.get(bk, 0.0) > 0: continue
            lip, th, dh = LM.lip(bk); recv, z, rim = self._landing(bk, lip, 0.0, dh)
            out.append(dict(src=bk, lip=lip, film_ml=f, land_z=z, recv=recv, contents=self.contents(bk)))
        return out

    def funnel_flow(self):
        """liquid on its way through the funnel into the flask: grams in flight to the funnel and their contents"""
        LM = self.LM
        if LM is None: return None
        parts = {}
        for t_land, _, p in LM.parcels:
            if p['recv'] == 'funnel':
                for s, g in p['parts'].items(): parts[s] = parts.get(s, 0.0) + g
        g = sum(parts.values())
        return dict(g=g, contents=parts, rim=self.site('funnel_rim')) if g > 1e-4 else None

    def spills(self):
        """table landings merged per 5 mm cell: list of (xy, mL, contents). LM.landings only grows (a row per landed
        parcel, thousands per pour), so only the rows added since the last frame are read."""
        LM = self.LM
        if LM is None: return []
        rows = LM.landings; cells = self._spill_cells
        for x in rows[self._spill_seen:]:
            if x['recv'] != 'table': continue
            k = (round(x['xy'][0] / 5), round(x['xy'][1] / 5)); c = cells.setdefault(k, [np.zeros(2), 0.0, 0.0])
            c[0] += np.asarray(x['xy']) * x['g']; c[1] += x['g']; c[2] += x['g'] / DENSITY.get('water', 1.0)
        self._spill_seen = len(rows)
        return [(c[0] / c[1], c[2], None) for c in cells.values() if c[1] > 0]

    # ------------------------------------------------------------------ yeast auger
    def auger(self):
        """dict(dosing, outlet, land_z, recv) while the auger screw turns; None when idle"""
        A = self.A
        if A is None: return None
        mo = A.mega.motion
        if not (mo and mo.get('cmd') == 'AUG'): return None
        o = self.site('auger_outlet'); bk = A.receiver()
        if bk is None: return dict(outlet=o, land_z=TABLE_Z, recv=None)
        p, R = self.beaker_frame(bk); lev = self.L.volume_ml(bk) * 1000.0 / (math.pi * self.r_in ** 2)
        return dict(outlet=o, land_z=p[2] + self.floor + lev, recv=bk)

    # ------------------------------------------------------------------ foam
    def foam(self):
        """dict(neck (world mm), column_mm, cap_mm, inside_ml, overflow_ml, scroll_mm, age_s, rate (O2 mL/s), dyed, yeast) or None"""
        F = self.F
        if F is None: return None
        rate = 0.0
        if len(F.trace) >= 2:
            a, b = F.trace[-2], F.trace[-1]
            if b['t'] > a['t']: rate = (b['o2_ml'] - a['o2_ml']) / (b['t'] - a['t'])
        c = self.contents('flask')
        return dict(neck=self.site('flask_neck_top'), column_mm=F.column_mm(), cap_mm=F.F['column_max_mm'], r_col=F.r_col,
                    inside_ml=F.inside_ml, overflow_ml=F.overflow_ml,
                    scroll_mm=(F.column_ml + F.overflow_ml) * 1000.0 / F.a_col,      # foam pushed out of the neck so far, net of collapse
                    age_s=None if F.t_contact is None else self.t - F.t_contact, rate=rate, dyed=c.get('dye', 0.0) > 0,
                    yeast=c.get('yeast', 0.0) > 0)
