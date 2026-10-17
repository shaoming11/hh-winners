"""Video and still capture from the simulation (sim time based)."""
import imageio.v2 as imageio

from .render import Renderer


class Recorder:
    def __init__(self, world, out_dir, camera='overview', fps=25, width=960, height=540, video_name=None):
        self.w = world; self.dir = out_dir; self.dir.mkdir(parents=True, exist_ok=True); self.cam = camera; self.fps = fps
        self.r = Renderer(world.m, width=width, height=height); self.next_t = world.time; self.stills = []
        self.writer = imageio.get_writer(str(self.dir / video_name), fps=fps, codec='libx264', quality=6, macro_block_size=8) if video_name else None
        self.overlay = ''
        world.frame_hooks.append(self.hook)

    def hook(self, w):
        if self.writer is None or w.time + 1e-9 < self.next_t: return
        self.next_t += 1.0 / self.fps
        self.writer.append_data(self.r.frame(w.d, self.cam))

    def still(self, name, label, camera=None):
        import imageio.v3 as iio
        p = self.dir / ('%s.png' % name); iio.imwrite(p, self.r.frame(self.w.d, camera or self.cam))
        self.stills.append(dict(t=round(self.w.time, 3), path=p.name, label=label, camera=camera or self.cam)); return p

    def close(self):
        if self.writer is not None: self.writer.close(); self.writer = None
        if self.hook in self.w.frame_hooks: self.w.frame_hooks.remove(self.hook)
