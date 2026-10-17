import math

import numpy as np

from sim.chemistry import Chemistry


def test_capacity_shape():
    r, h = 28.0, 74.0
    full = math.pi * r * r * h / 1000.0
    caps = [Chemistry.capacity_ml(r, h, math.radians(t)) for t in range(0, 90, 5)]
    assert abs(caps[0] - full) < 1e-6                       # upright: the whole cylinder
    assert all(a >= b - 1e-9 for a, b in zip(caps, caps[1:]))   # monotonically decreasing
    assert caps[-1] < 0.05 * full                            # nearly horizontal: nearly empty
    # the two analytic branches meet continuously where the surface reaches the floor
    t_knee = math.degrees(math.atan(h / (2 * r)))
    a = Chemistry.capacity_ml(r, h, math.radians(t_knee - 0.01))
    b = Chemistry.capacity_ml(r, h, math.radians(t_knee + 0.01))
    assert abs(a - b) < 0.5
    # 70 mL in a 100 mL beaker first spills near 58 deg (docs: first drop ~55-65 deg)
    first = next(t for t in np.arange(0, 90, 0.5) if Chemistry.capacity_ml(r, h, math.radians(t)) < 70.0)
    assert 54 <= first <= 62
