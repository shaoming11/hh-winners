"""Copy a run's evidence into reports/<name>/ (run log, traces, frames, notebook with linked frames, video).

    python -m benchsim.collect_evidence <run_dir> <name> [--no-video] [--no-frames]
"""
import shutil
import sys
from pathlib import Path

from . import paths


def collect(run_dir, name, video=True, frames=True):
    run_dir = Path(run_dir); out = paths.SIM_ROOT / 'reports' / name
    shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    for f in ['run_log.json', 'scale.csv', 'joints.csv'] + sorted(p.name for p in run_dir.glob('pour_*.csv')):
        if (run_dir / f).exists(): shutil.copy2(run_dir / f, out / f)
    if frames and (run_dir / 'frames').exists(): shutil.copytree(run_dir / 'frames', out / 'frames')
    if video and (run_dir / 'demo.mp4').exists(): shutil.copy2(run_dir / 'demo.mp4', out / 'demo.mp4')
    from .notebook import render
    render(out, out_dir=out, embed_frames=False)
    return out


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if not x.startswith('--')]
    print(collect(a[0], a[1], video='--no-video' not in sys.argv, frames='--no-frames' not in sys.argv))
