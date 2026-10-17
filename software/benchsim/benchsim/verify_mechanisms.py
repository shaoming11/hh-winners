"""Phase 7 checks: auger dosing, carousel stations, stage geometry and foam, run against the MuJoCo model.

    python -m benchsim.verify_mechanisms      # reports/mechanisms_report.{md,json}, reports/foam_frames/*.png; exit 1 if a gate fails

(a) Dosing. The host g/rev is calibrated in the simulation (architecture 6: 3 x 10 rev into a tared cup). Then
    N_DOSES doses of the recipe yeast run through ``Mechanisms.dose_yeast``: carousel moves, AUG over the protocol,
    and verification on the simulated HX711 scale. The transfer-arm moves are replaced by teleporting P2 between its
    pick pocket and the scale pan; that is allowed for this check, and the arm move is the sequencer's job. Also
    checked: a transient jam (one stall, recovered), a jammed auger (AUGER_JAM), an empty hopper (HOPPER_EMPTY from
    the device model, and from the host scale rule with the device rule off) and the host g/rev error sensitivity.
(b) Carousel. The deck visits every station angle. Measured: deck angle error, every pocket centre vs its station,
    whether P1/P2 stay in their pockets, and travel time vs the commanded time (>= 2 s per 45 deg).
(c) Stage. The crank steps 0..150 deg by 10. The MuJoCo closed chain (hinge + hinge + connect + slide) is compared
    with the analytic slider-crank at the measured crank angle, then ERUPT travel vs 97.3 mm and the WORK return.
(d) Foam. Zero cases (no yeast, no developer, no soap), then the demo timeline. Developer is in the flask; the yeast
    slurry goes in at t = 0, STAGE_OUT starts STAGE_START_S later and the foam grows at ERUPT. The O2 yield, the
    height curve and the peak are reported, and foam_cam frames are rendered offscreen. The 'flask_neck_top' site is
    projected with the camera intrinsics (fovy) and pose, and foam-coloured pixels are counted in the region above
    it, cross-checked against MuJoCo segmentation.
"""
import colorsys
import json
import math
import sys
import time

import imageio.v3 as iio
import mujoco
import numpy as np

from . import paths, protocol, scene
from .backends.sim import SimMega, SimWorld
from .bench import make_bench
from .chem.auger import AugerModel
from .chem.foam import FoamModel, flask_volume_ml, load_flask, o2_yield_ml
from .chem.vessels import Ledger
from .mechanisms import Mechanisms, slider_crank_travel, station_table, travel_ms
from .units import m, mm

REPORTS = paths.SIM_ROOT / 'reports'
FRAMES = REPORTS / 'foam_frames'
N_DOSES = 10
SENSITIVITY = (0.8, 0.9, 1.1, 1.2)       # host g/rev over the calibrated value
DROP_MM = 0.05                            # teleported beakers start this far above their seat, as in scene.beakers
SETTLE_S = 0.5                            # settle after a teleport or a stage step (scale flexure ~58 Hz, zeta 0.25)
SCALE_SAMPLES = 16                        # 0.2 s of 80 Hz samples per reading
POCKET_TOL_MM = 1.0                       # pocket centre vs station, beaker vs its pocket (same gate as verify_layout)
STAGE_TOL_MM = 0.5                        # same gate as benchsim.exercise
STAGE_START_S = 1.5                       # architecture 4.5: STAGE_OUT starts <= 1.5 s after the catalyst untilt
FOAM_RUN_S = 60.0
FRAME_TIMES = [4.0 + 0.25 * i for i in range(17)] + [10.0, 15.0, 20.0, 30.0, 45.0, 60.0]   # s after the slurry goes in; plus the ERUPT arrival
SAVE_FRAMES = (4.5, 4.75, 5.0, 5.5, 30.0, 60.0)                                            # saved as PNG, plus the ERUPT arrival frame
CAM, CAM_W, CAM_H = 'foam_cam', 640, 480
REGION_HALF_W = 2.0                       # region half-width above the neck, in projected column radii
HUE_TOL_DEG, MIN_SAT, MIN_VAL = 30.0, 0.15, 0.25   # foam-colour classifier (HSV) around the foam rgba hue


def bench(model, builder, seed=0):
    return make_bench('sim', world=SimWorld(model, builder, seed=seed))


def place(w, beaker, xy, bottom_z):
    """teleport a beaker (free joint) upright onto a seat at bottom_z (mm), at rest"""
    j = w.m.joint('beaker_' + beaker); a = j.qposadr[0]; v = j.dofadr[0]
    w.d.qpos[a:a + 3] = m([xy[0], xy[1], bottom_z + DROP_MM]); w.d.qpos[a + 3:a + 7] = [1, 0, 0, 0]; w.d.qvel[v:v + 6] = 0
    mujoco.mj_forward(w.m, w.d)


class ScaleHooks:
    """weigh/back hooks for Mechanisms.dose_yeast with the transfer-arm moves replaced by teleports"""

    def __init__(self, bb, mech):
        self.bb = bb; self.w = bb.world; self.mech = mech; s = mech.bench['stations']['scale_pan']; self.seat = (s['xy'], s['z']); self.tare = {}
        bb.mega.command('STREAM', on=True); bb.mega.command('TARE')          # empty pan

    def read(self, beaker):
        place(self.w, beaker, *self.seat); self.w.advance(SETTLE_S); return self.bb.mega.read_mass(SCALE_SAMPLES)

    def pocket_seat(self, k):
        p = mm(self.w.d.site('pocket%d' % k).xpos); return p[:2], p[2]

    def tare_beaker(self, beaker):
        self.tare[beaker] = self.read(beaker); place(self.w, beaker, *self.pocket_seat(self.mech.pocket_of(beaker))); return self.tare[beaker]

    def weigh(self, beaker): return self.read(beaker) - self.tare[beaker]

    def back(self, beaker): place(self.w, beaker, *self.pocket_seat(self.mech.pocket_at('pick')))


def clear_faults(bb):
    bb.world.auger_jam = False; bb.mega.command('CLR'); bb.mega.faults.clear()


