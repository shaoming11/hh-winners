// Wet Lab Bench live dashboard. Reads benchsim.feed/1 snapshots from /events (Server-Sent Events) and the sim camera
// from /stream.mjpg. No build step and no libraries.
'use strict';
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (v, d = 1) => (v === null || v === undefined || Number.isNaN(v)) ? '–' : Number(v).toFixed(d);

const GLYPH = { pending: '□', running: '■', passed: '✔', failed: '✕', skipped: '–' };
const STATE = { IDLE: 'ready', PRECHECK: 'precheck', RUNNING: 'running', DONE: 'done', SAFE_STOP: 'safe stop', FAILED: 'failed' };
const ARM = { pourer: 'Pourer arm (west)', transfer: 'Transfer arm (east)' };

let last = null;
let wireSeen = 0;
let replayVideo = null;   // the <video> element in replay mode

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
  renderBar(s); renderSpeeds(s); renderCams(s); renderCaption(s); renderRun(s); renderChem(s); renderTwin(s);
  renderWire(s); renderErrors(s);
}

const SPEEDS = [0.5, 1, 2, 4, 8];
let speedKey = '';
function renderSpeeds(s) {
  const r = s.probes && s.probes.runner; const cur = replayVideo ? replayVideo.playbackRate : (r ? r.speed : null);
  if (String(cur) === speedKey) return;
  speedKey = String(cur);
  $('speeds').innerHTML = SPEEDS.map((x) => '<button data-speed="' + x + '" class="' + (x === cur ? 'on' : '') + '" title="' + x + '× real time">' + x + '×</button>').join('');
}
$('speeds').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-speed]'); if (!b) return;
  if (replayVideo) { replayVideo.playbackRate = Number(b.dataset.speed); speedKey = ''; renderSpeeds(last); } else command('speed/' + b.dataset.speed);
});

// Chemistry: categorical slots in fixed order (validated: dataviz validator, both themes); text carries every value too
const SPECIES = [['developer', 'H₂O₂ developer', '--s1'], ['yeast', 'yeast', '--s2'], ['water', 'water', '--s3'], ['soap', 'soap', '--s4'], ['dye', 'dye', '--s5']];
const VESSELS = [['dev', 'Peroxide beaker'], ['water', 'Water beaker'], ['hopper', 'Yeast hopper'], ['P1', 'Beaker P1'], ['P2', 'Beaker P2'], ['flask', 'Flask']];
const FULL_G = 100;   // bar scale shared by every vessel, so lengths compare
function renderChem(s) {
  if (!s.vessels) return;
  if (!$('chem-legend').childElementCount) {
    $('chem-legend').innerHTML = SPECIES.map(([, label, c]) => '<span style="--c: var(' + c + ')">' + esc(label) + '</span>').join('');
  }
  const top = Math.max(FULL_G, ...VESSELS.map(([v]) => Object.values(s.vessels[v] || {}).reduce((a, b) => a + b, 0)));
  $('chem').innerHTML = VESSELS.map(([v, label]) => {
    const comp = s.vessels[v] || {};
    const parts = SPECIES.filter(([k]) => (comp[k] || 0) > 0.05);
    const total = parts.reduce((a, [k]) => a + comp[k], 0);
    const bar = parts.map(([k, , c]) => '<i style="--c: var(' + c + '); width: ' + (comp[k] / top * 100) + '%" title="' + esc(k) + ' ' + fmt(comp[k], 1) + ' g"></i>').join('');
    const txt = parts.length ? parts.map(([k]) => k + ' ' + fmt(comp[k], 1)).join(' · ') + ' g' : 'empty';
    // one line per vessel: the total shows, the per-species split is in the tooltip
    return '<div class="vessel' + (parts.length ? '' : ' empty') + '" title="' + esc(label + ': ' + txt) + '"><span class="name">' + esc(label) + '</span><span class="vbar">' + bar + '</span>' +
      '<span class="txt">' + (parts.length ? fmt(total, 1) + ' g' : 'empty') + '</span></div>';
  }).join('');
  const f = s.probes && s.probes.foam; const bits = [];
  if (s.spilled_g !== null && s.spilled_g !== undefined) bits.push('spilled <b>' + fmt(s.spilled_g, 2) + ' g</b>');
  if (f && f.t_contact !== null) {
    bits.push('O₂ released <b>' + fmt(f.o2_ml, 0) + ' mL</b>', 'foam column <b>' + fmt(f.column_mm, 0) + ' mm</b>');
    if (f.peak_mm) bits.push('peak <b>' + fmt(f.peak_mm, 0) + ' mm</b>');
    if (f.h2o2_left_g !== null) bits.push('H₂O₂ left <b>' + fmt(f.h2o2_left_g, 2) + ' g</b>');
  }
  $('foam').innerHTML = bits.join('');
}

