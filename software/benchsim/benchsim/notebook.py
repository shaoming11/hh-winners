"""Lab notebook: render a run directory (benchsim.runlog schema) as notebook.html and notebook.md.

    python -m benchsim.notebook <run_dir> [--out DIR] [--link-frames]

notebook.html is one self-contained file: inline CSS, the scale trace as inline SVG with a small hover script, camera
frames embedded as base64 PNG (``--link-frames`` links them by relative path instead). notebook.md carries the same
tables, links the frames by relative path and links scale_trace.svg, written next to it.

Sections: run header (id, mode, times, config hashes, SO-101 revision), protocol (source, text, validation, approval, the
approved plan), every step (status, reason, target vs measured, start/end), a mass summary, faults, the scale trace with
step bands, camera frames and an event count.

Inputs this module reads beyond the run log itself:
    traces.scale_csv   CSV with a header row; time column 't', 't_s', 'time' or 'time_s' (s) and mass column 'w', 'w_g',
                       'g', 'grams' or 'mass_g' (g). Otherwise the first two columns are used.
    step target/measured   dicts; numeric keys present in both are compared, 'tol_g' in the target is the tolerance.
"""
import argparse
import base64
import csv
import datetime
import hashlib
import html
import json
import math
import os
from pathlib import Path

from . import runlog

T_COLS = ('t', 't_s', 'time', 'time_s')
G_COLS = ('w', 'w_g', 'g', 'grams', 'mass_g')
TOL_KEYS = ('tol_g', 'tol')
MAX_TRACE_POINTS = 1200                      # SVG polyline points (min/max per bucket keeps spikes)


# ======================================================================= data
def read_scale_csv(path):
    """-> (t list in s, grams list)"""
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    if not rows: return [], []
    head = [h.strip().lower() for h in rows[0]]
    ti = next((head.index(c) for c in T_COLS if c in head), 0)
    gi = next((head.index(c) for c in G_COLS if c in head), 1)
    t, g = [], []
    for r in rows[1:]:
        try: t.append(float(r[ti])); g.append(float(r[gi]))
        except (ValueError, IndexError): continue
    return t, g


