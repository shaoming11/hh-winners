// Wet Lab Bench live dashboard. Reads benchsim.feed/1 snapshots from /events (Server-Sent Events) and the sim camera
// from /stream.mjpg. No build step and no libraries.
'use strict';
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v)) ? '–' : Number(v).toFixed(d);

const STATUS = { pending: '○ pending', running: '● running', passed: '✓ passed', failed: '✕ failed', skipped: '– skipped' };
const STATE = { IDLE: 'ready', PRECHECK: 'precheck', RUNNING: 'running', DONE: 'done', SAFE_STOP: 'safe stop', FAILED: 'failed' };
const ARM = { pourer: 'Pourer arm (west)', transfer: 'Transfer arm (east)' };

let last = null;
let wireSeen = 0;

// ------------------------------------------------------------------ connection
function connect() {
  const es = new EventSource('/events');
  es.onmessage = (m) => { last = JSON.parse(m.data); render(last); };
  es.onerror = () => { $('state').textContent = 'reconnecting…'; $('state').className = 'pill'; };
}

async function command(cmd) {
  try {
    const r = await fetch('/api/' + cmd, { method: 'POST' });
    const j = await r.json(); toast(j.message);
  } catch (e) { toast('server unreachable'); }
}

let toastTimer = null;
function toast(msg) {
  $('toast').textContent = msg; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').textContent = ''; }, 4000);
}

// ------------------------------------------------------------------ render
function render(s) {
  renderBar(s); renderTimeline(s); renderCaption(s); renderNow(s); renderWire(s); renderErrors(s);
}

function renderBar(s) {
  const runner = s.probes && s.probes.runner;
  const phase = runner ? runner.phase : null;
  $('mode').textContent = (s.mode || 'sim').toUpperCase();
  const st = $('state');
  st.textContent = phase === 'building' ? 'building bench…' : (STATE[s.seq_state] || s.seq_state);
  st.className = 'pill ' + ({ RUNNING: 'running', PRECHECK: 'running', DONE: 'done', SAFE_STOP: 'stopped', FAILED: 'stopped' }[s.seq_state] || '');
  $('clock').textContent = 't = ' + fmt(s.t, 1) + ' s';
  $('rtf').textContent = runner && runner.rtf ? 'sim speed ' + fmt(runner.rtf, 2) + '×' : '';
  $('btn-start').disabled = phase !== 'ready';
  $('btn-stop').disabled = !(phase === 'running' || phase === 'starting');
  $('btn-reset').disabled = !(phase === 'ready' || phase === 'finished');
  $('runner').textContent = runner ? 'Runner: ' + runner.name + ' · log: ' + runner.out : '';
}

function renderTimeline(s) {
  $('timeline').innerHTML = s.steps.map((st) =>
    '<li class="' + st.status + '" title="' + esc(st.reason || st.type) + '"><span class="n">' + st.index + '</span>' +
    esc(st.label.replace(/^\d+\s*/, '') || st.type) + '<span class="st">' + STATUS[st.status] + '</span></li>').join('');
}

function meter(cur, s) {
  // a pour fills toward its target; a wait counts down
  if (!cur) return null;
  const p = cur.params || {};
  if (cur.type === 'POUR_TO_SCALE' && s.scale.g !== null && cur.scale_start_g !== null) {
    return { value: s.scale.g - cur.scale_start_g, target: p.target_g, tol: p.tol_g,
             text: fmt(s.scale.g - cur.scale_start_g, 1) + ' / ' + fmt(p.target_g, 1) + ' g' };
  }
  if (cur.type === 'WAIT') {
    return { value: cur.elapsed_s, target: p.seconds, tol: 0, text: fmt(Math.max(0, p.seconds - cur.elapsed_s), 0) + ' s left' };
  }
  return null;
}

function renderCaption(s) {
  const cur = s.current;
  const stopped = s.seq_state === 'SAFE_STOP' || s.seq_state === 'FAILED';
  $('banner').hidden = !stopped;
  if (stopped) $('banner').textContent = '■ SAFE STOP: ' + (s.stop_reason || (s.errors || [])[0] || s.seq_state);
  if (cur) {
    $('cap-step').textContent = 'Step ' + cur.index + ' of ' + cur.of;
    $('cap-title').textContent = cur.narration.title;
  } else {
    $('cap-step').textContent = { DONE: 'Run complete', IDLE: 'Ready', SAFE_STOP: 'Stopped', FAILED: 'Not run' }[s.seq_state] || '';
    $('cap-title').textContent = s.seq_state === 'DONE' ? 'All ' + s.steps.length + ' steps passed'
      : s.seq_state === 'IDLE' ? 'Press Start to run ' + s.steps.length + ' steps' : $('cap-title').textContent;
  }
  const arm = cur && (cur.narration.arm || null);
  $('armtag').hidden = !arm; if (arm) $('armtag').textContent = ARM[arm] || arm;
  const m = meter(cur, s);
  $('cap-meter').hidden = !m;
  if (m) {
    const top = Math.max(m.target * 1.25, m.value, 1e-6);
    const pct = (v) => Math.max(0, Math.min(100, (v / top) * 100)) + '%';
    $('cap-fill').style.width = pct(m.value);
    $('cap-target').style.left = pct(m.target);
    $('cap-band').style.left = pct(m.target - m.tol); $('cap-band').style.width = 'calc(' + pct(2 * m.tol) + ')';
    $('cap-band').hidden = !m.tol;
    $('cap-meter-text').textContent = m.text;
  }
}

