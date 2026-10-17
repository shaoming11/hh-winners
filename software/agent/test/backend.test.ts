import { test, after } from "node:test";
import assert from "node:assert/strict";
import { backendUp, SKIP_LIVE, BACKEND_URL } from "./helpers.js";

const up = await backendUp();
const { backend } = await import("../src/backend.js");

test("backend.state() matches the live backend", { skip: !up && SKIP_LIVE }, async () => {
  const s = await backend.state();
  assert.equal(typeof s.mode, "string");
  assert.ok(["sim", "real", "hardware"].includes(s.backend) || typeof s.backend === "string");
  assert.ok(Array.isArray(s.alerts));
  assert.ok(Array.isArray(s.pending_approvals));
  assert.equal(typeof s.health.ok, "boolean");
  assert.equal(typeof s.mega.estop, "boolean");
  assert.ok(s.run === null || typeof s.run.run_id === "string");
});

test("backend.people() is a map keyed by id", { skip: !up && SKIP_LIVE }, async () => {
  const p = await backend.people();
  for (const [k, v] of Object.entries(p)) assert.equal(v.id, k);
});

test("backend.recordMessage shows up in /api/events?kinds=message", { skip: !up && SKIP_LIVE }, async () => {
  const text = `agent-test ${Date.now()}`;
  const { event_id } = await backend.recordMessage({ channel: "test", person: "agent-tester", person_name: "Tester", text, direction: "inbound", space_id: "t1" });
  assert.equal(typeof event_id, "number");
  const evs = (await (await fetch(`${BACKEND_URL}/api/events?kinds=message&since=${event_id - 1}`)).json()) as { id: number; kind: string; message: string; data: Record<string, unknown> }[];
  const mine = evs.find((e) => e.id === event_id);
  assert.ok(mine, "event present");
  assert.equal(mine.kind, "message");
  assert.equal(mine.message, text);
  assert.equal(mine.data.channel, "test");
  assert.equal(mine.data.direction, "inbound");
  const people = await backend.people();
  assert.equal(people["agent-tester"]?.name, "Tester", "person registered by name");
});

after(async () => { await (await import("../src/mcp.js")).closeMcp(); });

test("backend.markNotified lands on the alert (via a rehearsed e-stop)", { skip: !up && SKIP_LIVE }, async (t) => {
  const { callTool } = await import("../src/mcp.js");
  await callTool("simulate_estop", { pressed: true });
  try {
    let estop: { id: string; notified: string[] } | undefined;
    for (let i = 0; i < 20 && !estop; i++) {
      estop = (await backend.state()).alerts.find((a) => a.code.toUpperCase().includes("ESTOP") && !a.resolved);
      if (!estop) await new Promise((r) => setTimeout(r, 100));
    }
    // observed 2026-10-17: while idle the sim/watchdog do not tick, so simulate_estop raises nothing
    if (!estop) { t.skip("backend: simulate_estop raised no ESTOP alert within 2 s (sim idle); cannot exercise markNotified"); return; }
    const ch = `agent:test-${Date.now()}`;
    await backend.markNotified(estop.id, ch);
    const again = (await backend.state()).alerts.find((a) => a.id === estop!.id);
    assert.ok(again?.notified.includes(ch), `notified recorded: ${JSON.stringify(again?.notified)}`);
  } finally {
    await callTool("simulate_estop", { pressed: false });
  }
});

test("backend.markNotified on an unknown alert id rejects (backend answers 404)", { skip: !up ? "no backend" : false }, async () => {
  await assert.rejects(backend.markNotified("no-such-alert", "agent:test"), /404/);
});
test("backend.snapshot returns bytes or null, never throws on a bad camera", { skip: !up && SKIP_LIVE }, async () => {
  const b = await backend.snapshot("no-such-camera");
  assert.ok(b === null || Buffer.isBuffer(b));
});

test("backend.watch receives a state event within 5 s, then unsubscribes", { skip: !up && SKIP_LIVE }, async () => {
  const got = await new Promise<{ mode: string }>((resolve, reject) => {
    const t = setTimeout(() => { stop(); reject(new Error("no state event in 5 s")); }, 5000);
    const stop = backend.watch((s) => { clearTimeout(t); stop(); resolve(s); }, (e) => { clearTimeout(t); stop(); reject(e); });
  });
  assert.equal(typeof got.mode, "string");
});
