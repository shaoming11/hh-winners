"""benchsim command line. Run ``python -m benchsim --help``."""
import argparse
import json
import sys

from . import paths


def cmd_fetch(a):
    from . import assets
    assets.fetch()


def cmd_build(a):
    import mujoco
    from . import scene
    model, b = scene.build()
    out = paths.RUNS / 'model'; out.mkdir(parents=True, exist_ok=True)
    (out / 'bench.xml').write_text(b.spec.to_xml())
    (out / 'fidelity.json').write_text(json.dumps(b.fid.rows, indent=1))
    (out / 'scene_meta.json').write_text(json.dumps(b.meta, indent=1, default=float))
    print('compiled: nbody %d njnt %d nu %d ngeom %d -> %s' % (model.nbody, model.njnt, model.nu, model.ngeom, out))


def cmd_view(a):
    import mujoco
    import mujoco.viewer
    from . import scene, state
    model, _ = scene.build(); data = mujoco.MjData(model); state.reset(model, data)
    mujoco.viewer.launch(model, data)


def cmd_render(a):
    import mujoco
    from . import render, scene, state
    model, _ = scene.build(); data = mujoco.MjData(model); state.reset(model, data)
    out = paths.RUNS / 'renders'; out.mkdir(parents=True, exist_ok=True)
    r = render.Renderer(model)
    for cam in a.cameras.split(','):
        print(r.save_png(data, out / ('scene_%s.png' % cam), cam))


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m benchsim')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('fetch', help='download and verify the pinned SO-101 model').set_defaults(f=cmd_fetch)
    sub.add_parser('build', help='compile the bench model, write runs/model/bench.xml and the fidelity table').set_defaults(f=cmd_build)
    sub.add_parser('view', help='open the interactive MuJoCo viewer with both arms parked').set_defaults(f=cmd_view)
    r = sub.add_parser('render', help='render PNGs of the parked bench'); r.add_argument('--cameras', default='overview,top,bench_cam,foam_cam')
    r.set_defaults(f=cmd_render)
    a = p.parse_args(argv); a.f(a)


if __name__ == '__main__':
    sys.exit(main())
