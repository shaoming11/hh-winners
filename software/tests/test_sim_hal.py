import math

import pytest

from bench.config import load
from bench.hal.sim import make_sim_bench


@pytest.fixture()
def bench():
    b = make_sim_bench(load())
    b.connect()
    return b


def test_mega_rejects_range_and_busy(bench):
    assert bench.mega.command({"cmd": "stage", "deg": 170, "ms": 2500})["err"] == "RANGE"
    assert bench.mega.command({"cmd": "carousel", "deg": 90, "ms": 2000})["ok"]
    assert bench.mega.command({"cmd": "auger", "rev": 1})["err"] == "BUSY"
    bench.clock.sleep(2.5)
    assert any("done" in m for m in bench.mega.drain())


def test_weight_stream_has_mega_millis(bench):
    it = bench.mega.samples()
    a, b = next(it), next(it)
    assert "w" in a and "w" in b
    assert 10 <= b["w"][0] - a["w"][0] <= 15          # ~12.5 ms at 80 Hz


def test_estop_latches_and_blocks_commands(bench):
    bench.mega.command({"cmd": "estop_test", "pressed": True})
    bench.clock.sleep(0.05)
    assert bench.mega.command({"cmd": "carousel", "deg": 0, "ms": 2000})["ok"] is False
    assert bench.mega.command({"cmd": "clr"})["err"] == "ESTOP"
    bench.mega.command({"cmd": "estop_test", "pressed": False})
    assert bench.mega.command({"cmd": "clr"})["ok"]


def test_stage_travel_matches_design(bench):
    cfg = load()
    bench.mega.command({"cmd": "stage", "deg": 150, "ms": 2500})
    bench.clock.sleep(4.0)
    assert abs(bench.sim.sled_travel_mm() - cfg.at("stations.stage.travel_mm")) < 0.5
    bench.mega.command({"cmd": "stage", "deg": 0, "ms": 2500})
    bench.clock.sleep(4.0)
