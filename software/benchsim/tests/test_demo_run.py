"""Full simulated demo (about 40 s wall). Deterministic for a given seed."""
import json
import tempfile
from pathlib import Path

from benchsim import demo_run


def test_full_demo_passes_every_step():
    out_dir = Path(tempfile.mkdtemp())
    assert demo_run.main(['--no-video', '--out', str(out_dir)]) == 0
    run = next(out_dir.iterdir()); d = json.loads((run / 'run_log.json').read_text())
    assert d['summary']['state'] == 'DONE' and d['summary']['failed'] == 0 and d['summary']['skipped'] == 0
    m = {s['label']: s['measured'] for s in d['steps']}
    assert abs([v for k, v in m.items() if k.startswith('2 ')][0]['added_g'] - 39.0) <= 2.0
    if '6 verify yeast' in m:                           # the full protocol (auger + water pour)
        assert abs(m['6 verify yeast']['content_g'] - 7.0) <= 0.7
        assert abs(m['7 water onto P2']['added_g'] - 30.0) <= 2.0
    else:                                               # pre-mixed / yeast in the flask: the erupting funnel pour empties its beaker
        last = [v for k, v in m.items() if 'ERUPT' in k][0]
        assert abs(last['left_in_beaker_g']) <= 2.0 and last['erupt_crank_deg'] > 140
    assert (run / 'notebook.html').exists() and (run / 'scale.csv').exists()


def test_stop_during_pour_untilts_and_keeps_the_beaker():
    out_dir = Path(tempfile.mkdtemp())
    assert demo_run.main(['--no-video', '--stop-during-pour', '--out', str(out_dir)]) == 1
    run = next(out_dir.iterdir()); d = json.loads((run / 'run_log.json').read_text())
    fs = d['summary']['final_state']
    assert d['summary']['state'] == 'SAFE_STOP' and fs['held'].get('pourer') == 'dev'
    assert all(fs['torque'].values()) and fs['beaker_tilt_deg']['dev'] < 5.0
