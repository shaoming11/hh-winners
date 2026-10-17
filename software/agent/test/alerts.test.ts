import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { useTempDataDir, mkState, mkAlert, mkRun, sleep, until } from "./helpers.js";

useTempDataDir();
const { CONFIG } = await import("../src/config.js");
const { backend } = await import("../src/backend.js");
const { memo } = await import("../src/memory.js");
const { AlertWatcher, runSummary } = await import("../src/alerts.js");
import type { State } from "../src/backend.js";
import type { Sender } from "../src/alerts.js";

CONFIG.warningBatchMs = 60;
CONFIG.criticalBatchMs = 10;
CONFIG.operatorPhones = [];

test("runSummary: complete run lists doses and foam", () => {
  const s = mkState({ run: mkRun("complete"), chemistry: { foam_h_mm: 85, spilled_total_g: 0 } });
  const t = runSummary(s);
  assert.match(t, /^Run r1 finished/);
  assert.match(t, /developer 38\.6 g \(-0\.4\)/);
  assert.ok(!t.includes("yeast"), "undosed reagent omitted");
  assert.match(t, /foam 85 mm/);
  assert.match(t, /Notebook/);
});

test("runSummary: SAFE_STOP names the failed step and the fault", () => {
  const s = mkState({ mode: "safe_stop", run: mkRun("SAFE_STOP"), health: { ok: false, spill_detected: true, spilled_g: 3, arm_settle_overruns: 0, open_alerts: 1 } });
  const t = runSummary(s);
  assert.match(t, /safe-stopped during "pour developer"/);
  assert.match(t, /spill detected/);
  assert.match(t, /grippers closed/);
  assert.match(t, /mode safe_stop/);          // tail is brain.summarize()
});

// ---------------------------------------------------------------- AlertWatcher with a fake backend
type Sent = { text?: string; content: unknown };
let push: (s: State) => void = () => {};
let sends: Sent[] = [];
let notified: [string, string][] = [];
let recorded: unknown[] = [];
let closed = false;

const fakeSender: Sender = {
  async reach({ personId }) {
    if (!personId) return null;
    const m = memo("test", personId);
    return { channel: "test", memo: m, send: async (c: unknown) => { sends.push({ text: typeof c === "string" ? c : undefined, content: c }); } };
  },
};

beforeEach(() => {
  sends = []; notified = []; recorded = []; closed = false;
  backend.watch = (onState) => { push = onState; return () => { closed = true; }; };
  backend.people = async () => ({ op: { id: "op", name: "Op", role: "operator" }, bystander: { id: "by", role: "guest" }, fan: { id: "fan", subscribed: true } });
  backend.markNotified = async (id, ch) => { notified.push([id, ch]); return {}; };
  backend.snapshot = async () => Buffer.from("not really a jpeg");
  backend.recordMessage = async (m) => { recorded.push(m); return { event_id: 1 }; };
});

function watcher() { const w = new AlertWatcher(fakeSender); w.start(); return w; }
const texts = () => sends.filter((s) => s.text !== undefined).map((s) => s.text!);

test("alerts: a critical goes out at once, with a still, and is marked notified", async () => {
  const w = watcher();
  push(mkState({ mode: "safe_stop", alerts: [mkAlert()], health: { ok: false, spill_detected: true, spilled_g: 3.2, arm_settle_overruns: 0, open_alerts: 1 } }));
  await until(() => notified.length >= 2);
  // two recipients (operator + subscribed): each gets the text and the image
  assert.equal(texts().length, 2);
  for (const t of texts()) {
    assert.match(t, /bench stopped itself/);
    assert.match(t, /spill of 3\.2 g on the scale/);
    assert.match(t, /during pour developer/);
    assert.match(t, /goggles/);
  }
  const images = sends.filter((s) => s.text === undefined).map((s) => s.content as { type?: string; name?: string });
  assert.equal(images.length, 2);
  assert.deepEqual(notified, [["a1", "agent:test"], ["a1", "agent:test"]]);
  assert.equal(recorded.length, 2);
  assert.equal((recorded[0] as { direction: string }).direction, "outbound");
  w.close();
  assert.equal(closed, true);
});

