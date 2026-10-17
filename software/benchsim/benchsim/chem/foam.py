"""Elephant-toothpaste foam model (analytic, not CFD). It reads the flask contents from the ledger and drives the
'foam' geom, which rides on the sled. Parameters are in bench_params.toml [foam] and [flask]; values marked "assumed"
there need the first live run (architecture 4.5: measure T_foam).

Chemistry: 2 H2O2 -> 2 H2O + O2. The developer is h2o2_mass_frac H2O2. 39 g of 12 % developer is 4.68 g =
0.1376 mol H2O2, which gives 0.0688 mol O2, or 1.68 L at 25 C and 1 atm (demo_process 1: "about 1.7 L").

Model, integrated in update_dt_s steps:
- The clock starts when the flask first holds both developer and yeast. After ``induction_s`` (assumed catalyst
  mixing delay) the H2O2 left decomposes first-order, dn/dt = -k n, with k = k_ml_per_g_s * yeast g / liquid mL
  (catalase activity taken as proportional to the yeast concentration). It is never zero-order or Michaelis-Menten
  saturated, and there is no temperature or activation-time dependence.
- Of the released O2, a fraction trap_frac_soap (trap_frac_no_soap without soap) is held as foam with liquid volume
  fraction liquid_frac, so foam = trap * gas / (1 - liquid_frac). The liquid in all the foam made cannot exceed the
  liquid in the flask; past that, the gas escapes. Untrapped gas leaves without foam.
- Foam first fills the headspace, which is the flask's internal volume (a frustum plus the neck, from [flask], with
  wall (neck_od - neck_id)/2) minus the liquid volume. The excess is extruded through the neck as a column of neck
  bore diameter. The liquid carried by the foam is not taken out of the pool when sizing the headspace, an error of
  at most liquid_frac of the foam volume.
- Standing foam inside the flask and in the column collapses with time constant collapse_tau_s. A column taller
  than column_max_mm topples into the catch well (overflow).
- The column is drawn straight up from the neck top. The funnel, which stays in the neck at ERUPT, is ignored, so
  the column shows through the semi-transparent funnel cone.

    ledger = Ledger(bb.world); load_flask(ledger)          # soap + dye pre-loaded by hand (demo_process 1)
    foam = FoamModel(bb.world, ledger)                     # registers as a SimWorld plugin; works with world.idle too
    foam.column_mm(); foam.state(); foam.trace             # height above the neck, summary, time series
"""
import math

from .. import units
from .vessels import DENSITY

ML_PER_L = 1000.0
MM3_PER_ML = 1000.0
HIDDEN_HALF_MM = 0.5                 # half-length of the hidden (alpha 0) geom, as built in scene.stage


def flask_volume_ml(flask):
    """internal volume of the modelled flask: body frustum + neck, wall (neck_od - neck_id)/2"""
    wall = (flask['neck_od'] - flask['neck_id']) / 2; r0 = flask['base_od'] / 2 - wall; r1 = flask['neck_id'] / 2
    hb = flask['height'] - flask['neck_h']
    return (math.pi * hb / 3 * (r0 * r0 + r0 * r1 + r1 * r1) + math.pi * r1 * r1 * flask['neck_h']) / MM3_PER_ML


def o2_yield_ml(developer_g, foam):
    """O2 volume (mL) from complete decomposition of the H2O2 in developer_g of developer"""
    return foam['h2o2_mass_frac'] * developer_g / foam['h2o2_molar_mass'] / 2 * foam['o2_molar_volume_l'] * ML_PER_L


def load_flask(ledger, params=None):
    """the hand-loaded flask charge: [flask] soap_ml of dish soap and [foam] dye_g of food colouring"""
    P = params or ledger.w.P
    ledger.add('flask', 'soap', P['flask']['soap_ml'] * DENSITY['soap']); ledger.add('flask', 'dye', P['foam']['dye_g'])


