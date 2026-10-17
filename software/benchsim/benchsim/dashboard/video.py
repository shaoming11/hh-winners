"""Sim camera for the dashboard: renders one MuJoCo camera at ``fps`` of sim time from a world frame hook, JPEG-encodes
it and hands it to the Hub (/stream.mjpg). Main thread only: the renderer owns a GL context.

``camera`` is a scene camera name or 'auto', which follows the running step: close-up on the carousel and scale for
transfers and dosing, the flask camera for the eruption, the overview otherwise.
"""
import io

from ..render import Renderer

AUTO = {'TRANSFER': 'bench_cam', 'DOSE_YEAST': 'bench_cam', 'CAROUSEL': 'bench_cam', 'VERIFY_MASS': 'bench_cam'}


def auto_camera(snap):
    cur = (snap or {}).get('current')
    if cur is None:
        steps = (snap or {}).get('steps') or []
        done = [s for s in steps if s['status'] == 'passed']
        erupted = done and done[-1]['type'] == 'STAGE' and 'ERUPT' in done[-1]['label'].upper()
        return 'foam_cam' if erupted else 'overview'
    if cur['type'] == 'STAGE' and cur['params'].get('position') == 'ERUPT': return 'foam_cam'
    return AUTO.get(cur['type'], 'overview')


class Video:
    def __init__(self, hub, camera='auto', fps=15.0, width=960, height=540, quality=80, snapshot=None):
        """snapshot: callable -> the latest feed snapshot (for 'auto')"""
        self.hub = hub; self.camera = camera; self.fps = fps; self.size = (width, height); self.quality = quality
        self.snapshot = snapshot or (lambda: None); self.w = None; self.r = None; self.next_t = 0.0; self.shown = None

    def cameras(self):
        return [self.w.m.camera(i).name for i in range(self.w.m.ncam)] if self.w is not None else []

    def set_camera(self, name):
        if name != 'auto' and name not in self.cameras(): return False
        self.camera = name; return True

    def attach(self, world):
        self.detach(); self.w = world; self.r = Renderer(world.m, width=self.size[0], height=self.size[1])
        world.frame_hooks.append(self.hook); self.next_t = world.time; self.push()

    def detach(self):
        if self.w is not None and self.hook in self.w.frame_hooks: self.w.frame_hooks.remove(self.hook)
        if self.r is not None: self.r.close()
        self.w = None; self.r = None

    def hook(self, w):
        if w.time + 1e-9 < self.next_t: return
        self.next_t = w.time + 1.0 / self.fps; self.push()

    def current(self):
        return auto_camera(self.snapshot()) if self.camera == 'auto' else self.camera

    def push(self):
        from PIL import Image
        cam = self.current(); buf = io.BytesIO()
        Image.fromarray(self.r.frame(self.w.d, cam)).save(buf, 'JPEG', quality=self.quality)
        self.shown = cam; self.hub.frame(buf.getvalue())

    def idle(self):
        """between runs nothing moves; re-render only when the chosen camera changes"""
        if self.w is not None and self.current() != self.shown: self.push()
