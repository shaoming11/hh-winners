"""Quick stills of the camera look, plain | fx side by side, for working on benchsim.fx without running the whole demo.

    python -m benchsim.fx.preview                       # every scene
    python -m benchsim.fx.preview --scene pour funnel   # developer onto P1 at the scale; P1 into the funnel
    python -m benchsim.fx.preview --scene dose foam bench

Writes runs/fx_preview/<scene>/<sim time>_<camera>.png (left plain, right fx) and prints the fx draw time per frame.
"""
import argparse
import math
import sys
import time

import mujoco
import numpy as np

from .. import paths
from ..chem.vessels import DENSITY
from ..render import Renderer
from ..units import m
from . import make

OUT = paths.SIM_ROOT / 'runs' / 'fx_preview'
W, H = 960, 540


def free_cam(lookat_mm, dist_mm, azimuth, elevation):
    c = mujoco.MjvCamera(); c.type = mujoco.mjtCamera.mjCAMERA_FREE
    c.lookat[:] = m(np.asarray(lookat_mm, float)); c.distance = dist_mm / 1000.0; c.azimuth = azimuth; c.elevation = elevation
    return c


class Shooter:
    """frame hook: plain and fx stills of each camera, every ``every`` s of sim time while ``when(world)`` holds"""

    def __init__(self, world, scene, cams, every=0.5, when=lambda w: True, max_shots=10):
        self.w = world; self.dir = OUT / scene; self.dir.mkdir(parents=True, exist_ok=True)
        for old in self.dir.glob('*.png'): old.unlink()
        self.cams = cams; self.every = every; self.when = when; self.max = max_shots; self.next = -1.0; self.n = 0
        self.fx = make(world); self.plain = Renderer(world.m, W, H); self.pretty = Renderer(world.m, W, H, fx=self.fx)

    def hook(self, w):
        if self.n >= self.max or w.time < self.next or not self.when(w): return
        self.next = w.time + self.every; self.shoot()

    def shoot(self, label=None):
        import imageio.v3 as iio
        for name, cam in self.cams.items():
            a = self.plain.frame(self.w.d, cam); b = self.pretty.frame(self.w.d, cam)
            iio.imwrite(self.dir / ('%07.2f_%s%s.png' % (self.w.time, name, '_' + label if label else '')), np.concatenate([a, b], axis=1))
        self.n += 1

    def close(self):
        ms = self.fx.ms
        if ms: print('  %s: %d frames, fx draw %.2f ms mean, %.2f ms max -> %s' % (self.dir.name, len(ms), float(np.mean(ms)), max(ms), self.dir))
        self.plain.close(); self.pretty.close()


def demo_world(seed=0):
    """the full demo's bench and chemistry, as demo_run.SimDemo sets it up (nothing run)"""
    from ..bench import make_bench
    from ..chem.auger import AugerModel
    from ..chem.foam import FoamModel, load_flask
    from ..chem.liquid import LiquidModel
    from ..chem.vessels import Ledger
    from ..demo_run import INITIAL
    bb = make_bench('sim', seed=seed); w = bb.world
    L = Ledger(w); LM = LiquidModel(w, L); aug = AugerModel(w, bb.mega_device, L, seed=seed); foam = FoamModel(w, L); load_flask(L)
    L.add('dev', 'developer', INITIAL['developer_ml'] * DENSITY['developer']); L.add('water', 'water', INITIAL['water_ml'] * DENSITY['water'])
    aug.fill(INITIAL['hopper_g'])
    return bb, L, LM, aug, foam


# ====================================================================== scenes
def bench():
    bb, L, *_ = demo_world(); w = bb.world; w.advance(0.3)
    sh = Shooter(w, 'bench', {c: c for c in ('overview', 'bench_cam', 'foam_cam', 'top')}); sh.shoot(); sh.close()


