"""python -m benchsim.dashboard: serve the live dashboard and run the protocol in simulation on demand.

    python -m benchsim.dashboard                       # http://127.0.0.1:8765, real-time pacing
    python -m benchsim.dashboard --speed 2             # twice real time (0 = as fast as the sim goes)
    python -m benchsim.dashboard --host 0.0.0.0        # reachable from another screen on the LAN
"""
import argparse
import sys
import webbrowser

from . import runner, server


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m benchsim.dashboard')
    p.add_argument('--host', default='127.0.0.1'); p.add_argument('--port', type=int, default=8765)
    p.add_argument('--speed', type=float, default=1.0, help='sim seconds per wall second (0 = unpaced)')
    p.add_argument('--seed', type=int, default=0); p.add_argument('--open', action='store_true', help='open the browser')
    a = p.parse_args(argv)
    hub = server.Hub(); run = runner.Runner(hub, speed=a.speed, seed=a.seed)
    try:
        srv = server.serve(hub, run.control, host=a.host, port=a.port)
    except OSError as e:
        print('cannot listen on %s:%d (%s); try --port' % (a.host, a.port, e)); return 2
    url = 'http://%s:%d/' % ('127.0.0.1' if a.host == '0.0.0.0' else a.host, srv.server_address[1])
    print('dashboard: %s  (building the bench, then press Start)' % url)
    if a.open: webbrowser.open(url)
    try:
        run.loop()
    except KeyboardInterrupt:
        print('\nbye')
    return 0


if __name__ == '__main__':
    sys.exit(main())
