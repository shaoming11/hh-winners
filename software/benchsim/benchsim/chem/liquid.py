"""Analytic liquid model for the pours. This is NOT CFD: every relation below is a lumped, quasi-static
approximation, labelled where it is used.

Pieces (all coefficients come from [liquid] in config/bench_params.toml):

* ``TiltedCylinder``: the liquid in a tilted right-circular cavity (the beaker's inside: radius od/2 - wall, height
  height - floor). The free surface is assumed flat and horizontal at every instant (no slosh, no meniscus). It
  gives the volume as a function of tilt and of the surface height above the pour lip (the lowest rim point), the
  critical volume V_c(theta) whose surface just touches the lip, and its inverse theta_first(V).
* Weir flow over the lip (approximation): a sharp-crested rectangular weir of effective width ``lip_width_mm``,
  Q = Cd * 2/3 * sqrt(2 g) * w * (h - h_hold)^1.5, with h the surface height above the lip and h_hold a capillary
  hold-up head below which nothing flows. The rim's curvature and the spout shape are folded into the effective
  width; viscosity and surface tension beyond h_hold are ignored.
* Stream (approximation): the liquid crosses the lip, runs down it for ``transport_delay_s`` and then falls
  ballistically (no drag) from the outer lip point with the weir's critical-depth velocity sqrt(g * 2h/3) along the
  horizontal pour direction. Material in flight is tracked as parcels. A parcel is caught by the first (highest)
  receiver opening it falls through; the caught share is the overlap of a jet disc of radius ``jet_radius_mm``
  with the opening. The rest is recorded with ``Ledger.spill`` (spilled liquid is removed from the mass balance,
  even if it lands on the scale pan).
* Optional impact force: the vertical momentum flux of the landing stream (m_dot * v_z) pushes on the receiver
  beaker body, so the simulated scale reads the dynamic overshoot of a real stream.
* After-drip (approximation): while liquid flows a small lip film builds up (``drip_ml``); when the stream stops it
  drains exponentially (``drip_tau_s``) and falls vertically from the lip.

``LiquidModel`` is the SimWorld plugin that applies all of this to the Ledger: mass leaves the source beaker, rides
in parcels, and lands in the receiver vessel (another beaker, or 'flask' through the funnel) or is spilled.
"""
import heapq
import math

import numpy as np

from .vessels import BEAKERS
from ..units import mm

G_MM_S2 = 9810.0                        # standard gravity in mm/s^2 (MuJoCo default gravity is 9.81 m/s^2)
ML = 1000.0                             # mm^3 per mL


