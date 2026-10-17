"""python -m benchsim.dashboard: serve the live dashboard and run the protocol in simulation on demand.

    python -m benchsim.dashboard                       # http://127.0.0.1:8765, real-time pacing
    python -m benchsim.dashboard --speed 2             # twice real time (0 = as fast as the sim goes)
    python -m benchsim.dashboard --host 0.0.0.0        # reachable from another screen on the LAN
"""
import argparse
import sys
import webbrowser

from . import runner, server, video


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m benchsim.dashboard')
    p.add_argument('--host', default='127.0.0.1'); p.add_argument('--port', type=int, default=8765)
    p.add_argument('--speed', type=float, default=1.0, help='sim seconds per wall second (0 = unpaced)')
    p.add_argument('--camera', default='auto', help="auto (follows the step), overview, bench_cam, top or foam_cam")
    p.add_argument('--fps', type=float, default=15.0, help='camera frames per sim second'); p.add_argument('--no-video', action='store_true')
    p.add_argument('--seed', type=int, default=0); p.add_argument('--open', action='store_true', help='open the browser')
    a = p.parse_args(argv)
    hub = server.Hub(); cam = None if a.no_video else video.Video(hub, camera=a.camera, fps=a.fps)
    run = runner.Runner(hub, speed=a.speed, seed=a.seed, video=cam)
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


if __name__ == '__main__':
    sys.exit(main())
