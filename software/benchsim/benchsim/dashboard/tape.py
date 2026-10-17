"""Recording of a dashboard run for replay (demo-day insurance): ``dashboard.mp4`` (the camera view the audience saw,
one frame per 1/fps of sim time) and ``tape.json`` (schema ``benchsim.dashboard-tape/1``):

    {"schema", "fps", "frame_t": [sim t of each video frame],
     "snaps": [feed snapshots without wire/events, at most SNAP_HZ per sim second],
     "wire": [every wire line once, by id], "events": [every ctx event once, by id]}

The replay page maps video time -> frame -> sim t and rebuilds a full snapshot from these, so scrubbing works both
ways. Frames are written as they are rendered (ffmpeg subprocess); the JSON is written on close.
"""
import json
from pathlib import Path

from .server import clean

SCHEMA = 'benchsim.dashboard-tape/1'
SNAP_HZ = 5.0


class Tape:
    def __init__(self, out_dir, fps):
        import imageio.v2 as imageio
        self.dir = Path(out_dir); self.fps = fps; self.frame_t = []; self.snaps = []; self.wire = {}; self.events = {}
        self._next_snap = -1e9; self._key = None
        self.writer = imageio.get_writer(str(self.dir / 'dashboard.mp4'), fps=fps, codec='libx264', quality=6, macro_block_size=4,
                                         ffmpeg_params=['-movflags', '+faststart'])

    def frame(self, rgb, t):
        self.writer.append_data(rgb); self.frame_t.append(round(float(t), 3))

    def snap(self, s):
        for w in s.get('wire', []): self.wire.setdefault(w['id'], w)
        for e in s.get('events', []): self.events.setdefault(e['id'], e)
        key = (s['seq_state'], tuple(x['status'] for x in s['steps']))       # never drop a status change
        if s['t'] < self._next_snap and key == self._key: return
        self._next_snap = s['t'] + 1.0 / SNAP_HZ; self._key = key
        self.snaps.append({k: v for k, v in s.items() if k not in ('wire', 'events')})

    def close(self):
        self.writer.close()
        d = dict(schema=SCHEMA, fps=self.fps, frame_t=self.frame_t, snaps=self.snaps,
                 wire=[self.wire[k] for k in sorted(self.wire)], events=[self.events[k] for k in sorted(self.events)])
        p = self.dir / 'tape.json'; p.write_text(json.dumps(clean(d), separators=(',', ':'))); return p


def load(run_dir):
    run_dir = Path(run_dir); p = run_dir / 'tape.json'; v = run_dir / 'dashboard.mp4'
    if not p.exists() or not v.exists(): raise FileNotFoundError('%s has no tape.json + dashboard.mp4 (record a run first)' % run_dir)
    if json.loads(p.read_text()).get('schema') != SCHEMA: raise ValueError('%s is not a %s file' % (p, SCHEMA))
    return p, v
