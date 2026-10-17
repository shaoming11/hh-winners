import math

import mujoco
import numpy as np
import pytest

from benchsim import layout, scene
from benchsim.backends.sim import SimMega, SimWorld
from benchsim.bench import make_bench
from benchsim.chem.auger import AugerModel
from benchsim.chem.foam import FoamModel, load_flask, o2_yield_ml
from benchsim.chem.vessels import Ledger
from benchsim.mechanisms import (Mechanisms, crank_for_travel, deck_angle, first_pass_rev, slider_crank_travel, station_table, topup_rev,
                                 travel_ms)
from benchsim.units import m, mm
from benchsim.verify_mechanisms import ScaleHooks, place


@pytest.fixture(scope='module')
def fresh():
    """a private model: these tests resize the foam geom and drive the Mega actuators"""
    return scene.build()


def auger_rig(model, b, seed=3):
    w = SimWorld(model, b); mega = SimMega(w); L = Ledger(w, apply_weight=False); return w, mega, L, AugerModel(w, mega, L, seed=seed)


def turn(mega, aug, rev, step=0.01):
    """drive the hook the way SimMega does: angle first, then the signed revolutions of the step"""
    n = int(round(abs(rev) / step)); s = math.copysign(step, rev)
    for _ in range(n): mega.aug_angle += 360.0 * s; aug.on_revs(s)


# ======================================================================= stage
def test_slider_crank_formula():
    S = layout.load_params()['stage']; r, L = S['crank_r'], S['rod_l']
    assert slider_crank_travel(0.0, r, L) == pytest.approx(0.0, abs=1e-12)
    assert slider_crank_travel(S['erupt_deg'], r, L) == pytest.approx(S['expected_travel_mm'], abs=0.05)
    assert slider_crank_travel(180.0, r, L) == pytest.approx(2 * r)
    s = [slider_crank_travel(t, r, L) for t in np.arange(0.0, 180.01, 1.0)]
    assert np.all(np.diff(s) > 0)
    for t in (10.0, 47.5, 90.0, 150.0):                 # the rod stays L long: crank pin to sled pin on the slider axis
        pin = np.array([-r * math.sin(math.radians(t)), r * math.cos(math.radians(t))]); sled = np.array([0.0, r + L - slider_crank_travel(t, r, L)])
        assert np.linalg.norm(sled - pin) == pytest.approx(L)
    assert crank_for_travel(slider_crank_travel(123.0, r, L), r, L) == pytest.approx(123.0, abs=1e-6)


# ======================================================================= carousel
def test_carousel_station_angles(fresh):
    model, b = fresh; bench = b.bench; C = bench['params']['carousel']; st = bench['stations']
    tab = {(r['pocket'], r['station']): r['deck_deg'] for r in station_table(bench)}
    want = {(0, 'pick'): 0, (0, 'auger'): 180, (1, 'pick'): 270, (1, 'auger'): 90, (2, 'pick'): 180, (2, 'auger'): 0, (3, 'pick'): 90, (3, 'auger'): 270}
    for k, v in want.items(): assert tab[k] == pytest.approx(v, abs=0.1), k
    assert all(C['deck_range_deg'][0] <= v <= C['deck_range_deg'][1] for v in tab.values())
    assert deck_angle(0.0, 300.0, C['deck_range_deg']) is None          # outside the 270 deg servo travel + trim
    d = mujoco.MjData(model); qa = model.joint('carousel').qposadr[0]
    for (k, s), a in tab.items():                     # the compiled model puts that pocket on the update13_final station
        d.qpos[qa] = math.radians(a); mujoco.mj_kinematics(model, d)
        assert np.linalg.norm(mm(d.site('pocket%d' % k).xpos[:2]) - st['carousel_' + s]['xy']) < 0.2, (k, s)
    assert travel_ms(180.0, C) == 8000 and travel_ms(45.0, C) == 2000 and travel_ms(0.0, C) == 0


def test_pocket_bookkeeping():
    class Stub: clock = None
    mech = Mechanisms(Stub())
    assert mech.beaker_at('pick') == 'P1' and mech.pocket_of('P2') == 1 and mech.pocket_at('auger') == 2
    with pytest.raises(ValueError): mech.remove('P2')                   # P2 is not at the pick at deck 0
    mech.deck = mech.deck_for(1, 'pick'); assert mech.beaker_at('pick') == 'P2' and mech.pocket_at('auger') == 3
    assert mech.remove('P2') == 1 and mech.pockets == ['P1', None, None, None]
    with pytest.raises(KeyError): mech.pocket_of('P2')
    assert mech.insert('P2') == 1
    with pytest.raises(ValueError): mech.insert('P2')


def test_dose_arithmetic():
    P = layout.load_params(); A, M = P['auger'], P['auger_model']
    assert first_pass_rev(7.0, 0.85, A, M) == pytest.approx(7.0)        # 85 % of 7 g at 0.85 g/rev
    assert topup_rev(7.0, 5.95, 0.85, M) == pytest.approx(1.2)          # round(1.235, 0.1)


# ======================================================================= auger model
def test_auger_g_per_rev_statistics(fresh):
    w, mega, L, aug = auger_rig(*fresh); aug.fill(1000.0); P = w.P; n = 400
    turn(mega, aug, n)
    g = np.array(aug.draws); mu = P['auger']['g_per_rev_nominal'] * P['auger_model']['true_over_nominal']; cv = P['auger']['g_per_rev_cv']
    assert len(g) == n and len(aug.rev_grams) == n
    assert abs(g.mean() - mu) < 4 * cv * mu / math.sqrt(n)
    assert abs(g.std(ddof=1) / g.mean() - cv) < 0.25 * cv
    assert 1000.0 - L.mass('hopper') == pytest.approx(g.sum()) == pytest.approx(sum(aug.rev_grams))
    assert 'HOPPER_EMPTY' not in mega.faults


