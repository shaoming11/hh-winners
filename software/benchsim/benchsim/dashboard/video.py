"""Sim camera for the dashboard: renders one MuJoCo camera at ``fps`` of sim time from a world frame hook, JPEG-encodes
it and hands it to the Hub (/stream.mjpg). Main thread only: the renderer owns a GL context.

``camera`` is a scene camera name or 'auto', which follows the running step: close-up on the carousel and scale for
transfers and dosing, the pour and funnel close-ups for pours, the eruption camera from the moment the foam leaves the
neck, the overview otherwise. ``fx=True`` draws the camera look (benchsim.fx: room, glass, liquids, streams, foam) into each frame.

``'free'`` is a mouse-driven orbit camera: the dashboard sends absolute azimuth / elevation / distance / look-at and
this renders an ``MjvCamera`` instead of a scene camera.  Entering free mode copies the pose of whatever fixed camera
was on screen, so the picture does not jump when someone starts dragging.
"""
import io

import mujoco
import numpy as np

from ..render import Renderer

AUTO = {'TRANSFER': 'bench_cam', 'DOSE_YEAST': 'bench_cam', 'CAROUSEL': 'bench_cam', 'VERIFY_MASS': 'bench_cam',
        'POUR_TO_SCALE': 'pour_cam', 'POUR_TO_FUNNEL': 'funnel_cam'}


def auto_camera(snap):
    foam = ((snap or {}).get('probes') or {}).get('foam') or {}
    if (foam.get('column_mm') or 0) > 0: return 'erupt_cam'          # once the foam is out of the neck, watch it
    cur = (snap or {}).get('current')
    if cur is None:
        steps = (snap or {}).get('steps') or []
        done = [s for s in steps if s['status'] == 'passed']
        erupted = done and done[-1]['type'] == 'STAGE' and 'ERUPT' in done[-1]['label'].upper()
        return 'erupt_cam' if erupted else 'overview'
    if cur['type'] == 'STAGE' and cur['params'].get('position') == 'ERUPT': return 'erupt_cam'
    return AUTO.get(cur['type'], 'overview')


class Video:
    def __init__(self, hub, camera='auto', fps=15.0, width=960, height=540, quality=80, snapshot=None, fx=False):
        """snapshot: callable -> the latest feed snapshot (for 'auto'); fx: draw the camera look"""
        self.fx = fx; self.hub = hub; self.camera = camera; self.fps = fps; self.size = (width, height); self.quality = quality
        self.snapshot = snapshot or (lambda: None); self.w = None; self.r = None; self.next_t = 0.0; self.shown = None
        self.tape = None                                   # a dashboard.tape.Tape while a run is recorded
        self.free = None                                   # MjvCamera while camera == 'free'

    def cameras(self):
        return [self.w.m.camera(i).name for i in range(self.w.m.ncam)] if self.w is not None else []

    def set_camera(self, name):
        if name == 'free':
            if self.w is None: return False
            self.free = self._free_from(self.shown or 'overview'); self.camera = 'free'; return True
        if name != 'auto' and name not in self.cameras(): return False
        self.camera = name; return True

    def _free_from(self, name):
        """an MjvCamera that looks the same as scene camera `name`, so switching to free does not jump"""
        cam = mujoco.MjvCamera()
        mujoco.mjv_defaultFreeCamera(self.w.m, cam)
        try:
            cid = mujoco.mj_name2id(self.w.m, mujoco.mjtObj.mjOBJ_CAMERA, name)
            if cid < 0: return cam
            pos = np.array(self.w.d.cam_xpos[cid], dtype=float)
            fwd = -np.array(self.w.d.cam_xmat[cid], dtype=float).reshape(3, 3)[:, 2]   # -z is the view direction
            dist = float(np.linalg.norm(np.array(cam.lookat, dtype=float) - pos)) or 1.2
            cam.lookat[:] = pos + fwd * dist
            cam.distance = dist
            cam.azimuth = float(np.degrees(np.arctan2(fwd[1], fwd[0])))
            cam.elevation = float(np.degrees(np.arcsin(max(-1.0, min(1.0, fwd[2])))))
        except Exception:                                   # a hook must never raise; a default view is fine
            pass
        return cam

    def set_view(self, azimuth=None, elevation=None, distance=None, lookat=None):
        """absolute free-camera pose from the page (it owns the gesture state); switches to free mode"""
        if self.w is None: return False
        if self.free is None or self.camera != 'free':
            self.free = self._free_from(self.shown or 'overview'); self.camera = 'free'
        c = self.free
        if azimuth is not None: c.azimuth = float(azimuth)
        if elevation is not None: c.elevation = max(-89.0, min(89.0, float(elevation)))
        if distance is not None: c.distance = max(0.05, min(6.0, float(distance)))
        if lookat is not None and len(lookat) == 3: c.lookat[:] = [float(v) for v in lookat]
        return True

    def view(self):
        """the current free pose, for the page to seed its gesture state"""
        c = self.free
        if c is None: return None
        return dict(azimuth=round(float(c.azimuth), 2), elevation=round(float(c.elevation), 2),
                    distance=round(float(c.distance), 4), lookat=[round(float(v), 4) for v in c.lookat])

    def attach(self, world):
        from .. import fx
        self.detach(); self.w = world
        self.r = Renderer(world.m, width=self.size[0], height=self.size[1], fx=fx.make(world) if self.fx else None)
        world.frame_hooks.append(self.hook); self.next_t = world.time; self.push()

    def detach(self):
        if self.w is not None and self.hook in self.w.frame_hooks: self.w.frame_hooks.remove(self.hook)
        if self.r is not None: self.r.close()
        self.w = None; self.r = None

    def hook(self, w):
        if w.time + 1e-9 < self.next_t: return
        self.next_t = w.time + 1.0 / self.fps; rgb = self.push()
        if self.tape is not None: self.tape.frame(rgb, w.time)

    def current(self):
        if self.camera == 'free': return 'free'
        return auto_camera(self.snapshot()) if self.camera == 'auto' else self.camera

    def push(self):
        from PIL import Image
        cam = self.current(); buf = io.BytesIO()
        rgb = self.r.frame(self.w.d, self.free if cam == 'free' and self.free is not None else cam)
        Image.fromarray(rgb).save(buf, 'JPEG', quality=self.quality)
        self.shown = cam; self.hub.frame(buf.getvalue()); return rgb

    def idle(self):
        """between runs nothing moves; re-render when the chosen camera changes - or on every call in free
        mode, where the camera itself moves while the world stands still"""
        if self.w is not None and (self.camera == 'free' or self.current() != self.shown): self.push()
