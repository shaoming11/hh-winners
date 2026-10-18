"""Phase 2 gate: station centres measured in the compiled MuJoCo model vs update13_final, and beaker settling.

    python -m benchsim.verify_layout          # writes reports/layout_report.{json,md}; exit 1 if a gate fails

Gates: every station centre within 1 mm of update13_final (xy, and z where the source gives one); no beaker
starts interpenetrating anything (contact depth <= 0.2 mm); after 2 s every beaker is within 1 mm of its
station and tilted less than 0.5 deg.
"""
import json
import sys

import mujoco
import numpy as np

from . import layout, paths, scene, state
from .units import mm

TOL_MM = 1.0
REPORTS = paths.SIM_ROOT / 'reports'


def measure(model, data, b):
    st = b.st; rows = []

    def row(name, got, want, src='update13_final'):
        got = np.asarray(got, float); want = np.asarray(want, float); n = min(len(got), len(want))
        err = float(np.linalg.norm(got[:n] - want[:n]))
        rows.append(dict(station=name, model_mm=np.round(got[:n], 2).tolist(), source_mm=np.round(want[:n], 2).tolist(),
                         error_mm=round(err, 3), pass_=err <= TOL_MM, source=src))
    for arm in scene.ARMS:
        row('%s base axis' % arm, mm(data.joint('%s/shoulder_pan' % arm).xanchor)[:2] if hasattr(data.joint('%s/shoulder_pan' % arm), 'xanchor')
            else mm(data.xanchor[model.joint('%s/shoulder_pan' % arm).id])[:2], st['%s_base' % arm]['xy'])
    row('scale pan centre', mm(data.site('scale_centre').xpos), st['scale_pan']['xy'] + [st['scale_pan']['z']])
    row('funnel rim (sled at WORK)', mm(data.site('funnel_rim').xpos), st['funnel']['xy'] + [st['funnel']['z']])
    row('carousel centre', mm(data.xanchor[model.joint('carousel').id])[:2], st['carousel_centre']['xy'])
    row('carousel pick pocket', mm(data.site('pocket0').xpos), st['carousel_pick']['xy'] + [st['carousel_pick']['z']])
    # the auger may sit anywhere on the pocket circle (trial saddle layout: ~96 deg from the pick, not opposite it):
    # it must be on the circle, at beaker-bottom height, and every pocket must be able to reach it inside the deck range
    cc = np.asarray(st['carousel_centre']['xy']); p0 = mm(data.site('pocket0').xpos)
    row('carousel auger on the pocket circle (r, z)', [float(np.linalg.norm(np.asarray(st['carousel_auger']['xy']) - cc)), st['carousel_auger']['z']],
        [float(np.linalg.norm(p0[:2] - cc)), float(p0[2])])
    from . import mechanisms
    bad = [r['pocket'] for r in mechanisms.station_table(b.bench) if r['station'] == 'auger' and r['deck_deg'] is None]
    rows.append(dict(station='every pocket reaches the auger in deck range', model_mm=bad, source_mm=[], error_mm=float(len(bad)),
                     pass_=not bad, source='mechanisms.station_table'))
    for i in (1, 2, 3):
        row('rack pocket %d' % i, mm(data.site('rack_%d' % i).xpos), st['rack_%d' % i]['xy'] + [st['rack_%d' % i]['z']])
    for name, key in (('X-front rail centre Y', 'front_centre_Y'), ('X-back rail centre Y', 'rear_centre_Y')):
        g = model.geom('rail_X_' + ('front' if 'front' in key else 'back')).id
        row(name, [mm(data.geom_xpos[g][1])], [b.bench['x_rails'][key]])
    ao = mm(data.site('auger_outlet').xpos)[:2]
    off = float(np.linalg.norm(ao - np.asarray(st['carousel_auger']['xy'])))
    rows.append(dict(station='auger outlet over auger pocket', model_mm=np.round(ao, 2).tolist(), source_mm=st['carousel_auger']['xy'],
                     error_mm=round(off, 3), pass_=off <= 20.0, source='demo_process 2.4: +-20 mm is fine'))
    return rows