def downsample(t, g, n=MAX_TRACE_POINTS):
    """keep the min and max of each of n/2 buckets, in time order"""
    if len(t) <= n: return list(zip(t, g))
    out = []; k = max(1, len(t) // (n // 2))
    for i in range(0, len(t), k):
        seg = list(range(i, min(i + k, len(t))))
        lo = min(seg, key=lambda j: g[j]); hi = max(seg, key=lambda j: g[j])
        out += [(t[j], g[j]) for j in sorted({lo, hi})]
    return out


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def comparisons(step):
    """numeric keys present in both target and measured -> list of dict(key, target, measured, delta, tol, ok)"""
    tg = step.get('target') or {}; ms = step.get('measured') or {}
    tol = next((tg[k] for k in TOL_KEYS if is_num(tg.get(k))), None)
    out = []
    for k, v in tg.items():
        if k in TOL_KEYS or not is_num(v) or not is_num(ms.get(k)): continue
        d = ms[k] - v
        out.append(dict(key=k, target=v, measured=ms[k], delta=d, tol=tol, ok=None if tol is None else abs(d) <= tol + 1e-9))
    return out


def all_frames(log):
    """run-level frames plus step-level frame paths not listed at run level -> list of dict(t, camera, path, label, step)"""
    frames = [dict(f, step=None) for f in log.get('frames') or []]
    known = {f['path']: f for f in frames}
    for s in log.get('steps') or []:
        for p in s.get('frames') or []:
            if p in known:
                known[p]['step'] = s.get('index')
            else:
                f = dict(t=s.get('t_start'), camera='', path=p, label=s.get('label', ''), step=s.get('index')); frames.append(f); known[p] = f
    return frames


# ======================================================================= formatting
def fnum(x, nd=2):
    if x is None: return '–'
    if isinstance(x, bool): return 'yes' if x else 'no'
    if isinstance(x, int): return str(x)
    if isinstance(x, float): return ('%.' + str(nd) + 'f') % x
    return str(x)


def kv(d, nd=2):
    if not d: return ''
    if not isinstance(d, dict): return fnum(d, nd)
    return ', '.join('%s %s' % (k, kv(v, nd) if isinstance(v, dict) else fnum(v, nd)) for k, v in d.items())


def params_text(p):
    return ', '.join('%s=%s' % (k, fnum(v)) for k, v in (p or {}).items())


def delta_text(c):
    s = '%+.2f' % c['delta']
    if c['ok'] is None: return s
    return '%s (%s ±%s)' % (s, 'within' if c['ok'] else 'OUTSIDE', fnum(c['tol']))


def nice_ticks(lo, hi, n=5):
    if hi <= lo: hi = lo + 1.0
    raw = (hi - lo) / n; mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    return [i * step for i in range(math.floor(lo / step), math.ceil(hi / step) + 1)]


# ======================================================================= scale trace SVG
def scale_svg(t, g, steps=(), faults=(), width=960, height=300, standalone=False):
    """line chart of the scale reading with one band per timed step and a marker per fault. Colours come from CSS custom
    properties (with fallbacks) so the page's light/dark tokens apply; ``standalone`` adds an XML header for a .svg file."""
    L, R, T, B = 56, 16, 28, 40
    pts = downsample(t, g)
    t0 = min([p[0] for p in pts] + [s['t_start'] for s in steps if is_num(s.get('t_start'))])
    t1 = max([p[0] for p in pts] + [s['t_end'] for s in steps if is_num(s.get('t_end'))])
    gy = nice_ticks(min(0.0, min(p[1] for p in pts)), max(p[1] for p in pts))
    g0, g1 = gy[0], gy[-1]
    X = lambda v: L + (v - t0) / max(t1 - t0, 1e-9) * (width - L - R)
    Y = lambda v: T + (g1 - v) / max(g1 - g0, 1e-9) * (height - T - B)
    e = html.escape; o = []
    if standalone: o.append('<?xml version="1.0" encoding="UTF-8"?>')
    o.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" class="trace" role="img" '
             'aria-label="Scale reading in grams over run time in seconds, with step bands">' % (width, height))
    if standalone: o.append('<style>%s</style><rect width="100%%" height="100%%" fill="#fcfcfb"/>' % SVG_STANDALONE_CSS)
    for i, s in enumerate(steps):
        if not (is_num(s.get('t_start')) and is_num(s.get('t_end'))): continue
        x0, x1 = X(s['t_start']), X(s['t_end']); st = s.get('status', '')
        cls = 'band-fail' if st == 'failed' else ('band-a' if i % 2 == 0 else 'band-b')
        o.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" class="%s"><title>%s</title></rect>' % (
            x0, T, max(x1 - x0, 0.5), height - T - B, cls,
            e('step %s %s (%s) %.1f–%.1f s' % (s.get('index'), s.get('label', ''), st, s['t_start'], s['t_end']))))
        if x1 - x0 >= 14:
            o.append('<text x="%.1f" y="%d" class="band-label" text-anchor="middle">%s</text>' % ((x0 + x1) / 2, T - 8, e(str(s.get('index')))))
    for v in gy:
        o.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" class="grid"/>' % (L, width - R, Y(v), Y(v)))
        o.append('<text x="%d" y="%.1f" class="tick" text-anchor="end" dy="0.32em">%s</text>' % (L - 6, Y(v), fnum(v, 0 if v == int(v) else 1)))
    for v in nice_ticks(t0, t1, 8):
        if t0 - 1e-9 <= v <= t1 + 1e-9:
            o.append('<text x="%.1f" y="%d" class="tick" text-anchor="middle">%s</text>' % (X(v), height - B + 16, fnum(v, 0 if v == int(v) else 1)))
    o.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" class="axis"/>' % (L, width - R, Y(0) if g0 <= 0 <= g1 else height - B, Y(0) if g0 <= 0 <= g1 else height - B))
    o.append('<text x="%d" y="%d" class="axis-title" text-anchor="end">time (s)</text>' % (width - R, height - 6))
    o.append('<text x="%d" y="%d" class="axis-title">g</text>' % (L - 30, T - 8))
    for f in faults:
        if is_num(f.get('t')) and t0 <= f['t'] <= t1:
            o.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" class="fault"><title>%s</title></line>' % (
                X(f['t']), X(f['t']), T, height - B, e('fault %s at %.1f s %s' % (f.get('code'), f['t'], f.get('detail', '')))))
            right = X(f['t']) > width - R - 60                         # label on the left of a marker near the right edge
            o.append('<text x="%.1f" y="%d" class="fault-label" text-anchor="%s">%s</text>' % (
                X(f['t']) + (-4 if right else 4), T + 12, 'end' if right else 'start', e(str(f.get('code')))))
    o.append('<polyline class="line" points="%s"/>' % ' '.join('%.1f,%.1f' % (X(a), Y(b)) for a, b in pts))
    o.append('<g class="hover" visibility="hidden"><line class="xhair" x1="0" x2="0" y1="%d" y2="%d"/><circle r="4" class="dot"/></g>' % (T, height - B))
    o.append('</svg>')
    meta = dict(L=L, R=R, T=T, B=B, W=width, H=height, t0=t0, t1=t1, g0=g0, g1=g1)
    return '\n'.join(o), meta, pts