# ======================================================================= tilted cylinder
class TiltedCylinder:
    """Liquid in a cylindrical cavity of radius ``r_mm`` and height ``h_mm`` tilted by theta (deg, axis from vertical).

    Cavity frame: x' toward the lowest rim point (the lip), z' along the axis from the cavity floor. With a flat
    horizontal surface at height s above the lip crest (x' = r, z' = h), the wetted region is
        z' cos(theta) - x' sin(theta) <= h cos(theta) - r sin(theta) + s.
    ``volume_ml`` integrates that region exactly up to quadrature error (Chebyshev-U weights for the circular chord
    width). ``v_crit`` / ``head`` use tables on a (theta, s) grid built once per instance."""

    def __init__(self, r_mm, h_mm, theta_max_deg=120.0, dtheta_deg=0.25, s_range_mm=(-12.0, 30.0), ds_mm=0.25, n_quad=600):
        self.r = float(r_mm); self.h = float(h_mm); self.n_quad = int(n_quad)
        k = np.arange(1, self.n_quad + 1); a = k * math.pi / (self.n_quad + 1)
        self._x = self.r * np.cos(a)                                       # nodes on (-r, r)
        self._w = 2 * self.r * self.r * math.pi / (self.n_quad + 1) * np.sin(a) ** 2    # int 2 sqrt(r^2-x^2) f(x) dx
        self.th = np.arange(0.0, theta_max_deg + 1e-9, dtheta_deg)
        self.s = np.arange(s_range_mm[0], s_range_mm[1] + 1e-9, ds_mm)
        self.V = np.stack([self.volume_ml(t, self.s) for t in self.th])     # (n_theta, n_s) mL
        self.Vc = np.array([self.volume_ml(t, 0.0) for t in self.th])
        self.capacity_ml = math.pi * self.r ** 2 * self.h / ML

    # ---------------------------------------------------------------- exact (quadrature)
    def volume_ml(self, theta_deg, s_mm):
        """liquid volume (mL) at tilt theta with the surface s_mm above the lip crest (s may be an array)"""
        t = math.radians(float(theta_deg)); c, sn = math.cos(t), math.sin(t)
        s = np.atleast_1d(np.asarray(s_mm, float))[:, None]; x = self._x[None, :]
        if abs(c) < 1e-9:                                              # axis horizontal: full columns where x' >= r - s
            L = np.where(x * sn >= self.r * sn - s, self.h, 0.0)
        else:
            Z = self.h - (self.r - x) * (sn / c) + s / c               # boundary z'(x') of the wetted region
            L = np.clip(Z, 0.0, self.h) if c > 0 else self.h - np.clip(Z, 0.0, self.h)
        v = (L * self._w[None, :]).sum(axis=1) / ML
        return float(v[0]) if np.ndim(s_mm) == 0 else v

    # ---------------------------------------------------------------- tables
    def _row(self, theta_deg):
        th = min(max(float(theta_deg), self.th[0]), self.th[-1]); i = min(int(th / (self.th[1] - self.th[0])), len(self.th) - 2)
        f = (th - self.th[i]) / (self.th[i + 1] - self.th[i]); return self.V[i] * (1 - f) + self.V[i + 1] * f

    def v_crit_ml(self, theta_deg):
        """volume whose surface just touches the lip at this tilt (mL)"""
        return float(np.interp(theta_deg, self.th, self.Vc))

    def theta_crit_deg(self, v_ml):
        """theta_first(V): the tilt at which a fill of v_ml reaches the lip"""
        return float(np.interp(v_ml, self.Vc[::-1], self.th[::-1]))

    def dv_dtheta_ml_per_deg(self, theta_deg, step=0.5):
        """slope of the critical-volume curve (negative: tilting further lowers V_c)"""
        return (self.v_crit_ml(theta_deg + step) - self.v_crit_ml(theta_deg - step)) / (2 * step)

    def head_mm(self, theta_deg, v_ml):
        """surface height above the lip crest for v_ml at this tilt (clamped to the table's s range)"""
        return float(np.interp(v_ml, self._row(theta_deg), self.s))

    def surface_area_mm2(self, theta_deg, s_mm=0.0, ds=0.25):
        """free-surface area dV/ds (mm^2)"""
        return (self.volume_ml(theta_deg, s_mm + ds) - self.volume_ml(theta_deg, s_mm - ds)) * ML / (2 * ds)


# ======================================================================= weir and stream relations
def weir_flow_ml_s(head_mm, cd, lip_width_mm, hold_head_mm=0.0, g=G_MM_S2):
    """rectangular sharp-crested weir (approximation): Q = Cd 2/3 sqrt(2g) w (h - h_hold)^1.5, mL/s"""
    he = max(float(head_mm) - hold_head_mm, 0.0)
    return cd * (2.0 / 3.0) * math.sqrt(2 * g) * lip_width_mm * he ** 1.5 / ML


def weir_head_mm(q_ml_s, cd, lip_width_mm, hold_head_mm=0.0, g=G_MM_S2):
    """inverse of weir_flow_ml_s"""
    if q_ml_s <= 0: return hold_head_mm
    return hold_head_mm + (q_ml_s * ML / (cd * (2.0 / 3.0) * math.sqrt(2 * g) * lip_width_mm)) ** (2.0 / 3.0)


def exit_speed_mm_s(head_mm, coeff, hold_head_mm=0.0, g=G_MM_S2):
    """free-overfall approximation: the sheet leaves the crest at the critical depth h_c = 2/3 h with v = sqrt(g h_c)"""
    he = max(float(head_mm) - hold_head_mm, 0.0)
    return coeff * math.sqrt(g * 2.0 / 3.0 * he)


