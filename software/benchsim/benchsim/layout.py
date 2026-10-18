"""Bench configuration from the final layout (tools/layout/layout_final.json, key ``update13_final``).

``load_bench()`` returns one dict in millimetres: station centres from update13_final, dimensions from
config/bench_params.toml, and a provenance tag on every station. Older JSON keys and layout_final.md are
not read. ``python -m benchsim.layout`` prints the config and the cross-checks against the recorded
r/bearing table."""
import json
import math
import sys
import tomllib

from . import paths

FINAL_KEY = 'update13_final'
EXPECTED_STATUS = 'ALL 8 STEPS PASS'


class LayoutError(RuntimeError):
    pass


def load_final(path=paths.LAYOUT_JSON):
    d = json.loads(path.read_text())
    if FINAL_KEY not in d:
        raise LayoutError('%s has no key %s' % (path, FINAL_KEY))
    u = d[FINAL_KEY]
    if u.get('status') != EXPECTED_STATUS:
        raise LayoutError('%s.status is %r, expected %r' % (FINAL_KEY, u.get('status'), EXPECTED_STATUS))
    return u


def load_params(path=paths.CONFIG / 'bench_params.toml'):
    return tomllib.loads(path.read_text())


def bearing(base, p):
    """distance and bearing (deg, measured from -Y, positive toward +X) as used in the layout tables"""
    dx, dy = p[0] - base[0], p[1] - base[1]
    return math.hypot(dx, dy), math.degrees(math.atan2(dx, -dy))


def load_bench():
    u = load_final(); P = load_params()
    src = 'layout_final.json:%s' % FINAL_KEY
    st = {}

    def add(name, xy, z=None, source=src, **kw):
        st[name] = dict(xy=[float(xy[0]), float(xy[1])], z=None if z is None else float(z), source=source, **kw)

    add('pourer_base', u['pourer_base']['xy'])
    add('transfer_base', u['transfer_base']['xy'])
    add('scale_pan', u['scale']['pan'][:2], u['scale']['pan'][2], note='z = beaker bottom on the pan')
    add('funnel', u['funnel']['xy'], u['funnel']['rim_z'], note='z = funnel rim, sled at WORK')
    add('carousel_centre', u['carousel']['centre'])
    add('carousel_pick', u['carousel']['pick'], u['carousel']['beaker_bottom_z'], note='z = beaker bottom')
    add('carousel_auger', u['carousel']['auger'], u['carousel']['beaker_bottom_z'])
    for i, r in enumerate(u['rack_stands']):
        add('rack_%d' % (i + 1), r['xy'], u['rack_beaker_bottom_z'], note='z = beaker bottom')
    bench = dict(params=P, stations=st, carousel_rotation_deg=float(u['carousel']['rotation_deg']),
                 x_rails=u['X_rails'], r_bearing=u['r_bearing'], recorded_steps=u['steps'],
                 tape_datums=u['tape_datums'], source=src,
                 auger_boxes={k: u['carousel'][k] for k in ('auger_post_box', 'auger_head_box', 'auger_rail_E5') if k in u['carousel']})
    return bench


def cross_checks(bench):
    """recompute r/bearing from the station coordinates and compare with the recorded table; also check the
    carousel pocket geometry. Returns a list of dict rows."""
    st = bench['stations']; rb = bench['r_bearing']; rows = []

    def row(arm, station, xy_name, rec_r, rec_b):
        r, b = bearing(st['%s_base' % arm]['xy'], st[xy_name]['xy'])
        rows.append(dict(arm=arm, station=station, r_mm=round(r, 1), bearing_deg=round(b, 1), recorded_r=rec_r,
                         recorded_bearing=rec_b, dr=round(r - rec_r, 1), dbearing=round(b - rec_b, 1)))
    for i, b in enumerate(rb['pourer']['rack'][1]):
        row('pourer', 'rack %d' % (i + 1), 'rack_%d' % (i + 1), rb['pourer']['rack'][0], b)
    row('pourer', 'scale', 'scale_pan', *rb['pourer']['scale'])
    row('pourer', 'funnel', 'funnel', *rb['pourer']['funnel'])
    row('transfer', 'carousel pick', 'carousel_pick', *rb['transfer']['carousel_pick'])
    row('transfer', 'scale', 'scale_pan', *rb['transfer']['scale'])
    c = st['carousel_centre']['xy']; P = bench['params']['carousel']
    for name in ('carousel_pick', 'carousel_auger'):
        p = st[name]['xy']; r = math.hypot(p[0] - c[0], p[1] - c[1]); a = math.degrees(math.atan2(p[1] - c[1], p[0] - c[0])) % 360
        rows.append(dict(arm='-', station=name + ' vs centre', r_mm=round(r, 2), bearing_deg=round(a, 2), recorded_r=P['pitch_r'],
                         recorded_bearing=None, dr=round(r - P['pitch_r'], 2), dbearing=None))
    return rows


if __name__ == '__main__':
    b = load_bench()
    if '--json' in sys.argv:
        print(json.dumps({k: v for k, v in b.items() if k != 'params'}, indent=1)); sys.exit()
    for k, v in b['stations'].items():
        print('%-16s xy %-18s z %-6s %s' % (k, v['xy'], v['z'], v.get('note', '')))
    print('\nr / bearing cross-check (recomputed from coordinates vs recorded table)')
    for r in cross_checks(b):
        flag = '' if (abs(r['dr']) <= 1.0 and (r['dbearing'] is None or abs(r['dbearing']) <= 1.0)) else '  <-- DISAGREES'
        print('  %-8s %-24s r %6.1f (rec %6.1f)  bearing %6s (rec %5s)%s' % (r['arm'], r['station'], r['r_mm'], r['recorded_r'],
              r['bearing_deg'], r['recorded_bearing'], flag))
