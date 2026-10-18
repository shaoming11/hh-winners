import math

import numpy as np
import pytest

from benchsim.chem import liquid
from benchsim.chem.liquid import SyntheticPour, TiltedCylinder, beaker_cylinder, capture_fraction, fall_time_s, weir_flow_ml_s
from benchsim.layout import load_params
from benchsim.process.pour import LineFit, PourController, fit_cut_law
from benchsim.process.pour_sim import ManifoldTilt

P = load_params()


@pytest.fixture(scope='module')
def cyl():
    return beaker_cylinder(P)


# ----------------------------------------------------------------------- tilted cylinder vs closed forms
def test_tilted_cylinder_matches_analytic_cases(cyl):
    r, h = cyl.r, cyl.h
    assert abs(cyl.v_crit_ml(0.0) - math.pi * r * r * h / 1000) < 1e-3                 # upright: brim full
    for th in (10.0, 30.0, 50.0):                                                      # surface clear of the floor: pi r^2 (h - r tan)
        assert math.tan(math.radians(th)) <= h / (2 * r)
        exact = math.pi * r * r * (h - r * math.tan(math.radians(th))) / 1000
        assert abs(cyl.volume_ml(th, 0.0) - exact) < 1e-3 * exact
    th_u = math.degrees(math.atan(h / r))                                              # surface through the floor's centre line: ungula
    assert abs(cyl.volume_ml(th_u, 0.0) - 2.0 / 3.0 * r * r * h / 1000) < 1e-3
    assert cyl.v_crit_ml(90.0) < 1e-6                                                  # horizontal: the lip is the lowest point
    # below the lip (surface inside the cavity, clear of the floor) the free surface is the full ellipse pi r^2 / cos(theta)
    assert abs(cyl.surface_area_mm2(20.0, -1.0) - math.pi * r * r / math.cos(math.radians(20.0))) < 2.0
    assert cyl.surface_area_mm2(20.0, 1.0) < cyl.surface_area_mm2(20.0, -1.0)         # above the lip part of it is past the rim


def test_theta_first_inverts_v_crit(cyl):
    for v in (30.0, 46.0, 60.0, 80.0, 120.0):
        assert abs(cyl.v_crit_ml(cyl.theta_crit_deg(v)) - v) < 0.05
    assert abs(cyl.theta_crit_deg(46.0) - 65.6) < 0.5                                  # architecture 5.2: theta_table(46 mL) ~ 65 deg
    v = np.array([cyl.v_crit_ml(t) for t in np.arange(0, 90, 1.0)])
    assert np.all(np.diff(v) < 0)                                                      # V_c falls monotonically to the horizontal


def test_head_is_consistent_with_volume(cyl):
    for th, s in ((45.0, 2.0), (65.0, 4.0), (80.0, 1.0)):
        v = cyl.volume_ml(th, s)
        assert abs(cyl.head_mm(th, v) - s) < 0.02


# ----------------------------------------------------------------------- flow
def test_flow_monotonic_in_head_volume_and_tilt(cyl):
    L = P['liquid']
    q = [weir_flow_ml_s(h, L['cd'], L['lip_width_mm'], L['hold_head_mm']) for h in np.linspace(0, 10, 41)]
    assert q[0] == 0.0 and all(b >= a for a, b in zip(q, q[1:])) and q[-1] > q[1]
    assert weir_flow_ml_s(L['hold_head_mm'] * 0.9, L['cd'], L['lip_width_mm'], L['hold_head_mm']) == 0.0
    f = liquid.LipFlow(cyl, L)
    qv = [f.flow_ml_s(65.0, v) for v in np.linspace(40, 70, 31)]                      # more liquid at a fixed tilt -> more flow
    assert all(b >= a for a, b in zip(qv, qv[1:])) and qv[-1] > 0 and qv[0] == 0
    qt = [f.flow_ml_s(t, 50.0) for t in np.linspace(55, 80, 26)]                       # more tilt at a fixed volume -> more flow
    assert all(b >= a for a, b in zip(qt, qt[1:])) and qt[-1] > 0 and qt[0] == 0
    dv, h = f.step(80.0, 50.0, 0.001)
    assert 0 < dv < 50.0 and h > L['hold_head_mm']


def test_lipflow_drains_to_the_film(cyl):
    f = liquid.LipFlow(cyl, P['liquid']); v = 30.0
    for _ in range(20000): v -= f.step(105.0, v, 0.001)[0]
    assert abs(v - P['liquid']['residual_film_ml']) < 0.05