def pour():
    from ..chem.liquid import beaker_cylinder
    from ..layout import load_params
    from ..pour_trials import PourRig, Tracer
    from ..process.pour import PourController
    P = load_params(); R = P['recipe']
    rig = PourRig(0); rig.place('P1', 'scale_pan'); rig.L.add('dev', 'developer', 60.0 * DENSITY['developer'])
    segs, info, tilt, grasp = rig.to_prepour('dev'); rig.tare()
    sc = rig.w.d.site('scale_centre').xpos * 1000.0
    cams = {'overview': 'overview', 'pour_cam': 'pour_cam', 'side': free_cam(sc + [0, 0, 60], 300, 120, -8)}
    LM = rig.LM; sh = Shooter(rig.w, 'pour', cams, every=0.6, when=lambda w: any(q > 0 for q in LM.q_ml_s.values()) or any(f > 1e-3 for f in LM.film.values()))
    rig.w.frame_hooks.append(sh.hook)
    pc = PourController(P['pour'], beaker_cylinder(P), DENSITY['developer'], R['developer_g'], R['developer_tol_g'], 'developer')
    tr = Tracer(rig, 'dev', 'P1', tilt, pc); pc.run(rig.clock, tr.samples, tr.set_theta)
    sh.close()


def funnel():
    from ..layout import load_params
    from ..pour_trials import PourRig, Tracer
    from ..process.pour import funnel_pour
    P = load_params()
    rig = PourRig(0); rig.place('P1', 'scale_pan'); rig.L.add('P1', 'developer', P['recipe']['developer_g'])
    segs, info, tilt, grasp = rig.to_prepour('funnel')
    rim = rig.w.d.site('funnel_rim').xpos * 1000.0
    cams = {'overview': 'overview', 'funnel_cam': 'funnel_cam', 'close': free_cam(rim + [0, 0, 10], 420, 160, -22)}
    LM = rig.LM; sh = Shooter(rig.w, 'funnel', cams, every=0.5, when=lambda w: any(q > 0 for q in LM.q_ml_s.values()) or any(
        p['recv'] == 'funnel' for _, _, p in LM.parcels))
    rig.w.frame_hooks.append(sh.hook)
    tr = Tracer(rig, 'P1', 'flask', tilt); funnel_pour(P['pour'], rig.clock, tr.set_theta)
    rig.clock.sleep(P['liquid']['funnel_delay_s'] + 0.5); sh.close()


def dose():
    from ..mechanisms import Mechanisms
    bb, L, LM, aug, foam = demo_world(); w = bb.world; mech = Mechanisms(bb.mega)
    mech.carousel_to('P2', 'auger')
    o = w.d.site('auger_outlet').xpos * 1000.0; u = o[:2] - w.d.body('carousel').xpos[:2] * 1000.0     # look outward from the deck centre
    cams = {'bench_cam': 'bench_cam', 'close': free_cam(o - [0, 0, 70], 260, math.degrees(math.atan2(u[1], u[0])) + 25, -20)}
    sh = Shooter(w, 'dose', cams, every=0.7, when=lambda w: bool(aug.mega.motion and aug.mega.motion.get('cmd') == 'AUG'), max_shots=5)
    w.frame_hooks.append(sh.hook); mech.auger(4.0); sh.shoot('after'); sh.close()


def foam():
    from ..mechanisms import Mechanisms
    from ..verify_mechanisms import STAGE_START_S
    bb, L, LM, aug, fm = demo_world(); w = bb.world; Rc = w.P['recipe']; mech = Mechanisms(bb.mega)
    L.add('flask', 'developer', Rc['developer_g']); w.advance(0.2)
    t0 = w.time; L.put('flask', dict(yeast=Rc['yeast_g'], water=Rc['water_g'])); w.advance(STAGE_START_S); mech.stage_to('ERUPT')
    cams = {'foam_cam': 'foam_cam', 'erupt_cam': 'erupt_cam', 'overview': 'overview'}
    sh = Shooter(w, 'foam', cams, max_shots=99)
    for tf in (3.0, 4.5, 6.0, 8.0, 12.0, 20.0, 35.0, 60.0):
        if t0 + tf > w.time: w.idle(t0 + tf - w.time)
        sh.shoot('t+%04.1fs' % tf)
    sh.close()


SCENES = dict(bench=bench, pour=pour, funnel=funnel, dose=dose, foam=foam)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m benchsim.fx.preview')
    ap.add_argument('--scene', nargs='+', choices=sorted(SCENES), default=list(SCENES))
    a = ap.parse_args(argv)
    for s in a.scene:
        t = time.time(); SCENES[s](); print('  %s done in %.0f s' % (s, time.time() - t), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
