"""Station poses: every pick, place, lift and pour manifold the demo needs, solved by IK
against the bench model and checked against the margin rules of docs/demo_process.md 3
(>= 10 deg at picks/places/pours, >= 5 deg on carries, limits shrunk 5 deg).

Results are cached in software/out/poses.json keyed by the bench.yaml inputs hash, so a layout
change invalidates them automatically.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field

import numpy as np

from bench.config import Config, load
from bench.paths import OUT_DIR
from .kinematics import ArmKin, BenchKin, IKResult

UP = np.array([0.0, 0.0, 1.0])


@dataclass
class Pose:
    label: str
    q: list[float]
    margin: float
    binding: str
    pos_err: float = 0.0

    def ok(self, rule: float) -> bool:
        return self.margin >= rule


@dataclass
class PickPlan:
    role: str
    station: str
    grasp: str
    grip_h: float
    pre: Pose
    grasp_pose: Pose
    lift: Pose
    carry: Pose


@dataclass
class PourPlan:
    role: str
    receiver: str
    grip_h: float
    lip_above: float
    psi_deg: float
    sign: int
    thetas: list[float]
    qs: list[list[float]]
    margin: float
    binding: str
    lip_drift_mm: float
    entry: Pose                    # upright pose directly above the pour start
    max_step_deg: float = 0.0      # largest joint change between adjacent samples
    lurch_theta: float = -1.0      # tilt at which it happens (pour controller slows there)


class StationPlanner:
    def __init__(self, cfg: Config | None = None, kin: BenchKin | None = None):
        self.cfg = cfg or load()
        self.kin = kin or BenchKin(cfg=self.cfg)
        self.rules = self.cfg.at("arms.margin_rule_deg")
        self.carry_z = float(self.cfg.at("arms.carry_z"))
        self.bk = self.cfg.at("beaker")

    # ------------------------------------------------------------ helpers
    def _ik(self, arm: ArmKin, target, axis, grasp, q0=None, flip_ok=True, **kw) -> IKResult:
        cands = [axis]
        if flip_ok and grasp == "side":
            cands.append(-np.asarray(axis))
        best = None
        for a in cands:
            r = arm.ik_multi(target, a, grasp, **kw) if q0 is None else arm.ik(target, a, grasp, q0=q0, **kw)
            if best is None or (r.ok and (not best.ok or r.margin_deg > best.margin_deg)):
                best = r
        return best

    @staticmethod
    def _pose(label: str, r: IKResult) -> Pose:
        return Pose(label, [float(v) for v in r.q_deg], float(r.margin_deg), r.binding, r.pos_err_mm)

    def grasp_target(self, beaker_xy, beaker_bottom_z: float, grip_h: float, grasp: str) -> np.ndarray:
        """Where the gripper's grasp site must be to hold a beaker at this station."""
        x, y = beaker_xy
        if grasp == "side":
            return np.array([x, y, beaker_bottom_z + grip_h])
        # top-down: finger tips grip_h above the bottom; the site is TIP_BEYOND_SITE above the tips
        from .gripper_geom import TIP_BEYOND_SITE
        return np.array([x, y, beaker_bottom_z + grip_h + TIP_BEYOND_SITE * 1000.0])

    def _topdown_clearance(self, arm: ArmKin, q, beaker_xy, bottom_z: float, descent: float = 60.0):
        """Clearance (mm) between the fixed finger's inner face and a vertical Phi56 beaker at
        `beaker_xy`, over the finger span plus the descent above it, and the world shift of the
        grasp target that would restore 2 mm.  Everything is measured in the gripper frame
        RELATIVE TO THE GRASP SITE (fk() returns the site), so the finger geometry is expressed
        relative to the site too."""
        from .gripper_geom import BEAKER_OUT, FINGER_L, FIXED_FACE_X, SITE_GAP
        site_x = (FIXED_FACE_X + 0.028 + SITE_GAP) * 1000.0  # site x in the gripper frame (mm)
        face_x = FIXED_FACE_X * 1000.0 - site_x             # fixed face, relative to the site
        hinge_z = BEAKER_OUT * 1000.0                        # hinge is BEAKER_OUT above the site
        p, R = arm.fk(q)
        c = R.T @ (np.array([beaker_xy[0], beaker_xy[1], bottom_z]) - p)
        a = R.T @ UP
        worst = 1e9
        for s in np.linspace(hinge_z - FINGER_L * 1000.0, hinge_z + descent, 16):
            if abs(a[2]) < 1e-6:
                continue
            t = (s - c[2]) / a[2]
            if t < 0 or t > self.bk["h"]:              # the beaker only exists along its height
                continue
            x_axis = c[0] + a[0] * t
            worst = min(worst, x_axis - self.bk["d"] / 2 - face_x)
        if worst >= 1e8:
            return 1e9, np.zeros(3)
        need = max(0.0, SITE_GAP * 1000.0 * 0.5 - worst)
        return worst, -(R @ np.array([1.0, 0, 0])) * need

    # ------------------------------------------------------------ picks / places
    def plan_pick(self, role: str, station: str, beaker_xy, beaker_bottom_z: float,
                  grip_h: float, grasp: str, up_sign: int = 0) -> PickPlan:
        """`up_sign`: for side grasps, +1/-1 forces beaker-up = +/-gripper y (must match the
        pour manifold's roll direction, or the roll tilts the beaker the wrong way); 0 = free."""
        arm = self.kin[role]
        tgt = self.grasp_target(beaker_xy, beaker_bottom_z, grip_h, grasp)
        off = self.cfg.at("calibration.station_offsets_mm", {}).get(f"{role}:{station}")
        if off:                                          # taught on the bench with scripts/teach.py
            tgt = tgt + np.asarray(off, float)
        if grasp == "side":
            g = (self._ik(arm, tgt, UP * up_sign, grasp, flip_ok=False) if up_sign
                 else self._ik(arm, tgt, UP, grasp))
        else:
            # Top-down: fingers down, finger faces kept vertical (lean only about the hinge),
            # lean amount chosen for margin.  The recorded Update-13 poses lean ~20 deg; the
            # fin-ray channel tolerates that and so do vertical faces around a vertical beaker.
            g = arm.ik_topdown_multi(tgt)
            if not g.ok:
                raise RuntimeError(f"no top-down grasp at {station}: {g}")
            clear, _ = self._topdown_clearance(arm, g.q_deg, beaker_xy, beaker_bottom_z)
            if clear < 0.2:
                raise RuntimeError(f"top-down grasp at {station} would clip the beaker ({clear:.1f} mm)")
        q_g = g.q_deg
        _, R = arm.fk(q_g)
        if grasp == "side":
            back = R @ np.array([0, 0, 1.0])               # +z gripper = back along the fingers
            back[2] = 0; back /= max(np.linalg.norm(back), 1e-9)
            pre_t = tgt + back * 45.0
        else:
            pre_t = tgt + UP * 60.0
        axis_now = arm.beaker_axis(q_g, grasp)

        def solve(target, q0):
            if grasp == "side":
                return self._ik(arm, target, axis_now, grasp, q0=q0, flip_ok=False)
            r = arm.ik_topdown(target, q0=q0)      # same family, seeded from the grasp
            if not r.ok:
                r = arm.ik_topdown_multi(target)
            return r

        pre = solve(pre_t, q_g)
        if grasp == "side" and pre.margin_deg < self.rules["carry"]:
            # the straight back-off can pin the wrist at its limit: shorten it until it clears
            for back_mm in (35.0, 28.0, 20.0):
                alt = solve(tgt + back * back_mm, q_g)
                if alt.ok and alt.margin_deg > pre.margin_deg:
                    pre = alt
                if pre.margin_deg >= self.rules["carry"]:
                    break
        lift = solve(tgt + UP * 60.0, q_g)
        # carry height: as high as the carry-margin rule allows (Z 300 by design; a station too
        # far out may only reach lower), never a pose at a joint limit
        carry = None
        for z in (self.carry_z, 260.0, 230.0, 200.0, 170.0, 150.0):
            c = solve(np.array([tgt[0], tgt[1], z]), lift.q_deg)
            if c.ok and c.margin_deg >= self.rules["carry"]:
                carry = c
                break
            if carry is None or (c.ok and c.margin_deg > carry.margin_deg):
                carry = c
        return PickPlan(role, station, grasp, grip_h,
                        self._pose(f"{station}:pre", pre), self._pose(f"{station}:grasp", g),
                        self._pose(f"{station}:lift", lift), self._pose(f"{station}:carry", carry))

    # ------------------------------------------------------------ pours
    def plan_pour(self, role: str, receiver: str, receiver_xy, rim_z: float, lip_above: float,
                  grip_h: float, theta_start: float = 55.0, theta_end: float = 105.0,
                  step: float = 1.0, theta_mid: float = 80.0,
                  drift_mm=(0.0, -10.0, 10.0, -20.0, 20.0), lip_extra=(0.0, 8.0), psis=None,
                  signs=(1, -1), debug: bool = False) -> PourPlan:
        """Wrist-roll pour manifold, theta 55..105 (the 0..55 tilt-in is a separate path).

        The documented pour is a wrist roll with the other joints barely moving
        (anim_paths.json q_pour55 -> q_pour105: roll sweeps 50 deg, the rest move 3-4 deg).
        Solving full IK at every tilt instead fights the wrist singularity near 90 deg.  So:
        pick a posture at theta_mid that puts the beaker's lowest rim point ("lip") `lip_above`
        the receiver; from there, step the tilt by rolling the wrist, and only when the lip leaves
        its landing window pull it back with a small 4-joint correction (roll fixed).  The window
        is the receiver's accept radius and lip_above .. lip_above+25 mm (layout_final.md).
        """
        arm = self.kin[role]
        base = np.array(self.cfg.at(f"arms.{role}.base_xy"))
        b0 = math.degrees(math.atan2(receiver_xy[1] - base[1], receiver_xy[0] - base[0]))
        if psis is None:
            psis = [b0 + d for d in range(-180, 180, 15)]
        h, r = self.bk["h"], self.bk["d"] / 2
        accept = float(self.cfg.at("control.pour.landing_accept_r")[receiver]) - 4.0
        # the stream leaves the lip at ~250 mm/s and falls `lip_above`: it lands this far
        # downstream (layout_final.md Update 8), so the lip is aimed that far UPSTREAM of the
        # receiver axis
        v_exit = float(self.cfg.at("control.pour.stream_exit_mmps"))
        land_off = v_exit * math.sqrt(2 * lip_above / 9810.0)
        rx0, ry0 = receiver_xy
        thetas = [float(t) for t in np.arange(theta_start, theta_end + 1e-6, step)]
        lo5, hi5 = np.radians(arm.lo), np.radians(arm.hi)

        def aim(psi: float):
            """where the lip should be in plan: upstream of the axis by the landing offset"""
            pdir = np.array([math.cos(math.radians(psi)), math.sin(math.radians(psi)), 0.0])
            return pdir, rx0 - pdir[0] * land_off, ry0 - pdir[1] * land_off

        def site_for(psi: float, th: float, drift: float, extra: float):
            pdir, rx, ry = aim(psi)
            t = math.radians(th)
            axis = np.array([pdir[0] * math.sin(t), pdir[1] * math.sin(t), math.cos(t)])
            low = -UP - axis * (-UP @ axis)
            n = np.linalg.norm(low)
            low = low / n if n > 1e-6 else pdir
            lip = np.array([rx + pdir[0] * drift, ry + pdir[1] * drift, rim_z + lip_above + extra])
            return lip - axis * (h - grip_h) - low * r, axis

        def lip_of(q, sign):
            """lowest rim point and tilt (deg from vertical, can exceed 90) for a held beaker
            whose bottom->rim axis is sign * gripper y."""
            p, R = arm.fk(q)
            axis = R[:, 1] * sign
            low = -UP - axis * (-UP @ axis)
            n = np.linalg.norm(low)
            low = low / n if n > 1e-6 else np.array([1.0, 0, 0])
            tilt = math.degrees(math.acos(float(np.clip(axis[2], -1, 1))))
            return p + axis * (h - grip_h) + low * r, tilt

        def set_tilt(q, th, sign):
            """1-D Newton on wrist_roll so the tilt equals th (deg)."""
            q = q.copy()
            for _ in range(12):
                t0 = lip_of(q, sign)[1]
                e = th - t0
                if abs(e) < 0.05:
                    break
                dq = 0.5
                q2 = q.copy(); q2[4] += dq
                d = (lip_of(q2, sign)[1] - t0) / dq
                if abs(d) < 1e-3:
                    break
                q[4] += float(np.clip(e / d, -15, 15))
            return q

        def pull_lip(q, target, sign, iters=25):
            """Small correction on joints 0-3 (roll fixed) to bring the lip to `target`."""
            q = q.copy()
            for _ in range(iters):
                lip, _ = lip_of(q, sign)
                e = target - lip
                if np.linalg.norm(e) < 0.5:
                    break
                J = np.zeros((3, 4))
                for k in range(4):
                    q2 = q.copy(); q2[k] += 0.05
                    J[:, k] = (lip_of(q2, sign)[0] - lip) / 0.05
                dq = np.linalg.solve(J.T @ J + 0.5 * np.eye(4), J.T @ e)
                q[:4] += np.clip(dq, -1.5, 1.5)
                q[:4] = np.clip(q[:4], arm.lo[:4], arm.hi[:4])
            return q

        def window(lip, rx, ry):
            """nearest point of the landing window to `lip` (None if already inside)."""
            dxy = np.array([lip[0] - rx, lip[1] - ry]); dist = float(np.linalg.norm(dxy))
            z = lip[2] - rim_z
            inside = dist <= accept and lip_above <= z <= lip_above + 25
            if inside:
                return None
            if dist > accept:
                dxy = dxy / dist * (accept - 1.0)
            z = float(np.clip(z, lip_above + 2, lip_above + 23))
            return np.array([rx + dxy[0], ry + dxy[1], rim_z + z])

        best: PourPlan | None = None
        best_key = -1e9
        tried = 0
        for psi in psis:
            pdir_, rx, ry = aim(psi)
            for sign in signs:
                for drift in drift_mm:
                    for extra in lip_extra:
                        site, axis = site_for(psi, theta_mid, drift, extra)
                        res = arm.ik_multi(site, axis * sign, "side", seeds=8, iters=160)
                        if not res.ok or res.margin_deg < 8.0:
                            continue
                        # the IK axis constraint is sign-free up to this check: make sure the
                        # bottom->rim direction really is sign * y (not flipped)
                        if abs(lip_of(res.q_deg, sign)[1] - theta_mid) > 3.0:
                            continue
                        tried += 1
                        poses = {}
                        ok = True
                        for direction in (+1, -1):
                            q = res.q_deg.copy()
                            ths = [t for t in thetas if (t >= theta_mid if direction > 0 else t < theta_mid)]
                            ths = ths if direction > 0 else ths[::-1]
                            for th in ths:
                                q = set_tilt(q, th, sign)
                                lip, tilt = lip_of(q, sign)
                                tgt = window(lip, rx, ry)
                                if tgt is not None:
                                    q = pull_lip(q, tgt, sign)
                                    q = set_tilt(q, th, sign)
                                    lip, tilt = lip_of(q, sign)
                                m, who = arm.margin(q)
                                dist = math.hypot(lip[0] - rx, lip[1] - ry); z = lip[2] - rim_z
                                if (abs(tilt - th) > 1.0 or m < 5.0 or dist > accept + 2
                                        or not (lip_above - 3 <= z <= lip_above + 28)):
                                    ok = False
                                    break
                                poses[th] = (q.copy(), m, who, dist)
                            if not ok:
                                break
                        if not ok:
                            continue
                        ths = sorted(poses)
                        qs = [[float(v) for v in poses[t][0]] for t in ths]
                        margins = [poses[t][1] for t in ths]
                        i_min = int(np.argmin(margins))
                        steps = np.max(np.abs(np.diff(np.array(qs), axis=0)), axis=1)
                        if steps.max() > 2.0 * step + 6.0:
                            continue
                        q_first = np.array(qs[0])
                        site0 = arm.fk(q_first)[0]
                        entry = arm.ik(site0 + UP * 30.0, UP * sign, "side", q0=q_first)
                        plan = PourPlan(role, receiver, grip_h, lip_above, float(psi), int(sign),
                                        ths, qs, float(margins[i_min]), poses[ths[i_min]][2],
                                        float(max(poses[t][3] for t in ths)),
                                        self._pose(f"{receiver}:pour_entry", entry),
                                        float(steps.max()), -1.0)
                        key = plan.margin - 0.1 * plan.lip_drift_mm + (5.0 if entry.ok else -20.0)
                        if debug:
                            print(f"    psi {psi:6.1f} sign {sign:+d} drift {drift:+.0f} extra {extra:.0f}: "
                                  f"margin {plan.margin:.1f} lip<= {plan.lip_drift_mm:.0f} mm step {steps.max():.1f} entry {'ok' if entry.ok else 'X'} key {key:.1f}")
                        if key > best_key:
                            best, best_key = plan, key
        if best is None:
            raise RuntimeError(f"no pour manifold for {role} -> {receiver} ({tried} postures tried)")
        return best

    def plan_tilt_in(self, plan: PourPlan, step: float = 5.0) -> list[list[float]]:
        """Path from the upright entry pose into the first manifold pose, tilting 0 -> theta_start
        with the grasp site interpolated straight between them (chained IK, no singularity here)."""
        arm = self.kin[plan.role]
        q0 = np.array(plan.entry.q); q1 = np.array(plan.qs[0])
        p0 = arm.fk(q0)[0]; p1 = arm.fk(q1)[0]
        th1 = plan.thetas[0]
        pdir = np.array([math.cos(math.radians(plan.psi_deg)), math.sin(math.radians(plan.psi_deg)), 0.0])
        path, q = [list(map(float, q0))], q0
        n = max(int(th1 / step), 1)
        for k in range(1, n + 1):
            u = k / n
            th = math.radians(th1 * u)
            axis = np.array([pdir[0] * math.sin(th), pdir[1] * math.sin(th), math.cos(th)]) * plan.sign
            site = p0 + (p1 - p0) * u
            res = arm.ik(site, axis, "side", q0=q)
            q = res.q_deg
            path.append([float(v) for v in q])
        path.append(list(map(float, q1)))
        return path

    # ------------------------------------------------------------ the whole set
    def plan_all(self) -> dict:
        st = self.cfg.at("stations"); gh = self.cfg.at("gripper.grip_h")
        rk, sc, car, fu = st["rack"], st["scale"], st["carousel"], st["funnel"]
        plans: dict[str, object] = {}
        # pours first: their roll direction fixes which way up the side grasps hold the beaker
        la = self.cfg.at("control.pour.lip_above_rim")
        plans["pourer:pour_scale"] = self.plan_pour("pourer", "scale", sc["pan_xy"],
                                                    sc["beaker_bottom_z"] + self.bk["h"], la["scale"],
                                                    gh["scale_pour"])
        plans["pourer:pour_funnel"] = self.plan_pour("pourer", "funnel", fu["xy"], fu["rim_z"],
                                                     la["funnel"], gh["funnel_pour"])
        # pourer: side grasps at the rack (poured onto the scale) and the scale (poured into the funnel)
        for nm in ("developer", "water"):
            plans[f"pourer:rack_{nm}"] = self.plan_pick("pourer", f"rack_{nm}", rk["pockets"][nm],
                                                        rk["beaker_bottom_z"], gh["scale_pour"], "side",
                                                        up_sign=plans["pourer:pour_scale"].sign)
        plans["pourer:scale"] = self.plan_pick("pourer", "scale", sc["pan_xy"], sc["beaker_bottom_z"],
                                              gh["funnel_pour"], "side",
                                              up_sign=plans["pourer:pour_funnel"].sign)
        # transfer: top-down at the carousel pick pocket and the scale
        plans["transfer:carousel_pick"] = self.plan_pick("transfer", "carousel_pick",
                                                         car["pockets"]["pick"]["xy"],
                                                         car["beaker_bottom_z"], gh["top_down"], "top_down")
        plans["transfer:scale"] = self.plan_pick("transfer", "scale", sc["pan_xy"],
                                                sc["beaker_bottom_z"], gh["top_down"], "top_down")
        return plans


def _inputs_hash(cfg: Config) -> str:
    return hashlib.sha256(json.dumps(cfg["meta"]["inputs"], sort_keys=True).encode()).hexdigest()[:12]


def load_or_plan(cfg: Config | None = None, force: bool = False, verbose: bool = True) -> dict:
    cfg = cfg or load()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = OUT_DIR / "poses.json"
    key = _inputs_hash(cfg)
    if cache.exists() and not force:
        data = json.loads(cache.read_text())
        if data.get("key") == key:
            return _from_json(data["plans"])
    if verbose:
        print("planning station poses (cached afterwards in software/out/poses.json) ...")
    plans = StationPlanner(cfg).plan_all()
    cache.write_text(json.dumps({"key": key, "plans": {k: asdict(v) for k, v in plans.items()}}, indent=1))
    return plans


def _from_json(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if "thetas" in v:
            v = dict(v); v["entry"] = Pose(**v["entry"])
            out[k] = PourPlan(**v)
        else:
            v = dict(v)
            for f in ("pre", "grasp_pose", "lift", "carry"):
                v[f] = Pose(**v[f])
            out[k] = PickPlan(**v)
    return out