# ======================================================================= (a) dosing
def check_doses(model, builder, log=print):
    bb = bench(model, builder, seed=11); w = bb.world; P = w.P; R = P['recipe']; M = P['auger_model']
    L = Ledger(w); aug = AugerModel(w, bb.mega_device, L, seed=7); aug.fill(M['hopper_load_g'])
    mech = Mechanisms(bb.mega); H = ScaleHooks(bb, mech); tare = H.tare_beaker('P2')
    out = dict(beaker_tare_g=round(tare, 3), g_per_rev_nominal=P['auger']['g_per_rev_nominal'], g_per_rev_true=aug.g_per_rev, cv=aug.cv)

    def refill():
        if M['hopper_load_g'] > L.mass('hopper'): aug.fill(M['hopper_load_g'] - L.mass('hopper'))

    def reset_p2():                              # operator empties P2; it goes back into its pocket at the pick
        L.take('P2', L.mass('P2'))
        if 'P2' not in mech.pockets: H.back('P2'); mech.insert('P2')

    def dose(gpr, fill=True, **kw):
        if fill: refill()
        y0 = L.mass('P2'); spill0 = aug.spilled_g; r = mech.dose_yeast('P2', R['yeast_g'], H.weigh, H.back, g_per_rev=gpr, **kw)
        d = r.to_dict(); truth = L.mass('P2') - y0
        d.update(truth_g=round(truth, 4), truth_error_g=round(truth - R['yeast_g'], 4), spilled_g=round(aug.spilled_g - spill0, 4),
                 stalls=sum(p['stalls'] or 0 for p in r.passes)); reset_p2(); return d

    # outlet over the auger pocket with P2 in it: the landing rule
    mech.carousel_to('P2', 'auger'); o = mm(w.d.site('auger_outlet').xpos); lip = mm(w.d.site('beaker_P2_lip').xpos)
    out['landing'] = dict(receiver=aug.receiver(), outlet_to_axis_mm=round(math.hypot(*(o[:2] - lip[:2])), 3), limit_mm=round(aug.open_r, 3),
                          outlet_above_lip_mm=round(o[2] - lip[2], 2))
    mech.carousel_to('P2', 'pick')
    cal = mech.calibrate('P2', H.weigh, H.back); reset_p2(); gpr = cal['g_per_rev']
    out['calibration'] = dict(g_per_rev=round(gpr, 4), runs=[dict(rev=p['rev_done'], added_g=round(p['added_g'], 4), g_per_rev=round(p['g_per_rev'], 4))
                                                             for p in cal['runs']])
    log('calibration: %.4f g/rev (true %.3f per dispensing rev)' % (gpr, aug.g_per_rev))
    rows = []
    for i in range(N_DOSES):
        d = dose(gpr); d['n'] = i + 1; rows.append(d)
        log('dose %2d: %-5s scale %.3f g (err %+.3f) truth %.3f g, top-ups %d, revs %.1f' % (i + 1, d['status'], d['measured_g'], d['error_g'], d['truth_g'],
                                                                                              d['topups'], d['revs']))
    out['doses'] = rows
    err = np.array([r['error_g'] for r in rows]); terr = np.array([r['truth_error_g'] for r in rows])
    out['stats'] = dict(n=len(rows), mean_error_g=round(float(err.mean()), 4), std_error_g=round(float(err.std(ddof=1)), 4),
                        max_abs_error_g=round(float(np.abs(err).max()), 4), truth_mean_error_g=round(float(terr.mean()), 4),
                        truth_std_error_g=round(float(terr.std(ddof=1)), 4), truth_max_abs_error_g=round(float(np.abs(terr).max()), 4),
                        topups={str(k): sum(r['topups'] == k for r in rows) for k in range(P['auger']['max_topups'] + 1)},
                        tol_g=R['yeast_tol_g'], spilled_g=round(sum(r['spilled_g'] for r in rows), 4))
    out['sensitivity'] = []
    for f in SENSITIVITY:
        for _ in range(2):
            d = dose(gpr * f); out['sensitivity'].append(dict(host_over_calibrated=f, status=d['status'], measured_g=d['measured_g'], truth_g=d['truth_g'],
                                                              topups=d['topups'], first_rev=d['passes'][0]['rev_cmd'], revs=d['revs']))
    # transient jam: the screw is blocked for 0.25 s, 1 s into the first pass -> one stall, reverse, retry
    mega = bb.mega_device

    def jam_window(w):
        mo = mega.motion
        if mo and mo['cmd'] == 'AUG' and jam_window.seq is None: jam_window.seq = mo['seq']       # the first pass of this dose
        w.auger_jam = bool(mo and mo['cmd'] == 'AUG' and mo['seq'] == jam_window.seq and 1.0 <= w.time - mo['t0'] < 1.25)
    jam_window.seq = None
    w.frame_hooks.append(jam_window); d = dose(gpr); w.frame_hooks.remove(jam_window); w.auger_jam = False
    out['transient_jam'] = dict(status=d['status'], first_pass_stalls=d['passes'][0]['stalls'], measured_g=d['measured_g'], fault=d['fault'])
    # jammed auger
    w.auger_jam = True; nst = len([e for e in w.events if e['kind'] == 'auger_stall']); d = dose(gpr)
    stalls = len([e for e in w.events if e['kind'] == 'auger_stall']) - nst; clear_faults(bb)
    out['jam'] = dict(status=d['status'], fault=d['fault'], stalls=stalls, detail=d['detail'])
    # empty hopper: device model rule
    L.take('hopper', L.mass('hopper'))
    d = dose(gpr, fill=False); clear_faults(bb)
    out['hopper_empty'] = dict(status=d['status'], fault=d['fault'], detail=d['detail'], revs=d['revs'], passes=len(d['passes']), measured_g=d['measured_g'])
    # empty hopper: host scale rule alone (the real Mega cannot weigh)
    L.take('hopper', L.mass('hopper')); empty_g = aug.empty_g; aug.empty_g = -1.0
    d = dose(gpr, fill=False); aug.empty_g = empty_g; clear_faults(bb)
    out['hopper_empty_host'] = dict(status=d['status'], fault=d['fault'], detail=d['detail'], revs=d['revs'], measured_g=d['measured_g'])
    out['model_totals'] = aug.totals(); out['ledger_spilled_g'] = round(L.spilled_mass(), 4)
    tol = R['yeast_tol_g']
    out['gates'] = dict(
        doses_within_tol=all(r['status'] == 'ok' and abs(r['error_g']) <= tol and abs(r['truth_error_g']) <= tol for r in rows),
        topups_le_max=all(r['topups'] <= P['auger']['max_topups'] for r in rows),
        landing_in_P2=out['landing']['receiver'] == 'P2' and out['stats']['spilled_g'] == 0.0,
        transient_jam_recovered=out['transient_jam']['status'] == 'ok' and (out['transient_jam']['first_pass_stalls'] or 0) >= 1,
        jam_faults=out['jam']['fault'] == 'AUGER_JAM' and stalls >= P['auger']['max_stalls'],
        hopper_empty_faults=out['hopper_empty']['fault'] == 'HOPPER_EMPTY' and 'host scale check' not in out['hopper_empty']['detail'],
        hopper_empty_host_rule=out['hopper_empty_host']['fault'] == 'HOPPER_EMPTY' and 'host scale check' in out['hopper_empty_host']['detail'])
    return out


