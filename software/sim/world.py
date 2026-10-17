"""The simulated bench: MuJoCo physics + the analytic chemistry, behind one object.

Everything the HAL sim backend needs is a method here; nothing above the HAL imports mujoco.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import mujoco
import numpy as np

from bench.config import MM, Config, load
from bench.paths import BENCH_XML
from bench.motion.calib import park_mjcf_deg
from sim.chemistry import Chemistry, Vessel

ARM_JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]
BEAKERS = ["P1", "P2", "developer", "soap", "water"]
JAW_CONTACT_RAD = 0.35                    # must match sim/build_scene.py JAW_CONTACT
JAW_TRAVEL_RAD = math.radians(14.0)


@dataclass
class ServoMove:
    joint: str
    q0: float
    q1: float
    t0: float
    dur: float

    def value(self, t: float) -> tuple[float, bool]:
        u = 1.0 if self.dur <= 0 else min(max((t - self.t0) / self.dur, 0.0), 1.0)
        s = u * u * (3 - 2 * u)
        return self.q0 + (self.q1 - self.q0) * s, u >= 1.0


def paint_fluids(scene, world) -> None:
    """Append the world's fluid decorations to an mjvScene (viewer user_scn or a Renderer's
    scene).  Visual only."""
    for g in world.fluid_geoms():
        if scene.ngeom >= scene.maxgeom:
            break
        geom = scene.geoms[scene.ngeom]
        mujoco.mjv_initGeom(geom, getattr(mujoco.mjtGeom, "mjGEOM_" + g["type"].upper()),
                            np.asarray(g["size"], float), np.asarray(g["pos"], float),
                            np.asarray(g["mat"], float), np.asarray(g["rgba"], np.float32))
        scene.ngeom += 1


class World:
    def __init__(self, cfg: Config | None = None, xml=BENCH_XML, seed: int = 0,
                 render_size=(480, 640)):
        self.cfg = cfg or load()
        self.m = mujoco.MjModel.from_xml_path(str(xml))
        self.d = mujoco.MjData(self.m)
        self.rng = np.random.default_rng(seed)
        self.dt = float(self.m.opt.timestep)
        self.t = 0.0
        self.chem = Chemistry(self.cfg, self.cfg.at("recipe.densities"), self.rng)
        self._renderer = None
        self._render_size = render_size
        self.events: list[tuple[float, str]] = []
        self.hooks: list = []                      # callables run after every physics step

        # ---- lookups
        self.jid = {}; self.qadr = {}; self.dadr = {}
        for j in range(self.m.njnt):
            n = mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_JOINT, j)
            self.jid[n] = j; self.qadr[n] = self.m.jnt_qposadr[j]; self.dadr[n] = self.m.jnt_dofadr[j]
        self.aid = {mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_ACTUATOR, i): i
                    for i in range(self.m.nu)}
        self.bid = {mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_BODY, i): i
                    for i in range(self.m.nbody)}
        self.sid = {mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_SITE, i): i
                    for i in range(self.m.nsite)}
        self.gid = {mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_GEOM, i): i
                    for i in range(self.m.ngeom)}
        self.eqid = {mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_EQUALITY, i): i
                     for i in range(self.m.neq)}
        self.sens = {mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_SENSOR, i): self.m.sensor_adr[i]
                     for i in range(self.m.nsensor)}

        # ---- vessels
        b = self.cfg.at("beaker")
        for nm in BEAKERS:
            self.chem.add_vessel(Vessel(nm, f"beaker_{nm}", b["d"] / 2, b["h"],
                                        accept_r_mm=b["d"] / 2 - 3, empty_g=b["mass_empty_g"]))
        fu = self.cfg.at("stations.funnel")
        self.chem.add_vessel(Vessel("flask", "stage_sled", 42.5, 148.0,
                                    accept_r_mm=fu["accept_r"], empty_g=0.0,
                                    is_funnel_target=True))
        self.base_mass = {nm: float(self.m.body_mass[self.bid[f"beaker_{nm}"]]) for nm in BEAKERS}
        self.base_inertia = {nm: self.m.body_inertia[self.bid[f"beaker_{nm}"]].copy()
                             for nm in BEAKERS}
        self.held: dict[str, str | None] = {"pourer": None, "transfer": None}
        # Collision bit layout: fingers/palms bit 1 only; everything else bits 1|2.  A held
        # beaker drops to bit 2 so the weld never fights finger contacts, while it still
        # collides with the bench and the other beakers.  Free beakers are bits 1|2.
        self._finger_geoms = {g for g in range(self.m.ngeom)
                              if any(k in (mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_GEOM, g) or "")
                                     for k in ("finger_fixed", "finger_moving", "palm"))}
        self._beaker_geoms = {nm: self.gid[f"beaker_{nm}_geom"] for nm in BEAKERS}
        for g in range(self.m.ngeom):
            if g in self._finger_geoms:
                self.m.geom_contype[g], self.m.geom_conaffinity[g] = 1, 1
            elif self.m.geom_contype[g] | self.m.geom_conaffinity[g]:
                self.m.geom_contype[g], self.m.geom_conaffinity[g] = 3, 3

        # ---- mechanisms
        self.moves: dict[str, ServoMove] = {}
        self.auger_cmd_rev = 0.0; self.auger_rev_done = 0.0; self.auger_dir = 1
        self.auger_active = False; self.auger_rev_base = 0.0
        self.auger_last_dose_rev = 0.0
        self._auger_dribble_pending = 0.0

        # ---- scale
        self.scale_rate = float(self.cfg.at("control.scale.rate_hz"))
        self.scale_noise = float(self.cfg.at("control.scale.noise_g"))
        self.counts_per_g = float(self.cfg.at("calibration.counts_per_g"))
        self._next_sample_t = 0.0
        self.samples: deque = deque(maxlen=4000)   # ring of the last 50 s
        self.n_samples = 0                           # total ever produced (ring-safe cursor)
        self.estop_pressed = False

        # start parked, with the jaws open
        park = park_mjcf_deg(self.cfg)
        for role in ("pourer", "transfer"):
            self.set_arm_goals_deg(role, dict(zip(ARM_JOINTS[:5], park)))
            self.set_arm_goals_deg(role, {"gripper": self.jaw_open_deg()})
            for jn, q in zip(ARM_JOINTS[:5], park):
                self.d.qpos[self.qadr[f"{role}_{jn}"]] = math.radians(q)
            self.d.qpos[self.qadr[f"{role}_gripper"]] = math.radians(self.jaw_open_deg())
        mujoco.mj_forward(self.m, self.d)
        self.step_time(0.5)

    # ---------------------------------------------------------------- time
    def step(self, n: int = 1) -> None:
        for _ in range(n):
            self._pre_step()
            mujoco.mj_step(self.m, self.d)
            self.t = float(self.d.time)
            self._post_step()

    def step_time(self, seconds: float) -> None:
        self.step(max(1, int(round(seconds / self.dt))))

    def _pre_step(self) -> None:
        # servo-style smooth moves on the hobby servos
        for name, mv in list(self.moves.items()):
            q, done = mv.value(self.t)
            self.d.ctrl[self.aid[name]] = q
            if done:
                del self.moves[name]
        # auger: velocity control by revolutions
        if self.auger_active:
            done = abs(self.auger_pos_rev() - self.auger_rev_base)
            if done >= abs(self.auger_cmd_rev):
                self.d.ctrl[self.aid["auger"]] = 0.0
                self.auger_active = False
                self.auger_rev_done = done
            else:
                self.d.ctrl[self.aid["auger"]] = (
                    self.auger_dir * 2 * math.pi * float(self.cfg.at("control.auger.rev_per_s")))
        if self.estop_pressed:
            for n in ("carousel", "stage", "auger"):
                pass  # servos hold (no PWM); we freeze their targets at current values
            self.d.ctrl[self.aid["auger"]] = 0.0
            self.auger_active = False

    def _post_step(self) -> None:
        self._chemistry_step()
        for h in self.hooks:
            h()
        if self.t >= self._next_sample_t:
            self._next_sample_t += 1.0 / self.scale_rate
            self.samples.append((int(self.t * 1000), self.scale_grams_raw()))
            self.n_samples += 1

    # ---------------------------------------------------------------- chemistry glue
    def beaker_pose(self, nm: str):
        b = self.bid[f"beaker_{nm}"]
        return self.d.xpos[b] / MM, self.d.xmat[b].reshape(3, 3)

    def _receivers(self) -> dict[str, tuple[np.ndarray, float]]:
        out = {}
        h = self.cfg.at("beaker.h")
        for nm in BEAKERS:
            p, R = self.beaker_pose(nm)
            rim = p + R[:, 2] * h
            out[nm] = (rim, float(rim[2]))
        f = self.d.site_xpos[self.sid["funnel_rim"]] / MM
        out["flask"] = (f, float(f[2]))
        return out

    def _chemistry_step(self) -> None:
        recv = self._receivers()
        b = self.cfg.at("beaker")
        for nm in BEAKERS:
            v = self.chem.vessels[nm]
            if v.total_g <= 0:
                continue
            p, R = self.beaker_pose(nm)
            axis = R[:, 2]
            tilt = math.acos(float(np.clip(axis[2], -1, 1)))
            if tilt < math.radians(5):
                self.chem.last_flow_gps[nm] = 0.0
                continue
            # lowest rim point: rim centre + r * (horizontal component of the tilt direction)
            rim_c = p + axis * b["h"]
            tdir = np.array([axis[0], axis[1], 0.0])
            n = np.linalg.norm(tdir)
            tdir = tdir / n if n > 1e-9 else np.array([1.0, 0, 0])
            # the beaker leans toward +tdir, so the low side of the rim is on that side
            radial = tdir - axis * (tdir @ axis)
            radial /= max(np.linalg.norm(radial), 1e-9)
            lip = rim_c + radial * b["d"] / 2
            self.chem.pour_step(v, tilt, lip, (tdir[0], tdir[1]), self.t, self.dt, recv)
        impulse = self.chem.land_step(self.t)
        # stream momentum on whatever sits on the pan
        for nm, f_n in impulse.items():
            if nm in BEAKERS:
                self.d.xfrc_applied[self.bid[f"beaker_{nm}"], 2] = -f_n
        for nm in BEAKERS:
            if nm not in impulse:
                self.d.xfrc_applied[self.bid[f"beaker_{nm}"], 2] = 0.0
            self._apply_mass(nm)
        self.chem.foam_step(self.chem.vessels["flask"], self.t, self.dt)
        self._draw_foam()
        self._draw_liquids()

    def _apply_mass(self, nm: str) -> None:
        """Push a vessel's current mass into MuJoCo.  body_subtreemass is a cached derived
        quantity (used by the COM / implicit integration); it must follow body_mass or the
        model goes inconsistent and a held beaker blows up mid-carry."""
        bid = self.bid[f"beaker_{nm}"]
        m = self.chem.mass_g(nm) / 1000.0
        old = float(self.m.body_mass[bid])
        if abs(m - old) < 1e-7:
            return
        self.m.body_mass[bid] = m
        self.m.body_inertia[bid] = self.base_inertia[nm] * (m / self.base_mass[nm])
        self.m.body_subtreemass[bid] = m                          # a free body: itself
        self.m.body_subtreemass[0] += m - old                      # the world's total

    COLOURS = {"developer": (0.75, 0.9, 1.0), "water": (0.3, 0.6, 1.0), "yeast": (0.78, 0.62, 0.3),
               "soap": (0.4, 0.9, 0.5)}

    def _colour(self, contents: dict) -> tuple:
        tot = sum(contents.values()) or 1.0
        rgb = np.zeros(3)
        for k, g in contents.items():
            rgb += np.array(self.COLOURS.get(k, (0.6, 0.6, 0.6))) * g / tot
        return (*rgb, 0.8)

    def _draw_liquids(self) -> None:
        """Visual only: a column in each vessel sized by its contents, and a stream capsule from
        the lip to the landing point while a beaker pours."""
        r_in = (self.cfg.at("beaker.d") / 2 - 1.5) * MM
        for nm in BEAKERS:
            v = self.chem.vessels[nm]
            g = self.gid[f"beaker_{nm}_liquid"]
            vol_m3 = sum(gr / self.chem.density(k) for k, gr in v.contents.items()) * 1e-6
            h = min(vol_m3 / (math.pi * r_in * r_in), self.cfg.at("beaker.h") * MM - 0.002)
            self.m.geom_size[g] = [r_in, max(h / 2, 0.0005), 0]
            self.m.geom_pos[g][2] = 0.0015 + max(h / 2, 0.0005)
            self.m.geom_rgba[g] = self._colour(v.contents) if v.total_g > 0 else (0, 0, 0, 0)
            # stream
            sg = self.gid[f"stream_{nm}"]
            land = self.chem.last_landing.get(nm)
            if False and self.chem.last_flow_gps.get(nm, 0.0) > 0.05 and land is not None:   # droplets now
                p, R = self.beaker_pose(nm)
                axis = R[:, 2]
                rim_c = p + axis * self.cfg.at("beaker.h")
                tdir = np.array([axis[0], axis[1], 0.0]); n = np.linalg.norm(tdir)
                tdir = tdir / n if n > 1e-9 else np.array([1.0, 0, 0])
                radial = tdir - axis * (tdir @ axis); radial /= max(np.linalg.norm(radial), 1e-9)
                lip = (rim_c + radial * self.cfg.at("beaker.d") / 2) * MM
                target, _, lxy = land
                if target in BEAKERS:
                    rp, rR = self.beaker_pose(target)
                    z_land = (rp + rR[:, 2] * self.cfg.at("beaker.h"))[2] * MM
                elif target == "flask":
                    z_land = self.d.site_xpos[self.sid["funnel_rim"]][2]
                else:
                    z_land = 0.0
                end = np.array([lxy[0] * MM, lxy[1] * MM, z_land])
                seg = end - lip; L = float(np.linalg.norm(seg))
                if L > 1e-3:
                    q = np.zeros(4); mujoco.mju_quatZ2Vec(q, seg / L)
                    self.m.geom_pos[sg] = (lip + end) / 2
                    self.m.geom_quat[sg] = q
                    self.m.geom_size[sg] = [0.0025, L / 2, 0]
                    self.m.geom_rgba[sg] = self._colour(v.contents)
                    continue
            self.m.geom_pos[sg] = [0, 0, -1.0]
            self.m.geom_size[sg] = [0.0025, 0.001, 0]
        # the flask
        fl = self.chem.vessels["flask"]; g = self.gid["flask_liquid"]
        vol_m3 = sum(gr / self.chem.density(k) for k, gr in fl.contents.items()) * 1e-6
        h = min(vol_m3 / (math.pi * 0.040 ** 2), 0.14)
        fz0 = self.cfg.at("stations.stage.flask.z")[0] * MM
        self.m.geom_size[g] = [0.040, max(h / 2, 0.0005), 0]
        self.m.geom_pos[g][2] = fz0 + 0.0005 + max(h / 2, 0.0005)
        self.m.geom_rgba[g] = self._colour(fl.contents) if fl.total_g > 0 else (0, 0, 0, 0)

    # ---------------------------------------------------------------- fluid look (visual only)
    def fluid_geoms(self) -> list[dict]:
        """Decorations drawn on top of the scene every frame: droplets along each pour stream,
        a splash where it lands, and a level (horizontal) free surface in every vessel.
        Nothing here feeds back into the physics or the control loop."""
        out = []
        h_b = self.cfg.at("beaker.h"); r_b = self.cfg.at("beaker.d") / 2 - 1.5
        for nm in BEAKERS:
            v = self.chem.vessels[nm]
            if v.total_g <= 0:
                continue
            p, R = self.beaker_pose(nm)
            axis = R[:, 2]
            vol = sum(gr / self.chem.density(k) for k, gr in v.contents.items()) * 1000.0   # mm^3
            h_mean = min(vol / (math.pi * r_b * r_b), h_b - 2)
            tilt = math.acos(float(np.clip(axis[2], -1, 1)))
            rgba = self._colour(v.contents)
            # free surface: a horizontal disc through the mean fill point, radius grows with tilt
            c = (p + axis * h_mean) * MM
            rr = min(r_b / max(math.cos(tilt), 0.35), r_b * 1.6) * MM
            out.append(dict(type="cylinder", size=[rr, 0.0006, 0], pos=c, mat=np.eye(3).ravel(), rgba=rgba))
            # stream droplets
            flow = self.chem.last_flow_gps.get(nm, 0.0)
            land = self.chem.last_landing.get(nm)
            if flow > 0.05 and land is not None:
                rim_c = p + axis * h_b
                tdir = np.array([axis[0], axis[1], 0.0]); n = np.linalg.norm(tdir)
                tdir = tdir / n if n > 1e-9 else np.array([1.0, 0, 0])
                radial = tdir - axis * (tdir @ axis); radial /= max(np.linalg.norm(radial), 1e-9)
                lip = rim_c + radial * (r_b + 1.5)
                target, _, lxy = land
                if target in BEAKERS:
                    rp, rR = self.beaker_pose(target); z_land = (rp + rR[:, 2] * h_b)[2]
                elif target == "flask":
                    z_land = self.d.site_xpos[self.sid["funnel_rim"]][2] / MM
                else:
                    z_land = 0.0
                fall = max(lip[2] - z_land, 1.0)
                t_fall = math.sqrt(2 * fall / 9810.0)
                vx = (np.array([lxy[0], lxy[1]]) - lip[:2]) / t_fall       # mm/s, from the landing model
                n_drops = int(np.clip(6 + flow * 2.5, 6, 40))
                rad = (1.0 + 0.25 * min(flow, 12.0)) * MM
                phase = (self.t * 3.0) % 1.0
                for k in range(n_drops):
                    sfrac = ((k + phase) / n_drops)
                    tt = sfrac * t_fall
                    pos = np.array([lip[0] + vx[0] * tt, lip[1] + vx[1] * tt, lip[2] - 0.5 * 9810.0 * tt * tt])
                    out.append(dict(type="sphere", size=[rad, 0, 0], pos=pos * MM, mat=np.eye(3).ravel(), rgba=rgba))
                # splash
                rs = self.rng
                for k in range(5):
                    jit = rs.normal(0, 4.0, 2)
                    pos = np.array([lxy[0] + jit[0], lxy[1] + jit[1], z_land + abs(rs.normal(0, 3.0))])
                    out.append(dict(type="sphere", size=[0.8 * MM, 0, 0], pos=pos * MM, mat=np.eye(3).ravel(),
                                    rgba=(rgba[0], rgba[1], rgba[2], 0.6)))
        # flask surface
        fl = self.chem.vessels["flask"]
        if fl.total_g > 0:
            vol = sum(gr / self.chem.density(k) for k, gr in fl.contents.items()) * 1000.0
            fz0 = self.cfg.at("stations.stage.flask.z")[0]
            fx, fy = self.cfg.at("stations.stage.flask.xy")
            sled_y = self.d.qpos[self.qadr["stage_sled"]] / MM
            h = min(vol / (math.pi * 40 ** 2), 140.0)
            r_at = 42.5 - (42.5 - 17) * min(max((h - 8) / 102.0, 0.0), 1.0)
            out.append(dict(type="cylinder", size=[(r_at - 1) * MM, 0.0006, 0], pos=np.array([fx, fy + sled_y, fz0 + h]) * MM,
                            mat=np.eye(3).ravel(), rgba=self._colour(fl.contents)))
        return out

    def _draw_foam(self) -> None:
        g = self.gid["foam"]
        h = self.chem.foam_h_mm * MM
        self.m.geom_size[g] = [0.0425, max(h / 2, 0.0005), 0]
        fz1 = self.cfg.at("stations.stage.flask.z")[1] * MM
        self.m.geom_pos[g][2] = fz1 + h / 2

    # ---------------------------------------------------------------- arms (ArmBus side)
    def arm_qpos_deg(self, role: str) -> dict[str, float]:
        return {jn: math.degrees(self.d.qpos[self.qadr[f"{role}_{jn}"]]) for jn in ARM_JOINTS}

    def arm_load(self, role: str) -> dict[str, float]:
        """Present_Load-like: the torque each servo is exerting as a fraction of its limit,
        in +-1000 (the real STS3215 reports PWM duty).  A jaw stalled on a beaker sits at its
        torque limit; a jaw at its goal with nothing between the fingers reads ~0."""
        out = {}
        for jn in ARM_JOINTS:
            a = self.aid[f"{role}_{jn}"]
            fr = float(self.m.actuator_forcerange[a][1]) or 3.35
            out[jn] = float(np.clip(self.d.actuator_force[a] / fr * 1000.0, -1000, 1000))
        return out

    def set_arm_goals_deg(self, role: str, goals: dict[str, float]) -> None:
        for jn, q in goals.items():
            a = self.aid[f"{role}_{jn}"]
            lo, hi = self.m.actuator_ctrlrange[a]
            self.d.ctrl[a] = float(np.clip(math.radians(q), lo, hi))

    def jaw_open_deg(self) -> float:
        return math.degrees(JAW_CONTACT_RAD - JAW_TRAVEL_RAD * self._jaw_open_sign())

    def jaw_contact_deg(self) -> float:
        return math.degrees(JAW_CONTACT_RAD)

    def jaw_close_deg(self) -> float:
        """Command past contact by SQUEEZE so the servo stalls on the beaker."""
        sq = math.radians(self.cfg.at("gripper.squeeze_deg"))
        return math.degrees(JAW_CONTACT_RAD + sq * self._jaw_open_sign())

    _jaw_sign_cache: int | None = None

    def _jaw_open_sign(self) -> int:
        """+1 if increasing the gripper joint opens the jaw (moves the finger away from the
        fixed finger), else -1.  Measured once from the model."""
        if World._jaw_sign_cache is not None:
            return World._jaw_sign_cache
        d = mujoco.MjData(self.m)
        fixed, moving = self.gid["pourer_finger_fixed"], self.gid["pourer_finger_moving"]
        gaps = []
        for q in (JAW_CONTACT_RAD - 0.2, JAW_CONTACT_RAD + 0.2):
            d.qpos[:] = self.d.qpos
            d.qpos[self.qadr["pourer_gripper"]] = q
            mujoco.mj_kinematics(self.m, d)
            gaps.append(np.linalg.norm(d.geom_xpos[moving] - d.geom_xpos[fixed]))
        World._jaw_sign_cache = -1 if gaps[1] > gaps[0] else 1
        # sign convention: open = contact - travel*sign  => if +q opens, sign must be -1
        return World._jaw_sign_cache

    # ---------------------------------------------------------------- grasping
    def grasp_site(self, role: str) -> np.ndarray:
        return self.d.site_xpos[self.sid[f"{role}_grasp"]] / MM

    def gripper_rot(self, role: str) -> np.ndarray:
        return self.d.xmat[self.bid[f"{role}_gripper"]].reshape(3, 3)

    def beaker_in_jaws(self, role: str, tol=(14.0, 18.0, 22.0)) -> str | None:
        """Which beaker (if any) sits in the capture region of this gripper, gripper frame."""
        g = self.grasp_site(role); R = self.gripper_rot(role)
        half_h = self.cfg.at("beaker.h") / 2
        for nm in BEAKERS:
            p, Rb = self.beaker_pose(nm)
            c = p + Rb[:, 2] * half_h                   # beaker mid-height centre
            # the grasp site marks where the beaker centreline crosses the finger band, so
            # compare against the closest point on the beaker axis
            axis = Rb[:, 2]
            s = float(np.clip((g - p) @ axis, 0, 2 * half_h))
            q = p + axis * s
            e = R.T @ (q - g)
            if abs(e[0]) < tol[0] and abs(e[1]) < tol[1] and abs(e[2]) < tol[2]:
                return nm
        return None

    def grasp(self, role: str) -> str | None:
        """Activate the weld to whatever beaker is in the jaws. Returns its name or None."""
        nm = self.beaker_in_jaws(role)
        if nm is None:
            return None
        eq = self.eqid[f"grasp_{role}_{nm}"]
        b1, b2 = self.bid[f"{role}_gripper"], self.bid[f"beaker_{nm}"]
        # relpose of body2 in body1's frame
        R1 = self.d.xmat[b1].reshape(3, 3); p1 = self.d.xpos[b1]
        R2 = self.d.xmat[b2].reshape(3, 3); p2 = self.d.xpos[b2]
        rel_p = R1.T @ (p2 - p1)
        rel_R = R1.T @ R2
        q = np.zeros(4); mujoco.mju_mat2Quat(q, rel_R.ravel())
        self.m.eq_data[eq][:3] = 0.0
        self.m.eq_data[eq][3:6] = rel_p
        self.m.eq_data[eq][6:10] = q
        self.m.eq_data[eq][10] = 1.0
        self.d.eq_active[eq] = 1
        g = self._beaker_geoms[nm]
        self.m.geom_contype[g], self.m.geom_conaffinity[g] = 2, 2     # no finger contacts now
        # the clamped beaker blocks the jaw where it is: lock the gripper joint
        lock = self.eqid[f"lock_{role}_jaw"]
        self.m.eq_data[lock][:5] = [self.d.qpos[self.qadr[f"{role}_gripper"]], 0, 0, 0, 0]
        self.d.eq_active[lock] = 1
        self.held[role] = nm
        self.events.append((self.t, f"{role} grasped {nm}"))
        return nm

    def release(self, role: str) -> None:
        nm = self.held.get(role)
        if nm:
            self.d.eq_active[self.eqid[f"grasp_{role}_{nm}"]] = 0
            g = self._beaker_geoms[nm]
            self.m.geom_contype[g], self.m.geom_conaffinity[g] = 3, 3
            self.d.eq_active[self.eqid[f"lock_{role}_jaw"]] = 0
            self.events.append((self.t, f"{role} released {nm}"))
        self.held[role] = None

    # ---------------------------------------------------------------- scale (Mega side)
    def scale_force_n(self) -> float:
        a = self.sens["load_cell"]
        return float(self.d.sensordata[a + 2])            # +ve = weight pressing down

    def scale_grams_raw(self) -> float:
        g = self.scale_force_n() / 9.81 * 1000.0
        g += self.rng.normal(0.0, self.scale_noise)
        counts = round(g * self.counts_per_g)             # HX711 quantisation
        return counts / self.counts_per_g

    def beaker_on_scale(self) -> str | None:
        pan = self.d.site_xpos[self.sid["scale_station"]] / MM
        for nm in BEAKERS:
            p, _ = self.beaker_pose(nm)
            if np.linalg.norm(p[:2] - pan[:2]) < 20 and abs(p[2] - pan[2]) < 8:
                return nm
        return None

    # ---------------------------------------------------------------- mechanisms (Mega side)
    def servo_move(self, name: str, target: float, duration_s: float) -> None:
        a = self.aid[name]
        self.moves[name] = ServoMove(name, float(self.d.ctrl[a]), float(target), self.t,
                                     max(duration_s, 0.05))

    def servo_busy(self, name: str) -> bool:
        return name in self.moves

    def carousel_deg(self) -> float:
        return math.degrees(self.d.qpos[self.qadr["carousel"]])

    def stage_deg(self) -> float:
        return math.degrees(self.d.qpos[self.qadr["stage_crank"]])

    def sled_travel_mm(self) -> float:
        return -self.d.qpos[self.qadr["stage_sled"]] / MM

    def auger_pos_rev(self) -> float:
        return self.d.qpos[self.qadr["auger"]] / (2 * math.pi)

    def auger_start(self, revolutions: float, direction: int = 1) -> None:
        self.auger_rev_base = self.auger_pos_rev()
        self.auger_cmd_rev = revolutions
        self.auger_dir = 1 if direction >= 0 else -1
        self.auger_active = True
        if self.auger_dir > 0:
            self._auger_dribble_pending = 0.12            # grams that fall after stopping
        else:
            self._auger_dribble_pending = 0.0

    def auger_busy(self) -> bool:
        return self.auger_active

    def beaker_under_auger(self) -> str | None:
        o = self.d.site_xpos[self.sid["auger_outlet"]] / MM
        for nm in BEAKERS:
            p, _ = self.beaker_pose(nm)
            if np.linalg.norm(p[:2] - o[:2]) < 20 and p[2] + self.cfg.at("beaker.h") < o[2]:
                return nm
        return None

    def auger_deliver(self, revolutions: float) -> float:
        """Called by the fake Mega as revolutions accumulate; routes yeast to the beaker."""
        tgt = self.beaker_under_auger()
        v = self.chem.vessels[tgt] if tgt else None
        return self.chem.dose_yeast(v, revolutions, float(self.cfg.at("calibration.g_per_rev")))

    # ---------------------------------------------------------------- misc
    def min_clearance_mm(self, body_prefix: str, exclude: tuple[str, ...] = ()) -> tuple[float, str]:
        """Smallest distance between any geom of bodies starting with `body_prefix` and any
        other collision geom, via mj_geomDistance.  Slow (O(n^2)); use for checks only."""
        mine = [g for g in range(self.m.ngeom)
                if mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_BODY, self.m.geom_bodyid[g]).startswith(body_prefix)
                and self.m.geom_contype[g] | self.m.geom_conaffinity[g]]
        others = [g for g in range(self.m.ngeom)
                  if g not in mine and (self.m.geom_contype[g] | self.m.geom_conaffinity[g])
                  and not any(mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_BODY, self.m.geom_bodyid[g]).startswith(e) for e in exclude)]
        best, who = math.inf, ""
        fromto = np.zeros(6)
        for a in mine:
            for b in others:
                dist = mujoco.mj_geomDistance(self.m, self.d, a, b, 0.05, fromto)
                if dist < best:
                    best, who = dist, f"{mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_GEOM, a)} x {mujoco.mj_id2name(self.m, mujoco.mjtObj.mjOBJ_GEOM, b)}"
        return best / MM, who

    def render(self, camera: str = "overview") -> np.ndarray:
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.m, *self._render_size)
        self._renderer.update_scene(self.d, camera=camera)
        paint_fluids(self._renderer.scene, self)
        return self._renderer.render()

    def fill(self, beaker: str, reagent: str, grams: float) -> None:
        self.chem.vessels[beaker].add(reagent, grams)
        self._apply_mass(beaker)
