import math

import mujoco
import numpy as np
import pytest

from benchsim import fx
from benchsim.backends.sim import SimWorld
from benchsim.bench import make_bench
from benchsim.chem.auger import AugerModel
from benchsim.chem.foam import FoamModel, load_flask
from benchsim.chem.liquid import LiquidModel
from benchsim.chem.vessels import Ledger
from benchsim.render import Renderer


@pytest.fixture
def demo(built):
    """the demo's chemistry on a fresh world: developer in 'dev', water in 'water', the flask charged"""
    model, b = built
    bb = make_bench('sim', world=SimWorld(model=model, builder=b)); w = bb.world
    L = Ledger(w); LM = LiquidModel(w, L); A = AugerModel(w, bb.mega_device, L); F = FoamModel(w, L); load_flask(L)
    L.add('dev', 'developer', 60.0); L.add('water', 'water', 50.0)
    return w, L, LM, A, F


def tilt(w, beaker, deg):
    """turn a beaker about +X in place (its free joint), as a pour would"""
    j = w.m.joint('beaker_' + beaker); a = j.qposadr[0]; h = math.radians(deg) / 2
    w.d.qpos[a + 2] += 0.08; w.d.qpos[a + 3:a + 7] = [math.cos(h), math.sin(h), 0, 0]; mujoco.mj_forward(w.m, w.d)


def model_arrays(m, d):
    return [x.copy() for x in (m.geom_rgba, m.geom_size, m.geom_pos, m.geom_matid, m.light_diffuse, d.qpos, d.geom_xpos)]


def test_context_finds_the_models(demo):
    w, L, LM, A, F = demo
    ctx = fx.Context.from_world(w)
    assert ctx.L is L and ctx.LM is LM and ctx.A is A and ctx.F is F
    assert ctx.streams() == [] and ctx.auger() is None and ctx.foam()['column_mm'] == 0
    lv = {x['name']: x for x in ctx.levels()}
    assert lv['dev']['volume_ml'] > 50 and lv['P1']['volume_ml'] == 0 and lv['dev']['tilt_deg'] < 1


def test_stream_follows_the_pour(demo):
    w, L, LM, A, F = demo
    tilt(w, 'dev', 100.0); w.step()
    s = fx.Context.from_world(w).streams()
    assert [x['src'] for x in s] == ['dev']
    pts = s[0]['points']
    assert np.allclose(pts[0], LM.lip('dev')[0]) and np.all(np.diff(pts[:, 2]) < 0)    # leaves the lip and falls
    assert pts[-1][2] >= -1e-6                                                          # lands on something (here the table)


def test_fx_draws_into_the_scene_only(demo):
    w, L, LM, A, F = demo
    tilt(w, 'dev', 100.0); w.step()
    L.add('flask', 'developer', 39.0); L.put('flask', dict(yeast=7.0, water=30.0)); w.idle(12.0)      # foam over the neck
    assert F.column_mm() > 0
    look = fx.make(w); plain = Renderer(w.m, 320, 180); pretty = Renderer(w.m, 320, 180, fx=look)
    try:
        before = model_arrays(w.m, w.d)
        plain.frame(w.d, 'overview'); n_plain = plain.r.scene.ngeom
        img = pretty.frame(w.d, 'erupt_cam'); n_fx = pretty.r.scene.ngeom
        for a, b in zip(before, model_arrays(w.m, w.d)): assert np.array_equal(a, b)
        assert n_fx > n_plain + 100 and n_fx < pretty.r.scene.maxgeom and img.shape == (180, 320, 3)
        hidden = [g for g in (w.m.geom('foam').id, w.m.geom('liquid_dev').id)]
        sc = pretty.r.scene
        for i in range(sc.ngeom):
            if sc.geoms[i].objtype == mujoco.mjtObj.mjOBJ_GEOM and sc.geoms[i].objid in hidden: assert sc.geoms[i].rgba[3] == 0
        assert max(look.ms) < 50.0
    finally:
        plain.close(); pretty.close()


def test_plain_renderer_draws_no_sites(built):
    model, b = built
    w = SimWorld(model=model, builder=b); r = Renderer(w.m, 160, 90)
    try:
        r.frame(w.d, 'overview'); sc = r.r.scene; site = int(mujoco.mjtObj.mjOBJ_SITE)
        assert not any(sc.geoms[i].objtype == site for i in range(sc.ngeom))
    finally:
        r.close()