# ======================================================================= (b) carousel
def check_carousel(model, builder, log=print):
    bb = bench(model, builder); w = bb.world; mech = Mechanisms(bb.mega); C = w.P['carousel']; st = mech.bench['stations']
    table = station_table(mech.bench); rows = []; stops = []
    seat = {b: mech.pocket_of(b) for b in ('P1', 'P2')}
    for deg in (180.0, 90.0, 270.0, 0.0, 90.0, 270.0):        # every station angle, spans 180/90/180/270/90/180; ends at the demo moves
        target = min(table, key=lambda r: abs(r['deck_deg'] - deg))['deck_deg']
        mv = mech.turn_deck(target); w.advance(SETTLE_S)
        deck = math.degrees(w.d.joint('carousel').qpos[0]); need = 1000.0 * C['min_s_per_45deg'] * mv['span_deg'] / 45.0
        stop = dict(cmd_deg=target, deck_deg=round(deck, 3), deck_error_deg=round(deck - target, 3), span_deg=mv['span_deg'], cmd_ms=mv['cmd_ms'],
                    min_ms=round(need, 1), travel_s=mv['travel_s'], overrun_s=round(mv['travel_s'] - mv['cmd_ms'] / 1000.0, 3), stations={}, beakers={})
        for s in ('pick', 'auger'):
            k, aerr = mech.nearest_pocket(s); p = mm(w.d.site('pocket%d' % k).xpos)
            e = float(np.linalg.norm(p[:2] - np.asarray(st['carousel_' + s]['xy'])))
            stop['stations'][s] = dict(pocket=k, beaker=mech.pockets[k], position_error_mm=round(e, 3), table_error_deg=round(aerr, 3))
            rows.append(dict(pocket=k, station=s, deck_deg=target, measured_deck_deg=round(deck, 3), position_error_mm=round(e, 3)))
        for b, k in seat.items():
            pb = mm(w.d.body('beaker_' + b).xpos); ps = mm(w.d.site('pocket%d' % k).xpos)
            tilt = math.degrees(math.acos(np.clip(w.d.body('beaker_' + b).xmat[8], -1, 1)))
            stop['beakers'][b] = dict(pocket=k, offset_mm=round(float(np.linalg.norm(pb[:2] - ps[:2])), 3), tilt_deg=round(tilt, 3))
        stops.append(stop)
        log('deck %6.1f: err %+.3f deg, travel %.2f s (cmd %.2f s), pick pocket %d %.3f mm, auger pocket %d %.3f mm' % (
            target, deck - target, mv['travel_s'], mv['cmd_ms'] / 1000.0, stop['stations']['pick']['pocket'], stop['stations']['pick']['position_error_mm'],
            stop['stations']['auger']['pocket'], stop['stations']['auger']['position_error_mm']))
    covered = {(r['pocket'], r['station']) for r in rows}
    gates = dict(
        all_pocket_station_pairs_visited=covered == {(r['pocket'], r['station']) for r in table},
        all_reachable=all(r['deck_deg'] is not None for r in table),
        deck_angle_within_done_tol=all(abs(s['deck_error_deg']) <= SimMega.MOVE_TOL_DEG for s in stops),
        pockets_on_stations=all(v['position_error_mm'] <= POCKET_TOL_MM for s in stops for v in s['stations'].values()),
        beakers_stay_in_pockets=all(v['offset_mm'] <= POCKET_TOL_MM for s in stops for v in s['beakers'].values()),
        commanded_time_obeys_2s_per_45deg=all(s['cmd_ms'] >= s['min_ms'] - 1e-6 for s in stops),
        travel_time_within_cmd_plus_timeout=all(0.0 <= s['overrun_s'] <= C['timeout_extra_s'] for s in stops))
    return dict(table=table, stops=stops, rows=rows, gates=gates, done_tol_deg=SimMega.MOVE_TOL_DEG, tol_mm=POCKET_TOL_MM)


