"""Dashboard: the feed watches a sequencer run without changing it; runner controls; HTTP endpoints."""
import json
import urllib.error
import urllib.request

import numpy as np
from test_sequencer import PROTO, build

from benchsim.dashboard import narration
from benchsim.dashboard.feed import Feed
from benchsim.dashboard.twin import Twin
from benchsim.process import steps as S

ORDER = {'pending': 0, 'running': 1, 'passed': 2, 'failed': 2, 'skipped': 2}


def run_with_feed(hook=None, probes=None, twin=False):
    bb, seq = build(); snaps = []
    tw = Twin(bb.world.m) if twin else None
    feed = Feed(bb, snaps.append, rate_hz=20.0, timebase=bb.clock.now, probes=probes, twin=tw).attach(seq); feed.plan(PROTO)
    if hook: seq.ctx.on_tick_hooks.append(hook(bb, seq))
    out = seq.run(PROTO); feed.flush()
    return bb, out, snaps


def test_feed_follows_the_run():
    bb, out, snaps = run_with_feed()
    assert out['state'] == 'DONE' and len(snaps) > 20
    for i in range(len(PROTO)):
        seen = [s['steps'][i]['status'] for s in snaps]
        assert 'running' in seen and seen[-1] == 'passed'
        assert all(ORDER[a] <= ORDER[b] for a, b in zip(seen, seen[1:])), seen
    last = snaps[-1]; assert last['seq_state'] == 'DONE' and last['current'] is None
    running = [s['current'] for s in snaps if s['current'] and s['current']['index'] == 1]
    assert 'P1' in running[0]['narration']['title'] and running[0]['narration']['arm'] == 'transfer'
    mega_tx = [w['text'] for w in last['wire'] if w['dev'] == 'mega' and w['dir'] == 'tx']
    texts = ' '.join(w['text'] for s in snaps for w in s['wire'])
    assert '"cmd":"STREAM"' in texts and '"cmd":"TARE"' in texts and '"crc":"' in texts
    assert any(w['dev'] == 'transfer' and w['text'].startswith('goal') for s in snaps for w in s['wire'])
    assert last['arms']['transfer']['goal_deg'] is not None and last['scale']['rate_hz'] >= 70
    ids = [w['id'] for w in last['wire']]; assert ids == sorted(ids) and mega_tx is not None


def test_feed_shows_a_safe_stop():
    def hook(bb, seq):
        w = bb.world; fired = {}

        def h():
            if not fired and w.held.get('transfer') and w.beaker_pose('P1')[0][2] > 75:
                seq.ctx.request_stop('operator stop (test)'); fired['t'] = w.time
        return h
    bb, out, snaps = run_with_feed(hook)
    last = snaps[-1]
    assert last['seq_state'] == 'SAFE_STOP' and 'operator stop' in last['stop_reason']
    assert [s['status'] for s in last['steps']] == ['failed', 'skipped', 'skipped']
    assert last['errors'] and any(e['kind'] == 'safe_stop' for e in last['events'])
    assert last['arms']['transfer']['holding'] == 'P1' and last['arms']['transfer']['torque']


def test_a_broken_probe_never_stops_the_run():
    def boom(): raise RuntimeError('probe broke')
    bb, out, snaps = run_with_feed(probes=dict(bad=boom, ok=lambda: 1.5))
    assert out['state'] == 'DONE' and out['passed'] == 3
    last = snaps[-1]; assert last['probes'] == dict(bad=None, ok=1.5) and any('probe broke' in e for e in last['errors'])


def test_narration_covers_the_demo():
    for st in S.demo_protocol():
        d = narration.describe(st.to_dict())
        assert d['title'] and d['detail'] is not None
    funnel_p2 = [s for s in S.demo_protocol() if s.type == 'POUR_TO_FUNNEL' and s.params['beaker'] == 'P2'][0]
    assert 'O₂' in narration.describe(funnel_p2.to_dict())['science']['equation']
    assert narration.clearance(dict(type='POUR_TO_FUNNEL', params={}))['mm'] == 5.3


def test_runner_controls_and_operator_stop(tmp_path):
    from benchsim.dashboard import runner as R, server
    hub = server.Hub(); r = R.Runner(hub, speed=0, out_root=tmp_path)
    assert r.control('start')[0] is False                       # still building
    r.build(); assert r.control('stop')[0] is False and r.control('reset')[0] is True
    r.build(); assert r.control('start') == (True, 'starting') and r.control('start')[0] is False
    r.stop_flag = True; r._start()                              # Stop pressed before the first tick
    assert r.result['state'] == 'SAFE_STOP' and r.phase == 'finished'
    snap = json.loads(hub.snap)
    assert snap['stop_reason'] == 'operator stop (dashboard)' and snap['probes']['runner']['phase'] == 'finished'
    assert r.control('reset')[0] is True


def test_server_endpoints():
    from benchsim.dashboard import server
    hub = server.Hub(); calls = []
    srv = server.serve(hub, lambda c: (calls.append(c) or c == 'start', 'ok %s' % c), port=0)
    base = 'http://127.0.0.1:%d' % srv.server_address[1]
    try:
        hub.publish(dict(t=float('nan'), x=np.float32(1.5)))
        assert json.loads(urllib.request.urlopen(base + '/api/snapshot').read()) == dict(t=None, x=1.5)
        assert b'Wet Lab Bench' in urllib.request.urlopen(base + '/').read()
        req = urllib.request.Request(base + '/api/start', method='POST')
        assert json.loads(urllib.request.urlopen(req).read()) == dict(ok=True, message='ok start')
        try: urllib.request.urlopen(urllib.request.Request(base + '/api/stop', method='POST')); assert False
        except urllib.error.HTTPError as e: assert e.code == 409
        assert calls == ['start', 'stop']
    finally:
        srv.shutdown()


def test_video_frames_and_auto_camera():
    from benchsim.bench import make_bench
    from benchsim.dashboard import server, video as V
    snap = dict(current=dict(type='STAGE', params=dict(position='ERUPT')))
    assert V.auto_camera(snap) == 'foam_cam' and V.auto_camera(dict(current=dict(type='TRANSFER', params={}))) == 'bench_cam'
    assert V.auto_camera(dict(current=None, steps=[dict(status='passed', type='STAGE', label='10 ERUPT')])) == 'foam_cam'
    hub = server.Hub(); bb = make_bench('sim'); v = V.Video(hub, fps=10.0, width=320, height=180); v.attach(bb.world)
    assert hub.jpeg[:2] == b'\xff\xd8' and v.shown == 'overview' and v.set_camera('nope') is False
    n = hub.jpeg_ver; bb.clock.sleep(1.0); assert hub.jpeg_ver - n in (10, 11)          # fps of sim time
    v.set_camera('top'); v.idle(); assert v.shown == 'top'; v.detach()


def test_twin_error_is_small_when_settled_and_shows_lag_while_moving():
    bb, out, snaps = run_with_feed(twin=True)
    tw = [s['arms']['transfer']['twin'] for s in snaps if 'error_mm' in s['arms']['transfer']['twin']]
    settled = [t['error_mm'] for t in tw if t['settled']]; moving = [t['error_mm'] for t in tw if not t['settled']]
    assert settled and max(settled) < 1.0, max(settled)
    assert moving and max(moving) > 1.0                               # the streamed goal runs ahead of the servo
    last = tw[-1]; assert len(last['commanded_mm']) == 3 and set(last['joint_err_deg']) == {'shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll'}
    assert 'error_mm' not in snaps[-1]['arms']['pourer']['twin']       # the pourer never moved in this protocol