def settle(model, data, b, seconds=2.0):
    state.reset(model, data)
    pen = []
    for i in range(data.ncon):
        c = data.contact[i]
        names = (model.body(model.geom_bodyid[c.geom1]).name, model.body(model.geom_bodyid[c.geom2]).name)
        if any(n.startswith('beaker_') for n in names): pen.append((names, float(-c.dist * 1000)))
    start = {k: data.body('beaker_' + k).xpos.copy() for k in scene.BEAKERS}
    for _ in range(int(seconds / model.opt.timestep)): mujoco.mj_step(model, data)
    rows = []
    for k, info in b.meta['beakers'].items():
        p = data.body('beaker_' + k).xpos; tilt = float(np.degrees(np.arccos(np.clip(data.body('beaker_' + k).xmat[8], -1, 1))))
        tgt = np.r_[info['xy'], info['bottom_z']]
        err = float(np.linalg.norm(mm(p) - tgt)); moved = float(np.linalg.norm(mm(p - start[k])))
        maxpen = max([d for n, d in pen if 'beaker_' + k in n] + [0.0])
        rows.append(dict(beaker=k, station=info['start'], final_mm=np.round(mm(p), 2).tolist(), target_mm=np.round(tgt, 2).tolist(),
                         error_mm=round(err, 3), moved_mm=round(moved, 3), tilt_deg=round(tilt, 3), initial_penetration_mm=round(maxpen, 3),
                         pass_=err <= TOL_MM and tilt <= 0.5 and maxpen <= 0.2))
    return rows


def main():
    model, b = scene.build(); data = mujoco.MjData(model); state.reset(model, data)
    stations = measure(model, data, b); beakers = settle(model, data, b)
    cross = layout.cross_checks(b.bench)
    fits = json.loads((paths.CONFIG / 'mesh_fits.json').read_text())
    ok = all(r['pass_'] for r in stations + beakers)
    rep = dict(source=b.bench['source'], tolerance_mm=TOL_MM, pass_=ok, stations=stations, beakers=beakers,
               r_bearing_cross_check=cross, cad_mesh_fits=fits, fidelity=b.fid.rows)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / 'layout_report.json').write_text(json.dumps(rep, indent=1))
    L = ['# Layout verification report', '', 'Generated by `python -m benchsim.verify_layout`. Source: `%s`. Gate: station centre error'
         ' <= %.1f mm; beakers settle within 1 mm, tilt <= 0.5 deg, no initial interpenetration > 0.2 mm.' % (b.bench['source'], TOL_MM), '',
         '**Overall: %s**' % ('PASS' if ok else 'FAIL'), '', '## Station centres (measured in the compiled MuJoCo model)', '',
         '| Station | Model (mm) | update13_final (mm) | Error (mm) | Result |', '|---|---|---|---|---|']
    for r in stations:
        L.append('| %s | %s | %s | %.3f | %s |' % (r['station'], r['model_mm'], r['source_mm'], r['error_mm'], 'PASS' if r['pass_'] else 'FAIL'))
    L += ['', '## Beakers after 2 s of free settling', '', '| Beaker | Station | Error (mm) | Moved (mm) | Tilt (deg) | Initial penetration (mm) | Result |',
          '|---|---|---|---|---|---|---|']
    for r in beakers:
        L.append('| %s | %s | %.3f | %.3f | %.3f | %.3f | %s |' % (r['beaker'], r['station'], r['error_mm'], r['moved_mm'], r['tilt_deg'],
                                                              r['initial_penetration_mm'], 'PASS' if r['pass_'] else 'FAIL'))
    L += ['', '## Recorded r / bearing table vs coordinates (coordinates are authoritative)', '', '| Arm | Station | r | r recorded | Bearing | Bearing recorded |',
          '|---|---|---|---|---|---|']
    for r in cross:
        L.append('| %s | %s | %.1f | %.1f | %s | %s |' % (r['arm'], r['station'], r['r_mm'], r['recorded_r'], r['bearing_deg'], r['recorded_bearing']))
    L += ['', '## Imported CAD mesh placement', '', '| Part | File | Placement check | Residual (mm) |', '|---|---|---|---|']
    for f in fits:
        L.append('| %s | `%s` | %s | %s |' % (f['part'], f['file'], f['verified'], 'n/a' if f['residual_mm'] is None else '%.3f' % f['residual_mm']))
    L += ['', '## Fidelity', '', '| Part | Visual | Collision | Source | Note |', '|---|---|---|---|---|']
    for r in b.fid.rows:
        L.append('| %s | %s | %s | %s | %s |' % (r['part'], r['visual'], r['collision'], r['source'], r['note']))
    (REPORTS / 'layout_report.md').write_text('\n'.join(L) + '\n')
    for r in stations: print('%-32s err %7.3f mm  %s' % (r['station'], r['error_mm'], 'PASS' if r['pass_'] else 'FAIL'))
    for r in beakers: print('beaker %-6s err %.3f mm tilt %.3f pen %.3f  %s' % (r['beaker'], r['error_mm'], r['tilt_deg'], r['initial_penetration_mm'],
                                                                             'PASS' if r['pass_'] else 'FAIL'))
    print('layout gate:', 'PASS' if ok else 'FAIL', '->', REPORTS / 'layout_report.md')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