const CAM = { auto: 'Auto', overview: 'Overview', bench_cam: 'Close-up', top: 'Top', foam_cam: 'Flask' };
let camKey = '';
function renderCams(s) {
  const v = s.probes && s.probes.video;
  if (!v) { $('cams').hidden = true; return; }
  const names = ['auto'].concat(v.cameras);
  $('cams').hidden = false;
  if (names.join(',') !== camKey) {   // rebuild only when the camera list changes, so a click is never lost mid-rebuild
    camKey = names.join(',');
    $('cams').innerHTML = names.map((n) => '<button data-cam="' + esc(n) + '">' + esc(CAM[n] || n) + (n === 'auto' ? '<span class="live"></span>' : '') + '</button>').join('');
  }
  for (const b of $('cams').children) b.classList.toggle('on', b.dataset.cam === v.camera);
  $('cams').querySelector('.live').textContent = v.camera === 'auto' ? ' · ' + (CAM[v.shown] || v.shown) : '';
}
$('cams').addEventListener('click', (e) => { const b = e.target.closest('button[data-cam]'); if (b) command('camera/' + b.dataset.cam); });

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
  $('runner').textContent = $('runner').title = runner ? 'Runner: ' + runner.name + ' · log: ' + runner.out : '';
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

// Run panel, styled like the Claude Code terminal: a spinner line for the current step, then the steps as a todo list
// with finished steps folded away and the current step's details nested under it
const SPIN = ['·', '✢', '✳', '✶', '✻', '✽'];
const SPIN_LOOP = SPIN.concat(SPIN.slice(1, -1).reverse());   // forward, then back
const STILL = matchMedia('(prefers-reduced-motion: reduce)').matches;
const spinGlyph = () => STILL ? '✻' : SPIN_LOOP[Math.floor(performance.now() / 120) % SPIN_LOOP.length];
setInterval(() => { const g = document.querySelector('#run-head .spin'); if (g) g.textContent = spinGlyph(); }, 120);
let runOpen = false;   // finished steps unfolded
let runHtml = '';

function runHead(s) {
  // -> [class, glyph (null = spinner), title, muted suffix]
  const cur = s.current; const runner = s.probes && s.probes.runner; const n = s.steps.length;
  if (s.seq_state === 'SAFE_STOP' || s.seq_state === 'FAILED') return ['stopped', '✕', 'Safe stop: ' + (s.stop_reason || (s.errors || [])[0] || s.seq_state), ''];
  if (cur) return ['busy', null, cur.narration.title + '…', '(' + fmt(cur.elapsed_s, 1) + ' s' + (cur.remaining_s !== null ? ' · times out in ' + fmt(cur.remaining_s, 0) + ' s' : '') + ')'];
  if (runner && runner.phase === 'building') return ['busy', null, 'Building the bench…', ''];
  if (s.seq_state === 'PRECHECK' || s.seq_state === 'RUNNING') return ['busy', null, s.seq_state === 'PRECHECK' ? 'Running prechecks…' : 'Running…', ''];
  if (s.seq_state === 'DONE') {
    const ok = s.steps.filter((st) => st.status === 'passed').length;
    return ['done', '✔', 'Run complete · ' + (ok === n ? 'all ' + n + ' steps passed' : ok + ' of ' + n + ' steps passed'), ''];
  }
  return ['idle', '✻', 'Ready · press Start to run ' + n + ' steps', ''];
}

function runFacts(s, cur) {
  const n = cur.narration; const facts = [['Step type', cur.type]];
  if (n.chemical) facts.push(['Chemical', n.chemical.name + (n.chemical.formula ? ' (' + n.chemical.formula + ')' : '')]);
  if (n.amount_g !== null) facts.push(['Target', fmt(n.amount_g, 1) + ' g' + (n.tol_g ? ' ± ' + fmt(n.tol_g, 1) : '')]);
  if (s.scale.g !== null) facts.push(['Scale', fmt(s.scale.g, 1) + ' g' + (s.scale.rate_hz ? ' · ' + s.scale.rate_hz + ' samples/s' : '')]);
  if (n.clearance) facts.push(['Tightest gap', n.clearance.mm + ' mm (' + n.clearance.between + ')']);
  return '<dl class="facts">' + facts.map(([k, v]) => '<dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd>').join('') + '</dl>';
}

function runRow(st, s) {
  const cur = s.current && s.current.index === st.index ? s.current : null;
  let sub = '';
  if (cur) {
    const n = cur.narration;
    sub = (n.detail ? '<p>' + esc(n.detail) + '</p>' : '') +
      (n.science ? '<div class="science"><div class="eq">' + esc(n.science.equation) + '</div><div>' + esc(n.science.text) + '</div></div>' : '') + runFacts(s, cur);
  } else if (st.status === 'failed' && st.reason) sub = '<p class="why">' + esc(st.reason) + '</p>';
  return '<li class="' + st.status + '" title="' + esc(st.reason || st.type) + '"><span class="g">' + GLYPH[st.status] + '</span><span class="n">' + st.index +
    '</span><span class="lbl">' + esc(st.label.replace(/^\d+\s*/, '') || st.type) + '</span>' + (sub ? '<div class="sub">' + sub + '</div>' : '') + '</li>';
}

