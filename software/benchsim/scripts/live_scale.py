"""Live load-cell readout from the Mega (Ctrl-C to stop). The backend must not hold the port.

    python scripts/live_scale.py          # grams, about 4 updates a second
    python scripts/live_scale.py --tare   # zero it first (pan empty)
    python scripts/live_scale.py --beaker 19.9   # also show what is in the beaker (total minus the empty beaker)
    python scripts/live_scale.py --zero 350.48   # software zero: subtract this raw reading (the Mega's own tare is lost
                                                 # whenever the port is reopened, because that resets the Mega)
"""
import os, statistics, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import replay_plan as rp  # noqa: E402
from benchsim.backends.real import make_real_bench  # noqa: E402


def main():
    bb = make_real_bench(port_mega=rp.PORTS['port_mega'], dry_run=False); m = bb.mega
    time.sleep(2.5)                                         # the port open may reset the Mega
    try: bb.transport.read_lines()
    except Exception: pass
    m.command('STREAM', on=True)
    if '--tare' in sys.argv: m.command('TARE'); print('tared')
    zero = float(sys.argv[sys.argv.index('--zero') + 1]) if '--zero' in sys.argv else 0.0
    beaker = float(sys.argv[sys.argv.index('--beaker') + 1]) if '--beaker' in sys.argv else None
    print('live scale (g) - Ctrl-C to stop' + ('  |  in the beaker = total - %.1f g' % beaker if beaker is not None else ''), flush=True)
    try:
        while True:
            t0 = time.time(); got = []
            while time.time() - t0 < 0.25:
                m._keepalive(); got += m.take_samples(); time.sleep(0.01)
            if got:
                w = [s['w'] for s in got]
                g = statistics.mean(w) - zero
                extra = '   in the beaker %8.2f g' % (g - beaker) if beaker is not None else ''
                print('\rtotal %9.2f g%s   (%2d samples, spread %.2f g)   ' % (g, extra, len(w), max(w) - min(w)), end='', flush=True)
            else:
                print('\r   no samples from the scale          ', end='', flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        try: m.command('STREAM', on=False)
        except Exception: pass
        bb.transport.close(); print()


if __name__ == '__main__':
    main()