# ----------------------------------------------------------------------- landing / spill
def test_capture_fraction_and_fall_time():
    assert capture_fraction(0.0, 26.8, 3.0) == 1.0
    assert capture_fraction(23.0, 26.8, 3.0) == 1.0
    assert capture_fraction(30.0, 26.8, 3.0) == 0.0
    mid = capture_fraction(26.8, 26.8, 3.0)
    assert 0.4 < mid < 0.6                                                             # jet centred on the rim: about half caught
    fr = [capture_fraction(d, 26.8, 3.0) for d in np.linspace(20, 32, 25)]
    assert all(b <= a + 1e-12 for a, b in zip(fr, fr[1:]))
    t = fall_time_s(45.0, 0.0, 0.0)
    assert abs(t - math.sqrt(2 * 45.0 / liquid.G_MM_S2)) < 1e-9
    assert fall_time_s(0.0, 0.0, 10.0) is None                                         # never rises to a higher plane


def test_liquid_model_classifies_landing(sim):
    """parcels released over P1 land in P1; parcels 60 mm off land on the table (spill); over the funnel -> flask"""
    from benchsim.backends.sim import SimWorld
    from benchsim.chem.vessels import Ledger
    model, _, b = sim
    w = SimWorld(model, b); L = Ledger(w); LM = liquid.LiquidModel(w, L)
    L.add('water', 'water', 50.0)
    p1, _ = w.beaker_pose('P1'); rim = p1 + [0, 0, P['beaker']['height']]
    LM._release('water', 1.0, rim + [0, 0, 45.0], 0.0, np.zeros(2), w.time, 0.0, 70.0)
    LM._release('water', 1.0, rim + [60.0, 0, 45.0], 0.0, np.zeros(2), w.time, 0.0, 70.0)
    fun = liquid.mm(w.d.site('funnel_rim').xpos.copy())
    LM._release('water', 1.0, fun + [10.0, 0, 30.0], 0.0, np.zeros(2), w.time, 0.0, 70.0)
    w.advance(P['liquid']['transport_delay_s'] + P['liquid']['funnel_delay_s'] + 0.5)
    LM.flush_spill()
    g = 1.0 * 0.992
    assert abs(L.mass('P1') - g) < 1e-6 and abs(L.mass('flask') - g) < 1e-6 and abs(L.spilled_mass() - g) < 1e-3
    assert abs(L.mass('water') - (50.0 - 3 * g)) < 1e-6


# ----------------------------------------------------------------------- controller on the synthetic plant (no MuJoCo)
def run_synthetic(fill, cfg_over=None, reagent_over=None, seed=0, tol=2.0, **plant):
    cfg = dict(P['pour'], **(cfg_over or {}))
    if reagent_over: cfg['developer'] = dict(cfg['developer'], **reagent_over)
    pl = SyntheticPour(P, fill, seed=seed, **plant)
    pc = PourController(cfg, beaker_cylinder(P), 1.04, 39.0, tol, 'developer')
    r = pc.run(pl, pl.samples, pl.set_theta); pl.sleep(2.0)
    return r, pl


def states(r):
    seq = []
    for e in r.events:
        if 'state' in e and (not seq or seq[-1] != e['state']): seq.append(e['state'])
    return seq


def test_controller_nominal_pour():
    r, pl = run_synthetic(65.0)
    assert r.outcome == 'OK', r.reason
    assert states(r) == ['FAST', 'RAMP', 'FLOW', 'CUT', 'DRIP', 'SETTLE', 'DONE']
    assert abs(pl.recv_g - 39.0) <= 2.0 and abs(r.final_g - pl.recv_g) < 0.2
    assert r.time_s < 25.0 and r.topup_pulses == 0
    assert abs(r.v_first_ml - 65.0) < 3.0                                              # fill inferred from theta_first with the offset
    th = [x[2] for x in r.trace]; dt = P['pour']['control_dt_s']
    flow = [x for x in r.trace if x[1] == 'FLOW']
    assert max(abs(b[2] - a[2]) for a, b in zip(flow, flow[1:])) <= P['pour']['max_rate_deg_s'] * dt + 1e-9
    assert max(th) <= P['pour']['theta_max_deg']


