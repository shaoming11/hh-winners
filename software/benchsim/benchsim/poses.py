"""MuJoCo-native station poses and arm paths (simulation only).

These are solved on the MJCF arms by IK, seeded from the recorded CAD poses mapped with benchsim.cadmap so the
planner's choices (grasp type, hinge up/down, pour direction, lip height) are kept, but every endpoint is exact
in the MuJoCo model. They are NOT hardware trajectories: the recorded files in tools/layout/ are untouched, and
the hardware backend refuses plans whose ``origin`` is ``mujoco-native``.

A plan is a list of segments: dict(name, kind, phase, qs [list of 6-vectors, MJCF rad], gripper ('open' | 'close' |
'hold'), held (beaker name or None), grasp (site name)). ``check_plan`` measures margins, contacts and clearance on
every densified configuration.
"""
import json
import math

import numpy as np

from . import cadmap, paths, scene, state, trajectories
from .kinematics import RULE, Kin

Z_CARRY = 300.0              # pourer: grasp centre height on carries (demo_process 3)
APPROACH_MM = 45.0           # side-grasp stand-off along the approach direction
TD_ABOVE_MM = 20.3           # transfer: the recorded T1/T2 paths lift the beaker 20.3 mm and carry at that height;
                             # higher top-down lifts run the wrist flex into its limit at r ~190 mm (kinematics report)
TD_SLIDE_MM = 60.0           # slide out along the finger channel after a top-down place (demo_process 3)
TD_LIFT_MM = 20.0
LIP_PRE_MM = 50.0            # pre-pour: lip this far above its pour height (recorded tilt-in starts ~50 mm up)
LIP_DRIFT_MAX_MM = 25.0      # planner rule: lip free along the pour direction, drift <= 25 mm (layout_final.py)
MAX_DEV = math.radians(17.0)  # continuation IK search box around the previous configuration
CONTACT_MM = 0.5             # report contacts deeper than this (beaker walls are 20-box polygons; the fixed finger
                             # is meant to touch the beaker at the grasp)
SIDE_CLEAR_MM = 4.0          # side grasp: descend with the fixed finger this far off the beaker wall, then close the gap
GH_STEP_MAX_MM = 15.0        # side grasp: raise the grip height at most this much to meet the pick margin rule
PLACE_CLEAR_MM = 1.5         # placements release this far above the floor (the beaker drops onto it)
UP = np.array([0, 0, 1.0])


class PlanError(RuntimeError):
    pass


def _densify(qs, max_step_deg=1.5):
    out = [np.asarray(qs[0], float)]
    for a, b in zip(qs[:-1], qs[1:]):
        a, b = np.asarray(a, float), np.asarray(b, float)
        n = max(1, int(math.ceil(math.degrees(np.abs(b - a).max()) / max_step_deg)))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return out