# ======================================================================= (c) stage
def check_stage(model, builder, log=print):
    bb = bench(model, builder); w = bb.world; S = w.P['stage']; mech = Mechanisms(bb.mega); r, L = S['crank_r'], S['rod_l']
    lim = protocol.Limits(w.P); jc = w.d.joint('crank'); js = w.d.joint('sled'); rows = []

    def measure():
        th = math.degrees(jc.qpos[0]); s = -mm(float(js.qpos[0])); return th, s
    for th_cmd in range(0, int(S['erupt_deg']) + 1, 10):
        if th_cmd > 0: bb.mega.motion('ST', done_timeout=lim.st_ms_min / 1000.0 + 2 * S['timeout_extra_s'], deg=float(th_cmd), ms=int(lim.st_ms_min))
        w.advance(SETTLE_S); th, s = measure(); sa = slider_crank_travel(th, r, L)
        rows.append(dict(cmd_deg=th_cmd, crank_deg=round(th, 3), sled_travel_mm=round(s, 3), analytic_at_measured_mm=round(sa, 3),
                         analytic_at_cmd_mm=round(slider_crank_travel(th_cmd, r, L), 3), linkage_error_mm=round(s - sa, 4),
                         error_vs_cmd_mm=round(s - slider_crank_travel(th_cmd, r, L), 4)))
    ret = []
    for pos in ('WORK', 'ERUPT', 'WORK'):
        mv = mech.stage_to(pos); w.advance(SETTLE_S); th, s = measure()
        ret.append(dict(position=pos, crank_deg=round(th, 3), sled_travel_mm=round(s, 3), travel_s=mv['travel_s'], cmd_s=mv['cmd_ms'] / 1000.0))
    erupt = ret[1]; work = [x for x in ret if x['position'] == 'WORK']
    lerr = max(abs(x['linkage_error_mm']) for x in rows); cerr = max(abs(x['error_vs_cmd_mm']) for x in rows)
    log('stage: linkage max err %.4f mm, vs commanded %.4f mm, ERUPT %.3f mm, WORK return %s mm' % (lerr, cerr, erupt['sled_travel_mm'], [x['sled_travel_mm'] for x in work]))
    gates = dict(linkage_matches_analytic=lerr <= STAGE_TOL_MM, travel_vs_commanded_angle=cerr <= STAGE_TOL_MM,
                 analytic_150deg_is_97_3=abs(slider_crank_travel(S['erupt_deg'], r, L) - S['expected_travel_mm']) <= 0.05,
                 erupt_travel_97_3=abs(erupt['sled_travel_mm'] - S['expected_travel_mm']) <= STAGE_TOL_MM,
                 work_return=all(abs(x['sled_travel_mm']) <= STAGE_TOL_MM for x in work))
    return dict(rows=rows, moves=ret, max_linkage_error_mm=round(lerr, 4), max_error_vs_cmd_mm=round(cerr, 4),
                analytic_150_mm=round(slider_crank_travel(S['erupt_deg'], r, L), 4), tol_mm=STAGE_TOL_MM, gates=gates)


# ======================================================================= (d) foam
def project(model, data, cam, p_mm, W, H):
    """pixel (u right, v down) and depth (mm) of a world point, from the camera pose and model.cam_fovy (vertical)"""
    c = data.cam(cam); R = c.xmat.reshape(3, 3); pc = R.T @ (m(p_mm) - c.xpos); z = -pc[2]
    f = (H / 2) / math.tan(math.radians(float(model.cam(cam).fovy[0])) / 2)
    return W / 2 + f * pc[0] / z, H / 2 - f * pc[1] / z, mm(float(z)), f


def foam_mask(img, rgba):
    """pixels whose HSV hue is within HUE_TOL_DEG of the foam colour, with enough saturation and value"""
    x = img[..., :3].astype(float) / 255.0; mx = x.max(-1); mn = x.min(-1); sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0.0)
    r, g, b = x[..., 0], x[..., 1], x[..., 2]; d = np.maximum(mx - mn, 1e-9)
    hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60.0
    h0 = colorsys.rgb_to_hsv(*rgba[:3])[0] * 360.0; dh = np.abs((hue - h0 + 180.0) % 360.0 - 180.0)
    return (dh <= HUE_TOL_DEG) & (sat >= MIN_SAT) & (mx >= MIN_VAL)


def foam_zero_cases(model, builder):
    out = {}
    D = builder.P['recipe']
    for name, parts in (('no yeast', dict(developer=D['developer_g'], water=D['water_g'])), ('no developer', dict(yeast=D['yeast_g'], water=D['water_g'])),
                        ('no soap', dict(developer=D['developer_g'], yeast=D['yeast_g'], water=D['water_g']))):
        w = SimWorld(model, builder); L = Ledger(w, apply_weight=False)
        if name != 'no soap': load_flask(L)
        else: L.add('flask', 'dye', w.P['foam']['dye_g'])
        f = FoamModel(w, L); L.put('flask', parts); w.idle(FOAM_RUN_S)
        out[name] = dict(peak_mm=round(f.peak_mm, 4), foam_ml=round(f.foam_ml, 4), o2_ml=round(f.o2_ml, 2))
    return out