def fall_time_s(z0_mm, vz_mm_s, z1_mm, g=G_MM_S2):
    """time for a ballistic point to fall from z0 to z1 (None if it never gets there)"""
    a = 0.5 * g; b = -vz_mm_s; c = z1_mm - z0_mm               # a t^2 + b t + c = 0 with z(t) = z0 + vz t - g t^2/2
    disc = b * b - 4 * a * c
    if disc < 0: return None
    t = (-b + math.sqrt(disc)) / (2 * a)
    return t if t >= 0 else None


def capture_fraction(dist_mm, r_open_mm, r_jet_mm):
    """share of a uniform jet disc (radius r_jet) centred dist_mm from an opening's centre that falls inside the
    opening (radius r_open): circle-circle overlap area over the jet area"""
    d, R, r = abs(float(dist_mm)), float(r_open_mm), float(r_jet_mm)
    if r <= 0: return 1.0 if d < R else 0.0
    if d >= R + r: return 0.0
    if d <= abs(R - r): return 1.0 if R >= r else (R / r) ** 2
    a1 = r * r * math.acos(np.clip((d * d + r * r - R * R) / (2 * d * r), -1, 1))
    a2 = R * R * math.acos(np.clip((d * d + R * R - r * r) / (2 * d * R), -1, 1))
    a3 = 0.5 * math.sqrt(max((-d + r + R) * (d + r - R) * (d - r + R) * (d + r + R), 0.0))
    return (a1 + a2 - a3) / (math.pi * r * r)


class LipFlow:
    """the pure flow model of one beaker (no MuJoCo): volume + tilt -> head, flow, exit speed. Used by LiquidModel and
    by the synthetic plants in the tests, so both run the same relations."""

    def __init__(self, cyl: TiltedCylinder, cfg):
        self.cyl = cyl; self.cfg = cfg
        self.cd = cfg['cd']; self.w = cfg['lip_width_mm']; self.h_hold = cfg['hold_head_mm']; self.film = cfg['residual_film_ml']

    def head_mm(self, theta_deg, v_ml):
        return self.cyl.head_mm(theta_deg, v_ml)

    def flow_ml_s(self, theta_deg, v_ml):
        if v_ml <= self.film: return 0.0
        return weir_flow_ml_s(self.head_mm(theta_deg, v_ml), self.cd, self.w, self.h_hold)

    def step(self, theta_deg, v_ml, dt):
        """volume that leaves over the lip in dt (mL), never more than the drainable volume, and the head (mm).
        Explicit Euler with the outflow capped so the head cannot cross below the hold-up level in one step."""
        h = self.head_mm(theta_deg, v_ml)
        if h <= self.h_hold or v_ml <= self.film: return 0.0, h
        q = weir_flow_ml_s(h, self.cd, self.w, self.h_hold)
        v_floor = max(self.film, float(np.interp(self.h_hold, self.cyl.s, self.cyl._row(theta_deg))))
        return min(q * dt, max(v_ml - v_floor, 0.0)), h


def beaker_cylinder(P, **kw):
    """the inside of the bench's beaker (bench_params [beaker]): radius od/2 - wall, height height - floor"""
    B = P['beaker']; return TiltedCylinder(B['od'] / 2 - B['wall'], B['height'] - B['floor'], **kw)