SVG_STANDALONE_CSS = (".grid{stroke:#e1e0d9}.axis{stroke:#c3c2b7}.tick,.band-label,.axis-title{fill:#898781;font:11px system-ui,sans-serif}"
                      ".line{fill:none;stroke:#2a78d6;stroke-width:2;stroke-linejoin:round}.band-a{fill:#f0efec}.band-b{fill:#f7f6f3}"
                      ".band-fail{fill:#f6d5d5}.fault{stroke:#d03b3b;stroke-width:1.5;stroke-dasharray:4 3}"
                      ".fault-label{fill:#b42323;font:600 11px system-ui,sans-serif}.hover{display:none}")

HOVER_JS = """
(function () {
  var box = document.getElementById('trace-box'); if (!box) return;
  var svg = box.querySelector('svg'), tip = box.querySelector('.tip');
  var D = JSON.parse(document.getElementById('trace-data').textContent);
  var m = D.meta, pts = D.pts, steps = D.steps, hov = svg.querySelector('.hover');
  var line = hov.querySelector('line'), dot = hov.querySelector('circle');
  function X(t) { return m.L + (t - m.t0) / Math.max(m.t1 - m.t0, 1e-9) * (m.W - m.L - m.R); }
  function Y(g) { return m.T + (m.g1 - g) / Math.max(m.g1 - m.g0, 1e-9) * (m.H - m.T - m.B); }
  svg.addEventListener('pointermove', function (ev) {
    var r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) * m.W / r.width;
    var t = m.t0 + (x - m.L) / (m.W - m.L - m.R) * (m.t1 - m.t0), lo = 0, hi = pts.length - 1;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (pts[mid][0] < t) lo = mid; else hi = mid; }
    var p = Math.abs(pts[lo][0] - t) < Math.abs(pts[hi][0] - t) ? pts[lo] : pts[hi];
    var st = steps.filter(function (s) { return s[0] <= p[0] && p[0] <= s[1]; })[0];
    line.setAttribute('x1', X(p[0])); line.setAttribute('x2', X(p[0]));
    dot.setAttribute('cx', X(p[0])); dot.setAttribute('cy', Y(p[1])); hov.setAttribute('visibility', 'visible');
    tip.textContent = 't ' + p[0].toFixed(2) + ' s   ' + p[1].toFixed(2) + ' g' + (st ? '   step ' + st[2] : '');
    tip.style.left = Math.min(X(p[0]) / m.W * r.width + 12, r.width - 220) + 'px'; tip.hidden = false;
  });
  svg.addEventListener('pointerleave', function () { hov.setAttribute('visibility', 'hidden'); tip.hidden = true; });
})();
"""