def check_foam(model, builder, log=print):
    zero = foam_zero_cases(model, builder)
    bb = bench(model, builder); w = bb.world; P = w.P; Rc = P['recipe']; F = P['foam']
    L = Ledger(w, apply_weight=False); load_flask(L); foam = FoamModel(w, L); mech = Mechanisms(bb.mega)
    L.add('flask', 'developer', Rc['developer_g']); w.advance(0.2)                       # step 3: developer poured at WORK
    t0 = w.time; L.put('flask', dict(yeast=Rc['yeast_g'], water=Rc['water_g']))          # step 8: the slurry goes in at once
    w.advance(STAGE_START_S); sled = []
    def sled_log(w): sled.append((w.time - t0, -mm(float(w.d.joint('sled').qpos[0]))))
    w.frame_hooks.append(sled_log); mech.stage_to('ERUPT'); w.frame_hooks.remove(sled_log); t_erupt = w.time - t0
    sled_travel = -mm(float(w.d.joint('sled').qpos[0])); rim_z = mm(float(w.d.site('funnel_rim').xpos[2]))
    rnd = mujoco.Renderer(model, height=CAM_H, width=CAM_W); opt = mujoco.MjvOption()
    for g in range(6): opt.geomgroup[g] = 1 if g in (0, 1, 2) else 0
    for g in range(6): opt.sitegroup[g] = 0
    FRAMES.mkdir(parents=True, exist_ok=True)
    for old in FRAMES.glob('*.png'): old.unlink()
    frames = []; gid = foam.gid; rgba = F['rgba_dyed']
    for tf in [t_erupt] + FRAME_TIMES:
        if tf < t_erupt - 1e-9: continue
        if t0 + tf > w.time: w.idle(t0 + tf - w.time)
        neck = mm(w.d.site('flask_neck_top').xpos); u, v, z, f = project(model, w.d, CAM, neck, CAM_W, CAM_H)
        r_px = f * foam.r_col / z; hw = REGION_HALF_W * r_px
        u0, u1 = int(max(0, math.floor(u - hw))), int(min(CAM_W, math.ceil(u + hw))); v1 = int(min(CAM_H, max(0, math.ceil(v))))
        rnd.update_scene(w.d, camera=CAM, scene_option=opt); img = rnd.render().copy()
        rnd.enable_segmentation_rendering(); rnd.update_scene(w.d, camera=CAM, scene_option=opt); seg = rnd.render().copy(); rnd.disable_segmentation_rendering()
        segm = (seg[..., 0] == gid) & (seg[..., 1] == int(mujoco.mjtObj.mjOBJ_GEOM)); colm = foam_mask(img, rgba)
        h = foam.column_mm(); top = None
        if h > 0:               # highest image point of the column's top rim: far edge seen from above, near edge from below
            cpos = mm(w.d.cam(CAM).xpos); away = neck[:2] - cpos[:2]; away /= np.linalg.norm(away)
            if neck[2] + h > cpos[2]: away = -away
            tu, tv, _, _ = project(model, w.d, CAM, [neck[0] + away[0] * foam.r_col, neck[1] + away[1] * foam.r_col, neck[2] + h], CAM_W, CAM_H)
            rows_seg = np.nonzero(segm[:, u0:u1].any(axis=1))[0]
            if 0 <= tv < CAM_H and len(rows_seg):
                # below the funnel rim the semi-transparent cone is in front and segmentation records the funnel, not the foam
                top = dict(predicted_v=round(tv, 1), segmented_v=int(rows_seg.min()), diff_px=round(rows_seg.min() - tv, 1), above_rim=bool(neck[2] + h > rim_z))
        fr = dict(t=round(tf, 3), column_mm=round(h, 2), neck_px=[round(u, 1), round(v, 1)], region=[u0, 0, u1, v1],
                  colour_px=int(colm[:v1, u0:u1].sum()), segmented_px=int(segm[:v1, u0:u1].sum()), colour_px_outside=int(colm.sum() - colm[:v1, u0:u1].sum()),
                  top_check=top)
        if tf == t_erupt or any(abs(tf - s) < 1e-9 for s in SAVE_FRAMES):
            ann = img.copy(); ann[0:v1, [u0, max(u0, u1 - 1)]] = (0, 255, 255); ann[max(0, v1 - 1), u0:u1] = (0, 255, 255)
            iu, iv = int(round(u)), int(round(v))
            ann[max(0, iv - 6):iv + 7, max(0, iu - 1):iu + 2] = (0, 255, 0); ann[max(0, iv - 1):iv + 2, max(0, iu - 6):iu + 7] = (0, 255, 0)
            p = FRAMES / ('foam_t%05.2fs.png' % tf); iio.imwrite(p, ann); fr['png'] = str(p.relative_to(paths.SIM_ROOT))
        frames.append(fr)
        log('foam t %5.2f s: column %6.1f mm, colour px %6d, segmented px %6d' % (tf, h, fr['colour_px'], fr['segmented_px']))
    rnd.close()
    if w.time < t0 + FOAM_RUN_S: w.idle(t0 + FOAM_RUN_S - w.time)
    tr = foam.trace; s = foam.state()
    curve = [dict(t=round(x['t'] - t0, 2), h2o2_left_g=round(x['h2o2_left_g'], 3), o2_ml=round(x['o2_ml'], 1), foam_ml=round(x['foam_ml'], 1),
                  inside_ml=round(x['inside_ml'], 1), column_mm=round(x['column_mm'], 1), overflow_ml=round(x['overflow_ml'], 1))
             for x in tr if any(abs(x['t'] - t0 - q) < F['update_dt_s'] / 2 for q in list(range(0, 16)) + list(range(20, 61, 5)))]
    foam_made = np.array([x['foam_ml'] for x in tr]); col = np.array([x['column_mm'] for x in tr]); ip = int(np.argmax(col))
    grow = [fr for fr in frames if fr['t'] <= (s['t_peak'] or 0) - t0 + 1e-9]
    yield_ml = o2_yield_ml(Rc['developer_g'], F)
    t_neck = None if s['t_foam_at_neck'] is None else s['t_foam_at_neck'] - t0
    sled_at_neck = None if t_neck is None else (sled_travel if t_neck >= sled[-1][0] else
                                                float(np.interp(t_neck, [x[0] for x in sled], [x[1] for x in sled])) if t_neck >= sled[0][0] else 0.0)
    out = dict(params={k: v for k, v in F.items()}, flask_internal_ml=round(flask_volume_ml(P['flask']), 1), o2_yield_ml=round(yield_ml, 1),
               o2_released_ml=round(s['o2_ml'], 1), state=s, t_catalyst=0.0, t_stage_start=STAGE_START_S, t_stage_at_erupt=round(t_erupt, 3),
               sled_travel_mm=round(sled_travel, 3), t_foam_at_neck=None if t_neck is None else round(t_neck, 3),
               sled_travel_at_foam_neck_mm=None if sled_at_neck is None else round(sled_at_neck, 2), funnel_rim_z=round(rim_z, 2),
               t_peak=None if s['t_peak'] is None else round(s['t_peak'] - t0, 3), curve=curve, frames=frames, zero_cases=zero,
               camera=dict(name=CAM, width=CAM_W, height=CAM_H, fovy_deg=float(model.cam(CAM).fovy[0]), hue_tol_deg=HUE_TOL_DEG, min_sat=MIN_SAT, min_val=MIN_VAL,
                           region_half_width_radii=REGION_HALF_W))
    cnt = [fr['colour_px'] for fr in grow]; sg = [fr['segmented_px'] for fr in grow]
    tops = [fr['top_check']['diff_px'] for fr in frames if fr['top_check'] and fr['top_check']['above_rim']]
    out['gates'] = dict(
        o2_yield_about_1_7_l=abs(yield_ml - 1700.0) <= 50.0,
        o2_released_conserved=s['o2_ml'] <= yield_ml + 1e-6 and s['h2o2_left_g'] >= 0.0,
        zero_foam_without_yeast=zero['no yeast']['foam_ml'] == 0.0 and zero['no yeast']['peak_mm'] == 0.0,
        zero_foam_without_developer=zero['no developer']['foam_ml'] == 0.0 and zero['no developer']['peak_mm'] == 0.0,
        foam_made_monotonic=bool(np.all(np.diff(foam_made) >= -1e-9)),
        column_monotonic_to_peak=bool(np.all(np.diff(col[:ip + 1]) >= -1e-9)) and s['peak_mm'] > 0,
        camera_frames_cover_growth=len(grow) >= 3,
        camera_colour_px_grow=len(cnt) >= 3 and all(b >= a for a, b in zip(cnt, cnt[1:])) and cnt[-1] > cnt[0],
        camera_segmented_px_grow=len(sg) >= 3 and all(b >= a for a, b in zip(sg, sg[1:])) and sg[-1] > sg[0],
        camera_projection_matches_top=len(tops) >= 2 and max(abs(x) for x in tops) <= 3.0)
    out['stats'] = dict(peak_mm=s['peak_mm'], growth_frames=len(grow), colour_px_first=cnt[0] if cnt else None, colour_px_last=cnt[-1] if cnt else None,
                        segmented_px_last=sg[-1] if sg else None, top_checks=len(tops), max_top_projection_diff_px=max((abs(x) for x in tops), default=None))
    log('foam: O2 %.0f mL (yield %.0f), at neck %.2f s, peak %.1f mm at %.2f s, stage at ERUPT %.2f s' % (
        s['o2_ml'], yield_ml, out['t_foam_at_neck'] or -1, s['peak_mm'], out['t_peak'] or -1, t_erupt))
    return out


