"""Live viewer (mjpython) and an offscreen video recorder for the sim."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import imageio

from sim.world import paint_fluids
import numpy as np

from bench.hal.base import BenchFault

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Recorder:
    """Hook into World.hooks; grabs a frame every 1/fps of sim time."""

    def __init__(self, world, path, fps: int = 20, camera: str = "overview", size=(540, 960)):
        self.w = world
        self.path = Path(path)
        self.fps = fps
        self.camera = camera
        self.w._render_size = size
        self.w._renderer = None
        self._next = 0.0
        self._writer = self._open_writer(fps)
        self.label = ""
        self.frames = 0

    def _open_writer(self, fps: int):
        """imageio's video backends differ in what they accept; try the FFMPEG plugin, then
        PyAV, then fall back to a PNG sequence."""
        try:
            return imageio.get_writer(str(self.path), format="FFMPEG", mode="I", fps=fps,
                                      codec="libx264", macro_block_size=1)
        except Exception:  # noqa: BLE001
            pass
        try:
            import imageio.v3 as iio
            w = iio.imopen(str(self.path), "w", plugin="pyav")
            w.init_video_stream("libx264", fps=fps)
            class _PyAV:
                def append_data(self_, img):
                    w.write_frame(img)
                def close(self_):
                    w.close()
            return _PyAV()
        except Exception:  # noqa: BLE001
            pass
        frames_dir = self.path.with_suffix("")
        frames_dir.mkdir(parents=True, exist_ok=True)
        class _PNGs:
            n = 0
            def append_data(self_, img):
                imageio.imwrite(frames_dir / f"{self_.n:06d}.png", img); self_.n += 1
            def close(self_):
                pass
        self.path = frames_dir
        return _PNGs()

    def mark(self, name: str, status: str) -> None:
        self.label = f"{name} [{status}]"

    def tick(self) -> None:
        if self.w.t < self._next:
            return
        self._next = self.w.t + 1.0 / self.fps
        img = self.w.render(self.camera)
        self._writer.append_data(img)
        self.frames += 1

    def close(self) -> None:
        self._writer.close()


class LiveView:
    """Interactive MuJoCo viewer paced to wall-clock time, driven from World.hooks.

    Needs `mjpython` on macOS.  Mouse: left-drag orbits, right-drag pans, scroll zooms.
    Keys: SPACE play/pause   [ / ] slower/faster   c cycle cameras (free, overview, webcam, top)
          h re-print this help   TAB / Shift+TAB hide or show the left / right panels.
    The panels are MuJoCo's own (rendering flags, contact/force visualisation, joint and
    actuator readouts); the demo keeps stepping the physics itself, so use SPACE here to pause.
    Closing the window stops the run safely.
    """

    CAMERAS = ["free", "overview", "webcam", "top", "scale_cam"]
    SLIP = 0.25        # s of pacing lag forgiven before the clock re-baselines

    def __init__(self, world, factor: float = 1.0, camera: str = "free", start_paused: bool = False):
        import mujoco
        import mujoco.viewer
        self.w = world
        self.factor = factor
        self.paused = start_paused
        self._cam_i = self.CAMERAS.index(camera) if camera in self.CAMERAS else 0
        self.v = mujoco.viewer.launch_passive(world.m, world.d, show_left_ui=True,
                                              show_right_ui=True, key_callback=self._key)
        self._apply_camera()
        self._t0_wall = time.monotonic()
        self._t0_sim = world.t
        self._next_sync = 0.0
        self.closed = False
        self.help()

    def help(self) -> None:
        print(self.__doc__.strip(), flush=True)
        print("NOTE: the Run/Pause button in MuJoCo's left panel is inert in this (passive) viewer;\n"
              "      click the window and press SPACE to play or pause the bench.", flush=True)
        if self.paused:
            print(">>> PAUSED at start - press SPACE to run <<<", flush=True)

    def _apply_camera(self) -> None:
        import mujoco
        name = self.CAMERAS[self._cam_i]
        with self.v.lock():
            if name == "free":
                self.v.cam.type = mujoco.mjtCamera.mjCAMERA_FREE
                self.v.cam.lookat[:] = [0.50, 0.42, 0.12]
                self.v.cam.distance = 1.25
                self.v.cam.azimuth = 215
                self.v.cam.elevation = -28
            else:
                self.v.cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
                self.v.cam.fixedcamid = mujoco.mj_name2id(self.w.m, mujoco.mjtObj.mjOBJ_CAMERA, name)
        print(f"camera: {name}", flush=True)

    def _key(self, keycode: int) -> None:
        if keycode == 32:                              # space
            self.paused = not self.paused
            print("PAUSED - press SPACE to play" if self.paused else "playing", flush=True)
            if not self.paused:
                self._t0_wall = time.monotonic(); self._t0_sim = self.w.t
        elif keycode == ord("["):
            self.factor = max(0.1, self.factor / 1.5); self._retime()
        elif keycode == ord("]"):
            self.factor = min(20.0, self.factor * 1.5); self._retime()
        elif keycode in (ord("c"), ord("C")):
            self._cam_i = (self._cam_i + 1) % len(self.CAMERAS); self._apply_camera()
        elif keycode in (ord("h"), ord("H")):
            self.help()

    def _retime(self) -> None:
        self._t0_wall = time.monotonic(); self._t0_sim = self.w.t
        print(f"speed: {self.factor:.2f}x real time", flush=True)

    def tick(self) -> None:
        """Closing the window is a BenchFault, not a SystemExit: the sequencer then runs
        safe_stop() and run_demo still writes the notebook and the run json.  Anything else
        going wrong downgrades to headless rather than faking a safety event."""
        if self.closed:
            return
        try:
            if not self.v.is_running():
                self._stop()
            while self.paused:                          # hold the bench; the camera still works
                self.v.sync(); time.sleep(0.03)
                if not self.v.is_running():
                    self._stop()
            if self.w.t >= self._next_sync:
                self._next_sync = self.w.t + 1 / 60
                with self.v.lock():
                    self.v.user_scn.ngeom = 0
                    paint_fluids(self.v.user_scn, self.w)
                self.v.sync()
            if self.factor > 0:
                # never catch up: a blocking step (the 15 snapshot renders, mp4 encoding, the
                # approval prompt) must not turn into a fast-forward burst afterwards, so
                # past SLIP we forgive the debt instead of sprinting to pay it off.
                lag = time.monotonic() - (self._t0_wall + (self.w.t - self._t0_sim) / self.factor)
                if lag < 0:
                    time.sleep(min(-lag, 0.05))
                elif lag > self.SLIP:
                    self._t0_wall, self._t0_sim = time.monotonic(), self.w.t
        except BenchFault:
            raise
        except Exception as e:                          # noqa: BLE001
            self.closed = True
            print(f"viewer error ({type(e).__name__}: {e}) - continuing headless", flush=True)

    def _stop(self) -> None:
        # the flag, not hooks.remove(): World._post_step iterates the list in place, and
        # safe_stop() steps the world again on the way out.
        self.closed = True
        raise BenchFault("viewer closed")

    def wait(self) -> None:
        """Hold the finished scene on screen - the eruption - until the window is closed."""
        if self.closed:
            return
        print("viewer: close the window to exit", flush=True)
        try:
            while self.v.is_running():
                self.v.sync(); time.sleep(0.1)
        except Exception:                               # noqa: BLE001
            pass

    def close(self) -> None:
        try:
            self.v.close()
        except Exception:                               # noqa: BLE001
            pass



def main():  # pragma: no cover - interactive
    """mjpython -m sim.viewer   (macOS needs mjpython for the passive viewer)"""
    import mujoco.viewer
    from bench.config import load
    from sim.world import World
    w = World(load())
    with mujoco.viewer.launch_passive(w.m, w.d) as v:
        while v.is_running():
            w.step(5)
            v.sync()


if __name__ == "__main__":
    main()
