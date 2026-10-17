"""Closed-loop pour onto the scale (docs/software_architecture.md section 5) and the fixed-profile funnel pour.

Backend independent: no MuJoCo and no chemistry imports. The controller sees only
    samples()            -> list of (t_s, grams) scale samples since the last call (Mega clock, tared)
    set_theta(theta_deg)    tilt command along the pour manifold
    clock.now()/sleep(dt)
    vtable                  the pour beaker's V_table: v_crit_ml(theta), theta_crit_deg(v), dv_dtheta_ml_per_deg(theta)
and every gain and threshold comes from the [pour] config section (cfg dict).

State machine (section 5):
    FAST    fast move to theta_start (40 deg)
    RAMP    ramp_rate until first drop (q_hat > first_drop_q for first_drop_n samples and dm > first_drop_dm)
            -> V_first = V_table(theta_first) + fill_offset; PAUSE if V_first < low_fill_ml or no drop by then
    FLOW    theta = theta_ff + theta_PI; d theta_ff/dt = (d theta/dV)(V_remaining) q_hat/rho;
            PI on flow with conditional integration, integrator reset at first drop, rate clamp;
            q* = clamp(q_gain (target - m), q_min, q_ceiling); cut when m >= target - (a + b q_hat)
    CUT     fast untilt by delta (delta_big above untilt_big_q), then <= untilt_rate to theta_cut - untilt_total
    DRIP    hold drip_hold_s, no forward re-tilt
    SETTLE  until |q_hat| and the window sigma are small (timeout settle_timeout_s)
    TOPUP   if short by more than tol: ramp to theta_cut - topup_back at topup_ramp, then +topup_step every
            topup_period until q_hat > topup_flow or the cut law fires; PAUSE after max_topup_pulses pulses
    DONE    outcome OK, or OVERSHOOT (reported, never corrected: the approach is one-sided)
    PAUSE   LOW_FILL | NO_FLOW | LOW_REAGENT (manifold end reached short) | TOPUP_LIMIT | SPILL (mass deficit)

The mass-deficit (spill) check is an addition to section 5: while flowing, the mass the tilt says has left the
beaker is compared with what the scale has gained; a large sustained deficit means the stream is missing the
receiver. It uses the same V_table and a lip-head allowance (cfg spill_*), and can be switched off.
"""
import math
from dataclasses import asdict, dataclass, field

import numpy as np