def test_controller_pauses_on_low_fill():
    r, pl = run_synthetic(18.0)                       # below [pour.developer] low_fill_ml (23.1 mL, half dose)
    assert r.outcome in ('PAUSE_NO_FLOW', 'PAUSE_LOW_FILL')
    assert r.max_theta_deg < 82.0 and 'DRIP' in states(r)   # the no-flow pause tilt for low_fill_ml 23.1 mL is 79 deg                            # stopped, untilted, dripped before pausing


def test_controller_tops_up_after_an_early_cut():
    """a cut law that stops too early (b 1.0 s) with a tight tolerance: settle short, then top-up pulses add the rest"""
    r, pl = run_synthetic(70.0, cfg_over=dict(cut_b_s=1.0), tol=0.5)
    settled = [e['m'] for e in r.events if 'settled' in e]
    assert 'TOPUP_PULSE' in states(r) and 'TOPUP_FLOW' in states(r) and r.topup_pulses >= 1 and r.cuts >= 2
    assert settled[0] < 39.0 - 0.5 and pl.recv_g > settled[0] + 0.3                 # the top-up delivered
    assert r.outcome in ('OK', 'PAUSE_TOPUP_LIMIT') and pl.recv_g < 39.5


def test_controller_topup_impossible_when_cut_law_exceeds_tolerance():
    r, pl = run_synthetic(70.0, cfg_over=dict(cut_a_g=5.0))
    assert r.outcome == 'PAUSE_TOPUP_LIMIT' and 'zero flow' in r.reason and r.time_s < 25.0


def test_controller_reports_overshoot_without_correcting():
    r, pl = run_synthetic(70.0, cfg_over=dict(cut_a_g=-4.0, cut_b_s=0.0))
    assert r.outcome == 'OVERSHOOT' and pl.recv_g > 41.0 and 'TOPUP_RAMP' not in states(r)


def test_controller_topup_limit_pauses():
    r, pl = run_synthetic(70.0, cfg_over=dict(cut_b_s=1.0, max_topup_pulses=0), tol=0.5)
    assert r.outcome == 'PAUSE_TOPUP_LIMIT' and r.topup_pulses == 0


def test_controller_low_reagent_at_manifold_end():
    r, pl = run_synthetic(30.0, reagent_over=dict(low_fill_ml=0.0), cfg_over=dict(spill_check=False), seed=3)
    assert r.outcome == 'PAUSE_LOW_REAGENT' and r.max_theta_deg >= P['pour']['theta_max_deg'] - 1e-6
    assert pl.recv_g < 32.0 and pl.v < 1.0                                            # it delivered what there was


def test_spill_check_pauses_on_a_partial_miss():
    r, pl = run_synthetic(70.0, catch=0.3)
    assert r.outcome == 'PAUSE_SPILL' and pl.spilled_g > 0
    r2, _ = run_synthetic(70.0)
    assert r2.outcome == 'OK' and r2.spill_margin_g > 0


def test_linefit_slope_and_outliers():
    f = LineFit(0.5, 5.0, 0.07, 4); rng = np.random.default_rng(0)
    for k in range(80):
        t = k / 80.0; g = 2.0 + 4.0 * t + rng.normal(0, 0.05)
        if k == 60: g += 5.0                                                           # one spike
        f.add(t, g)
    assert abs(f.flow - 4.0) < 0.5 and abs(f.mass - (2.0 + 4.0 * 79 / 80)) < 0.1 and f.rejected == 1


def test_fit_cut_law_recovers_line():
    rows = [(q, 0.2 + 0.1 * q) for q in (1, 2, 3, 5, 8)]
    r = fit_cut_law(rows)
    assert abs(r['a_g'] - 0.2) < 1e-6 and abs(r['b_s'] - 0.1) < 1e-6


def test_manifold_tilt_interpolates():
    class Arm:
        def __init__(self): self.goals = []
        def set_goal(self, q, speed_scale=1.0): self.goals.append(np.array(q))
    arm = Arm(); th = [0.0, 40.0, 41.0]; qs = [np.zeros(6), np.ones(6) * 0.4, np.ones(6) * 0.5]
    t = ManifoldTilt(arm, th, qs, q6_hold=0.12)
    t.set_theta(20.0); t.set_theta(20.001); t.set_theta(40.5); t.set_theta(200.0)
    assert len(arm.goals) == 3
    assert np.allclose(arm.goals[0][:5], 0.2) and arm.goals[0][5] == 0.12
    assert np.allclose(arm.goals[1][:5], 0.45) and np.allclose(arm.goals[2][:5], 0.5)
