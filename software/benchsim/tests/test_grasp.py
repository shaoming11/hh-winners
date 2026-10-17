import tempfile
from pathlib import Path

import pytest

from benchsim import grasp_demo


@pytest.fixture(autouse=True)
def _tmp_out(monkeypatch):
    monkeypatch.setattr(grasp_demo, 'OUT', Path(tempfile.mkdtemp()))     # keep reports/grasp_demo clean


def test_carousel_to_scale_transfer_and_hold():
    r = grasp_demo.scenario('t_c2s', 'transfer', lambda P: P.plan_transfer('P1', 'carousel_pick', 'scale_pan'), 'dst')
    assert r['status'] == 'passed', r.get('detail')
    assert r['record']['grasps'][0]['outcome'] == 'grasped'
    assert r['hold_slip_max_mm'] < 1.0 and r['hold_tilt_max_deg'] < 2.0
    place = r['record']['scale'][0]
    assert 15 < place['after_g'] - place['before_g'] < 22          # the empty beaker (18 g) appears on the scale


def test_deliberate_miss_detected():
    def remove_p1(w):
        import mujoco
        adr = w.m.jnt_qposadr[w.m.joint('beaker_P1').id]; w.d.qpos[adr:adr + 3] = [0.95, 0.10, 0.0]; mujoco.mj_forward(w.m, w.d)
    r = grasp_demo.scenario('t_miss', 'transfer', lambda P: P.plan_transfer('P1', 'carousel_pick', 'scale_pan'), 'dst', prep=remove_p1)
    assert r['status'] == 'failed' and r['code'] == 'GRASP_MISS'
