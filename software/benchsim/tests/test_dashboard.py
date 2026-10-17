"""Dashboard feed: watches a sequencer run without changing it (no HTTP here)."""
from test_sequencer import PROTO, build

from benchsim.dashboard import narration
from benchsim.dashboard.feed import Feed
from benchsim.process import steps as S

ORDER = {'pending': 0, 'running': 1, 'passed': 2, 'failed': 2, 'skipped': 2}


def run_with_feed(hook=None, probes=None):
    bb, seq = build(); snaps = []
    feed = Feed(bb, snaps.append, rate_hz=20.0, timebase=bb.clock.now, probes=probes).attach(seq); feed.plan(PROTO)
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