function renderRun(s) {
  const [cls, glyph, title, meta] = runHead(s);
  $('run-head').className = 'run-head ' + cls;
  $('run-head').innerHTML = '<span class="g' + (glyph ? '' : ' spin') + '">' + (glyph || spinGlyph()) + '</span><span><span class="t">' + esc(title) + '</span>' +
    (meta ? ' <span class="meta">' + esc(meta) + '</span>' : '') + '</span>';
  const steps = s.steps;
  let focus = steps.findIndex((st) => st.status !== 'passed' && st.status !== 'skipped');
  if (focus < 0) focus = steps.length;
  const fold = focus >= 3 ? focus - 1 : 0;   // finished steps folded away; the last finished one stays in view
  const more = $('run-more'); more.hidden = !fold;
  if (fold) {
    const skipped = steps.slice(0, fold).filter((st) => st.status === 'skipped').length;
    more.textContent = runOpen ? '− hide ' + fold + ' finished steps' : '… +' + fold + ' steps done' + (skipped ? ' (' + skipped + ' skipped)' : '');
  }
  const html = steps.slice(runOpen ? 0 : fold).map((st) => runRow(st, s)).join('');
  if (html !== runHtml) { runHtml = html; $('run-steps').innerHTML = html; }
}
$('run-more').addEventListener('click', () => { runOpen = !runOpen; if (last) renderRun(last); });

const TIGHTEST_MM = 5.3;   // smallest verified clearance in the demo (held beaker vs funnel, demo_process 4)
const JOINT = { shoulder_pan: 'pan', shoulder_lift: 'lift', elbow_flex: 'elbow', wrist_flex: 'w.flex', wrist_roll: 'w.roll' };
const xyz = (p) => p ? p.map((v) => fmt(v, 1)).join(', ') : '–';

const ARM_SHORT = { pourer: 'Pourer (W)', transfer: 'Transfer (E)' };

function twinStatus(t, gap) {
  // -> [class, short label, full sentence]
  if (t.error_mm === undefined) return ['idle', 'idle', 'no command yet'];
  if (!t.settled) return ['lag', 'moving ' + fmt(t.error_mm, 1) + ' mm', 'moving: ' + fmt(t.error_mm, 1) + ' mm tracking lag'];
  if (t.error_mm >= gap) return ['crit', '✕ ' + fmt(t.error_mm, 2) + ' mm', '✕ ' + fmt(t.error_mm, 2) + ' mm: more than the ' + gap + ' mm gap'];
  if (t.error_mm >= gap / 2) return ['warn', '! ' + fmt(t.error_mm, 2) + ' mm', '! ' + fmt(t.error_mm, 2) + ' mm: over half the ' + gap + ' mm gap'];
  return ['ok', '✓ ' + fmt(t.error_mm, 2) + ' mm', '✓ ' + fmt(t.error_mm, 2) + ' mm off the plan'];
}

function renderTwin(s) {
  // one line per arm; plan/servo positions, joint errors and load are in the row's tooltip
  const cur = s.current;
  const html = Object.entries(s.arms || {}).map(([name, a]) => {
    const t = a.twin || {};
    const active = cur && cur.narration.arm === name;
    const gap = active && cur.narration.clearance ? cur.narration.clearance.mm : TIGHTEST_MM;
    const [cls, label, sentence] = twinStatus(t, gap);
    const top = Math.max(gap * 1.5, t.error_mm || 0);
    const pct = (v) => Math.max(0, Math.min(100, (v / top) * 100)) + '%';
    const joints = t.joint_err_deg ? Object.entries(t.joint_err_deg).map(([j, v]) => JOINT[j] + ' ' + (v >= 0 ? '+' : '') + fmt(v, 1) + '°').join('  ') : '–';
    const loads = (a.load_pm || []).slice(0, 5).map((v) => Math.abs(v) / 10);
    const maxLoad = loads.length ? Math.max(...loads) : 0;
    const maxJ = Object.keys(JOINT)[loads.indexOf(maxLoad)];
    const tip = [sentence + ' (gap ' + gap + ' mm)', 'plan (x, y, z): ' + xyz(t.commanded_mm) + ' mm', 'servos say: ' + xyz(t.measured_mm) + ' mm',
      'joint Δ: ' + joints, 'highest load: ' + (maxJ ? JOINT[maxJ] + ' ' + fmt(maxLoad, 0) + ' % of max torque' : '–')].join('\n');
    return '<div class="twin-arm' + (active ? ' active' : '') + '" title="' + esc(tip) + '"><b>' + esc(ARM_SHORT[name] || name) + '</b>' +
      '<span class="hold muted">' + (a.holding ? 'holding ' + esc(a.holding) : '') + '</span>' +
      '<div class="meter-track"><div class="meter-fill ' + cls + '" style="width:' + pct(t.error_mm || 0) + '"></div><div class="meter-target" style="left:' + pct(gap) + '"></div></div>' +
      '<span class="twin-status ' + cls + '">' + esc(label) + '</span></div>';
  }).join('');
  $('twin').innerHTML = html || '–';
}

