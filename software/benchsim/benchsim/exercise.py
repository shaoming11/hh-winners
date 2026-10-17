"""Phase 4 exercise: drive both arms and every Mega mechanism through the shared interfaces, plus the defined
error and fault responses. ``python -m benchsim.exercise`` -> reports/exercise_report.json (simulation only)."""
import json
import math
import sys

import numpy as np

from . import paths, state
from .bench import make_bench
from .interfaces import MegaError

REPORTS = paths.SIM_ROOT / 'reports'


def run():
    bb = make_bench('sim'); w = bb.world; mega = bb.mega; clock = bb.clock; rows = []

    def rec(test, ok, **kw):
        rows.append(dict(test=test, ok=bool(ok), t=round(clock.now(), 3), **kw)); print('%-58s %s %s' % (test, 'PASS' if ok else 'FAIL', kw))

    def expect_err(test, code, fn):
        try: fn(); rec(test, False, got='no error')
        except MegaError as e: rec(test, e.code == code, got=e.code, detail=e.reply.get('detail'))

    rec('PING', mega.command('PING').get('ok'), reply=mega.command('PING'))
    mega.command('STREAM', on=True); mega.command('TARE'); m0 = mega.read_mass(16)
    rec('scale stream + tare reads ~0 g', abs(m0) < 0.3, grams=round(m0, 3), samples_per_s=80)
    t0 = clock.now(); mega.take_samples(); clock.sleep(1.0); n = len(mega.take_samples())
    rec('scale stream rate 80 Hz', abs(n - 80) <= 1, samples_in_1s=n)

    # arms: a joint move each, then back to park
    park = state.park_q()
    for arm, dq in (('pourer', [-0.4, 0.2, 0.3, -0.2, 0.5, 0.0]), ('transfer', [0.3, 0.15, 0.2, 0.2, -0.4, 0.0])):
        a = bb.arms[arm]; goal = park + np.array(dq); a.set_goal(goal)
        t = clock.now()
        while a.is_moving() and clock.now() - t < 6: clock.sleep(0.02)
        err = np.degrees(np.abs(a.read_positions() - goal)).max()
        rec('%s joint goal reached' % arm, err < 0.5, max_err_deg=round(float(err), 3), move_s=round(clock.now() - t, 2),
            loads_permille=a.read_loads().tolist())
        a.set_goal(park)
        while a.is_moving(): clock.sleep(0.02)
    try: bb.arms['pourer'].set_goal(park + [0, 0, 0, 3.0, 0, 0]); rec('arm goal outside joint range rejected', False)
    except ValueError as e: rec('arm goal outside joint range rejected', True, detail=str(e)[:60])

    # stall: drive the transfer arm's gripper into the table -> goal not reached, load saturates
    from .poses import Planner
    a = bb.arms['transfer']; q = park.copy(); q[1] = math.radians(60); q[2] = math.radians(-20); q[3] = math.radians(60)
    a.set_goal(q, speed_scale=0.5); t = clock.now()
    while a.is_moving() and clock.now() - t < 5: clock.sleep(0.02)
    err = np.degrees(np.abs(a.goal_error())).max(); load = np.abs(a.read_loads()).max()
    rec('blocked arm motion detected as stall (goal error + load)', err > 2 and load > 600, goal_error_deg=round(float(err), 2), max_load_permille=float(load))
    a.set_goal(park)
    while a.is_moving(): clock.sleep(0.02)

    # carousel and stage
    r = mega.motion('TT', done_timeout=8, deg=90.0, ms=4000); deck = mega.t.mega.tt_deg()
    rec('carousel TT 90 deg', abs(deck - 90) < 0.6, done=r, deck_deg=round(deck, 2))
    sled0 = w.d.joint('sled').qpos[0]
    r = mega.motion('ST', done_timeout=8, deg=150.0, ms=2500); travel = (sled0 - w.d.joint('sled').qpos[0]) * 1000
    rec('stage ST 150 deg (ERUPT)', abs(travel - 97.3) < 0.5, done=r, sled_travel_mm=round(travel, 2))
    mega.motion('ST', done_timeout=8, deg=0.0, ms=2500); rec('stage back to WORK', abs(w.d.joint('sled').qpos[0]) * 1000 < 0.5)
    r = mega.motion('AUG', done_timeout=20, rev=2.0, dir=1); rec('auger AUG 2 rev', abs(r['rev'] - 2.0) < 1e-6, done=r)

    # defined error responses
    expect_err('unknown command -> BADCMD', 'BADCMD', lambda: mega.command('FLY'))
    expect_err('TT out of range -> RANGE', 'RANGE', lambda: mega.command('TT', deg=400.0, ms=20000))
    expect_err('TT faster than 2 s per 45 deg -> RANGE', 'RANGE', lambda: mega.command('TT', deg=0.0, ms=500))
    expect_err('AUG > 50 rev -> RANGE', 'RANGE', lambda: mega.command('AUG', rev=60.0, dir=1))
    s1 = mega.send('TT', deg=0.0, ms=4000); mega.wait(s1, key=('ack',))
    expect_err('ST while carousel moving -> BUSY', 'BUSY', lambda: mega.command('ST', deg=150.0, ms=2500))
    expect_err('AUG while carousel moving -> BUSY', 'BUSY', lambda: mega.command('AUG', rev=1.0, dir=1))
    mega.wait(s1, key=('done',), timeout=8)

    # e-stop during a move
    s1 = mega.send('TT', deg=90.0, ms=4000); mega.wait(s1, key=('ack',)); clock.sleep(1.0); w.estop = True; clock.sleep(0.1)
    angle_at = mega.t.mega.tt_deg(); clock.sleep(1.0); mega._pump()
    rec('e-stop during carousel move -> ESTOP fault, no done', any(f['fault'] == 'ESTOP' for f in mega.faults) and not any(r.get('done') for r in mega.replies.get(s1, [])),
        deck_deg_at_estop=round(angle_at, 1), deck_deg_after=round(mega.t.mega.tt_deg(), 1))
    expect_err('command while e-stop latched -> ESTOP', 'ESTOP', lambda: mega.command('TT', deg=0.0, ms=8000))
    expect_err('CLR with e-stop still pressed -> STATE', 'STATE', lambda: mega.command('CLR'))
    w.estop = False; rec('CLR after release', mega.command('CLR').get('ok')); mega.faults.clear()
    mega.motion('TT', done_timeout=10, deg=0.0, ms=4000)

    # comm watchdog: start a move and go silent
    s1 = mega.send('TT', deg=45.0, ms=4000); mega.wait(s1, key=('ack',)); w.advance(0.7); mega._pump()   # host silent
    rec('host silent 500 ms during a move -> WDT fault', any(f['fault'] == 'WDT' for f in mega.faults))
    mega.command('CLR'); mega.faults.clear(); mega.motion('TT', done_timeout=10, deg=0.0, ms=4000)

    # auger jam -> stall rule
    w.auger_jam = True
    try: mega.motion('AUG', done_timeout=20, rev=1.0, dir=1); rec('jammed auger -> AUGER_JAM after 3 stalls', False)
    except MegaError as e:
        stalls = [x for x in w.events if x['kind'] == 'auger_stall']
        rec('jammed auger -> AUGER_JAM after 3 stalls', e.code == 'AUGER_JAM' and len(stalls) >= 3, stalls=len(stalls))
    w.auger_jam = False; mega.command('CLR'); mega.faults.clear()

    # HX711 silent -> fault
    w.hx_fail = True; clock.sleep(0.3); mega._pump()
    rec('HX711 silent -> HX_TIMEOUT fault', any(f['fault'] == 'HX_TIMEOUT' for f in mega.faults))
    w.hx_fail = False; mega.command('CLR'); mega.faults.clear()
    rec('STOP is always accepted', mega.command('STOP').get('ok'))
    return rows


def main():
    rows = run(); REPORTS.mkdir(exist_ok=True)
    (REPORTS / 'exercise_report.json').write_text(json.dumps(rows, indent=1, default=str))
    ok = all(r['ok'] for r in rows); print('exercise:', 'PASS' if ok else 'FAIL', '(%d checks)' % len(rows))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
