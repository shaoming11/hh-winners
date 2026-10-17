"""Offscreen rendering helpers (PNG frames, MP4 video)."""
import mujoco
import numpy as np


class Renderer:
    def __init__(self, model, width=1280, height=720, fx=None):
        """fx: optional callable on each frame's scene copy (benchsim.fx.make(world)); None renders the plain scene"""
        self.model = model; self.r = mujoco.Renderer(model, height=height, width=width); self.fx = fx
        self.opt = mujoco.MjvOption()
        for g in (0, 1, 2): self.opt.geomgroup[g] = 1
        self.opt.geomgroup[3] = 0; self.opt.geomgroup[4] = 0
        for g in range(6): self.opt.sitegroup[g] = 0     # sites are named points (beaker lip, pockets...), not parts

    def frame(self, data, camera='overview'):
        self.r.update_scene(data, camera=camera, scene_option=self.opt)
        if self.fx is not None: self.fx(self.r.scene)
        return self.r.render()

    def save_png(self, data, path, camera='overview'):
        import imageio.v3 as iio
        iio.imwrite(path, self.frame(data, camera))
        return path

    def close(self): self.r.close()