CSS = """
:root { --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781; --grid: #e1e0d9;
  --axis: #c3c2b7; --ring: rgba(11,11,11,0.10); --series: #2a78d6; --band-a: #f0efec; --band-b: #f7f6f3; --band-fail: #f6d5d5;
  --good: #006300; --bad: #b42323; --skip: #6b6a66; --good-bg: #e3f3e3; --bad-bg: #fbe3e3; --skip-bg: #ecebe7; --crit: #d03b3b; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec;
  --ink-2: #c3c2b7; --muted: #898781; --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10); --series: #3987e5;
  --band-a: #242422; --band-b: #1f1f1d; --band-fail: #4a2323; --good: #0ca30c; --bad: #e66767; --skip: #a3a29c;
  --good-bg: #133113; --bad-bg: #3d1a1a; --skip-bg: #2a2a28; } }
:root[data-theme="dark"] { --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10); --series: #3987e5; --band-a: #242422; --band-b: #1f1f1d;
  --band-fail: #4a2323; --good: #0ca30c; --bad: #e66767; --skip: #a3a29c; --good-bg: #133113; --bad-bg: #3d1a1a; --skip-bg: #2a2a28; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; } h2 { font-size: 17px; margin: 32px 0 8px; } h3 { font-size: 14px; margin: 16px 0 8px; }
.sub { color: var(--ink-2); margin: 0 0 16px; }
.card { background: var(--surface); border: 1px solid var(--ring); border-radius: 8px; padding: 12px 16px; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { color: var(--ink-2); font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: .03em; }
td.num { text-align: right; white-space: nowrap; }
a { color: var(--series); }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
pre { white-space: pre-wrap; margin: 0; }
.pill { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.passed, .ok { color: var(--good); background: var(--good-bg); } .failed, .bad { color: var(--bad); background: var(--bad-bg); }
.skipped, .none { color: var(--skip); background: var(--skip-bg); }
.kpis { display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0; }
.kpi { background: var(--surface); border: 1px solid var(--ring); border-radius: 8px; padding: 8px 14px; min-width: 110px; }
.kpi b { display: block; font-size: 22px; } .kpi span { color: var(--ink-2); font-size: 12px; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; margin: 0; } dt { color: var(--ink-2); } dd { margin: 0; word-break: break-all; }
#trace-box { position: relative; } svg.trace { width: 100%; height: auto; display: block; }
svg .grid { stroke: var(--grid); stroke-width: 1; } svg .axis { stroke: var(--axis); stroke-width: 1; }
svg .tick, svg .band-label, svg .axis-title { fill: var(--muted); font-size: 11px; }
svg .line { fill: none; stroke: var(--series); stroke-width: 2; stroke-linejoin: round; }
svg .fault { stroke: var(--crit); stroke-width: 1.5; stroke-dasharray: 4 3; } svg .fault-label { fill: var(--bad); font-size: 11px; font-weight: 600; }
svg .band-a { fill: var(--band-a); } svg .band-b { fill: var(--band-b); } svg .band-fail { fill: var(--band-fail); }
svg .xhair { stroke: var(--ink-2); stroke-width: 1; } svg .dot { fill: var(--series); stroke: var(--surface); stroke-width: 2; }
.tip { position: absolute; top: 8px; background: var(--surface); border: 1px solid var(--ring); border-radius: 6px; padding: 4px 8px;
  font-size: 12px; white-space: pre; pointer-events: none; box-shadow: 0 2px 8px rgba(0,0,0,.12); }
.frames { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
figure { margin: 0; background: var(--surface); border: 1px solid var(--ring); border-radius: 8px; padding: 8px; }
figure img { width: 100%; height: auto; display: block; border-radius: 4px; }
figcaption { color: var(--ink-2); font-size: 12px; margin-top: 6px; }
.missing { color: var(--bad); font-size: 12px; padding: 24px 0; text-align: center; }
details summary { cursor: pointer; color: var(--ink-2); margin: 8px 0; }
footer { color: var(--muted); font-size: 12px; margin-top: 40px; }
"""


# ======================================================================= HTML
def _pill(status, text=None):
    """status pill; class passed/failed/skipped (also ok/bad/none) with the status word, or ``text``, as its label"""
    s = status or 'none'
    return '<span class="pill %s">%s</span>' % (html.escape(s), html.escape(text or s))


def _table(head, rows, num_cols=()):
    e = html.escape
    o = ['<div class="scroll"><table><thead><tr>%s</tr></thead><tbody>' % ''.join('<th>%s</th>' % e(h) for h in head)]
    for r in rows:
        o.append('<tr>%s</tr>' % ''.join('<td%s>%s</td>' % (' class="num"' if i in num_cols else '', c) for i, c in enumerate(r)))
    o.append('</tbody></table></div>')
    return '\n'.join(o)