def test_auger_reverse_returns_nothing_and_landing(fresh):
    w, mega, L, aug = auger_rig(*fresh); aug.fill(50.0)
    p = mm(w.d.site('pocket2').xpos); place(w, 'P2', p[:2], p[2])     # P2 under the outlet (pocket 2 at deck 0)
    assert aug.receiver() == 'P2'
    turn(mega, aug, 1.0); g1 = L.mass('P2'); assert g1 > 0 and aug.spilled_g == 0
    h = L.mass('hopper'); turn(mega, aug, -0.25)
    assert L.mass('hopper') == h and L.mass('P2') == g1                # reverse: nothing back, nothing out
    turn(mega, aug, 0.25); assert L.mass('P2') == pytest.approx(g1)     # re-covering the reverse dispenses nothing
    turn(mega, aug, 0.5); assert L.mass('P2') > g1
    q = mm(w.d.site('pocket1').xpos); place(w, 'P2', q[:2], q[2])       # nothing under the outlet -> spill
    assert aug.receiver() is None
    g2 = L.mass('P2'); turn(mega, aug, 1.0); aug.flush()
    assert L.mass('P2') == g2 and aug.spilled_g > 0 and L.spilled_mass() == pytest.approx(aug.spilled_g, abs=1e-3)


def test_hopper_empty_fault(fresh):
    w, mega, L, aug = auger_rig(*fresh); aug.fill(2.0)
    turn(mega, aug, 11.0); assert 'HOPPER_EMPTY' not in mega.faults    # revs 2..11 still carry > 1 g
    turn(mega, aug, 2.0); assert 'HOPPER_EMPTY' in mega.faults


def test_dose_procedure_on_sim_scale(fresh):
    model, b = fresh; bb = make_bench('sim', world=SimWorld(model, b, seed=5)); w = bb.world; P = w.P; R = P['recipe']
    L = Ledger(w); aug = AugerModel(w, bb.mega_device, L, seed=5); aug.fill(P['auger_model']['hopper_load_g'])
    mech = Mechanisms(bb.mega); H = ScaleHooks(bb, mech); H.tare_beaker('P2')
    r = mech.dose_yeast('P2', R['yeast_g'], H.weigh, H.back)
    assert r.ok and abs(r.error_g) <= R['yeast_tol_g'] and r.topups <= P['auger']['max_topups'], r.to_dict()
    assert abs(L.mass('P2') - R['yeast_g']) <= R['yeast_tol_g'] and aug.spilled_g == 0
    assert 'P2' not in mech.pockets                                       # left on the scale for the water pour
    assert r.passes[0]['rev_cmd'] == pytest.approx(first_pass_rev(R['yeast_g'], P['auger']['g_per_rev_nominal'], P['auger'], P['auger_model']))
    H.back('P2'); mech.insert('P2'); L.take('P2', L.mass('P2')); w.auger_jam = True
    r = mech.dose_yeast('P2', R['yeast_g'], H.weigh, H.back)
    assert r.status == 'fault' and r.fault == 'AUGER_JAM' and not r.passes


# ======================================================================= foam
def run_foam(model, b, parts, soap=True, seconds=40.0):
    w = SimWorld(model, b); L = Ledger(w, apply_weight=False)
    if soap: load_flask(L)
    f = FoamModel(w, L); L.put('flask', parts); w.idle(seconds); return w, f


def test_foam_growth_and_zero_cases(fresh):
    model, b = fresh; R = layout.load_params()['recipe']; F = layout.load_params()['foam']
    w, f = run_foam(model, b, dict(developer=R['developer_g'], yeast=R['yeast_g'], water=R['water_g']))
    tr = f.trace; made = np.array([x['foam_ml'] for x in tr]); o2 = np.array([x['o2_ml'] for x in tr]); col = np.array([x['column_mm'] for x in tr])
    ip = int(np.argmax(col))
    assert np.all(np.diff(made) >= 0) and np.all(np.diff(o2) >= 0) and np.all(np.diff(col[:ip + 1]) >= 0)
    assert f.peak_mm > 0 and f.t_neck is not None and f.t_neck >= F['induction_s']
    y = o2_yield_ml(R['developer_g'], F); assert abs(y - 1700.0) < 50.0           # demo_process 1: about 1.7 L
    assert 0.9 * y < f.o2_ml <= y + 1e-6
    g = model.geom('foam').id                                                     # the geom follows the column on the sled
    assert model.geom_size[g, 1] == pytest.approx(m(f.column_mm() / 2)) and model.geom_rgba[g, 3] > 0
    for parts, soap in ((dict(developer=R['developer_g'], water=R['water_g']), True), (dict(yeast=R['yeast_g'], water=R['water_g']), True)):
        _, z = run_foam(model, b, parts, soap)
        assert z.foam_ml == 0.0 and z.peak_mm == 0.0 and z.o2_ml == 0.0 and model.geom_rgba[g, 3] == 0.0
    _, ns = run_foam(model, b, dict(developer=R['developer_g'], yeast=R['yeast_g'], water=R['water_g']), soap=False)
    assert ns.o2_ml > 0 and ns.foam_ml == 0.0 and ns.peak_mm == 0.0                # no soap: the O2 escapes as bubbles
