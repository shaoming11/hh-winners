"""The hardware code path (LeRobotArm, SerialTransport/MegaClient, scripts/replay_plan.py) on emulated USB devices."""
import importlib.util
import types

import numpy as np

from benchsim import paths
from benchsim.backends import emu, real, sim
from benchsim.bench import make_bench


def _hw(built):
    model, b = built
    s = make_bench('sim', world=sim.SimWorld(model=model, builder=b))
    return s, emu.make_emulated_bench(s)


def test_emulated_bench_is_the_real_driver_on_the_sim(built):
    s, hw = _hw(built)
    arm = hw.arms['pourer']
    assert isinstance(arm, real.LeRobotArm) and isinstance(hw.transport, real.SerialTransport)
    assert np.allclose(arm.read_positions(), s.arms['pourer'].read_positions(), atol=np.radians(0.2))
    arm.set_torque(True)                                   # torque on holds the present pose
    q = arm.read_positions(); q[0] += np.radians(10)
    arm.set_goal(q, speed_scale=0.5); hw.clock.sleep(2.0)
    assert abs(np.degrees(s.arms['pourer'].read_positions()[0] - q[0])) < 2.0
    assert hw.mega.command('PING')['ok']
    r = hw.mega.motion('TT', done_timeout=6.0, deg=45.0, ms=1500)
    assert abs(r['deg'] - 45.0) < 2.0
    hw.arms['transfer'].set_torque(True)       # a limp SimArm zeroes the gains of the session's shared model


def test_replay_plan_step_1_moves_p1_onto_the_scale(built):
    s, hw = _hw(built)
    spec = importlib.util.spec_from_file_location('replay_plan_t', paths.SIM_ROOT / 'scripts' / 'replay_plan.py')
    rp = importlib.util.module_from_spec(spec); spec.loader.exec_module(rp)
    rp.CLOCK = hw.clock; steps = []
    rp.STEP_HOOKS.append(lambda k, ph: steps.append((k, ph)))
    p0 = np.asarray(s.world.beaker_pose('P1')[0]).copy()
    a = types.SimpleNamespace(speed=0.6, steps=['1'], no_mega=False, yes=True, end_turn=0.0, rest=False, check=False)
    assert rp.replay(hw, a) == 0
    assert steps == [('1 P1 carousel->scale', 'start'), ('1 P1 carousel->scale', 'done')]
    assert np.linalg.norm(np.asarray(s.world.beaker_pose('P1')[0]) - p0) > 0.05     # it was carried, not left behind
