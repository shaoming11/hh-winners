"""Machine-readable run record (shared contract). One JSON file per run, plus side files referenced by path.

    {
      "schema": "benchsim.runlog/1",
      "run_id": "20261017T101500Z-sim",  "mode": "sim" | "real",  "started_utc": ..., "finished_utc": ...,
      "config": {"layout_source": ..., "params_sha256": ..., "so101_revision": ..., "seed": ...},
      "protocol": {"source": "preset" | "llm" | "file", "text": ..., "steps": [Step.to_dict()...],
                   "validation": {"ok": bool, "problems": [...]}, "approved_by": ..., "approved_utc": ...},
      "steps": [{"index", "type", "label", "params", "status": "passed" | "failed" | "skipped", "reason",
                 "t_start", "t_end", "target": {...}, "measured": {...}, "faults": [...], "frames": [paths]}],
      "faults": [{"t", "code", "detail"}],
      "events": [{"t", "kind", ...}],                    # attach/detach, mega commands, stalls, ...
      "traces": {"scale_csv": path, "joints_csv": path, "pour_traces": [paths]},
      "frames": [{"t", "camera", "path", "label"}],
      "video": path | null,
      "summary": {"passed", "failed", "skipped", "masses": {...}, "spilled_g", "foam_peak_mm"}
    }
"""
import datetime
import hashlib
import json
from pathlib import Path

SCHEMA = 'benchsim.runlog/1'


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class RunLog:
    def __init__(self, out_dir, mode='sim', seed=0, run_id=None):
        self.started = utc()
        self.run_id = run_id or '%s-%s' % (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'), mode)
        self.dir = Path(out_dir) / self.run_id; self.dir.mkdir(parents=True, exist_ok=True)
        from . import assets, paths
        params = (paths.CONFIG / 'bench_params.toml').read_bytes()
        self.d = dict(schema=SCHEMA, run_id=self.run_id, mode=mode, started_utc=self.started, finished_utc=None,
                      config=dict(layout_source='tools/layout/layout_final.json:update13_final', params_sha256=hashlib.sha256(params).hexdigest(),
                                  so101_revision=json.loads(assets.LOCK.read_text())['revision'], seed=seed),
                      protocol=None, steps=[], faults=[], events=[], traces={}, frames=[], video=None, summary={})

    def set_protocol(self, source, steps, validation, text=None, approved_by=None):
        self.d['protocol'] = dict(source=source, text=text, steps=[s.to_dict() for s in steps], validation=validation,
                                  approved_by=approved_by, approved_utc=utc() if approved_by else None)

    def step(self, **row):
        self.d['steps'].append(row); return row

    def fault(self, t, code, detail=''):
        self.d['faults'].append(dict(t=round(t, 3), code=code, detail=detail))

    def frame(self, t, camera, path, label=''):
        self.d['frames'].append(dict(t=round(t, 3), camera=camera, path=str(Path(path).relative_to(self.dir)), label=label))

    def path(self, name):
        return self.dir / name

    def finish(self, summary, events=None):
        self.d['finished_utc'] = utc(); self.d['summary'] = summary
        if events is not None: self.d['events'] = events
        p = self.dir / 'run_log.json'; p.write_text(json.dumps(self.d, indent=1, default=str)); return p


def load(path):
    d = json.loads(Path(path).read_text())
    if d.get('schema') != SCHEMA: raise ValueError('not a %s file' % SCHEMA)
    return d