// follow new lines until the reader scrolls up; kept from scroll events because the box changes height with the window
let wireStick = true;
$('wire').addEventListener('scroll', () => { const b = $('wire'); wireStick = b.scrollTop + b.clientHeight >= b.scrollHeight - 8; });

function renderWire(s) {
  const box = $('wire');
  const fresh = s.wire.filter((w) => w.id > wireSeen);
  if (!fresh.length) return;
  const stick = wireStick;
  for (const w of fresh) {
    const div = document.createElement('div');
    div.className = 'row ' + w.dir;
    const arrow = w.dir === 'tx' ? '→' : w.dir === 'rx' ? '←' : '!';
    const who = w.dev === 'mega' ? 'Mega' : w.dev;
    // one line each (the note goes before the text so the ellipsis never hides it); the full line is the tooltip
    div.innerHTML = '<span class="t">' + fmt(w.t, 2) + '</span> <span class="arrow">' + arrow + '</span> <span class="dev">' + esc(who) +
      '</span> ' + (w.note ? '<span class="note">' + esc(w.note) + '</span> ' : '') + esc(w.text);
    div.title = fmt(w.t, 2) + ' ' + arrow + ' ' + who + ' ' + w.text + (w.note ? ' (' + w.note + ')' : '');
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
  $('errors').innerHTML = items.length ? items.slice(-4).map(([c, t]) => '<li class="' + c + '" title="' + esc(t) + '">' + esc(t) + '</li>').join('') : '<li class="muted">none</li>';
}

// ------------------------------------------------------------------ wiring
document.querySelectorAll('button[data-cmd]').forEach((b) => b.addEventListener('click', () => command(b.dataset.cmd)));
$('btn-theme').addEventListener('click', () => {
  const root = document.documentElement;
  root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem('wlb-theme', root.dataset.theme); } catch (e) { /* storage unavailable */ }
});
try { const t = localStorage.getItem('wlb-theme'); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* storage unavailable */ }
// ------------------------------------------------------------------ replay (python -m benchsim.dashboard --replay RUN_DIR)
const upto = (arr, t) => {   // index of the last item with .t <= t, or -1
  let lo = 0, hi = arr.length - 1, ans = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (arr[m].t <= t) { ans = m; lo = m + 1; } else hi = m - 1; }
  return ans;
};

async function startReplay() {
  let r;
  try { r = await fetch('/replay/tape.json'); } catch (e) { return false; }
  if (!r.ok) return false;
  const tape = await r.json();
  document.body.classList.add('replay'); $('brand-mode').textContent = '· replay';
  const v = document.createElement('video');
  v.src = '/replay/video.mp4'; v.controls = true; v.muted = true; v.playsInline = true;
  $('video').replaceWith(v); $('novideo').hidden = true; replayVideo = v;
  const ft = tape.frame_t; let lastKey = ''; let lastWire = -1;
  const tick = () => {
    const i = Math.max(0, Math.min(ft.length - 1, Math.floor(v.currentTime * tape.fps)));
    const t = ft.length ? ft[i] : 0;
    const si = Math.max(0, upto(tape.snaps, t)); const wi = upto(tape.wire, t); const ei = upto(tape.events, t);
    const key = si + '|' + wi + '|' + ei + '|' + t.toFixed(1);
    if (key !== lastKey && tape.snaps.length) {
      if (wi < lastWire) { $('wire').innerHTML = ''; wireSeen = 0; }   // scrubbed backwards
      lastKey = key; lastWire = wi;
      last = Object.assign({}, tape.snaps[si], { t: t, wire: tape.wire.slice(Math.max(0, wi - 79), wi + 1),
                                                 events: tape.events.slice(Math.max(0, ei - 39), ei + 1) });
      render(last);
      $('mode').textContent = 'REPLAY';
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
  return true;
}

startReplay().then((replaying) => {
  if (replaying) return;
  const img = $('video');
  img.addEventListener('load', () => { $('novideo').hidden = true; });
  img.addEventListener('error', () => { $('novideo').hidden = false; });
  img.src = '/stream.mjpg';
  connect();
});
