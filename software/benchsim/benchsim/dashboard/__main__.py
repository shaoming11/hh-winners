"""python -m benchsim.dashboard: serve the live dashboard and run the protocol in simulation on demand.

    python -m benchsim.dashboard                       # http://127.0.0.1:8765, real-time pacing
    python -m benchsim.dashboard --speed 2             # twice real time (0 = as fast as the sim goes; also live on the page)
    python -m benchsim.dashboard --dev                 # quick 3-step protocol instead of the full 12-step demo
    python -m benchsim.dashboard --host 0.0.0.0        # reachable from another screen on the LAN
    python -m benchsim.dashboard --plain               # the bare MuJoCo scene, without the camera look (benchsim.fx)
    python -m benchsim.dashboard --replay runs/dashboard/<run_id>   # play back a recorded run (no simulation)
"""
import argparse
import sys
import threading
import webbrowser

from . import runner, server, tape, video


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m benchsim.dashboard')
    p.add_argument('--host', default='127.0.0.1'); p.add_argument('--port', type=int, default=8765)
    p.add_argument('--speed', type=float, default=1.0, help='sim seconds per wall second (0 = unpaced)')
    p.add_argument('--camera', default='auto', help="auto (follows the step), overview, bench_cam, top or foam_cam")
    p.add_argument('--fps', type=float, default=15.0, help='camera frames per sim second'); p.add_argument('--no-video', action='store_true')
    p.add_argument('--plain', action='store_true', help='bare MuJoCo scene: no room, coloured liquids, streams or foam drawing')
    p.add_argument('--dev', action='store_true', help='quick 3-step protocol instead of the full demo')
    p.add_argument('--no-record', action='store_true', help='do not write dashboard.mp4 + tape.json into the run folder')
    p.add_argument('--replay', metavar='RUN_DIR', help='play back a recorded run instead of simulating')
    p.add_argument('--seed', type=int, default=0); p.add_argument('--open', action='store_true', help='open the browser')
    a = p.parse_args(argv)
    hub = server.Hub()
    if a.replay: return replay(hub, a)
    cam = None if a.no_video else video.Video(hub, camera=a.camera, fps=a.fps, fx=not a.plain)
    make = lambda out_root, seed: runner.make_run(out_root, seed, dev=a.dev)
    run = runner.Runner(hub, make_run=make, speed=a.speed, seed=a.seed, video=cam, record=not a.no_record)
    try:
        srv = server.serve(hub, run.control, host=a.host, port=a.port)
    except OSError as e:
        print('cannot listen on %s:%d (%s); try --port' % (a.host, a.port, e)); return 2
    url = 'http://%s:%d/' % ('127.0.0.1' if a.host == '0.0.0.0' else a.host, srv.server_address[1])
    print('dashboard: %s  (building the bench, then press Start)' % url, flush=True)
    if a.open: webbrowser.open(url)
    try:
        run.loop()
    except KeyboardInterrupt:
        print('\nbye')
    return 0


def replay(hub, a):
    try:
        tape_p, video_p = tape.load(a.replay)
    except (FileNotFoundError, ValueError) as e:
        print(e); return 2
    files = {'/replay/tape.json': tape_p, '/replay/video.mp4': video_p}
    try:
        srv = server.serve(hub, lambda cmd: (False, 'replay: there is no live bench'), host=a.host, port=a.port, extra_files=files)
    except OSError as e:
        print('cannot listen on %s:%d (%s); try --port' % (a.host, a.port, e)); return 2
    url = 'http://%s:%d/' % ('127.0.0.1' if a.host == '0.0.0.0' else a.host, srv.server_address[1])
    print('replay of %s: %s' % (a.replay, url), flush=True)
    if a.open: webbrowser.open(url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print('\nbye')
    return 0


if __name__ == '__main__':
    sys.exit(main())
