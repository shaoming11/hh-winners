"""Regenerate every piece of evidence in reports/ and print one line per gate.

    python -m benchsim.reproduce            # everything (~8 min): layout, kinematics, interfaces, grasping, pours,
                                            # mechanisms, full demo with video, safe stop, language-layer run, hw-check
    python -m benchsim.reproduce --quick    # skips the long pour trials and mechanism verification (~4 min)
"""
import subprocess
import sys
import time
from pathlib import Path

from . import paths

PY = sys.executable


def step(name, args, expect=0):
    t = time.time(); r = subprocess.run([PY, '-m'] + args, cwd=paths.SIM_ROOT, capture_output=True, text=True)
    ok = r.returncode == expect
    tail = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip() and 'WARNING' not in ln][-1:] or ['']
    print('%-22s %-4s %6.1fs  %s' % (name, 'PASS' if ok else 'FAIL', time.time() - t, tail[0][:110]), flush=True)
    return ok, r.stdout


def latest_run(before):
    runs = sorted(p for p in paths.RUNS.glob('*-sim') if p.name not in before)
    return runs[-1] if runs else None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv; quick = '--quick' in argv; ok = True
    for name, args in (('layout', ['benchsim.verify_layout']), ('kinematics', ['benchsim.verify_kinematics']),
                       ('interfaces', ['benchsim.exercise']), ('grasping', ['benchsim.grasp_demo'])):
        ok &= step(name, args)[0]
    if not quick:
        ok &= step('pour trials', ['benchsim.pour_trials'])[0]
        ok &= step('mechanisms', ['benchsim.verify_mechanisms'])[0]
    paths.RUNS.mkdir(exist_ok=True)
    for name, args, expect, ev, video in (('demo (video)', ['benchsim.demo_run'], 0, 'demo_run', True),
                                          ('safe stop in pour', ['benchsim.demo_run', '--no-video', '--stop-during-pour'], 1, 'demo_safe_stop', False),
                                          ('language layer', ['benchsim.demo_run', '--no-video', '--protocol-text',
                                                              'benchsim/ai/examples/elephant_toothpaste.txt', '--approve'], 0, 'demo_ai_protocol', False)):
        before = {p.name for p in paths.RUNS.glob('*-sim')}
        good, _ = step(name, args, expect); ok &= good
        run = latest_run(before)
        if run is not None:
            from .collect_evidence import collect
            collect(run, ev, video=video, frames=video)
    ok &= step('hw-check (offline)', ['benchsim', 'hw-check'])[0]
    print('reproduce:', 'ALL PASS' if ok else 'SOME FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