class FoamModel:
    def __init__(self, world, ledger, params=None):
        P = params or world.P; self.F = F = P['foam']; Fl = P['flask']
        if not 0 < F['liquid_frac'] < 1: raise ValueError('[foam] liquid_frac must be in (0, 1)')
        self.w = world; self.ledger = ledger; m = world.m
        self.gid = m.geom('foam').id; self.body = m.geom_bodyid[self.gid]; sid = m.site('flask_neck_top').id
        if m.site_bodyid[sid] != self.body: raise ValueError('the foam geom and flask_neck_top must ride on the same body')
        self.neck = units.mm(m.site_pos[sid].copy())            # neck top in the sled frame (mm)
        self.r_col = Fl['neck_id'] / 2; self.a_col = math.pi * self.r_col ** 2
        self.v_flask = flask_volume_ml(Fl); self.cap_ml = F['column_max_mm'] * self.a_col / MM3_PER_ML
        self.t = world.time; self.t_contact = None; self.n_reacted = 0.0
        self.o2_ml = 0.0; self.foam_ml = 0.0; self.inside_ml = 0.0; self.column_ml = 0.0; self.overflow_ml = 0.0
        self.collapsed_ml = 0.0; self.escaped_gas_ml = 0.0
        self.peak_mm = 0.0; self.t_peak = None; self.t_neck = None; self.trace = []
        self._show(0.0)
        world.add_plugin(self)

    # ------------------------------------------------------------- plugin
    def pre_step(self, w): pass

    def post_step(self, w):
        if w.time - self.t >= self.F['update_dt_s'] - 1e-12: self.advance(w.time)

    def idle(self, w, dt): self.advance(w.time + dt)

    def advance(self, t):
        while self.t < t - 1e-12:
            dt = min(self.F['update_dt_s'], t - self.t); self.t += dt; self._step(dt)
        self._show(self.column_mm())

    # ------------------------------------------------------------- model
    def column_mm(self): return self.column_ml * MM3_PER_ML / self.a_col

    def h2o2_left_g(self):
        F = self.F; return max(0.0, F['h2o2_mass_frac'] * self.ledger.v['flask'].get('developer', 0.0) - self.n_reacted * F['h2o2_molar_mass'])

    def _step(self, dt):
        F = self.F; c = self.ledger.v['flask']; dev = c.get('developer', 0.0); yeast = c.get('yeast', 0.0)
        if self.t_contact is None:
            if dev > 0 and yeast > 0: self.t_contact = self.t - dt
            else: return
        v_liq = self.ledger.volume_ml('flask')
        n_left = max(0.0, F['h2o2_mass_frac'] * dev / F['h2o2_molar_mass'] - self.n_reacted); dn = 0.0
        if self.t - self.t_contact >= F['induction_s'] and yeast > 0 and v_liq > 0:
            dn = n_left * (1.0 - math.exp(-F['k_ml_per_g_s'] * yeast / v_liq * dt))
        self.n_reacted += dn
        gas = dn / 2 * F['o2_molar_volume_l'] * ML_PER_L; self.o2_ml += gas
        trap = F['trap_frac_soap'] if c.get('soap', 0.0) >= F['soap_min_g'] else F['trap_frac_no_soap']
        room = max(0.0, v_liq - F['liquid_frac'] * self.foam_ml) / F['liquid_frac']       # foam the liquid left can still make
        foam = min(trap * gas / (1.0 - F['liquid_frac']), room)
        self.foam_ml += foam; self.escaped_gas_ml += gas - foam * (1.0 - F['liquid_frac'])
        head = max(0.0, self.v_flask - v_liq)
        self.inside_ml += foam; x = max(0.0, self.inside_ml - head); self.inside_ml -= x; self.column_ml += x
        f = 1.0 - math.exp(-dt / F['collapse_tau_s'])
        self.collapsed_ml += (self.inside_ml + self.column_ml) * f; self.inside_ml *= 1.0 - f; self.column_ml *= 1.0 - f
        if self.column_ml > self.cap_ml: self.overflow_ml += self.column_ml - self.cap_ml; self.column_ml = self.cap_ml
        h = self.column_mm()
        if h > 0 and self.t_neck is None: self.t_neck = self.t
        if h > self.peak_mm + 1e-9: self.peak_mm = h; self.t_peak = self.t
        self.trace.append(dict(t=round(self.t, 4), o2_ml=self.o2_ml, foam_ml=self.foam_ml, inside_ml=self.inside_ml, column_ml=self.column_ml,
                               column_mm=h, overflow_ml=self.overflow_ml, h2o2_left_g=self.h2o2_left_g()))

    def state(self):
        r = lambda x: None if x is None else round(x, 3)
        return dict(t=r(self.t), t_contact=r(self.t_contact), t_foam_at_neck=r(self.t_neck), t_peak=r(self.t_peak), column_mm=r(self.column_mm()),
                    peak_mm=r(self.peak_mm), o2_ml=r(self.o2_ml), foam_ml=r(self.foam_ml), inside_ml=r(self.inside_ml), column_ml=r(self.column_ml),
                    overflow_ml=r(self.overflow_ml), collapsed_ml=r(self.collapsed_ml), escaped_gas_ml=r(self.escaped_gas_ml),
                    h2o2_left_g=r(self.h2o2_left_g()), headspace_ml=r(max(0.0, self.v_flask - self.ledger.volume_ml('flask'))))

    # ------------------------------------------------------------- visual
    def _show(self, h):
        """column of height h (mm) on the neck top in the sled frame; hidden (alpha 0) at zero"""
        m = self.w.m; g = self.gid; F = self.F
        half = h / 2 if h > 0 else HIDDEN_HALF_MM
        m.geom_size[g, 0] = units.m(self.r_col); m.geom_size[g, 1] = units.m(half)
        m.geom_pos[g] = units.m([self.neck[0], self.neck[1], self.neck[2] + (h / 2 if h > 0 else HIDDEN_HALF_MM)])
        m.geom_rbound[g] = units.m(math.hypot(self.r_col, half))
        rgba = list(F['rgba_dyed'] if self.ledger.v['flask'].get('dye', 0.0) > 0 else F['rgba_plain'])
        if h <= 0: rgba[3] = 0.0
        m.geom_rgba[g] = rgba
        d = self.w.d; b = self.body                       # keep the world pose current while physics is frozen (world.idle)
        d.geom_xpos[g] = d.xpos[b] + d.xmat[b].reshape(3, 3) @ m.geom_pos[g]
