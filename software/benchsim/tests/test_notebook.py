import json
import shutil
from pathlib import Path

from benchsim import notebook, runlog

FIXTURE = Path(__file__).parent / 'fixtures' / 'sample_run'
STEP_KEYS = {'index', 'type', 'label', 'params', 'status', 'reason', 't_start', 't_end', 'target', 'measured', 'faults', 'frames'}


def test_fixture_follows_runlog_schema(tmp_path):
    log = runlog.load(FIXTURE / 'run_log.json')
    fresh = runlog.RunLog(tmp_path, run_id='x').d
    assert set(log) == set(fresh)
    assert set(log['config']) == set(fresh['config'])
    assert set(log['protocol']) == {'source', 'text', 'steps', 'validation', 'approved_by', 'approved_utc'}
    assert all(set(s) == STEP_KEYS for s in log['steps'])
    assert {s['status'] for s in log['steps']} == {'passed', 'failed', 'skipped'}
    for f in log['frames']:
        assert (FIXTURE / f['path']).exists()


def test_notebook_renders_fixture(tmp_path):
    out = notebook.render(FIXTURE, tmp_path)
    log = runlog.load(FIXTURE / 'run_log.json')
    h = out['html'].read_text(); m = out['md'].read_text()
    assert out['svg'].read_text().startswith('<?xml')
    assert h.startswith('<!doctype html>') and '<polyline class="line"' in h and 'id="trace-data"' in h
    assert h.count('data:image/png;base64,') == len(log['frames']) == 3
    for k in ('run_id',):
        assert log[k] in h and log[k] in m
    for v in (log['config']['params_sha256'], log['config']['so101_revision'], 'sample operator', 'grasp miss', 'ESTOP', '38.71'):
        assert v in h and v in m
    for s in log['steps']:
        assert s['label'].replace('>', '&gt;') in h and s['label'] in m
    assert h.count('class="pill passed"') == 10 and h.count('class="pill failed"') == 1 and h.count('class="pill skipped"') == 1
    assert 'mass_g -0.29 (within ±2.00)' in h and 'mass_g -0.29 (within ±2.00)' in m
    assert 'not approved' not in h
    # markdown frames are relative links that resolve from the output directory
    links = [ln[ln.index('](') + 2:-1] for ln in m.splitlines() if ln.startswith('![') and 'scale trace' not in ln]
    assert len(links) == 3 and all((tmp_path / p).resolve().exists() for p in links)


def test_notebook_handles_missing_frame_and_unapproved_protocol(tmp_path):
    run = tmp_path / 'run'; shutil.copytree(FIXTURE, run)
    (run / 'frames' / 'flask_step8.png').unlink()
    d = json.loads((run / 'run_log.json').read_text())
    d['protocol'].update(source='llm', approved_by=None, approved_utc=None, validation=dict(ok=False, problems=['step 2 (POUR_TO_SCALE): target 500.0 g outside 1..60']))
    (run / 'run_log.json').write_text(json.dumps(d))
    out = notebook.render(run)
    h = out['html'].read_text(); m = out['md'].read_text()
    assert 'missing: frames/flask_step8.png' in h and 'missing frame: `frames/flask_step8.png`' in m
    assert 'not approved' in h and '**not approved**' in m and 'target 500.0 g outside' in h
    assert out['html'].parent == run


def test_cli(tmp_path, capsys):
    notebook.main([str(FIXTURE), '--out', str(tmp_path), '--link-frames'])
    assert 'notebook.html' in capsys.readouterr().out
    h = (tmp_path / 'notebook.html').read_text()
    assert 'data:image/png' not in h and 'frames/pick_check_P1.png' in h
