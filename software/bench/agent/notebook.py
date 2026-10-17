"""Automatic lab-notebook record: JSON + a self-contained HTML page per run."""
from __future__ import annotations

import html
import json
import time
from pathlib import Path

from bench.paths import OUT_DIR


class Notebook:
    def __init__(self, out_dir: Path | None = None, operator: str = "", protocol_text: str = ""):
        self.dir = Path(out_dir or OUT_DIR / "notebook")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.stamp = time.strftime("%Y%m%d_%H%M%S")
        self.data = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "operator": operator,
                     "protocol_text": protocol_text, "plan": None, "validation": None,
                     "approved": False, "log": [], "doses": {}, "steps": [], "outcome": "",
                     "camera": [], "sim": None}

    # ---- recording
    def set_plan(self, plan, verdict) -> None:
        self.data["plan"] = {"title": plan.title, "source": plan.source,
                             "steps": [{"op": s.op, **s.args} for s in plan.steps]}
        self.data["validation"] = {"ok": verdict.ok, "problems": verdict.problems,
                                   "summary": verdict.summary}

    def approve(self, by: str = "operator") -> None:
        self.data["approved"] = True
        self.data["approved_by"] = by
        self.data["approved_at"] = time.strftime("%H:%M:%S")

    def log(self, line: str) -> None:
        self.data["log"].append(line)

    def snapshot(self, label: str, image, step: str = "") -> str:
        import imageio
        fn = self.dir / f"{self.stamp}_{len(self.data['camera']):02d}_{label}.png"
        imageio.imwrite(fn, image)
        self.data["camera"].append({"label": label, "step": step, "file": fn.name})
        return str(fn)

    def finish(self, run_record, sim_state: dict | None = None) -> Path:
        self.data["doses"] = run_record.doses
        self.data["steps"] = [{"name": s.name, "status": s.status, "t0": round(s.t_start, 1),
                               "t1": round(s.t_end, 1)} for s in run_record.steps]
        self.data["outcome"] = run_record.outcome
        self.data["faults"] = run_record.faults
        self.data["sim"] = sim_state
        p = self.dir / f"{self.stamp}_run.json"
        p.write_text(json.dumps(self.data, indent=1))
        (self.dir / f"{self.stamp}_run.html").write_text(self.render_html())
        return p

    # ---- rendering
    def render_html(self) -> str:
        d = self.data
        e = html.escape
        rows = ""
        for k, v in d["doses"].items():
            if isinstance(v, dict) and "target" in v:
                err = v.get("error", float("nan"))
                rows += (f"<tr><td>{e(k)}</td><td>{v['target']:.1f} g</td><td>{v['actual']:.2f} g</td>"
                         f"<td>{err:+.2f} g</td><td>{v.get('topups', 0)}</td></tr>")
            else:
                rows += f"<tr><td>{e(k)}</td><td colspan=4>{e(str(v))}</td></tr>"
        steps = "".join(f"<li><b>{e(s['name'])}</b> - {e(s['status'])} ({s['t0']:.0f}-{s['t1']:.0f} s)</li>"
                        for s in d["steps"])
        plan = "".join(f"<li><code>{e(json.dumps(s))}</code></li>" for s in (d["plan"] or {}).get("steps", []))
        imgs = "".join(f"<figure><img src='{e(c['file'])}' width=320><figcaption>{e(c['label'])} "
                       f"{e(c['step'])}</figcaption></figure>" for c in d["camera"])
        log = "\n".join(e(l) for l in d["log"][-400:])
        v = d["validation"] or {}
        return f"""<!doctype html><meta charset=utf-8><title>Wet Lab Bench run {e(self.stamp)}</title>
<style>body{{font:14px/1.4 system-ui;margin:2em;max-width:60em}} table{{border-collapse:collapse}}
td,th{{border:1px solid #ccc;padding:4px 8px}} pre{{background:#f6f6f6;padding:1em;overflow:auto;max-height:30em}}
figure{{display:inline-block;margin:0 1em 1em 0}} .ok{{color:#2a7}} .bad{{color:#c33}}</style>
<h1>Wet Lab Bench - run {e(self.stamp)}</h1>
<p><b>Outcome:</b> <span class="{'ok' if d['outcome']=='complete' else 'bad'}">{e(d['outcome'])}</span>
&nbsp; <b>Operator:</b> {e(d['operator'] or '-')} &nbsp; <b>Created:</b> {e(d['created'])}</p>
<h2>Protocol</h2><p>{e(d['protocol_text'] or '(preset)')}</p>
<h2>Plan ({e((d['plan'] or {}).get('source','-'))}) - validation {'PASSED' if v.get('ok') else 'FAILED'}
{'- approved by ' + e(d.get('approved_by','')) + ' at ' + e(d.get('approved_at','')) if d['approved'] else '- NOT approved'}</h2>
<p>{e(v.get('summary',''))}</p><ol>{plan}</ol>
{('<ul class=bad>' + ''.join('<li>'+e(p)+'</li>' for p in v.get('problems',[])) + '</ul>') if v.get('problems') else ''}
<h2>Doses (target vs actual, by weight)</h2>
<table><tr><th>dose</th><th>target</th><th>actual</th><th>error</th><th>top-ups</th></tr>{rows}</table>
<h2>Steps</h2><ol>{steps}</ol>
<h2>Camera</h2>{imgs or '<p>none</p>'}
<h2>Log</h2><pre>{log}</pre>
</html>"""