def to_html(log, run_dir, embed_frames=True, out_dir=None):
    run_dir = Path(run_dir); out_dir = Path(out_dir or run_dir); e = html.escape
    P = log.get('protocol') or {}; cfg = log.get('config') or {}; S = log.get('summary') or {}; steps = log.get('steps') or []
    faults = log.get('faults') or []; frames = all_frames(log)
    frame_ids = {f['path']: 'frame-%d' % i for i, f in enumerate(frames)}
    o = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
         '<title>Lab notebook %s</title><style>%s</style></head><body><main>' % (e(log.get('run_id', '')), CSS)]
    # header
    o.append('<h1>Lab notebook: run %s</h1>' % e(log.get('run_id', '')))
    o.append('<p class="sub">%s mode · started %s · finished %s</p>' % (e(str(log.get('mode', ''))), e(str(log.get('started_utc'))), e(str(log.get('finished_utc')))))
    counts = {k: sum(1 for s in steps if s.get('status') == k) for k in ('passed', 'failed', 'skipped')}
    o.append('<div class="kpis">%s</div>' % ''.join('<div class="kpi"><b>%s</b><span>%s</span></div>' % (e(fnum(v)), e(k)) for k, v in (
        ('steps passed', S.get('passed', counts['passed'])), ('failed', S.get('failed', counts['failed'])),
        ('skipped', S.get('skipped', counts['skipped'])), ('faults', len(faults)))))
    o.append('<div class="card"><dl>%s</dl></div>' % ''.join('<dt>%s</dt><dd><code>%s</code></dd>' % (e(k), e(fnum(v))) for k, v in (
        ('schema', log.get('schema')), ('layout source', cfg.get('layout_source')), ('bench_params sha256', cfg.get('params_sha256')),
        ('SO-101 model revision', cfg.get('so101_revision')), ('seed', cfg.get('seed')), ('video', log.get('video')))))
    # protocol
    o.append('<h2>Protocol</h2>')
    if not P:
        o.append('<p class="sub">No protocol recorded.</p>')
    else:
        V = P.get('validation') or {}; A = P.get('approval') or {}
        ok = V.get('ok')
        rows = [('source', e(fnum(P.get('source')))),
                ('validation', '%s %s' % (_pill(*{True: ('ok', 'passed'), False: ('bad', 'failed')}.get(ok, ('none', 'not run'))),
                                          '' if not V.get('problems') else '<ul>%s</ul>' % ''.join('<li>%s</li>' % e(p) for p in V['problems']))),
                ('approved by', e(fnum(P.get('approved_by'))) if P.get('approved_by') else '<span class="pill bad">not approved</span>'),
                ('approved at', e(fnum(P.get('approved_utc'))))]
        rows += [(k, '<code>%s</code>' % e(fnum(A[k]))) for k in ('approver', 'operator', 'plan_sha256', 'reason') if A.get(k) is not None]
        o.append('<div class="card"><dl>%s</dl></div>' % ''.join('<dt>%s</dt><dd>%s</dd>' % (e(k), v) for k, v in rows))
        if P.get('text'):
            o.append('<h3 class="sub">Protocol text</h3><div class="card"><pre>%s</pre></div>' % e(P['text']))
        if P.get('steps'):
            o.append('<h3 class="sub">Approved plan</h3>')
            o.append(_table(['#', 'type', 'params', 'label'], [(str(i + 1), '<code>%s</code>' % e(s.get('type', '')), e(params_text(s.get('params'))), e(s.get('label', '')))
                                                              for i, s in enumerate(P['steps'])], num_cols=(0,)))
    # steps
    o.append('<h2>Steps</h2>')
    rows = []
    for s in steps:
        cmp = comparisons(s)
        fr = ' '.join('<a href="#%s">%s</a>' % (frame_ids[p], e(Path(p).name)) for p in s.get('frames') or [] if p in frame_ids)
        sf = '; '.join('%s %s' % (f.get('code', ''), f.get('detail', '')) if isinstance(f, dict) else str(f) for f in s.get('faults') or [])
        rows.append((e(fnum(s.get('index'))), e(s.get('label', '')), '<code>%s</code>' % e(s.get('type', '')), _pill(s.get('status')),
                     e(s.get('reason') or '') + ('<br><b>faults:</b> %s' % e(sf) if sf else ''),
                     e(kv(s.get('target'))), e(kv(s.get('measured'))), '<br>'.join(e('%s %s' % (c['key'], delta_text(c))) for c in cmp),
                     e(fnum(s.get('t_start'), 1)), e(fnum(s.get('t_end'), 1)), fr))
    o.append(_table(['#', 'step', 'type', 'status', 'reason', 'target', 'measured', 'measured − target', 'start s', 'end s', 'frames'], rows, num_cols=(0, 8, 9)))
    # masses
    o.append('<h2>Masses</h2>')
    doses = [(e(fnum(s.get('index'))), e(s.get('label', '')), e(c['key']), e(fnum(c['target'])), e(fnum(c['measured'])), e('%+.2f' % c['delta']),
              e(fnum(c['tol'])), '–' if c['ok'] is None else (_pill('ok', 'within') if c['ok'] else _pill('bad', 'outside')))
             for s in steps for c in comparisons(s)]
    if doses: o.append(_table(['#', 'step', 'quantity', 'target', 'measured', 'difference', 'tolerance', 'result'], doses, num_cols=(0, 3, 4, 5, 6)))
    summ = [(e(k), e(kv(v) if isinstance(v, dict) else fnum(v))) for k, v in (S.get('masses') or {}).items()]
    summ += [(e(k), e(fnum(S.get(k)))) for k in ('spilled_g', 'foam_peak_mm') if k in S]
    if summ: o.append('<h3 class="sub">Run summary</h3>' + _table(['quantity', 'value'], summ, num_cols=(1,)))
    # faults
    o.append('<h2>Faults</h2>')
    o.append(_table(['t s', 'code', 'detail'], [(e(fnum(f.get('t'), 2)), '<code>%s</code>' % e(str(f.get('code'))), e(str(f.get('detail', ''))))
                                               for f in faults], num_cols=(0,)) if faults else '<p class="sub">No faults.</p>')
    # scale trace
    o.append('<h2>Scale trace</h2>')
    csv_rel = (log.get('traces') or {}).get('scale_csv')
    if csv_rel and (run_dir / csv_rel).exists():
        t, g = read_scale_csv(run_dir / csv_rel)
    else:
        t, g = [], []
    if t:
        svg, meta, pts = scale_svg(t, g, [s for s in steps], faults)
        data = dict(meta=meta, pts=[[round(a, 3), round(b, 3)] for a, b in pts],
                    steps=[[s['t_start'], s['t_end'], '%s %s' % (s.get('index'), s.get('label', ''))] for s in steps if is_num(s.get('t_start')) and is_num(s.get('t_end'))])
        o.append('<p class="sub">Scale reading (g) against run time (s), %d samples from <code>%s</code>. Bands are steps (red: failed), '
                 'dashed lines are faults.</p>' % (len(t), e(csv_rel)))
        o.append('<div class="card" id="trace-box">%s<div class="tip" hidden></div></div>' % svg)
        o.append('<script type="application/json" id="trace-data">%s</script>' % json.dumps(data).replace('</', '<\\/'))
        o.append('<script>%s</script>' % HOVER_JS)
        stride = max(1, len(t) // 100)
        o.append('<details><summary>Trace data (every %d%s sample, %d rows)</summary>%s</details>' % (
            stride, 'th' if stride > 1 else 'st', len(range(0, len(t), stride)),
            _table(['t s', 'g'], [(fnum(t[i], 3), fnum(g[i], 3)) for i in range(0, len(t), stride)], num_cols=(0, 1))))
    else:
        o.append('<p class="sub">No scale trace recorded%s.</p>' % (' (%s not found)' % e(csv_rel) if csv_rel else ''))
    # frames
    o.append('<h2>Camera frames</h2>')
    if not frames: o.append('<p class="sub">No frames recorded.</p>')
    else:
        o.append('<div class="frames">')
        for f in frames:
            p = run_dir / f['path']; cap = '%s · %s · t %s s%s' % (f.get('label') or Path(f['path']).name, f.get('camera') or '–', fnum(f.get('t'), 2),
                                                                    '' if f.get('step') is None else ' · step %s' % f['step'])
            if not p.exists(): img = '<div class="missing">missing: %s</div>' % e(f['path'])
            elif embed_frames: img = '<img alt="%s" src="data:image/png;base64,%s">' % (e(cap), base64.b64encode(p.read_bytes()).decode())
            else: img = '<img alt="%s" src="%s">' % (e(cap), e(Path(os.path.relpath(p, out_dir)).as_posix()))
            o.append('<figure id="%s">%s<figcaption>%s</figcaption></figure>' % (frame_ids[f['path']], img, e(cap)))
        o.append('</div>')
    # events
    ev = log.get('events') or []
    o.append('<h2>Events</h2>')
    if ev:
        kinds = {}
        for x in ev: kinds[x.get('kind')] = kinds.get(x.get('kind'), 0) + 1
        o.append(_table(['kind', 'count'], [(e(str(k)), str(v)) for k, v in sorted(kinds.items(), key=lambda kv_: -kv_[1])], num_cols=(1,)))
        o.append('<details><summary>All %d events%s</summary>%s</details>' % (len(ev), ' (first 500)' if len(ev) > 500 else '', _table(
            ['t s', 'kind', 'detail'], [(e(fnum(x.get('t'), 3)), e(str(x.get('kind'))), e(', '.join('%s=%s' % (k, v) for k, v in x.items() if k not in ('t', 'kind'))))
                                        for x in ev[:500]], num_cols=(0,))))
    else:
        o.append('<p class="sub">No events recorded.</p>')
    o.append('<footer>Generated by benchsim.notebook at %s from run_log.json (sha256 %s).</footer>' % (
        e(runlog.utc()), e(hashlib.sha256((run_dir / 'run_log.json').read_bytes()).hexdigest() if (run_dir / 'run_log.json').exists() else '–')))
    o.append('</main></body></html>')
    return '\n'.join(o)


# ======================================================================= Markdown
def _md(x):
    return str(x).replace('|', '\\|').replace('\n', ' ')


def _md_table(head, rows):
    o = ['| %s |' % ' | '.join(_md(h) for h in head), '|%s|' % '|'.join('---' for _ in head)]
    o += ['| %s |' % ' | '.join(_md(c) for c in r) for r in rows]
    return '\n'.join(o)


def to_markdown(log, run_dir, out_dir=None, svg_name=None):
    run_dir = Path(run_dir); out_dir = Path(out_dir or run_dir)
    P = log.get('protocol') or {}; cfg = log.get('config') or {}; S = log.get('summary') or {}; steps = log.get('steps') or []
    faults = log.get('faults') or []
    o = ['# Lab notebook: run %s' % log.get('run_id', ''), '',
         '%s mode · started %s · finished %s' % (log.get('mode'), log.get('started_utc'), log.get('finished_utc')), '',
         _md_table(['item', 'value'], [('schema', log.get('schema')), ('layout source', cfg.get('layout_source')),
                                       ('bench_params sha256', '`%s`' % cfg.get('params_sha256')), ('SO-101 model revision', '`%s`' % cfg.get('so101_revision')),
                                       ('seed', fnum(cfg.get('seed'))), ('steps passed / failed / skipped', '%s / %s / %s' % (
                                           S.get('passed', '–'), S.get('failed', '–'), S.get('skipped', '–'))), ('faults', len(faults)),
                                       ('video', fnum(log.get('video')))]), '', '## Protocol', '']
    if not P:
        o.append('No protocol recorded.')
    else:
        V = P.get('validation') or {}; A = P.get('approval') or {}
        rows = [('source', fnum(P.get('source'))), ('validation', {True: 'passed', False: 'FAILED'}.get(V.get('ok'), '–')),
                ('approved by', P.get('approved_by') or '**not approved**'), ('approved at', fnum(P.get('approved_utc')))]
        rows += [(k, '`%s`' % A[k]) for k in ('approver', 'operator', 'plan_sha256', 'reason') if A.get(k) is not None]
        o += [_md_table(['item', 'value'], rows), '']
        if V.get('problems'): o += ['Validation problems:', ''] + ['- %s' % p for p in V['problems']] + ['']
        if P.get('text'): o += ['Protocol text:', ''] + ['> %s' % ln for ln in str(P['text']).splitlines()] + ['']
        if P.get('steps'):
            o += ['Approved plan:', '', _md_table(['#', 'type', 'params', 'label'], [(i + 1, '`%s`' % s.get('type'), params_text(s.get('params')), s.get('label', ''))
                                                                             for i, s in enumerate(P['steps'])]), '']
    o += ['## Steps', '', _md_table(['#', 'step', 'type', 'status', 'reason', 'target', 'measured', 'measured − target', 'start s', 'end s'], [
        (fnum(s.get('index')), s.get('label', ''), '`%s`' % s.get('type', ''), '**%s**' % s.get('status') if s.get('status') != 'passed' else 'passed',
         (s.get('reason') or '') + (' faults: %s' % '; '.join('%s %s' % (f.get('code', ''), f.get('detail', '')) if isinstance(f, dict) else str(f)
                                                              for f in s['faults']) if s.get('faults') else ''),
         kv(s.get('target')), kv(s.get('measured')), '; '.join('%s %s' % (c['key'], delta_text(c)) for c in comparisons(s)),
         fnum(s.get('t_start'), 1), fnum(s.get('t_end'), 1)) for s in steps]), '', '## Masses', '']
    doses = [(fnum(s.get('index')), s.get('label', ''), c['key'], fnum(c['target']), fnum(c['measured']), '%+.2f' % c['delta'], fnum(c['tol']),
              '–' if c['ok'] is None else ('within' if c['ok'] else '**outside**')) for s in steps for c in comparisons(s)]
    if doses: o += [_md_table(['#', 'step', 'quantity', 'target', 'measured', 'difference', 'tolerance', 'result'], doses), '']
    summ = [(k, kv(v) if isinstance(v, dict) else fnum(v)) for k, v in (S.get('masses') or {}).items()]
    summ += [(k, fnum(S.get(k))) for k in ('spilled_g', 'foam_peak_mm') if k in S]
    if summ: o += ['Run summary:', '', _md_table(['quantity', 'value'], summ), '']
    o += ['## Faults', '', _md_table(['t s', 'code', 'detail'], [(fnum(f.get('t'), 2), '`%s`' % f.get('code'), f.get('detail', '')) for f in faults])
          if faults else 'No faults.', '', '## Scale trace', '']
    o.append('![scale trace](%s)' % svg_name if svg_name else 'No scale trace recorded.')
    o += ['', '## Camera frames', '']
    frames = all_frames(log)
    for f in frames:
        rel = Path(os.path.relpath(run_dir / f['path'], out_dir)).as_posix()
        cap = '%s · %s · t %s s%s' % (f.get('label') or Path(f['path']).name, f.get('camera') or '–', fnum(f.get('t'), 2), '' if f.get('step') is None else ' · step %s' % f['step'])
        o += ['![%s](%s)' % (_md(cap), rel) if (run_dir / f['path']).exists() else 'missing frame: `%s`' % f['path'], '', '*%s*' % cap, '']
    if not frames: o += ['No frames recorded.', '']
    ev = log.get('events') or []
    kinds = {}
    for x in ev: kinds[x.get('kind')] = kinds.get(x.get('kind'), 0) + 1
    o += ['## Events', '', _md_table(['kind', 'count'], sorted(kinds.items(), key=lambda kv_: -kv_[1])) if ev else 'No events recorded.', '',
          '---', 'Generated by benchsim.notebook at %s.' % runlog.utc(), '']
    return '\n'.join(o)


# ======================================================================= entry point
def render(run_dir, out_dir=None, embed_frames=True):
    """run_dir/run_log.json -> dict(html=Path, md=Path, svg=Path | None), written to out_dir (default run_dir)"""
    run_dir = Path(run_dir); out_dir = Path(out_dir or run_dir); out_dir.mkdir(parents=True, exist_ok=True)
    log = runlog.load(run_dir / 'run_log.json')
    svg_path = None; csv_rel = (log.get('traces') or {}).get('scale_csv')
    if csv_rel and (run_dir / csv_rel).exists():
        t, g = read_scale_csv(run_dir / csv_rel)
        if t:
            svg_path = out_dir / 'scale_trace.svg'
            svg_path.write_text(scale_svg(t, g, log.get('steps') or [], log.get('faults') or [], standalone=True)[0])
    h = out_dir / 'notebook.html'; h.write_text(to_html(log, run_dir, embed_frames, out_dir))
    m = out_dir / 'notebook.md'; m.write_text(to_markdown(log, run_dir, out_dir, svg_path.name if svg_path else None))
    return dict(html=h, md=m, svg=svg_path)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python -m benchsim.notebook', description='render a run directory as notebook.html and notebook.md')
    ap.add_argument('run_dir'); ap.add_argument('--out', default=None, help='output directory (default: the run directory)')
    ap.add_argument('--link-frames', action='store_true', help='link frames by relative path instead of embedding them')
    a = ap.parse_args(argv)
    out = render(a.run_dir, a.out, embed_frames=not a.link_frames)
    for k, p in out.items():
        if p: print('%s: %s' % (k, p))


if __name__ == '__main__':
    main()
