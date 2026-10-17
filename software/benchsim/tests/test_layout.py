from benchsim import layout, meshfit, verify_layout
import json


def test_final_layout_status():
    u = layout.load_final()
    assert u['status'] == 'ALL 8 STEPS PASS'


def test_station_centres_within_1mm(sim):
    model, data, b = sim
    rows = verify_layout.measure(model, data, b)
    bad = [r for r in rows if not r['pass_']]
    assert not bad, bad


def test_beakers_settle(sim):
    model, data, b = sim
    rows = verify_layout.settle(model, data, b)
    assert all(r['pass_'] for r in rows), rows


def test_cad_mesh_fits_recorded():
    fits = json.loads(meshfit.FITS_JSON.read_text())
    fitted = {f['part'].split()[0]: f for f in fits if f['residual_mm'] is not None}
    assert fitted['RK-03']['residual_mm'] < 0.5 and fitted['TT-04']['residual_mm'] < 0.5


def test_known_bearing_disagreements_reported():
    rows = layout.cross_checks(layout.load_bench())
    t = {(r['arm'], r['station']): r for r in rows}
    assert abs(t[('transfer', 'scale')]['dbearing']) > 5     # recorded -5 vs computed +4.5
