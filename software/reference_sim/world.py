"""Small MuJoCo control loop for the independent reference simulator."""
from __future__ import annotations

import math
from pathlib import Path

import mujoco
import numpy as np

from build_scene import build


SCENE = Path(__file__).resolve().parent / "build" / "bench.xml"


class BenchWorld:
    def __init__(self, scene: Path = SCENE):
        if not scene.exists():
            build()
        self.model = mujoco.MjModel.from_xml_path(str(scene))
        self.data = mujoco.MjData(self.model)
        self.scale_tare_m = 0.0
        self.scale_payload_g = 0.0
        self.scale_dof = int(self.model.jnt_dofadr[self._joint_id("scale_flex")])
        self._torque_enabled: dict[str, bool] = {"pourer": True, "transfer": True}
        self._held: dict[str, str] = {}
        self._actuator_power: dict[str, list[tuple[int, float, float]]] = {}
        self._arm_joint_names = ("shoulder_pan", "shoulder_lift", "elbow_flex",
                                 "wrist_flex", "wrist_roll", "gripper")
        for arm in ("pourer", "transfer"):
            self._actuator_power[arm] = []
            prefix = f"{arm}_"
            for joint in self._arm_joint_names:
                aid = self._actuator_id(prefix + joint)
                self._actuator_power[arm].append((
                    aid,
                    float(self.model.actuator_gainprm[aid, 0]),
                    float(self.model.actuator_biasprm[aid, 1]),
                ))
        mujoco.mj_forward(self.model, self.data)

    def _step_once(self) -> None:
        self.data.qfrc_applied[self.scale_dof] = -self.scale_payload_g / 1000 * 9.81
        mujoco.mj_step(self.model, self.data)

    def step(self, seconds: float) -> None:
        n = max(1, round(seconds / self.model.opt.timestep))
        for _ in range(n):
            self._step_once()

    def _joint_id(self, name: str) -> int:
        return mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, name)

    def _actuator_id(self, name: str) -> int:
        return mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)

    def set_actuator_goal_rad(self, actuator: str, target: float) -> None:
        aid = self._actuator_id(actuator)
        if aid < 0:
            raise ValueError(f"Unknown actuator: {actuator}")
        self.data.ctrl[aid] = float(target)

    def site_pose(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        sid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, name)
        if sid < 0:
            raise ValueError(f"Unknown site: {name}")
        return self.data.site_xpos[sid].copy(), self.data.site_xmat[sid].reshape(3, 3).copy()

    def body_pose(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, name)
        if bid < 0:
            raise ValueError(f"Unknown body: {name}")
        return self.data.xpos[bid].copy(), self.data.xmat[bid].reshape(3, 3).copy()

    @staticmethod
    def _matrix_quaternion(rotation: np.ndarray) -> list[float]:
        """Convert a 3x3 rotation matrix to MuJoCo's w,x,y,z quaternion order."""
        r = rotation
        trace = float(r[0, 0] + r[1, 1] + r[2, 2])
        if trace > 0:
            s = math.sqrt(trace + 1.0) * 2
            q = [0.25 * s, (r[2, 1] - r[1, 2]) / s,
                 (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s]
        elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
            s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
            q = [(r[2, 1] - r[1, 2]) / s, 0.25 * s,
                 (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s]
        elif r[1, 1] > r[2, 2]:
            s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
            q = [(r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s,
                 0.25 * s, (r[1, 2] + r[2, 1]) / s]
        else:
            s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
            q = [(r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s,
                 (r[1, 2] + r[2, 1]) / s, 0.25 * s]
        norm = math.sqrt(sum(x * x for x in q))
        return [x / norm for x in q]

    def grasp(self, arm: str, beaker: str, *, max_distance_m: float = 0.020) -> dict:
        """Latch a beaker at its current pose when the gripper reaches its grasp site."""
        if arm not in ("pourer", "transfer"):
            raise ValueError(f"Unknown arm: {arm}")
        if arm in self._held:
            raise RuntimeError(f"{arm} is already holding {self._held[arm]}")
        if beaker in self._held.values():
            raise RuntimeError(f"{beaker} is already held")
        tool_pos, tool_rot = self.site_pose(f"{arm}_gripperframe")
        object_pos, object_rot = self.body_pose(beaker)
        grasp_site = f"{beaker}_grasp"
        sid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, grasp_site)
        if sid < 0:
            raise ValueError(f"Unknown beaker grasp site: {grasp_site}")
        distance = float(np.linalg.norm(tool_pos - self.data.site_xpos[sid]))
        if distance > max_distance_m:
            return {"grasped": False, "beaker": beaker, "distance_mm": distance * 1000}

        # Set the local site frame to match the gripper now, preserving the object's pose.
        local_pos = object_rot.T @ (tool_pos - object_pos)
        local_rot = object_rot.T @ tool_rot
        self.model.site_pos[sid] = local_pos
        self.model.site_quat[sid] = self._matrix_quaternion(local_rot)
        mujoco.mj_setConst(self.model, self.data)
        eqid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_EQUALITY,
                                 f"weld_{arm}_{beaker}")
        if eqid < 0:
            raise ValueError(f"No grasp equality in scene for {arm} and {beaker}")
        self.data.eq_active[eqid] = 1
        mujoco.mj_forward(self.model, self.data)
        self._held[arm] = beaker
        return {"grasped": True, "beaker": beaker, "distance_mm": distance * 1000,
                "upright_axis": object_rot[:, 2].tolist()}

    def release(self, arm: str) -> str:
        if arm not in self._held:
            raise RuntimeError(f"{arm} is not holding a beaker")
        beaker = self._held.pop(arm)
        eqid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_EQUALITY,
                                 f"weld_{arm}_{beaker}")
        self.data.eq_active[eqid] = 0
        mujoco.mj_forward(self.model, self.data)
        return beaker

    def held_object(self, arm: str) -> str | None:
        return self._held.get(arm)

    def arm_contact_pairs(self, arm: str) -> list[dict]:
        """Return current MuJoCo contacts involving an arm body."""
        contacts = []
        prefix = f"{arm}_"
        for index in range(self.data.ncon):
            contact = self.data.contact[index]
            body1 = int(self.model.geom_bodyid[contact.geom1])
            body2 = int(self.model.geom_bodyid[contact.geom2])
            name1 = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, body1) or "world"
            name2 = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, body2) or "world"
            arm1, arm2 = name1.startswith(prefix), name2.startswith(prefix)
            if arm1 == arm2:
                continue
            contacts.append({
                "arm_body": name1 if arm1 else name2,
                "other_body": name2 if arm1 else name1,
                "distance_m": float(contact.dist),
            })
        return contacts

    def joint_position(self, name: str) -> float:
        jid = self._joint_id(name)
        return float(self.data.qpos[self.model.jnt_qposadr[jid]])

    def move_actuator(self, actuator: str, target: float, duration: float = 1.0) -> float:
        aid = self._actuator_id(actuator)
        joint_id = int(self.model.actuator_trnid[aid, 0])
        qadr = int(self.model.jnt_qposadr[joint_id])
        start = float(self.data.qpos[qadr])
        steps = max(1, round(duration / self.model.opt.timestep))
        for i in range(steps):
            ratio = (i + 1) / steps
            self.data.ctrl[aid] = start + (target - start) * ratio
            self._step_once()
        # Let the position servo settle so reported stage travel is meaningful.
        self.step(1.0)
        return float(self.data.qpos[qadr])

    def set_arm_targets_deg(self, arm: str, targets: dict[str, float], duration: float = 1.0) -> dict[str, float]:
        """Command named SO-101 joints in degrees. `arm` is `pourer` or `transfer`."""
        prefix = {"pourer": "pourer_", "transfer": "transfer_"}[arm]
        result = {}
        for joint, degrees in targets.items():
            actuator = prefix + joint
            result[joint] = math.degrees(self.move_actuator(actuator, math.radians(degrees), duration))
        return result

    def arm_positions_deg(self, arm: str) -> dict[str, float]:
        """Read the six articulated joints in the official SO-101 convention."""
        prefix = {"pourer": "pourer_", "transfer": "transfer_"}[arm]
        return {name: math.degrees(self.joint_position(prefix + name))
                for name in self._arm_joint_names}

    def set_arm_goals_deg(self, arm: str, goals: dict[str, float]) -> None:
        """Set position-servo goals without blocking the simulation step loop."""
        prefix = {"pourer": "pourer_", "transfer": "transfer_"}[arm]
        unknown = set(goals) - set(self._arm_joint_names)
        if unknown:
            raise ValueError(f"Unknown SO-101 joints: {sorted(unknown)}")
        if not self._torque_enabled[arm]:
            raise RuntimeError(f"Torque is disabled on {arm}")
        for joint, degrees in goals.items():
            aid = self._actuator_id(prefix + joint)
            self.data.ctrl[aid] = math.radians(float(degrees))

    def arm_load(self, arm: str) -> dict[str, float]:
        """Return simulated Present_Load-like values in the usual -1000..1000 range.

        This scales the MuJoCo actuator force to the configured 3.35 N m servo limit.
        It is a useful load trend, not a calibrated Feetech register model.
        """
        prefix = f"{arm}_"
        result = {}
        for joint in self._arm_joint_names:
            aid = self._actuator_id(prefix + joint)
            force_limit = max(abs(float(x)) for x in self.model.actuator_forcerange[aid])
            result[joint] = max(-1000.0, min(1000.0,
                float(self.data.actuator_force[aid]) / max(force_limit, 1e-9) * 1000.0))
        return result

    def set_arm_torque(self, arm: str, enabled: bool) -> None:
        """Enable or disable the MuJoCo position actuators for one arm."""
        if arm not in self._torque_enabled:
            raise ValueError(f"Unknown arm: {arm}")
        if self._torque_enabled[arm] == enabled:
            return
        for aid, gain, bias in self._actuator_power[arm]:
            if enabled:
                self.model.actuator_gainprm[aid, 0] = gain
                self.model.actuator_biasprm[aid, 1] = bias
            else:
                self.model.actuator_gainprm[aid, 0] = 0.0
                self.model.actuator_biasprm[aid, 1] = 0.0
        self._torque_enabled[arm] = enabled

    def move_carousel(self, degrees: float, duration: float = 2.0) -> float:
        return math.degrees(self.move_actuator("carousel_position", math.radians(degrees), duration))

    @staticmethod
    def stage_travel_mm(crank_degrees: float) -> float:
        """Slider-crank geometry, calibrated to the documented 97.3 mm at 150 degrees."""
        angle = math.radians(max(0.0, min(150.0, crank_degrees)))
        radius, rod = 0.050, 0.080
        x0 = radius + rod
        x = radius * math.cos(angle) + math.sqrt(rod * rod - (radius * math.sin(angle)) ** 2)
        raw_at_end = x0 - (radius * math.cos(math.radians(150)) +
                           math.sqrt(rod * rod - (radius * math.sin(math.radians(150))) ** 2))
        return (x0 - x) * (97.3 / (raw_at_end * 1000)) * 1000

    def move_stage(self, crank_degrees: float = 150.0, duration: float = 2.5) -> float:
        travel = self.stage_travel_mm(crank_degrees)
        measured_q = self.move_actuator("stage_position", -travel / 1000, duration)
        return -measured_q * 1000

    def scale_deflection_m(self) -> float:
        sid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SENSOR, "scale_deflection")
        adr = self.model.sensor_adr[sid]
        return float(self.data.sensordata[adr])

    def tare_scale(self) -> None:
        self.scale_tare_m = self.scale_deflection_m()

    def set_scale_payload_g(self, grams: float) -> None:
        """Apply the analytical liquid mass as a load on the MuJoCo scale flexure."""
        self.scale_payload_g = max(0.0, float(grams))

    def scale_grams(self) -> float:
        stiffness_n_m = 20000.0
        delta = self.scale_deflection_m() - self.scale_tare_m
        return -delta * stiffness_n_m / 9.81 * 1000.0

    def status(self) -> dict[str, float]:
        return {
            "time_s": float(self.data.time),
            "carousel_deg": self.joint_position("carousel_hinge") * 180 / math.pi,
            "stage_travel_mm": -self.joint_position("stage_slide") * 1000,
            "scale_deflection_m": self.scale_deflection_m(),
        }
