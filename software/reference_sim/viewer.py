"""Open the generated bench scene in MuJoCo's native viewer."""
from __future__ import annotations

import mujoco
import mujoco.viewer

from build_scene import build
from world import SCENE


def main() -> None:
    if not SCENE.exists():
        build()
    model = mujoco.MjModel.from_xml_path(str(SCENE))
    data = mujoco.MjData(model)
    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            mujoco.mj_step(model, data)
            viewer.sync()


if __name__ == "__main__":
    main()
