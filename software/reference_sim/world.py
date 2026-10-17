"""Small MuJoCo control loop for the independent reference simulator."""
from __future__ import annotations

import math
from pathlib import Path

import mujoco

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