# ======================================================================= SimWorld plugin
class LiquidModel:
    SPILL_BOOK_S = 0.05                                   # bookkeeping only: spill is booked in the Ledger in 50 ms batches
    """SimWorld plugin on top of the Ledger: flow over the lip of every tilted beaker, parcels in flight, landing in
    the receiver opening (beakers: inner radius at the rim; funnel: rim radius -> 'flask') or ``ledger.spill``.

    Register it after the Ledger so its impact force is added after the Ledger has written the weight forces.
    Read-only views for reports: ``stream`` (latest per-source state), ``landings`` (one row per landed parcel batch,
    decimated), ``flow_log`` (per-source totals)."""

    def __init__(self, world, ledger, cfg=None):
        if ledger not in world.plugins: raise ValueError('register the Ledger before the LiquidModel')
        self.w = world; self.L = ledger; P = world.P
        self.cfg = dict(cfg or P['liquid'])
        B = P['beaker']; self.H_outer = B['height']; self.R_outer = B['od'] / 2; self.r_open = B['od'] / 2 - B['wall']
        self.cyl = beaker_cylinder(P); self.flow = LipFlow(self.cyl, self.cfg)
        self.funnel_site = world.m.site('funnel_rim').id; self.r_funnel = P['funnel']['rim_d'] / 2
        self.body = dict(ledger.body)
        self.parcels = []; self._seq = 0                 # heap of (t_land, seq, parcel)
        self.film = {bk: 0.0 for bk in BEAKERS}          # lip film per source (mL), released as after-drip
        self.stream = {}; self.landings = []; self.totals = dict(poured_g=0.0, caught_g={}, spilled_g=0.0)
        self._impact = {}                                 # body id -> N this step
        self._spill_buf = dict(parts={}, t0=None, src=None, xy=None)
        self.q_ml_s = {bk: 0.0 for bk in BEAKERS}; self.head = {bk: None for bk in BEAKERS}
        world.add_plugin(self)

    # ---------------------------------------------------------------- geometry from the world (mm)
    def beaker_frame(self, bk):
        b = self.w.d.body('beaker_' + bk); return mm(b.xpos.copy()), b.xmat.reshape(3, 3).copy()

    def tilt_deg(self, bk):
        _, R = self.beaker_frame(bk); return math.degrees(math.acos(float(np.clip(R[2, 2], -1, 1))))

    def lip(self, bk):
        """outer lip point (lowest rim point, mm), the beaker's tilt (deg) and the horizontal pour direction"""
        p, R = self.beaker_frame(bk); u = R[:, 2]; th = math.degrees(math.acos(float(np.clip(u[2], -1, 1))))
        down = np.array([0, 0, -1.0]) - u * (-u[2])                    # -Z projected on the rim plane
        n = np.linalg.norm(down); wdir = down / n if n > 1e-9 else R[:, 0]
        dh = u[:2].copy(); dn = np.linalg.norm(dh); dh = dh / dn if dn > 1e-9 else np.zeros(2)
        return p + self.H_outer * u + self.R_outer * wdir, th, dh

    def receivers(self, exclude):
        """open containers a stream can fall into: (name, vessel, rim centre mm, opening radius mm, surface z mm, body id)"""
        out = []
        for bk in BEAKERS:
            if bk == exclude or bk in self.w.held.values(): continue
            p, R = self.beaker_frame(bk)
            if R[2, 2] < math.cos(math.radians(20.0)): continue      # a toppled beaker catches nothing
            fl = self.w.P['beaker']['floor']; lev = self.L.volume_ml(bk) * ML / (math.pi * self.r_open ** 2)
            out.append((bk, bk, p + self.H_outer * R[:, 2], self.r_open, p[2] + fl + lev, self.body[bk]))
        rim = mm(self.w.d.site_xpos[self.funnel_site].copy())
        out.append(('funnel', 'flask', rim, self.r_funnel, rim[2], None))
        return sorted(out, key=lambda r: -r[2][2])

    # ---------------------------------------------------------------- per physics step
    def pre_step(self, w):
        dt = w.dt; t = w.time; C = self.cfg
        self._impact = {}
        for bk in BEAKERS:
            v_tot = self.L.volume_ml(bk)
            if v_tot <= 0: self.film[bk] = 0.0; self.q_ml_s[bk] = 0.0; continue
            film = self.film[bk]; v = v_tot - film                     # the lip film is outside the cavity, still on the beaker
            th = math.degrees(math.acos(float(np.clip(w.d.xmat[self.body[bk], 8], -1, 1))))
            if film <= 0 and v < self.cyl.v_crit_ml(th) - 1.0: self.q_ml_s[bk] = 0.0; continue     # surface well below the lip
            lip, th, dh = self.lip(bk)
            dv, h = self.flow.step(th, v, dt)
            self.q_ml_s[bk] = dv / dt; self.head[bk] = h
            if dv > 0:
                fill = min(max(C['drip_ml'] - film, 0.0), dv)          # part of the overflow wets the outer lip
                self.film[bk] = film + fill
                self._release(bk, dv - fill, lip, exit_speed_mm_s(h, C['exit_velocity_coeff'], self.flow.h_hold), dh, t, h, th)
                self.stream[bk] = dict(t=round(t, 4), theta=round(th, 2), head_mm=round(h, 3), q_ml_s=round(dv / dt, 3), lip=np.round(lip, 1).tolist())
            elif film > 0:                                             # stream stopped: the lip film drips off vertically
                dd = film if film < 1e-5 else film * (1 - math.exp(-dt / C['drip_tau_s']))
                self.film[bk] = film - dd; self._release(bk, dd, lip, 0.0, dh, t, 0.0, th, drip=True)
        self._land(t, dt)
        for bid, f in self._impact.items(): w.d.xfrc_applied[bid, 2] -= f

    def _release(self, bk, dv_ml, lip, speed, dh, t, head, th, drip=False):
        """take dv from the source in the Ledger and put it in flight"""
        tot_v = self.L.volume_ml(bk)
        if dv_ml <= 0 or tot_v <= 0: return
        parts = self.L.take(bk, self.L.mass(bk) * min(dv_ml / tot_v, 1.0))
        if not parts: return
        g = sum(parts.values()); self.totals['poured_g'] += g
        t0 = t + (0.0 if drip else self.cfg['transport_delay_s'])
        vxy = speed * dh; vz = 0.0; z0 = lip[2]
        left = 1.0
        for name, vessel, rim, r_open, z_surf, bid in self.receivers(bk):
            tr = fall_time_s(z0, vz, rim[2])
            if tr is None: continue
            xy = lip[:2] + vxy * tr; dist = float(np.linalg.norm(xy - rim[:2]))
            f = capture_fraction(dist, r_open, self.cfg['jet_radius_mm']) * left
            if f <= 1e-9: continue
            ts = fall_time_s(z0, vz, z_surf) or tr; vimp = vz - G_MM_S2 * ts
            delay = self.cfg['funnel_delay_s'] if name == 'funnel' else 0.0
            self._push(t0 + ts + delay, dict(vessel=vessel, parts={s: x * f for s, x in parts.items()}, vz=vimp, body=bid, src=bk,
                                             dist=dist, recv=name, xy=xy, head=head, theta=th))
            left -= f
            break
        if left > 1e-9:
            tz = fall_time_s(z0, vz, 0.0) or 0.0; xy = lip[:2] + vxy * tz
            self._push(t0 + tz, dict(vessel=None, parts={s: x * left for s, x in parts.items()}, vz=0.0, body=None, src=bk, dist=None,
                                     recv='table', xy=xy, head=head, theta=th))

    def _push(self, t_land, parcel):
        self._seq += 1; heapq.heappush(self.parcels, (t_land, self._seq, parcel))

    def _land(self, t, dt):
        while self.parcels and self.parcels[0][0] <= t:
            _, _, p = heapq.heappop(self.parcels); g = sum(p['parts'].values())
            if p['vessel'] is None:
                b = self._spill_buf
                if not b['parts']: b['t0'] = t; b['src'] = p['src']; b['xy'] = p['xy']
                for s, x in p['parts'].items(): b['parts'][s] = b['parts'].get(s, 0.0) + x
                self.totals['spilled_g'] += g
            else:
                self.L.put(p['vessel'], p['parts'])
                self.totals['caught_g'][p['vessel']] = self.totals['caught_g'].get(p['vessel'], 0.0) + g
                if self.cfg['impact_force'] and p['body'] is not None:
                    self._impact[p['body']] = self._impact.get(p['body'], 0.0) + (g / 1000.0) * (-p['vz'] / 1000.0) / dt   # N
            self.landings.append(dict(t=round(t, 4), src=p['src'], recv=p['recv'], g=g, dist_mm=p['dist'], xy=p['xy'], head_mm=p['head'], theta=p['theta']))
        if self._spill_buf['parts'] and t - self._spill_buf['t0'] >= self.SPILL_BOOK_S: self.flush_spill()

    def flush_spill(self):
        """book the buffered spill in the Ledger (one entry per SPILL_BOOK_S keeps the ledger's 0.1 mg rounding small)"""
        b = self._spill_buf
        if b['parts']:
            self.L.spill(b['parts'], where='%s stream missed every receiver near (%.0f, %.0f) mm' % (b['src'], b['xy'][0], b['xy'][1]))
        self._spill_buf = dict(parts={}, t0=None, src=None, xy=None)

    def post_step(self, w):
        pass

    def in_flight_g(self):
        """mass in the air, plus spill that has landed but is not yet booked in the Ledger"""
        return float(sum(sum(p['parts'].values()) for _, _, p in self.parcels) + sum(self._spill_buf['parts'].values()))


