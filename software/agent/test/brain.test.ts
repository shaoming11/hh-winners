import { test } from "node:test";
import { after } from "node:test";
import { closeMcp } from "../src/mcp.js";
import assert from "node:assert/strict";
import { useTempDataDir, mkState, mkRun, mkAlert, backendUp } from "./helpers.js";

useTempDataDir();
const { summarize, think, SILENT } = await import("../src/brain.js");
const { memo } = await import("../src/memory.js");

test("summarize: null state", () => {
  assert.equal(summarize(null), "backend unreachable");
});

test("summarize: running state with doses, alerts and approvals", () => {
  const s = mkState({ mode: "running", run: mkRun("running"), chemistry: { foam_h_mm: 12.5, spilled_total_g: 0 },
    alerts: [mkAlert({ severity: "warning", code: "DOSE_ERROR" })], pending_approvals: [{ id: "p1", summary: "run 20 g developer", requested_by: "sam", status: "pending" }],
    mega: { estop: true, fault: null } });
  const t = summarize(s);
  assert.match(t, /^mode running; sim; run r1 "Elephant toothpaste" running, 40%, at "pour developer"/);
  assert.match(t, /developer 38\.6 g \(target 39\)/);
  assert.ok(!t.includes("yeast"), "undosed omitted");
  assert.ok(!t.includes("water_g"), "scalar doses omitted");
  assert.match(t, /foam 12\.5 mm/);
  assert.match(t, /E-STOP PRESSED/);
  assert.match(t, /open alerts: warning DOSE_ERROR/);
  assert.match(t, /waiting for approval: run 20 g developer/);
});

test("summarize: idle state is short", () => {
  assert.equal(summarize(mkState()), "mode idle; sim");
});

const hasKey = !!(process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_AUTH_TOKEN);
const up = await backendUp();
test("think: one real Claude turn against the live backend", { skip: !hasKey ? "no ANTHROPIC_API_KEY in env" : !up ? "no backend" : false }, async () => {
  const m = memo("test", "dm-think");
  const { backend: be } = await import("../src/backend.js");
  const [state, desc] = await Promise.all([be.state(), be.describe().catch(() => null)]);
  const out = await think({ memo: m, text: "what is the bench doing right now?", sender: { id: "+15550002", name: "Tester" },
    platform: "test", isGroup: false, state, describe: desc, people: {} });
  assert.ok(out.text && out.text !== SILENT, "a DM gets an answer");
  assert.match(out.text, /sim|idle|run|bench/i);
});

test("think: 'show me the bench' attaches a camera picture", { skip: !hasKey ? "no ANTHROPIC_API_KEY in env" : !up ? "no backend" : false }, async (t) => {
  const m = memo("test", "dm-think-camera");
  const { backend: be } = await import("../src/backend.js");
  const [state, desc] = await Promise.all([be.state(), be.describe().catch(() => null)]);
  // the snapshot route 404s when the backend was started with rendering off; skip rather than fail in that case
  const frame = await be.snapshot("overview").catch(() => null);
  if (!frame) { t.skip("backend: /api/snapshot 404s (rendering off); restart it with WLB_RENDER=1 for this test"); return; }
  const out = await think({ memo: m, text: "show me the bench", sender: { id: "+15550003", name: "Tester" },
    platform: "test", isGroup: false, state, describe: desc, people: {} });
  assert.ok(out.attachments.length >= 1, "show me the bench attaches a picture");
  assert.ok(out.attachments[0].data.length > 0);
});

after(async () => { await closeMcp(); });