class LineFit:
    """rolling least-squares line over the last ``window_s`` of (t, m) samples with an outlier gate.
    ``mass`` is the fitted value at the newest sample time and ``flow`` the slope (g/s)."""

    def __init__(self, window_s, outlier_sigma, sigma_floor_g, reset_n):
        self.win = window_s; self.k = outlier_sigma; self.floor = sigma_floor_g; self.reset_n = reset_n
        self.t = []; self.m = []; self.n_out = 0; self.rejected = 0
        self.mass = None; self.flow = 0.0; self.sigma = None

    def add(self, t, g):
        if self.mass is not None and len(self.t) >= 8:
            pred = self.mass + self.flow * (t - self.t[-1]); s = max(self.sigma or 0.0, self.floor)
            if abs(g - pred) > self.k * s:
                self.n_out += 1; self.rejected += 1
                if self.n_out < self.reset_n: return False
                self.t = self.t[-1:]; self.m = self.m[-1:]                # persistent step: restart the window
            else: self.n_out = 0
        self.t.append(t); self.m.append(g)
        while self.t and self.t[0] < t - self.win: self.t.pop(0); self.m.pop(0)
        self._fit(); return True

    def _fit(self):
        t = np.asarray(self.t); y = np.asarray(self.m)
        if len(t) < 3: self.mass = float(y[-1]); self.flow = 0.0; self.sigma = None; return
        tc = t - t[-1]; A = np.vstack([np.ones_like(tc), tc]).T
        (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
        self.mass = float(a); self.flow = float(b); r = y - (a + b * tc); self.sigma = float(np.std(r, ddof=2)) if len(t) > 3 else 0.0

    def span(self):
        return (self.t[-1] - self.t[0]) if len(self.t) > 1 else 0.0


@dataclass
class PourResult:
    target_g: float
    tol_g: float
    outcome: str = 'RUNNING'                     # OK | OVERSHOOT | PAUSE_*
    reason: str = ''
    final_g: float = None                        # settled scale mass seen by the controller
    error_g: float = None
    time_s: float = None
    theta_first_deg: float = None
    v_first_ml: float = None
    theta_cut_deg: float = None
    q_cut_g_s: float = None
    m_cut_g: float = None
    cuts: int = 0
    topup_pulses: int = 0
    max_theta_deg: float = None
    spill_margin_g: float = None                 # smallest (scale - spill_ratio * expected) seen by the armed spill check
    trace: list = field(default_factory=list)    # rows: t, state, theta, m, q, q_set
    events: list = field(default_factory=list)

    def summary(self):
        d = asdict(self); d.pop('trace'); return d


class PourController:
    def __init__(self, cfg, vtable, density_g_ml, target_g, tol_g, reagent='developer'):
        self.c = dict(cfg); r = cfg.get(reagent, {})
        self.c.update({k: v for k, v in r.items() if not isinstance(v, dict)})       # per-reagent overrides ([pour.<reagent>])
        self.vt = vtable; self.rho = float(density_g_ml); self.target = float(target_g); self.tol = float(tol_g); self.reagent = reagent
        c = self.c
        self.fit = LineFit(c['fit_window_s'], c['outlier_sigma'], c['outlier_sigma_floor_g'], c['outlier_reset_n'])
        self.res = PourResult(target_g=self.target, tol_g=self.tol)
        self.state = None; self.theta = 0.0; self.t_state = 0.0; self.t0 = None
        self.n_drop = 0; self.m_base = None; self.integ = 0.0; self.theta_ff = 0.0; self.theta_cut = None
        self.pulses = 0; self.t_pulse = 0.0; self.t_first = None; self.untilt_to = None; self.pause_code = None; self.deficit_since = None
        self.theta_pause = vtable.theta_crit_deg(c['low_fill_ml'] - c['fill_offset_ml'])
        self._last_q_set = None

    # ---------------------------------------------------------------- helpers
    def _go(self, state, t, **ev):
        self.state = state; self.t_state = t; self.res.events.append(dict(t=round(t - self.t0, 3), state=state, theta=round(self.theta, 2),
                                                                        m=None if self.fit.mass is None else round(self.fit.mass, 3), **ev))

    def _q_set(self, m):
        c = self.c; return min(max(c['q_gain_per_s'] * (self.target - m), c['q_min_g_s']), c['q_ceiling_g_s'])

    def _cut_due(self, m, q):
        return m >= self.target - (self.c['cut_a_g'] + self.c['cut_b_s'] * max(q, 0.0))

    def _start_cut(self, t, q, why):
        c = self.c; self.theta_cut = self.theta; self.res.cuts += 1
        if self.res.theta_cut_deg is None or why == 'cut':
            self.res.theta_cut_deg = round(self.theta, 2); self.res.q_cut_g_s = round(q, 3); self.res.m_cut_g = round(self.fit.mass, 3)
        delta = c['untilt_fast_big_deg'] if q > c['untilt_big_q_g_s'] else c['untilt_fast_deg']
        self.theta = max(self.theta - delta, 0.0); self.untilt_to = max(self.theta_cut - c['untilt_total_deg'], 0.0)
        self._go('CUT', t, why=why, theta_cut=round(self.theta_cut, 2), q=round(q, 3), delta=delta)

    def _pause(self, t, code, reason):
        self.pause_code = code; self.res.reason = reason
        if self.state in ('RAMP', 'FLOW', 'TOPUP_RAMP', 'TOPUP_PULSE', 'TOPUP_FLOW'):
            self._start_cut(t, self.fit.flow, why=code)                 # stop the stream first, then settle and pause
        else: self._finish(t, 'PAUSE_' + code)

    def _finish(self, t, outcome):
        r = self.res; r.outcome = outcome; r.time_s = round(t - self.t0, 3); r.topup_pulses = self.pulses
        if r.final_g is None and self.fit.mass is not None: r.final_g = round(self.fit.mass, 3)
        if r.final_g is not None: r.error_g = round(r.final_g - self.target, 3)
        self._go('DONE' if not outcome.startswith('PAUSE') else 'PAUSE', t, outcome=outcome)

    @property
    def done(self): return self.state in ('DONE', 'PAUSE')

    # ---------------------------------------------------------------- main loop
    def start(self, t, theta0=0.0):
        self.t0 = t; self.theta = float(theta0); self._go('FAST', t); return self.theta

    def tick(self, t, samples):
        """one control period: new scale samples in, tilt command out"""
        c = self.c; dt = c['control_dt_s']
        new = 0
        for ts, g in samples:
            if self.fit.add(ts, g): new += 1
        m = self.fit.mass if self.fit.mass is not None else 0.0; q = self.fit.flow
        st = self.state; th_prev = self.theta; q_set = None
        if st == 'FAST':
            self.theta = min(self.theta + c['fast_rate_deg_s'] * dt, c['theta_start_deg'])
            if self.theta >= c['theta_start_deg'] - 1e-9: self.m_base = m; self._go('RAMP', t)
        elif st == 'RAMP':
            if self.m_base is None: self.m_base = m
            for _ in range(new): self.n_drop = self.n_drop + 1 if q > c['first_drop_q_g_s'] else 0
            if self.n_drop >= c['first_drop_n'] and m - self.m_base > c['first_drop_dm_g']:
                self.res.theta_first_deg = round(self.theta, 2)
                self.res.v_first_ml = round(self.vt.v_crit_ml(self.theta) + c['fill_offset_ml'], 2)
                self.integ = 0.0; self.theta_ff = self.theta; self.t_first = t; self._go('FLOW', t, v_first_ml=self.res.v_first_ml)
                if self.res.v_first_ml < c['low_fill_ml']:
                    self._pause(t, 'LOW_FILL', 'V_first %.1f mL < %.1f mL: refill %s' % (self.res.v_first_ml, c['low_fill_ml'], self.reagent))
            elif self.theta >= self.theta_pause:
                self._pause(t, 'NO_FLOW', 'no first drop by theta %.1f (V_table %.1f mL): refill %s, or the stream misses the receiver'
                            % (self.theta, c['low_fill_ml'], self.reagent))
            else: self.theta = min(self.theta + c['ramp_rate_deg_s'] * dt, c['theta_max_deg'])
        elif st == 'FLOW':
            q_set = self._q_set(m)
            if self._cut_due(m, q): self._start_cut(t, q, 'cut')
            elif self._spill_check(t, m, q): pass
            elif self.theta >= c['theta_max_deg'] - 1e-9 and m < self.target - self.tol:
                self._pause(t, 'LOW_REAGENT', 'manifold end %.0f deg reached at %.1f g' % (c['theta_max_deg'], m))
            else:
                v_rem = max(self.res.v_first_ml - m / self.rho, 0.5)
                dvdth = self.vt.dv_dtheta_ml_per_deg(self.vt.theta_crit_deg(v_rem))
                dth_ff = -max(q, 0.0) / self.rho / dvdth if dvdth < -1e-3 else 0.0
                e = q_set - q; th_pi = c['kp_deg_per_gs'] * e + c['ki_deg_per_s_per_gs'] * self.integ
                want = self.theta_ff + dth_ff * dt + th_pi
                lim = c['max_rate_deg_s'] * dt; new_th = min(max(want, self.theta - lim), self.theta + lim, c['theta_max_deg'])
                if abs(new_th - want) < 1e-9 or (want > new_th) != (e > 0):   # conditional integration (anti-windup)
                    self.integ += e * dt
                self.theta_ff += dth_ff * dt
                if new_th != want: self.theta_ff = new_th - (c['kp_deg_per_gs'] * e + c['ki_deg_per_s_per_gs'] * self.integ)
                self.theta = new_th
        elif st == 'CUT':
            if self.theta > self.untilt_to: self.theta = max(self.theta - c['untilt_rate_deg_s'] * dt, self.untilt_to)
            if self.theta <= self.untilt_to + 1e-9: self._go('DRIP', t)
        elif st == 'DRIP':
            if t - self.t_state >= c['drip_hold_s']: self._go('SETTLE', t)
        elif st == 'SETTLE':
            settled = (self.fit.span() >= c['settle_window_s'] * 0.9 and abs(q) < c['settle_flow_g_s']
                       and (self.fit.sigma or 0.0) < c['settle_sigma_g'])
            if settled or t - self.t_state >= c['settle_timeout_s']:
                mean = float(np.mean([g for ts, g in zip(self.fit.t, self.fit.m) if ts >= self.fit.t[-1] - c['settle_window_s']]))
                self.res.final_g = round(mean, 3)
                self.res.events.append(dict(t=round(t - self.t0, 3), settled=bool(settled), m=round(mean, 3), sigma=self.fit.sigma, q=round(q, 3)))
                if self.pause_code: self._finish(t, 'PAUSE_' + self.pause_code)
                elif mean < self.target - self.tol:
                    if self.pulses >= c['max_topup_pulses']: self._finish(t, 'PAUSE_TOPUP_LIMIT'); self.res.reason = 'short after %d top-up pulses' % self.pulses
                    else: self._go('TOPUP_RAMP', t, short_g=round(self.target - mean, 3))
                else: self._finish(t, 'OVERSHOOT' if mean > self.target + self.tol else 'OK')
        elif st == 'TOPUP_RAMP':
            goal = self.theta_cut - c['topup_back_deg']
            self.theta = min(self.theta + c['topup_ramp_deg_s'] * dt, goal)
            if self.theta >= goal - 1e-9: self.t_pulse = t; self._go('TOPUP_PULSE', t)
        elif st in ('TOPUP_PULSE', 'TOPUP_FLOW'):
            q_set = c['topup_flow_g_s']
            if self._cut_due(m, q): self._start_cut(t, q, 'cut')
            elif st == 'TOPUP_PULSE' and q > c['topup_flow_g_s']: self._go('TOPUP_FLOW', t, q=round(q, 3))
            elif st == 'TOPUP_FLOW' and q < c['topup_flow_g_s']: self.t_pulse = t; self._go('TOPUP_PULSE', t, q=round(q, 3))
            elif st == 'TOPUP_PULSE' and t - self.t_pulse >= c['topup_period_s']:
                if self.pulses >= c['max_topup_pulses']: self._pause(t, 'TOPUP_LIMIT', 'no top-up flow after %d pulses' % self.pulses)
                elif self.theta >= c['theta_max_deg'] - 1e-9: self._pause(t, 'LOW_REAGENT', 'manifold end reached during top-up at %.1f g' % m)
                else:
                    self.theta = min(self.theta + c['topup_step_deg'], c['theta_max_deg']); self.pulses += 1; self.t_pulse = t
                    self.res.events.append(dict(t=round(t - self.t0, 3), pulse=self.pulses, theta=round(self.theta, 2)))
        self.res.max_theta_deg = round(max(self.res.max_theta_deg or 0.0, self.theta), 2)
        if q_set is not None: self._last_q_set = q_set
        self.res.trace.append((round(t - self.t0, 4), self.state, round(self.theta, 3), round(m, 4), round(q, 4), None if q_set is None else round(q_set, 3)))
        return self.theta

    def _spill_check(self, t, m, q):
        """mass deficit while flowing: liquid the tilt says has left the beaker but the scale has not seen"""
        c = self.c
        if not c['spill_check'] or t - self.t_first < c['spill_arm_s']: return False
        left_g = (self.res.v_first_ml - self.vt.v_crit_ml(self.theta)) * self.rho      # surface at the lip: lower bound
        expected = left_g - c['spill_allow_g'] - c['spill_allow_s'] * max(q, 0.0)
        if expected > 0:
            mg = m - c['spill_ratio'] * expected
            self.res.spill_margin_g = round(mg if self.res.spill_margin_g is None else min(self.res.spill_margin_g, mg), 3)
        if expected > 0 and m < c['spill_ratio'] * expected:
            if self.deficit_since is None: self.deficit_since = t
            if t - self.deficit_since >= c['spill_hold_s']:
                self._pause(t, 'SPILL', 'mass deficit: the tilt implies %.1f g has left the beaker, the scale shows %.1f g' % (left_g, m)); return True
        else: self.deficit_since = None
        return False

    def run(self, clock, samples, set_theta, theta0=0.0, max_s=None):
        """drive the state machine in real (or simulated) time until DONE/PAUSE or max_s"""
        c = self.c; set_theta(self.start(clock.now(), theta0)); samples()
        t_end = clock.now() + (max_s or c['max_pour_s'])
        while not self.done:
            clock.sleep(c['control_dt_s'])
            th = self.tick(clock.now(), samples()); set_theta(th)
            if clock.now() > t_end: self._finish(clock.now(), 'PAUSE_TIMEOUT'); self.res.reason = 'pour exceeded %.0f s' % (max_s or c['max_pour_s'])
        return self.res


def funnel_pour(cfg, clock, set_theta, theta0=0.0, on_tick=None):
    """fixed-profile funnel pour (section 5.6): fast to theta_start, ramp at funnel_rate to funnel_theta, hold
    funnel_hold_s, the same two-stage untilt, drip hold. Open loop (nothing weighs the flask). Returns the trace."""
    c = cfg; dt = c['control_dt_s']; th = float(theta0); t0 = clock.now(); trace = []; phase = 'FAST'; t_ph = t0

    def step(new_phase=None):
        nonlocal phase, t_ph
        set_theta(th); clock.sleep(dt); trace.append((round(clock.now() - t0, 4), phase, round(th, 3)))
        if on_tick: on_tick(clock.now() - t0, phase, th)
        if new_phase: phase = new_phase; t_ph = clock.now()
    while th < c['theta_start_deg'] - 1e-9: th = min(th + c['fast_rate_deg_s'] * dt, c['theta_start_deg']); step()
    phase = 'RAMP'
    while th < c['funnel_theta_deg'] - 1e-9: th = min(th + c['funnel_rate_deg_s'] * dt, c['funnel_theta_deg']); step()
    phase = 'HOLD'; t_ph = clock.now()
    while clock.now() - t_ph < c['funnel_hold_s']: step()
    th_cut = th; th = th - c['untilt_fast_big_deg']; goal = th_cut - c['untilt_total_deg']; phase = 'CUT'
    while th > goal + 1e-9: th = max(th - c['untilt_rate_deg_s'] * dt, goal); step()
    step(); phase = 'DRIP'; t_ph = clock.now()
    while clock.now() - t_ph < c['drip_hold_s']: step()
    return dict(trace=trace, time_s=round(clock.now() - t0, 3), theta_max_deg=c['funnel_theta_deg'])


def fit_cut_law(rows):
    """refit the cut law a + b q by least squares on (q_cut, settled - m_cut) pairs (section 5.4: >= 10 pours)"""
    q = np.array([r[0] for r in rows], float); e = np.array([r[1] for r in rows], float)
    if len(q) < 2: return None
    A = np.vstack([np.ones_like(q), q]).T; (a, b), *_ = np.linalg.lstsq(A, e, rcond=None)
    return dict(a_g=round(float(a), 4), b_s=round(float(b), 4), n=len(q), rms_g=round(float(np.sqrt(np.mean((A @ [a, b] - e) ** 2))), 4))