# ======================================================================= report
def write_report(rep):
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / 'mechanisms_report.json').write_text(json.dumps(rep, indent=1, default=str))
    a, b, c, d = rep['doses'], rep['carousel'], rep['stage'], rep['foam']; P = rep['params']
    ok = lambda x: 'PASS' if x else 'FAIL'
    fmt = lambda x, f='%.3f': 'n/a' if x is None else f % x
    L = ['# Mechanisms verification report (phase 7)', '',
         'Generated by `python -m benchsim.verify_mechanisms` (%.0f s wall). Auger dosing, foam and liquid volumes are analytic models, not CFD or '
         'granular simulation; every parameter is in `benchsim/config/bench_params.toml` ([auger], [auger_model], [foam], [flask]), and "assumed" '
         'values there have no measurement behind them.' % rep['wall_s'], '', '**Overall: %s**' % ok(rep['pass_']), '', '## Gates', '',
         '| Section | Gate | Result |', '|---|---|---|']
    for sec, g in (('(a) dosing', a['gates']), ('(b) carousel', b['gates']), ('(c) stage', c['gates']), ('(d) foam', d['gates'])):
        for k, v in g.items(): L.append('| %s | %s | %s |' % (sec, k.replace('_', ' '), ok(v)))
    s = a['stats']; cal = a['calibration']
    L += ['', '## (a) Yeast dosing', '',
          'Model: per-revolution g/rev drawn from N(%.3f, (%.2f x %.3f)^2) with a seeded RNG. Yeast leaves only on new screw travel, so the '
          '1/4-turn reverse after each AUG costs 1/4 rev of dispensing at the start of the next AUG. Host: first pass %.0f %% of target by revolutions, '
          'scale verification, at most %d top-ups of round((target - m)/g_per_rev, %.1f). P2 is teleported between its pick pocket and the scale pan '
          '(the transfer-arm move is the sequencer\'s job); its empty tare on the simulated HX711 was %.3f g.' % (
              a['g_per_rev_true'], a['cv'], a['g_per_rev_true'], 100 * P['auger']['first_pass_frac'], P['auger']['max_topups'], P['auger_model']['rev_resolution'],
              a['beaker_tare_g']), '',
          'Landing: outlet %.3f mm from the P2 axis at the auger station (limit %.3f = inner radius - outlet radius), %.1f mm above the lip; receiver = %s.' % (
              a['landing']['outlet_to_axis_mm'], a['landing']['limit_mm'], a['landing']['outlet_above_lip_mm'], a['landing']['receiver']), '',
          'Calibration (architecture 6, %d x %.0f rev into the tared cup): **%.4f g/rev** (model mean %.3f per dispensing revolution). Runs: %s.' % (
              len(cal['runs']), P['auger_model']['cal_revs'], cal['g_per_rev'], a['g_per_rev_true'],
              ', '.join('%.3f g/rev' % r['g_per_rev'] for r in cal['runs'])), '',
          '| Dose | Status | First pass (rev) | Top-ups | Revs total | Scale (g) | Error (g) | Ledger truth (g) | Truth error (g) |', '|---|---|---|---|---|---|---|---|---|']
    for r in a['doses']:
        L.append('| %d | %s | %.1f | %d | %.1f | %s | %s | %.3f | %+.3f |' % (r['n'], r['status'], r['passes'][0]['rev_cmd'], r['topups'], r['revs'],
                                                                         fmt(r['measured_g']), fmt(r['error_g'], '%+.3f'), r['truth_g'], r['truth_error_g']))
    L += ['', 'Target %.1f g +- %.1f g over %d doses: scale error mean %+.3f g, std %.3f g, max |error| %.3f g; ledger truth mean %+.3f g, std %.3f g, '
          'max |error| %.3f g. Top-up counts %s. Yeast spilled: %.4f g.' % (
              P['recipe']['yeast_g'], s['tol_g'], s['n'], s['mean_error_g'], s['std_error_g'], s['max_abs_error_g'], s['truth_mean_error_g'],
              s['truth_std_error_g'], s['truth_max_abs_error_g'], s['topups'], s['spilled_g']), '',
          '| Fault case | Result |', '|---|---|',
          '| Transient jam (screw blocked 0.25 s, 1 s into the first pass) | %s, first-pass stalls %s, scale %s g |' % (
              a['transient_jam']['status'], a['transient_jam']['first_pass_stalls'], fmt(a['transient_jam']['measured_g'])),
          '| Jammed auger | fault %s after %d stall events |' % (a['jam']['fault'], a['jam']['stalls']),
          '| Empty hopper (device model rule) | fault %s: %s |' % (a['hopper_empty']['fault'], a['hopper_empty']['detail']),
          '| Empty hopper (host scale rule, device rule off) | fault %s: %s |' % (a['hopper_empty_host']['fault'], a['hopper_empty_host']['detail']), '',
          'Sensitivity to a host g/rev error (true g/rev unchanged; informational):', '',
          '| Host g/rev / calibrated | Status | First pass (rev) | Top-ups | Scale (g) | Truth (g) |', '|---|---|---|---|---|---|']
    for r in a['sensitivity']:
        L.append('| %.2f | %s | %.1f | %d | %s | %.3f |' % (r['host_over_calibrated'], r['status'], r['first_rev'], r['topups'], fmt(r['measured_g']), r['truth_g']))
    L += ['', '## (b) Carousel stations', '', 'Deck angle that brings each pocket to each station; bearings from update13_final, pocket angles from '
          '[carousel] pocket_ids_deg.', '', '| Pocket | Station | Station bearing (deg) | Deck angle (deg) |', '|---|---|---|---|']
    for r in b['table']: L.append('| %d | %s | %.3f | %s |' % (r['pocket'], r['station'], r['station_bearing_deg'], r['deck_deg']))
    L += ['', 'Moves at the commanded minimum time (%.1f s per 45 deg). Gates: deck within the firmware done tolerance %.1f deg, pocket centres and '
          'beaker offsets within %.1f mm, travel time between commanded and commanded + %.1f s.' % (
              P['carousel']['min_s_per_45deg'], b['done_tol_deg'], b['tol_mm'], P['carousel']['timeout_extra_s']), '',
          '| Deck cmd (deg) | Span (deg) | Cmd (s) | Travel (s) | Deck error (deg) | Pick: pocket, error (mm) | Auger: pocket, error (mm) | P1 offset (mm) | P2 offset (mm) |',
          '|---|---|---|---|---|---|---|---|---|']
    for x in b['stops']:
        L.append('| %.2f | %.1f | %.3f | %.3f | %+.3f | %d (%s), %.3f | %d (%s), %.3f | %.3f | %.3f |' % (
            x['cmd_deg'], x['span_deg'], x['cmd_ms'] / 1000.0, x['travel_s'], x['deck_error_deg'], x['stations']['pick']['pocket'], x['stations']['pick']['beaker'],
            x['stations']['pick']['position_error_mm'], x['stations']['auger']['pocket'], x['stations']['auger']['beaker'], x['stations']['auger']['position_error_mm'],
            x['beakers']['P1']['offset_mm'], x['beakers']['P2']['offset_mm']))
    L += ['', '## (c) Stage slider-crank', '', 'Analytic s(theta) = (r + L) - r cos(theta) - sqrt(L^2 - r^2 sin^2(theta)), r %.0f, L %.0f; s(%.0f deg) = %.4f mm.' % (
              P['stage']['crank_r'], P['stage']['rod_l'], P['stage']['erupt_deg'], c['analytic_150_mm']), '',
          '| Cmd (deg) | Crank measured (deg) | Sled travel MuJoCo (mm) | Analytic at measured (mm) | Linkage error (mm) | Analytic at cmd (mm) | Error vs cmd (mm) |',
          '|---|---|---|---|---|---|---|']
    for r in c['rows']:
        L.append('| %d | %.3f | %.3f | %.3f | %+.4f | %.3f | %+.4f |' % (r['cmd_deg'], r['crank_deg'], r['sled_travel_mm'], r['analytic_at_measured_mm'],
                                                                  r['linkage_error_mm'], r['analytic_at_cmd_mm'], r['error_vs_cmd_mm']))
    L += ['', 'Max linkage error %.4f mm; max error vs commanded angle %.4f mm (gate %.1f mm).' % (c['max_linkage_error_mm'], c['max_error_vs_cmd_mm'], c['tol_mm']),
          '', '| Move | Crank (deg) | Sled travel (mm) | Travel time (s) | Commanded (s) |', '|---|---|---|---|---|']
    for x in c['moves']: L.append('| %s | %.3f | %.3f | %.3f | %.3f |' % (x['position'], x['crank_deg'], x['sled_travel_mm'], x['travel_s'], x['cmd_s']))
    F = d['params']
    L += ['', '## (d) Foam', '',
          'O2 yield: %.0f g developer x %.2f = %.2f g H2O2 = %.4f mol -> %.4f mol O2 x %.2f L/mol = **%.0f mL** (demo_process 1: about 1.7 L). '
          'Flask internal volume (modelled frustum + neck) %.1f mL.' % (
              P['recipe']['developer_g'], F['h2o2_mass_frac'], P['recipe']['developer_g'] * F['h2o2_mass_frac'],
              P['recipe']['developer_g'] * F['h2o2_mass_frac'] / F['h2o2_molar_mass'], P['recipe']['developer_g'] * F['h2o2_mass_frac'] / F['h2o2_molar_mass'] / 2,
              F['o2_molar_volume_l'], d['o2_yield_ml'], d['flask_internal_ml']), '',
          'Parameters ([foam], mostly assumed): induction %.1f s, k = %.2f mL/(g s) x yeast g / liquid mL, trap fraction %.2f with soap (%.2f without), '
          'liquid fraction %.2f, collapse tau %.0f s, column max %.0f mm above the neck, column diameter = neck bore %.0f mm.' % (
              F['induction_s'], F['k_ml_per_g_s'], F['trap_frac_soap'], F['trap_frac_no_soap'], F['liquid_frac'], F['collapse_tau_s'], F['column_max_mm'],
              P['flask']['neck_id']), '',
          'Timeline (t = 0 when the yeast slurry enters the flask, all at once): stage starts at %.1f s and reaches ERUPT at %.2f s (sled %.2f mm); '
          'foam reaches the neck top at %s s; column peak %.1f mm at %s s; after %.0f s, %.0f mL O2 released, %.0f mL foam made, %.0f mL overflowed '
          'into the catch well.' % (
              d['t_stage_start'], d['t_stage_at_erupt'], d['sled_travel_mm'], d['t_foam_at_neck'], d['state']['peak_mm'], d['t_peak'], FOAM_RUN_S,
              d['state']['o2_ml'], d['state']['foam_ml'], d['state']['overflow_ml']), '']
    margin = None if d['t_foam_at_neck'] is None else d['t_foam_at_neck'] - d['t_stage_at_erupt']
    L += ['Timing note (informational; it rests on the assumed induction_s and k): foam reaches the neck top %s the sled arrives at ERUPT '
          '(margin %s s), with the sled at %s mm of its %.1f mm travel by then. Architecture 4.5 wants the catalyst-to-neck time measured on the '
          'first live run.' % ('after' if margin is not None and margin >= 0 else 'BEFORE', 'n/a' if margin is None else '%+.2f' % margin,
                               fmt(d['sled_travel_at_foam_neck_mm'], '%.1f'), d['sled_travel_mm']), '',
          '| t (s) | H2O2 left (g) | O2 (mL) | Foam made (mL) | Foam in flask (mL) | Column above neck (mm) | Overflow (mL) |', '|---|---|---|---|---|---|---|']
    for r in d['curve']:
        L.append('| %.0f | %.3f | %.0f | %.0f | %.0f | %.1f | %.0f |' % (r['t'], r['h2o2_left_g'], r['o2_ml'], r['foam_ml'], r['inside_ml'], r['column_mm'], r['overflow_ml']))
    L += ['', 'Zero cases (%.0f s each): %s.' % (FOAM_RUN_S, '; '.join('%s: peak %.1f mm, foam %.1f mL, O2 %.0f mL' % (k, v['peak_mm'], v['foam_ml'], v['o2_ml'])
                                                               for k, v in d['zero_cases'].items())), '',
          '### Foam camera check (%s, %dx%d, fovy %.0f deg)' % (d['camera']['name'], d['camera']['width'], d['camera']['height'], d['camera']['fovy_deg']), '',
          'The flask_neck_top site is projected with f = (H/2)/tan(fovy/2) and the camera pose (data.cam_xpos/cam_xmat). The region is %.0f projected '
          'column radii either side of that pixel, from the image top down to it. Foam-coloured pixels: hue within %.0f deg of the foam rgba hue, saturation '
          '>= %.2f, value >= %.2f. Cross-checks: MuJoCo segmentation of the foam geom in the same region, and the predicted vs segmented top row of the '
          'column. The funnel (alpha 0.55) stands in front of the lower column: the colour test sees the foam through it, but segmentation records the '
          'funnel. The top-row check is therefore gated only while the column top is above the funnel rim (marked *). '
          'Saved frames are annotated: cyan = region, green = projected neck top.' % (
              d['camera']['region_half_width_radii'], d['camera']['hue_tol_deg'], d['camera']['min_sat'], d['camera']['min_val']), '',
          '| t (s) | Column (mm) | Neck pixel (u, v) | Colour px in region | Segmented px in region | Colour px outside | Top row predicted / segmented | Frame |',
          '|---|---|---|---|---|---|---|---|']
    for fr in d['frames']:
        tc = fr['top_check']; L.append('| %.2f | %.1f | %s | %d | %d | %d | %s | %s |' % (
            fr['t'], fr['column_mm'], fr['neck_px'], fr['colour_px'], fr['segmented_px'], fr['colour_px_outside'],
            '-' if not tc else '%.1f / %d%s' % (tc['predicted_v'], tc['segmented_v'], ' *' if tc['above_rim'] else ''), '[png](%s)' % fr['png'].replace('reports/', '') if 'png' in fr else ''))
    L += ['', '## Approximations', '',
          '- Auger: grams per revolution are i.i.d. normal per revolution of new screw travel; no bridging, no compaction, no dependence on hopper '
          'level until the hopper is empty. The fall from the outlet is instant.',
          '- The ledger applies the yeast weight to P2 as an external force, and the simulated scale reads it through the HX711 model (noise %.2f g at 80 Hz, '
          'mean of %d samples).' % (P['scale']['noise_g'], SCALE_SAMPLES),
          '- Foam: first-order kinetics after a fixed induction delay. The headspace ignores the liquid carried into the foam. The column is a cylinder of '
          'neck-bore diameter drawn through the funnel, which is ignored. Collapse is a single exponential; overflow above the standing height is '
          'only bookkept. None of this is CFD.',
          '- Stage and carousel use the MuJoCo position actuators driven by the simulated Mega smoothstep. The closed slider-crank uses a soft connect '
          'equality, so linkage errors are constraint compliance.']
    (REPORTS / 'mechanisms_report.md').write_text('\n'.join(L) + '\n')


def main():
    t = time.time(); model, builder = scene.build(); rep = dict(params=builder.P)
    print('(b) carousel'); rep['carousel'] = check_carousel(model, builder)
    print('(c) stage'); rep['stage'] = check_stage(model, builder)
    print('(a) dosing'); rep['doses'] = check_doses(model, builder)
    print('(d) foam'); rep['foam'] = check_foam(model, builder)
    for k in ('doses', 'carousel', 'stage', 'foam'): rep[k]['gates'] = {g: bool(v) for g, v in rep[k]['gates'].items()}
    gates = {'%s.%s' % (k, g): v for k in ('doses', 'carousel', 'stage', 'foam') for g, v in rep[k]['gates'].items()}
    rep['pass_'] = all(gates.values()); rep['failed'] = [k for k, v in gates.items() if not v]; rep['wall_s'] = round(time.time() - t, 1)
    write_report(rep)
    for k, v in gates.items(): print('  %-55s %s' % (k, 'PASS' if v else 'FAIL'))
    print('mechanisms gate:', 'PASS' if rep['pass_'] else 'FAIL %s' % rep['failed'], '->', REPORTS / 'mechanisms_report.md')
    return 0 if rep['pass_'] else 1


if __name__ == '__main__':
    sys.exit(main())
