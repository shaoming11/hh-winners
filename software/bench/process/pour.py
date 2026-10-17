"""Closed-loop gravimetric pour (software_architecture.md 5), driven along a pour manifold.

The manifold (motion/stations.PourPlan) maps tilt theta -> joint pose.  The controller owns
theta: it ramps at 3 deg/s until the first drop, then follows feed-forward + PI on the flow
estimate from the scale, cuts when  m_f >= target - (a + b * q_hat), untilts 5 deg fast then
at <= 60 deg/s to theta_cut - 15, holds 1.5 s for drips, and tops up with 0.5 deg pulses.
Funnel pours are open-loop: the same manifold, fixed profile to theta_end, nothing to weigh.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from bench.config import Config, load
from bench.hal.base import Bench, BenchFault
from bench.motion.player import Player
from bench.motion.stations import PourPlan, StationPlanner
from bench.process.scale import Scale


@dataclass
class PourLog:
    target_g: float
    theta_first: float = float("nan")
    theta_cut: float = float("nan")
    q_cut: float = float("nan")
    settled_g: float = float("nan")
    error_g: float = float("nan")
    topups: int = 0
    duration_s: float = 0.0
    trace: list = field(default_factory=list)     # (t, theta, m_f, q_hat, q_star)
    outcome: str = ""


class PourController:
    def __init__(self, bench: Bench, player: Player, scale: Scale, plan: PourPlan,
                 cfg: Config | None = None, log=print, planner: StationPlanner | None = None,
                 via=None):
        """`via`: high joint-space waypoints to pass through on the way in (and back out), so
        the held beaker crosses the bench at carry height instead of sweeping through the
        funnel/scale area."""
        self.via = [list(v) for v in (via or [])]
        self.b = bench
        self.player = player
        self.scale = scale
        self.plan = plan
        self.cfg = cfg or load()
        self.c = self.cfg.at("control.pour")
        self.log = log
        self.th = np.array(plan.thetas)
        self.qs = np.array(plan.qs)
        self.theta = float(self.th[0])
        self._tilt_in = None
        self.planner = planner

    # ---------------------------------------------------------------- manifold
    def q_at(self, theta: float) -> np.ndarray:
        theta = float(np.clip(theta, self.th[0], self.th[-1]))
        return np.array([np.interp(theta, self.th, self.qs[:, j]) for j in range(5)])

    def set_theta(self, theta: float) -> None:
        self.theta = float(np.clip(theta, self.th[0], self.th[-1]))
        g = self.q_at(self.theta)
        self.player._write(g)

    def enter(self) -> None:
        """From wherever the arm is (holding the beaker upright): entry pose, then tilt in to
        theta_start along the tilt-in path."""
        for v in self.via:
            self.player.move_to(v, 55)
        self.player.move_to(self.plan.entry.q, 45)
        if self._tilt_in is None:
            planner = self.planner or StationPlanner(self.cfg)
            self._tilt_in = planner.plan_tilt_in(self.plan)
        for q in self._tilt_in:
            self.player.move_to(q, 40, settle_tol=3.0, settle_timeout=0.4)
        self.theta = float(self.th[0])

    def leave(self) -> None:
        """Untilt to theta_start, then back out through the tilt-in path to the entry pose."""
        self.ramp_to(self.th[0], rate=float(self.c["untilt_rate_dps"]))
        for q in reversed(self._tilt_in or [self.plan.entry.q]):
            self.player.move_to(q, 40, settle_tol=3.0, settle_timeout=0.4)
        self.player.move_to(self.plan.entry.q, 45)
        for v in reversed(self.via):
            self.player.move_to(v, 55)

    def ramp_to(self, theta: float, rate: float, timeout_s: float = 30.0) -> None:
        theta = float(np.clip(theta, self.th[0], self.th[-1]))     # never chase a point off the manifold
        t0 = self.b.clock.now()
        while abs(self.theta - theta) > 1e-3 and self.b.clock.now() - t0 < timeout_s:
            d = np.clip(theta - self.theta, -rate * self.player.TICK, rate * self.player.TICK)
            self.set_theta(self.theta + d)
            self.b.clock.sleep(self.player.TICK)

    # ---------------------------------------------------------------- closed loop
    def pour_to(self, target_g: float, label: str = "") -> PourLog:
        c = self.c
        sc = self.cfg.at("control.scale")
        lg = PourLog(target_g)
        t0 = self.b.clock.now()
        self.scale.reset_fit()
        self.scale.next(); self.scale.next()
        base = self.scale.wait_settled(2.0)         # mass already on the pan (net of tare)
        goal = base + target_g
        self.log(f"  pour {label}: +{target_g:.1f} g (pan {base:.1f} g -> {goal:.1f} g)")

        # --- ramp until the first drop
        first = False; drops = 0; m_prev = base
        ramp = float(c["ramp_dps"]); dt = 1.0 / sc["rate_hz"]
        theta_first = None
        while not first:
            s = self.scale.next()
            self.set_theta(self.theta + ramp * dt)
            if s.q_hat > sc["first_drop_rate_gps"] and s.m_f - base > sc["first_drop_dm_g"]:
                drops += 1
                if drops >= sc["first_drop_samples"]:
                    first = True; theta_first = self.theta
            else:
                drops = 0
            if self.theta >= self.th[-1] - 0.5:
                lg.outcome = "PAUSE low reagent"
                self.log("  pour: reached the end of the manifold with no flow - low reagent")
                return self._finish(lg, t0)
            if self.b.clock.now() - t0 > c["timeout_s"]:
                lg.outcome = "timeout"
                return self._finish(lg, t0)
        lg.theta_first = theta_first
        self.log(f"  pour: first drop at theta {theta_first:.1f} deg")

        # --- PI on flow around a mass-dependent set-point, feed-forward from a nominal dV/dtheta
        kp, ki = float(c["kp"]), float(c["ki"])
        integ = 0.0; cut = False
        rate_clamp = float(c["rate_clamp_dps"])
        while not cut:
            s = self.scale.next()
            remaining = goal - s.m_f
            q_star = float(np.clip(c["flow_setpoint_k"] * remaining, c["flow_min_gps"], c["flow_ceiling_gps"]))
            err = q_star - s.q_hat
            # conditional integration: only when not clamped
            dth_ff = 0.6 * q_star / 8.0 * 3.0          # ~3 deg/s at the ceiling flow
            dth_pi = kp * err + ki * integ
            dth = float(np.clip(dth_ff + dth_pi, -rate_clamp, rate_clamp))
            if abs(dth_ff + dth_pi) < rate_clamp:
                integ += err * dt
            self.set_theta(self.theta + dth * dt)
            lg.trace.append((round(self.b.clock.now() - t0, 3), round(self.theta, 2),
                             round(s.m_f, 3), round(s.q_hat, 3), round(q_star, 2)))
            if s.m_f >= goal - (c["cut_a_g"] + c["cut_b_s"] * max(s.q_hat, 0.0)):
                cut = True
                lg.theta_cut, lg.q_cut = self.theta, s.q_hat
            if self.theta >= self.th[-1] - 0.5:
                lg.outcome = "PAUSE low reagent (mid-pour)"
                cut = True; lg.theta_cut, lg.q_cut = self.theta, s.q_hat
            if self.b.clock.now() - t0 > c["timeout_s"]:
                lg.outcome = "timeout"; cut = True; lg.theta_cut, lg.q_cut = self.theta, s.q_hat
        self.log(f"  pour: cut at theta {lg.theta_cut:.1f} deg, flow {lg.q_cut:.2f} g/s, m {s.m_f:.2f}")

        # --- untilt: fast step, then <= 60 deg/s to theta_cut - 15, then drip hold
        fast = float(c["untilt_fast_deg_highflow"] if lg.q_cut > 5 else c["untilt_fast_deg"])
        self.set_theta(self.theta - fast)
        self.scale.next()
        back = min(lg.theta_cut - float(c["untilt_back_deg"]), lg.theta_first - 4.0)   # below first drop
        self.ramp_to(max(back, self.th[0]), float(c["untilt_rate_dps"]))
        hold_until = self.b.clock.now() + float(c["drip_hold_s"])
        while self.b.clock.now() < hold_until:
            self.scale.next()

        # --- verify, top up if short (one-sided: overshoot is reported, not corrected)
        m = self.scale.read_settled()
        pulses = 0
        while goal - m > self.cfg.at("recipe.developer_tol_g") * 0.5 and pulses < int(c["topup_max_pulses"]) \
                and not lg.outcome:
            self.ramp_to(lg.theta_cut - 3.0, 10.0)
            pulses += 1
            self.set_theta(self.theta + float(c["topup_pulse_deg"]) * pulses)
            t_end = self.b.clock.now() + float(c["topup_period_s"])
            flowing = False
            while self.b.clock.now() < t_end:
                s = self.scale.next()
                if s.q_hat > 0.3 or s.m_f >= goal - c["cut_a_g"]:
                    flowing = True
                    break
            self.set_theta(self.theta - 6.0)
            hold_until = self.b.clock.now() + 1.0
            while self.b.clock.now() < hold_until:
                self.scale.next()
            m = self.scale.read_settled()
            self.log(f"  pour: top-up {pulses} -> {m:.2f} g")
            if flowing and goal - m <= 0.3:
                break
        lg.topups = pulses
        lg.settled_g = m - base
        lg.error_g = lg.settled_g - target_g
        if not lg.outcome:
            lg.outcome = "ok" if abs(lg.error_g) <= self.cfg.at("recipe.developer_tol_g") else "out of tolerance"
        self.log(f"  pour {label}: delivered {lg.settled_g:.2f} g (error {lg.error_g:+.2f} g, "
                 f"{lg.topups} top-ups) -> {lg.outcome}")
        return self._finish(lg, t0)

    def pour_all(self, seconds_at_end: float = 5.0) -> PourLog:
        """Open-loop funnel pour: run the manifold to the end, dwell, untilt."""
        lg = PourLog(float("nan"))
        t0 = self.b.clock.now()
        self.ramp_to(self.th[-1], 12.0)
        hold = self.b.clock.now() + seconds_at_end
        while self.b.clock.now() < hold:
            self.b.clock.sleep(0.05)
        self.ramp_to(max(self.th[-1] - 15.0, self.th[0]), float(self.c["untilt_rate_dps"]))
        hold = self.b.clock.now() + float(self.c["drip_hold_s"])
        while self.b.clock.now() < hold:
            self.b.clock.sleep(0.05)
        lg.theta_cut = self.th[-1]; lg.outcome = "ok"
        return self._finish(lg, t0)

    def _finish(self, lg: PourLog, t0: float) -> PourLog:
        lg.duration_s = self.b.clock.now() - t0
        return lg