function renderNow(s) {
  const cur = s.current;
  if (!cur) { $('now-title').textContent = $('cap-title').textContent; $('now-detail').textContent = ''; $('now-science').hidden = true; $('now-facts').innerHTML = ''; return; }
  const n = cur.narration;
  $('now-title').textContent = n.title; $('now-detail').textContent = n.detail || '';
  $('now-science').hidden = !n.science;
  if (n.science) $('now-science').innerHTML = '<div class="eq">' + esc(n.science.equation) + '</div><div class="small">' + esc(n.science.text) + '</div>';
  const facts = [['Step type', cur.type], ['Elapsed', fmt(cur.elapsed_s, 1) + ' s']];
  if (cur.remaining_s !== null) facts.push(['Timeout in', fmt(cur.remaining_s, 0) + ' s']);
  if (n.chemical) facts.push(['Chemical', n.chemical.name + (n.chemical.formula ? ' (' + n.chemical.formula + ')' : '')]);
  if (n.amount_g !== null) facts.push(['Target', fmt(n.amount_g, 1) + ' g' + (n.tol_g ? ' ± ' + fmt(n.tol_g, 1) : '')]);
  if (s.scale.g !== null) facts.push(['Scale', fmt(s.scale.g, 1) + ' g' + (s.scale.rate_hz ? ' · ' + s.scale.rate_hz + ' samples/s' : '')]);
  if (n.clearance) facts.push(['Tightest gap', n.clearance.mm + ' mm (' + n.clearance.between + ')']);
  $('now-facts').innerHTML = facts.map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>').join('');
}

function renderWire(s) {
  const box = $('wire');
  const fresh = s.wire.filter((w) => w.id > wireSeen);
  if (!fresh.length) return;
  const stick = box.scrollTop + box.clientHeight >= box.scrollHeight - 8;
  for (const w of fresh) {
    const div = document.createElement('div');
    div.className = 'row ' + w.dir;
    const arrow = w.dir === 'tx' ? '→' : w.dir === 'rx' ? '←' : '!';
    const who = w.dev === 'mega' ? 'Mega' : w.dev;
    div.innerHTML = '<span class="t">' + fmt(w.t, 2) + '</span> <span class="arrow">' + arrow + '</span> <span class="dev">' + esc(who) +
      '</span> ' + esc(w.text) + (w.note ? '<span class="note">' + esc(w.note) + '</span>' : '');
    box.appendChild(div);
  }
  wireSeen = fresh[fresh.length - 1].id;
  while (box.childElementCount > 300) box.removeChild(box.firstChild);
  if (stick) box.scrollTop = box.scrollHeight;
}

function renderErrors(s) {
  const items = [];
  for (const f of s.faults || []) items.push(['crit', 'Mega fault ' + f.fault + (f.detail ? ': ' + f.detail : '')]);
  for (const e of s.errors || []) items.push(['crit', e]);
  for (const e of (s.events || []).filter((e) => e.kind === 'grasp')) {
    const verdict = e.outcome === 'grasped' ? 'holds the beaker' : e.outcome === 'miss' ? 'MISSED the beaker' : 'grasp unclear';
    items.push([e.outcome === 'grasped' ? 'ok' : 'crit', (ARM[e.arm] || e.arm) + ' ' + verdict + ': jaw stopped at ' +
      fmt(e.jaw_deg, 2) + '°, expected ' + fmt(e.expected_deg, 2) + '°']);
  }
  $('errors').innerHTML = items.length ? items.slice(-12).map(([c, t]) => '<li class="' + c + '">' + esc(t) + '</li>').join('') : '<li class="muted">none</li>';
}

// ------------------------------------------------------------------ wiring
document.querySelectorAll('button[data-cmd]').forEach((b) => b.addEventListener('click', () => command(b.dataset.cmd)));
$('btn-theme').addEventListener('click', () => {
  const root = document.documentElement;
  root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem('wlb-theme', root.dataset.theme); } catch (e) { /* storage unavailable */ }
});
try { const t = localStorage.getItem('wlb-theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* storage unavailable */ }
const video = $('video');
video.addEventListener('load', () => { $('novideo').hidden = true; });
video.addEventListener('error', () => { $('novideo').hidden = false; });
video.src = '/stream.mjpg';
connect();
