"""backend/hardware.py: the replay clock, the follow rule, and a recording's timeline."""
import json

import numpy as np

from backend.hardware import Playback, TickClock, follow_q


class FakeClock:
    def __init__(self, step=0.002): self.t = 0.0; self.step = step

    def now(self): return self.t

    def sleep(self, dt):
        if dt > 0: self.t += max(self.step, dt)      # like SimWorld.advance: at least one physics step


def test_tickclock_always_finishes_a_wait_replay_plan_nap_style():
    """replay_plan.nap loops until left <= 0: a sleep must advance whenever any time is left (it once spun forever
    on a 5e-10 s remainder)"""
    c = TickClock(FakeClock(), tick=lambda: None)
    t_end = c.now() + 0.03
    n = 0
    while True:
        left = t_end - c.now()
        if left <= 0: break
        c.sleep(min(left, 0.05)); n += 1
        assert n < 1000
    c.sleep(1e-10)
    assert c.now() > t_end


def test_follow_q_takes_the_commanded_gripper():
    q = follow_q([0.1, 0.2, 0.3, 0.4, 0.5, 0.40], [9, 9, 9, 9, 9, 0.13])
    assert np.allclose(q[:5], [0.1, 0.2, 0.3, 0.4, 0.5]) and q[5] == 0.13
    assert follow_q([0, 0, 0, 0, 0, 0.4], None)[5] == 0.4


def test_playback_timeline(tmp_path):
    d = tmp_path / "hw-x"; d.mkdir()
    lines = [json.dumps(dict(schema="wlb.telemetry/1", mode="usb"))] + [json.dumps(dict(t=t, q={}, goal={})) for t in (10.0, 11.0, 12.0, 13.0)]
    (d / "telemetry.jsonl").write_text("\n".join(lines) + "\n")
    sub = lambda i, st, t0, t1: dict(index=i, name=f"s{i}", phase="pick", status=st, t0=t0, t1=t1, result="r", code=None)
    run = dict(run_id="hw-x", backend="real", kind="hw_replay", outcome="complete", doses={}, faults=["x"],
               steps=[dict(index=1, name="1 a", status="ok", t0=10.0, t1=11.5, subgoals=[sub(1, "ok", 10.0, 11.5)]),
                      dict(index=2, name="2 b", status="fault", t0=11.5, t1=13.0, subgoals=[sub(1, "failed", 11.5, 12.5), sub(2, "ok", 12.5, 13.0)])])
    (d / "run.json").write_text(json.dumps(run))
    pb = Playback(d)
    a = pb.status_at(10.5)
    assert [s["status"] for s in a["steps"]] == ["running", "pending"] and a["current_subgoal"] == "1 a / s1"
    b = pb.status_at(12.7)
    assert [s["status"] for s in b["steps"]] == ["ok", "running"] and len(b["faults"]) == 1
    c = pb.status_at(1e9)
    assert [s["status"] for s in c["steps"]] == ["ok", "fault"] and c["bench_seconds"] == 3.0