# ======================================================================= MuJoCo-free plant (tests, quick studies)
class SyntheticPour:
    """A pour without MuJoCo: the same LipFlow relations, a first-order rate-limited tilt actuator, a ballistic delay
    from lip to receiver, the stream's impact force and an 80 Hz noisy scale. Implements the controller's clock,
    sample source and tilt actuator, so ``PourController.run(plant, plant.samples, plant.set_theta)`` closes the loop.
    Approximations: the lip stays ``lip_above_mm`` above the receiver rim and every drop is caught."""

    def __init__(self, P, fill_ml, density=1.04, seed=0, lip_above_mm=45.0, servo_tau_s=0.03, servo_rate_deg_s=180.0,
                 theta_bias_deg=0.0, dt=0.001, catch=1.0):
        self.cfg = dict(P['liquid']); self.flow = LipFlow(beaker_cylinder(P), self.cfg); S = P['scale']
        self.v = float(fill_ml); self.rho = density; self.t = 0.0; self.dt = dt; self.rng = np.random.default_rng(seed)
        self.th_cmd = 0.0; self.th = 0.0; self.tau = servo_tau_s; self.rate = servo_rate_deg_s; self.bias = theta_bias_deg
        self.noise = S['noise_g']; self.sdt = 1.0 / S['rate_hz']; self.next_s = 0.0; self.out = []
        self.lip_above = lip_above_mm; self.recv_g = 0.0; self.spilled_g = 0.0; self.catch = catch
        self.flight = []; self.film = 0.0; self.impact_g = 0.0; self.log = []

    def now(self): return self.t

    def set_theta(self, th): self.th_cmd = float(th)

    def samples(self):
        o = self.out; self.out = []; return o

    def sleep(self, dt):
        n = max(1, int(round(dt / self.dt)))
        for _ in range(n): self._step()

    def _step(self):
        dt = self.dt; C = self.cfg
        d = (self.th_cmd - self.th) * min(dt / self.tau, 1.0); lim = self.rate * dt
        self.th += min(max(d, -lim), lim)
        th = self.th + self.bias
        dv, h = self.flow.step(th, self.v - self.film, dt)
        if dv > 0:
            fill = min(max(C['drip_ml'] - self.film, 0.0), dv); self.film += fill; self.v -= dv - fill
            stream = (dv - fill) * self.rho; vx = exit_speed_mm_s(h, C['exit_velocity_coeff'], self.flow.h_hold)
        elif self.film > 0:
            dd = self.film * (1 - math.exp(-dt / C['drip_tau_s'])); self.film -= dd; self.v -= dd; stream = dd * self.rho
        else: stream = 0.0
        if stream > 0:
            tf = fall_time_s(self.lip_above + 60.0, 0.0, 0.0)            # lip -> liquid surface ~60 mm below the rim
            self.flight.append((self.t + C['transport_delay_s'] + tf, stream, G_MM_S2 * tf))
        self.t += dt; landed = 0.0; vimp = 0.0
        while self.flight and self.flight[0][0] <= self.t:
            _, g, v = self.flight.pop(0); landed += g; vimp = v
        self.recv_g += landed * self.catch; self.spilled_g += landed * (1 - self.catch)
        imp = landed * self.catch * vimp / G_MM_S2 / dt if C['impact_force'] else 0.0      # grams-force
        self.impact_g = imp
        while self.next_s <= self.t:
            self.out.append((self.next_s, self.recv_g + imp + self.rng.normal(0, self.noise))); self.next_s += self.sdt
