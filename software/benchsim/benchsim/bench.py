"""The single place where the backend is chosen.

    make_bench('sim')                       MuJoCo world, simulated arms and Mega (default; no hardware touched)
    make_bench('real', allow_hardware=True) LeRobot SO-101 arms + Mega over serial. Requires the deliberate
                                            command-line flag --real --i-understand-this-moves-hardware
"""
from .interfaces import BenchBackends, MegaClient


class HardwareNotAllowed(RuntimeError):
    pass


def make_bench(mode='sim', allow_hardware=False, world=None, seed=0, **real_kw):
    if mode == 'sim':
        from .backends import sim
        w = world or sim.SimWorld(seed=seed)
        clock = sim.SimClock(w)
        arms = {a: sim.SimArm(w, a) for a in ('pourer', 'transfer')}
        mega = sim.SimMega(w)
        bb = BenchBackends('sim', clock, arms, MegaClient(sim.SimTransport(mega), clock), world=w)
        bb.mega_device = mega
        for a in arms.values(): a.connect()
        return bb
    if mode == 'real':
        if not allow_hardware:
            raise HardwareNotAllowed('real hardware mode needs allow_hardware=True (CLI: --real --i-understand-this-moves-hardware)')
        from .backends import real
        return real.make_real_bench(**real_kw)
    raise ValueError('mode must be sim or real')