test("alerts: a warning waits for the batch timer, then one message", async () => {
  const w = watcher();
  push(mkState({ alerts: [mkAlert({ id: "w1", severity: "warning", code: "DOSE_ERROR", message: "developer 1.1 g over", step: null })] }));
  await sleep(20);
  assert.equal(sends.length, 0, "not sent immediately");
  push(mkState({ alerts: [mkAlert({ id: "w1", severity: "warning", code: "DOSE_ERROR", message: "developer 1.1 g over", step: null }),
                           mkAlert({ id: "w2", severity: "warning", code: "SETTLE_OVERRUN", message: "arm took 4 s to settle", step: null })] }));
  await until(() => notified.length >= 4);
  assert.equal(texts().length, 2, "one message per recipient");
  assert.match(texts()[0], /Minor things/);
  assert.match(texts()[0], /developer 1\.1 g over/);
  assert.match(texts()[0], /arm took 4 s to settle/);
  assert.equal(sends.filter((s) => s.text === undefined).length, 0, "no image for warnings");
  assert.deepEqual(new Set(notified.map(([id]) => id)), new Set(["w1", "w2"]));
  w.close();
});

test("alerts: already notified by an agent is not re-sent; resolved ignored", async () => {
  const w = watcher();
  push(mkState({ alerts: [mkAlert({ notified: ["agent:terminal"] }), mkAlert({ id: "a2", resolved: true }),
                           mkAlert({ id: "a3", severity: "info", message: "fyi" })] }));
  await sleep(150);
  assert.equal(sends.length, 0);
  assert.equal(notified.length, 0);
  w.close();
});

test("alerts: running -> complete sends exactly one summary", async () => {
  const w = watcher();
  push(mkState({ mode: "running", run: mkRun("running") }));
  await sleep(30);
  assert.equal(sends.length, 0, "nothing during a normal run");
  push(mkState({ mode: "idle", run: mkRun("complete") }));
  await until(() => texts().length >= 2);
  push(mkState({ mode: "idle", run: mkRun("complete") }));
  push(mkState({ mode: "idle", run: mkRun("complete") }));
  await sleep(50);
  assert.equal(texts().length, 2, "one per recipient, once");
  assert.match(texts()[0], /^Run r1 finished/);
  assert.equal(notified.length, 0, "summaries are not alerts");
  w.close();
});

test("alerts: a run seen first as complete (agent restarted) gets no summary", async () => {
  const w = watcher();
  push(mkState({ run: mkRun("complete", { run_id: "r9" }) }));
  await sleep(30);
  assert.equal(sends.length, 0);
  w.close();
});

test("alerts: a storm of state events sends one critical, not one per event", async () => {
  const w = watcher();
  const st = mkState({ mode: "safe_stop", alerts: [mkAlert()] });
  for (let i = 0; i < 25; i++) push(st);                 // the SSE stream fires several times a second
  await until(() => notified.length >= 2);
  await sleep(60);
  assert.equal(texts().length, 2, "one text per recipient, once");
  w.close();
});

test("alerts: a person subscribed to critical-only gets no warning batch, but does get a critical", async () => {
  backend.people = async () => ({
    op: { id: "op", name: "Op", role: "operator" },
    critOnly: { id: "critOnly", notify_on: ["critical"] },
  });
  const w = watcher();
  push(mkState({ alerts: [mkAlert({ id: "w1", severity: "warning", code: "DOSE_ERROR", message: "developer 1.1 g over", step: null })] }));
  await sleep(90);
  // only the operator (gets everything) heard about the warning; critOnly did not
  assert.equal(texts().length, 1, "one recipient for the warning (the operator)");
  assert.ok(notified.some(([id]) => id === "w1"), "the warning was marked notified");

  sends = []; notified = [];
  push(mkState({ mode: "safe_stop", alerts: [mkAlert({ id: "c1" })],
    health: { ok: false, spill_detected: true, spilled_g: 3.2, arm_settle_overruns: 0, open_alerts: 1 } }));
  await until(() => texts().length >= 2);
  // both the operator and the critical-only subscriber hear about the critical
  assert.equal(texts().length, 2, "critical reaches both recipients");
  w.close();
});

test("alerts: a stop the person asked for is not announced to them, and not called 'stopped itself'", async () => {
  const w = watcher();
  push(mkState({ mode: "running", run: mkRun("running") }));
  await sleep(20);
  const run = { ...mkRun("SAFE_STOP"), faults: ["safe_stop requested by op"] };
  push(mkState({ mode: "safe_stop", run, alerts: [mkAlert({ id: "f1", code: "FAULT", message: "SAFE_STOP: safe_stop requested by op", step: "3 P1 -> funnel" })] }));
  await until(() => notified.length >= 1);
  await sleep(60);
  const t = texts();
  assert.ok(t.every((x) => !/stopped itself/.test(x)), "not the bench's doing");
  assert.ok(t.every((x) => /op stopped the bench/.test(x)), "says who stopped it");
  assert.equal(t.length, 1, "only the other subscriber (fan) hears about it, once, alert + summary merged");
  assert.match(t[0], /safe-stopped during/);
  assert.equal(sends.filter((s) => s.text === undefined).length, 0, "no camera still for a requested stop");
  w.close();
});