class Planner:
    def __init__(self, model, builder):
        self.m = model; self.b = builder; self.K = Kin(model); self.st = builder.st; self.P = builder.P
        self.park = state.park_q(); self.rec = {s['step']: s for s in trajectories.load()['steps']}
        gd = json.loads(paths.GRIPPER_DESIGN.read_text())['grip']['56']
        self.q6_contact = cadmap.cad_gripper_to_mj(math.radians(gd['q_contact']))
        self.q6_open = cadmap.cad_gripper_to_mj(math.radians(gd['q_open']))
        self.q6_wide = cadmap.cad_gripper_to_mj(math.radians(gd['q_open'] + 12.0))
        self.H = self.P['beaker']['height']; self.R = self.P['beaker']['od'] / 2

    # ------------------------------------------------------------------ helpers
    def station(self, name):
        """station bottom point (mm). 'carousel@<deg>' = the pocket at that world angle (the deck has turned)"""
        if name.startswith('carousel@'):
            a = math.radians(float(name.split('@')[1])); c = self.st['carousel_centre']['xy']; r = self.P['carousel']['pitch_r']
            return np.r_[c[0] + r * math.cos(a), c[1] + r * math.sin(a), self.st['carousel_pick']['z']]
        s = self.st[name]; return np.r_[s['xy'], s['z']]

    def ik(self, arm, site, pos, z_axis, seed, x_axis=None, z_sign_free=False, tol=0.5, cont=False, soft_dir=None):
        """cont=True: a continuation step, kept within MAX_DEV of the seed so a path stays on one IK branch.
        soft_dir: the position is only weakly held along this direction (the pour lip may drift along d)"""
        q, e, a = self.K.ik(arm, site, pos, z_axis=z_axis, x_axis=x_axis, q0=seed, z_sign_free=z_sign_free, iters=300,
                            max_dev=MAX_DEV if cont else None, soft_dir=soft_dir)
        if e > tol or a > 0.5:
            raise PlanError('%s IK for %s at %s: residual %.2f mm / %.2f deg' % (arm, site, np.round(pos, 1), e, a))
        return q

    def line(self, arm, site, q0, p1, z_axis, steps_mm=4.0, q6=None):
        """Cartesian straight line of a site from its pose at q0 to p1, keeping its z axis"""
        p0, _ = self.K.site(arm, q0, site); n = max(2, int(math.ceil(np.linalg.norm(p1 - p0) / steps_mm)) + 1)
        qs = [np.array(q0, float)]
        for k in range(1, n):
            qn = self.ik(arm, site, p0 + (p1 - p0) * k / (n - 1), z_axis, qs[-1], cont=True)
            qn[5] = q0[5] if q6 is None else q6
            if math.degrees(np.abs(qn[:5] - qs[-1][:5]).max()) > 12: raise PlanError('%s line jumps at step %d' % (arm, k))
            qs.append(qn)
        return qs

    def seg(self, name, kind, phase, qs, gripper='hold', held=None, grasp=None):
        return dict(name=name, kind=kind, phase=phase, qs=[np.asarray(q, float) for q in qs], gripper=gripper, held=held, grasp=grasp)

    # ------------------------------------------------------------------ transfer arm (top-down)
    def td_grasp(self, station, seed):
        q = self.ik('transfer', 'grasp_td_taught', self.station(station), UP, seed); q[5] = self.q6_wide; return q

    def plan_transfer(self, beaker, src, dst):
        """carousel <-> scale with the top-down taught grasp (demo_process steps 1, 4, 6, 9). Descend with the fixed
        finger 3 mm off the beaker (site grasp_td_taught), move the hand 3 mm so it touches (grasp_td_contact), close;
        at the destination release, move back 3 mm, lift 20 mm and slide out along the finger channel."""
        rec = self.rec['T1' if src == 'carousel_pick' else 'T2']['anim_paths'][0]['qs']
        seed_a = np.r_[cadmap.cad_to_mj(rec[0]), self.q6_wide]; seed_b = np.r_[cadmap.cad_to_mj(rec[-1]), self.q6_wide]
        site, cs = 'grasp_td_taught', 'grasp_td_contact'
        qa = self.td_grasp(src, seed_a); qb = self.td_grasp(dst, seed_b)
        pa = self.station(src); pb = self.station(dst) + [0, 0, PLACE_CLEAR_MM]
        qa_up = self.ik('transfer', site, pa + [0, 0, TD_ABOVE_MM], UP, qa); qa_up[5] = self.q6_wide
        descend = self.line('transfer', site, qa_up, pa, UP, q6=self.q6_wide)
        touch = self.line('transfer', cs, descend[-1], pa, UP, steps_mm=1.0, q6=self.q6_wide)
        lift = self.line('transfer', cs, np.r_[touch[-1][:5], self.q6_contact], pa + [0, 0, TD_ABOVE_MM], UP, q6=self.q6_contact)
        qb_above = self.ik('transfer', cs, pb + [0, 0, TD_ABOVE_MM - PLACE_CLEAR_MM], UP, qb); qb_above[5] = self.q6_contact
        lower = self.line('transfer', cs, qb_above, pb, UP, q6=self.q6_contact)
        q_rel = np.r_[lower[-1][:5], self.q6_wide]
        untouch = self.line('transfer', site, q_rel, pb, UP, steps_mm=1.0, q6=self.q6_wide)
        up20 = self.line('transfer', site, untouch[-1], pb + [0, 0, TD_ABOVE_MM], UP, q6=self.q6_wide)
        slide = self._channel_line(up20[-1], pb + [0, 0, TD_ABOVE_MM], out=True)
        slide_in = self._channel_line(qa_up, pa + [0, 0, TD_ABOVE_MM], out=False)
        q_hi = slide_in[0].copy(); q_hi[1] -= math.radians(12.0)          # raise the upper arm: hand up and back
        q_hi_out = slide[-1].copy(); q_hi_out[1] -= math.radians(12.0)
        return [self.seg('approach park->above channel entry', 'joint', 'approach', [self.park_open(), q_hi], 'open'),
                self.seg('lower to channel entry', 'joint', 'approach', [q_hi, slide_in[0]], 'open'),
                self.seg('slide in along finger channel', 'cartesian', 'approach', slide_in, 'open'),
                self.seg('descend to %s' % src, 'cartesian', 'approach', descend, 'open'),
                self.seg('touch fixed finger to %s' % beaker, 'cartesian', 'approach', touch, 'open'),
                self.seg('close on %s' % beaker, 'grip', 'pick', [touch[-1], np.r_[touch[-1][:5], self.q6_contact]], 'close', grasp=cs),
                self.seg('lift from %s' % src, 'cartesian', 'carry', lift, 'hold', beaker, cs),
                self.seg('carry %s->%s' % (src, dst), 'joint', 'carry', [lift[-1], qb_above], 'hold', beaker, cs),
                self.seg('lower onto %s' % dst, 'cartesian', 'carry', lower, 'hold', beaker, cs),
                self.seg('release', 'grip', 'place', [lower[-1], q_rel], 'open', grasp=cs),
                self.seg('move fixed finger off %s' % beaker, 'cartesian', 'retreat', untouch, 'open'),
                self.seg('lift 20 mm', 'cartesian', 'retreat', up20, 'open'),
                self.seg('slide out along finger channel', 'cartesian', 'retreat', slide, 'open'),
                self.seg('return to park', 'joint', 'park', [slide[-1], q_hi_out, self.park_open()], 'open')]

    def _channel_line(self, q_at, p_at, out=True):
        """straight line along the finger channel (the grasp site x axis = hinge direction, horizontal) between
        the pose above the beaker and a point TD_SLIDE_MM to the side; picks the side with more clearance"""
        site = 'grasp_td_taught'; _, Rs = self.K.site('transfer', q_at, site)
        dirv = Rs[:, 0].copy(); dirv[2] = 0; dirv /= np.linalg.norm(dirv); best = None
        for sgn in (1, -1):
            try:
                far = p_at + sgn * TD_SLIDE_MM * dirv
                if out: qs = self.line('transfer', site, q_at, far, UP, q6=q_at[5])
                else:
                    q_far = self.ik('transfer', site, far, UP, q_at); q_far[5] = q_at[5]
                    qs = self.line('transfer', site, q_far, p_at, UP, q6=q_at[5])
                c = min(self.K.clearance('transfer', q, self.others('transfer'))[0] for q in qs[::3])
                if best is None or c > best[0]: best = (c, qs)
            except PlanError: pass
        if best is None: raise PlanError('no finger-channel direction is reachable')
        return best[1]

    def park_open(self):
        q = self.park.copy(); return q

    def others(self, arm):
        return {a: self.park for a in scene.ARMS if a != arm}

    # ------------------------------------------------------------------ pourer (side grasp, wrist-roll pour)
    def side_grasp(self, station, gh, seed_q):
        """grasp centre on the beaker axis gh above the bottom, hinge vertical (sign kept from the seed)"""
        _, R = self.K.site('pourer', seed_q, 'grasp_side'); sgn = 1.0 if R[2, 2] > 0 else -1.0
        q = self.ik('pourer', 'grasp_side', self.station(station) + [0, 0, gh], sgn * UP, seed_q); q[5] = self.q6_open
        return q, sgn

    def plan_pour_best(self, step, beaker, src, gh_doc, lip_above, recv, beakers_at):
        """documented grip height first; if its pick misses the margin rule, try gh_doc-2 .. gh_doc+GH_STEP_MAX_MM in 1 mm
        steps and keep the plan with the best pick margin that is otherwise clean (pour margin rule, lip drift, no
        contacts). Returns (segs, info) with both the documented and the chosen result."""
        cands = []
        for gh in [gh_doc] + [g for g in np.arange(gh_doc - 2, gh_doc + GH_STEP_MAX_MM + 0.1, 1.0) if g != gh_doc]:
            try: segs, info = self.plan_pour(step, beaker, src, float(gh), lip_above, recv)
            except PlanError as e:
                cands.append(dict(gh=float(gh), ok=False, why=str(e))); continue
            rows = self.check_plan('pourer', segs, beakers_at)
            pick = self.K.min_margin('pourer', segs[2]['qs'][-1])
            clean = all(r['contacts'] == 0 for r in rows) and all(r['margin_ok'] for r in rows if r['phase'] not in ('pick', 'place'))
            cands.append(dict(gh=float(gh), ok=clean, pick=pick, segs=segs, info=info, rows=rows))
            if gh == gh_doc and clean and pick[0] >= RULE['pick']: break
        doc = cands[0]; good = [c for c in cands if c['ok']]
        if not good: raise PlanError('%s: no clean plan for grip heights %s' % (step, [c['gh'] for c in cands]))
        best = doc if (doc['ok'] and doc['pick'][0] >= RULE['pick']) else max(good, key=lambda c: c['pick'][0])
        info = dict(best['info']); info.update(grip_h_doc=gh_doc, grip_h_used=best['gh'],
                                               pick_margin_doc=None if not doc.get('pick') else round(doc['pick'][0], 2),
                                               pick_margin_used=round(best['pick'][0], 2), pick_binding=best['pick'][1],
                                               pick_rule_met=best['pick'][0] >= RULE['pick'],
                                               grip_h_scan=[dict(gh=c['gh'], ok=c['ok'], pick_margin=None if not c.get('pick') else round(c['pick'][0], 2),
                                                                 why=c.get('why')) for c in cands])
        return best['segs'], info

    def pour_frames(self, step, sgn, gh):
        """recorded pour manifold mapped to MJCF -> per-theta (d, lip offset along d) in this model"""
        rec = self.rec[step]; recv = trajectories.RECEIVER[step]; rc = self.station(recv)
        T = trajectories._held_T(sgn, gh); out = []
        for k in (1, 2):
            for qc in rec['anim_paths'][k]['qs']:
                q = np.r_[cadmap.cad_to_mj(qc), self.q6_contact]
                self.K.set('pourer', q); s = self.K.d.site('pourer/grasp_side'); Rs = s.xmat.reshape(3, 3)
                u = Rs @ T[:3, :3][:, 2]; th = math.degrees(math.acos(np.clip(u[2], -1, 1)))
                if th < 2: continue
                dvec = u.copy(); dvec[2] = 0; dvec /= np.linalg.norm(dvec)
                bottom = s.xpos * 1000 + Rs @ (T[:3, 3] * 1000); top = bottom + self.H * u
                w = math.cos(math.radians(th)) * dvec - math.sin(math.radians(th)) * UP; lip = top + self.R * w
                out.append((th, dvec, float((lip[:2] - rc[:2]) @ dvec[:2]), q))
        return out

    def manifold_target(self, th, dvec, off, recv, lip_above):
        rc = self.station(recv); rim = rc[2] + (self.H if recv == 'scale_pan' else 0.0)
        t = math.radians(th); u = math.cos(t) * UP + math.sin(t) * dvec; w = math.cos(t) * dvec - math.sin(t) * UP
        lip = np.r_[rc[:2] + off * dvec[:2], rim + lip_above]
        return lip, u, w

    def grasp_for_beaker(self, lip, u, w, gh):
        bottom = lip - self.R * w - self.H * u
        return bottom + gh * u

    def plan_pour(self, step, beaker, src, gh, lip_above, recv, thetas=(40.0, 105.0)):
        rec = self.rec[step]
        q_pick, sgn = self.side_grasp(src, gh, np.r_[cadmap.cad_to_mj(np.radians(rec['q_pick'])), self.q6_open])
        ghinfo = dict(grip_h_used=gh)
        frames = self.pour_frames(step, sgn, rec['grip_h'])
        dvec = np.mean([f[1] for f in frames if f[0] > 35], axis=0); dvec[2] = 0; dvec /= np.linalg.norm(dvec)
        th_rec = np.array([f[0] for f in frames]); off_rec = np.array([f[2] for f in frames]); order = np.argsort(th_rec)
        off_of = lambda th: float(np.interp(th, th_rec[order], off_rec[order]))
        # pour manifold 40..105 by 1 deg, continuation from the mapped recorded frame nearest 40 deg
        seed = min(frames, key=lambda f: abs(f[0] - thetas[0]))[3]; man = []; drift = []
        for th in np.arange(thetas[0], thetas[1] + 0.01, 1.0):
            lip, u, w = self.manifold_target(th, dvec, off_of(th), recv, lip_above)
            tgt = self.grasp_for_beaker(lip, u, w, gh)
            q = self.ik('pourer', 'grasp_side', tgt, sgn * u, seed, cont=len(man) > 0, soft_dir=dvec)
            p, _ = self.K.site('pourer', q, 'grasp_side'); drift.append(float((p - tgt) @ dvec))
            q[5] = self.q6_contact; man.append(q); seed = q
        lip_drift = max(drift) - min(drift)
        if lip_drift > LIP_DRIFT_MAX_MM: raise PlanError('%s lip drifts %.1f mm along the pour direction (> %.0f)' % (step, lip_drift, LIP_DRIFT_MAX_MM))
        # tilt-in: from the recorded upright pre-pour position (anim_paths tilt-in segment, first frame), refined to an
        # exactly upright beaker in MJCF, joint-interpolated into the exact 40 deg manifold pose
        q_rec_pre = np.r_[cadmap.cad_to_mj(rec['anim_paths'][1]['qs'][0]), self.q6_contact]
        p_rec_pre, _ = self.K.site('pourer', q_rec_pre, 'grasp_side')
        q_pre = self.ik('pourer', 'grasp_side', p_rec_pre + [0, 0, gh - rec['grip_h']], sgn * UP, q_rec_pre); q_pre[5] = self.q6_contact
        tilt = _densify([q_pre, man[0]], 2.0)
        ps = self.station(src); pick_up = ps + [0, 0, gh]
        # the recorded side-grasp approach descends vertically with the jaw open (anim_paths seg 3); margin grows upward.
        # The fixed finger is tangent to the beaker at contact, so descend SIDE_CLEAR_MM off it and close the gap at the bottom.
        _, Rp = self.K.site('pourer', q_pick, 'grasp_side')
        n_in = -math.sin(math.radians(25.0)) * Rp[:, 0] + math.cos(math.radians(25.0)) * Rp[:, 1]; n_in[2] = 0; n_in /= np.linalg.norm(n_in)
        off = pick_up - SIDE_CLEAR_MM * n_in
        q_stand = self.ik('pourer', 'grasp_side', off + [0, 0, APPROACH_MM], sgn * UP, q_pick); q_stand[5] = self.q6_open
        q_high = self.ik('pourer', 'grasp_side', off + [0, 0, APPROACH_MM + 60.0], sgn * UP, q_stand); q_high[5] = self.q6_open
        down = self.line('pourer', 'grasp_side', q_stand, off, sgn * UP, q6=self.q6_open)
        go_in = down + self.line('pourer', 'grasp_side', down[-1], pick_up, sgn * UP, steps_mm=1.0, q6=self.q6_open)[1:]
        q_hold = np.r_[go_in[-1][:5], self.q6_contact]
        lift = self.line('pourer', 'grasp_side', q_hold, np.r_[ps[:2], Z_CARRY], sgn * UP, q6=self.q6_contact)
        lower = self.line('pourer', 'grasp_side', lift[-1], pick_up + [0, 0, PLACE_CLEAR_MM], sgn * UP, q6=self.q6_contact)
        q_rel = np.r_[lower[-1][:5], self.q6_open]
        side = self.line('pourer', 'grasp_side', q_rel, off + [0, 0, PLACE_CLEAR_MM], sgn * UP, steps_mm=1.0, q6=self.q6_open)
        back = side + self.line('pourer', 'grasp_side', side[-1], off + [0, 0, APPROACH_MM], sgn * UP, q6=self.q6_open)[1:]
        # carry at Z_CARRY to above the pre-pour pose, then straight down to it
        p_pre, _ = self.K.site('pourer', q_pre, 'grasp_side')
        q_above = self.ik('pourer', 'grasp_side', np.r_[p_pre[:2], Z_CARRY], sgn * UP, q_pre); q_above[5] = self.q6_contact
        to_pre = self.line('pourer', 'grasp_side', q_above, p_pre, sgn * UP, q6=self.q6_contact)
        segs = [self.seg('approach park->above %s' % src, 'joint', 'approach', [self.park, q_high, q_stand], 'open'),
                self.seg('descend to %s' % src, 'cartesian', 'approach', go_in, 'open'),
                self.seg('close on %s' % beaker, 'grip', 'pick', [go_in[-1], q_hold], 'close', grasp='grasp_side'),
                self.seg('lift from %s' % src, 'cartesian', 'carry', lift, 'hold', beaker, 'grasp_side'),
                self.seg('carry to above pre-pour', 'joint', 'carry', [lift[-1], q_above], 'hold', beaker, 'grasp_side'),
                self.seg('lower to pre-pour', 'cartesian', 'carry', to_pre, 'hold', beaker, 'grasp_side'),
                self.seg('tilt-in 0->40', 'pour', 'pour', tilt, 'hold', beaker, 'grasp_side'),
                self.seg('pour manifold 40->105', 'manifold', 'pour', man, 'hold', beaker, 'grasp_side'),
                self.seg('untilt to pre-pour', 'pour', 'pour', tilt[::-1], 'hold', beaker, 'grasp_side'),
                self.seg('raise from pre-pour', 'cartesian', 'carry', to_pre[::-1], 'hold', beaker, 'grasp_side'),
                self.seg('carry back above %s' % src, 'joint', 'carry', [q_above, lift[-1]], 'hold', beaker, 'grasp_side'),
                self.seg('lower into %s' % src, 'cartesian', 'carry', lower, 'hold', beaker, 'grasp_side'),
                self.seg('release', 'grip', 'place', [lower[-1], q_rel], 'open', grasp='grasp_side'),
                self.seg('lift out', 'cartesian', 'retreat', back, 'open'),
                self.seg('return to park', 'joint', 'park', [back[-1], q_high, self.park], 'open')]
        info = dict(sign=sgn, dvec=dvec.tolist(), manifold_thetas=list(np.arange(thetas[0], thetas[1] + 0.01, 1.0)), lip_above_rim=lip_above,
                    receiver=recv, lip_drift_mm=round(lip_drift, 2), lip_offset_along_d_mm=[round(off_of(t) + dd, 1) for t, dd in
                                                                             zip(np.arange(thetas[0], thetas[1] + 0.01, 1.0), drift)], **ghinfo)
        return segs, info

    def plan_side_transfer(self, beaker, src, dst, gh, seed_step='P_dev', seed_dst='P_fun'):
        """pourer side-grasp transfer (e.g. rack -> scale): pick, lift to Z_CARRY, joint carry, lower, release, retreat"""
        qa, sgn = self.side_grasp(src, gh, np.r_[cadmap.cad_to_mj(np.radians(self.rec[seed_step]['q_pick'])), self.q6_open])
        qb, sgn_b = self.side_grasp(dst, gh, np.r_[cadmap.cad_to_mj(np.radians(self.rec[seed_dst]['q_pick'])), self.q6_open])
        if sgn_b != sgn: raise PlanError('hinge sign differs between %s and %s' % (src, dst))
        pa = self.station(src) + [0, 0, gh]; pb = self.station(dst) + [0, 0, gh]
        q_up_a = self.ik('pourer', 'grasp_side', pa + [0, 0, APPROACH_MM], sgn * UP, qa); q_up_a[5] = self.q6_open
        q_hi_a = self.ik('pourer', 'grasp_side', pa + [0, 0, APPROACH_MM + 60.0], sgn * UP, q_up_a); q_hi_a[5] = self.q6_open
        down = self.line('pourer', 'grasp_side', q_up_a, pa, sgn * UP, q6=self.q6_open)
        q_hold = np.r_[down[-1][:5], self.q6_contact]
        lift = self.line('pourer', 'grasp_side', q_hold, np.r_[pa[:2], Z_CARRY], sgn * UP, q6=self.q6_contact)
        q_above_b = self.ik('pourer', 'grasp_side', np.r_[pb[:2], Z_CARRY], sgn * UP, qb); q_above_b[5] = self.q6_contact
        lower = self.line('pourer', 'grasp_side', q_above_b, pb + [0, 0, PLACE_CLEAR_MM], sgn * UP, q6=self.q6_contact)
        q_rel = np.r_[lower[-1][:5], self.q6_open]
        out = self.line('pourer', 'grasp_side', q_rel, pb + [0, 0, APPROACH_MM], sgn * UP, q6=self.q6_open)
        return [self.seg('approach park->above %s' % src, 'joint', 'approach', [self.park, q_hi_a, q_up_a], 'open'),
                self.seg('descend to %s' % src, 'cartesian', 'approach', down, 'open'),
                self.seg('close on %s' % beaker, 'grip', 'pick', [down[-1], q_hold], 'close', grasp='grasp_side'),
                self.seg('lift from %s' % src, 'cartesian', 'carry', lift, 'hold', beaker, 'grasp_side'),
                self.seg('carry %s->%s' % (src, dst), 'joint', 'carry', [lift[-1], q_above_b], 'hold', beaker, 'grasp_side'),
                self.seg('lower onto %s' % dst, 'cartesian', 'carry', lower, 'hold', beaker, 'grasp_side'),
                self.seg('release', 'grip', 'place', [lower[-1], q_rel], 'open', grasp='grasp_side'),
                self.seg('lift out', 'cartesian', 'retreat', out, 'open'),
                self.seg('return to park', 'joint', 'park', [out[-1], self.park], 'open')]

    # ------------------------------------------------------------------ the eight arm steps
    STEPS = [('1 P1 carousel->scale', 'transfer', ('P1', 'carousel_pick', 'scale_pan'), {}),
             ('2 developer pour', 'pourer', ('P_dev', 'dev', 'rack_1', 40.0, 45.0, 'scale_pan'), {'P1': 'scale_pan'}),
             ('3 P1 funnel pour', 'pourer', ('P_fun', 'P1', 'scale_pan', 30.0, 65.0, 'funnel'), {'P1': 'scale_pan'}),
             ('4 P1 scale->carousel', 'transfer', ('P1', 'scale_pan', 'carousel_pick'), {'P1': 'scale_pan'}),
             ('6 P2 carousel->scale', 'transfer', ('P2', 'carousel_pick', 'scale_pan'), {'P2': 'carousel_pick', 'P1': 'carousel@296.1'}),
             ('7 water pour', 'pourer', ('P_wat', 'water', 'rack_3', 40.0, 45.0, 'scale_pan'), {'P2': 'scale_pan', 'P1': 'carousel@296.1'}),
             ('8 P2 funnel pour', 'pourer', ('P_fun', 'P2', 'scale_pan', 30.0, 65.0, 'funnel'), {'P2': 'scale_pan', 'P1': 'carousel@296.1'}),
             ('9 P2 scale->carousel', 'transfer', ('P2', 'scale_pan', 'carousel_pick'), {'P2': 'scale_pan', 'P1': 'carousel@296.1'})]

    def all_plans(self):
        """the eight arm steps of the demo (demo_process 4; grip heights from the doc); yeast dose and stage have no arm motion"""
        out = {}
        for name, arm, args, at in self.STEPS:
            if arm == 'transfer': out[name] = dict(arm=arm, segs=self.plan_transfer(*args), beakers_at=at, beaker=args[0], src=args[1], dst=args[2])
            else:
                segs, info = self.plan_pour_best(*args, at)
                out[name] = dict(arm=arm, segs=segs, info=info, beakers_at=at, beaker=args[1], src=args[2], dst=args[2], receiver=args[5])
        return out

    # ------------------------------------------------------------------ checks
    def check_plan(self, arm, segs, beakers_at, gh=None):
        """margins / contacts / clearance per segment. beakers_at: {beaker: station} before the plan starts"""
        K = self.K; other = self.others(arm); rows = []
        K.beaker_override = {bk: (self.station(stn) * 1e-3, np.array([1.0, 0, 0, 0])) for bk, stn in beakers_at.items()}
        Th = None
        for sg in segs:
            dense = _densify(sg['qs']); held = None
            if sg['held']:
                if Th is None:                   # beaker frame relative to the grasp site, fixed at the grasp
                    q0 = sg['qs'][0]; K.set(arm, q0, other); s = K.d.site('%s/%s' % (arm, sg['grasp']))
                    Rs, ps = s.xmat.reshape(3, 3), s.xpos.copy()
                    hb = K.d.body('beaker_' + sg['held']); Rb, pb = hb.xmat.reshape(3, 3), hb.xpos.copy()
                    Th = np.eye(4); Th[:3, :3] = Rs.T @ Rb; Th[:3, 3] = Rs.T @ (pb - ps)
                held = (sg['held'], Th, sg['grasp'])
            ign = (sg['held'],) if sg['held'] else ()
            ign_contact_beakers = ()
            if sg['phase'] in ('pick', 'place') or sg['kind'] == 'grip': ign_contact_beakers = tuple(bk for bk in beakers_at) + tuple(b for b in scene.BEAKERS)
            mg = [K.min_margin(arm, q) for q in dense]; worst = min(mg, key=lambda x: x[0])
            pens = []; clr = (1e9, '')
            for i, q in enumerate(dense):
                c = K.contacts(arm, q, other, held, ignore_beakers=ign_contact_beakers if sg['kind'] == 'grip' else ())
                if sg['phase'] in ('pick', 'place') or sg['name'].startswith(('lift from', 'lower')):
                    c = [x for x in c if not (sg['held'] and 'beaker_' + sg['held'] in x[:2] and x[2] < 0.5)]
                deep = [x for x in c if x[2] > CONTACT_MM]
                if deep: pens.append(max(deep, key=lambda x: x[2]))
                if i % 2 == 0 or i == len(dense) - 1:
                    ignb = ()
                    if sg['kind'] in ('grip',) or sg['phase'] in ('pick', 'place') or sg['name'].startswith(('descend', 'move in', 'lift', 'lower', 'release', 'back out', 'slide')):
                        ignb = tuple(b for b in scene.BEAKERS)
                    cl = K.clearance(arm, q, other, held, ignore_beakers=ignb)
                    if cl[0] < clr[0]: clr = cl
            row = dict(segment=sg['name'], phase=sg['phase'], kind=sg['kind'], configs=len(dense), min_margin_deg=round(worst[0], 2), binding=worst[1],
                       rule_deg=RULE.get(sg['phase'], 5.0), margin_ok=worst[0] >= RULE.get(sg['phase'], 5.0), contacts=len(pens),
                       worst_contact=None if not pens else dict(pair=max(pens, key=lambda x: x[2])[:2], depth_mm=round(max(p[2] for p in pens), 2)),
                       min_clearance_mm=round(clr[0], 2), clearance_at=clr[1])
            rows.append(row)
            if sg['held']:
                K.set(arm, dense[-1], other, held); hb = K.d.body('beaker_' + sg['held'])
                K.beaker_override[sg['held']] = (hb.xpos.copy(), hb.xquat.copy())
            if sg['name'] == 'release': Th = None
        K.beaker_override = {}
        return rows


def to_json(plans, origin='mujoco-native'):
    return dict(origin=origin, note='simulation-only paths solved on the upstream SO-101 MJCF; not hardware trajectories',
                steps={k: dict(arm=v['arm'], info=v.get('info'), segments=[dict(name=s['name'], kind=s['kind'], phase=s['phase'], gripper=s['gripper'],
                       held=s['held'], grasp=s['grasp'], qs=[np.round(q, 6).tolist() for q in s['qs']]) for s in v['segs']]) for k, v in plans.items()})
