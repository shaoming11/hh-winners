import { test, after } from "node:test";
import assert from "node:assert/strict";
import { backendUp, SKIP_LIVE } from "./helpers.js";

const up = await backendUp();
after(async () => { (await import("../src/mcp.js")).closeMcp(); });

test("mcp: connects, lists bench tools without camera_snapshot", { skip: !up && SKIP_LIVE }, async () => {
  const { mcpClient, benchTools } = await import("../src/mcp.js");
  const c = await mcpClient();
  assert.ok(c, "client");
  const tools = await benchTools();
  const names = tools.map((t) => t.name);
  for (const n of ["get_state", "qa_check", "start_run", "decide_approval"]) assert.ok(names.includes(n), `has ${n}`);
  assert.ok(!names.includes("camera_snapshot"), "camera_snapshot omitted");
  assert.ok(names.length > 10, `got ${names.length} tools`);
  // every tool has a runnable body
  for (const t of tools) assert.equal(typeof (t as { run?: unknown }).run, "function", `${t.name} runnable`);
});

test("mcp: get_state summary returns JSON with mode", { skip: !up && SKIP_LIVE }, async () => {
  const { callTool } = await import("../src/mcp.js");
  const out = await callTool("get_state", { detail: "summary" });
  assert.ok(!out.startsWith("ERROR"), out.slice(0, 200));
  const s = JSON.parse(out);
  assert.equal(typeof s.mode, "string");
  assert.ok(Array.isArray(s.alerts));
});

test("mcp: preset_plan returns steps", { skip: !up && SKIP_LIVE }, async () => {
  const { callTool } = await import("../src/mcp.js");
  const out = JSON.parse(await callTool("preset_plan", { developer_g: 20 }));
  const steps = out.steps ?? out.plan?.steps;
  assert.ok(Array.isArray(steps) && steps.length > 0, `steps: ${JSON.stringify(out).slice(0, 200)}`);
  assert.ok(JSON.stringify(out).includes("20"), "quantity echoed");
});

test("mcp: decide_approval by the agent is refused", { skip: !up && SKIP_LIVE }, async () => {
  const { callTool } = await import("../src/mcp.js");
  const out = await callTool("decide_approval", { request_id: "x", decision: "approve", by: "agent" });
  const body = out.startsWith("ERROR") ? null : JSON.parse(out);
  assert.ok(body === null || body.ok === false, `refused: ${out.slice(0, 200)}`);
  if (body) assert.match(body.message ?? body.err ?? "", /human|REJECTED/i);
});

test("mcp: trailing-slash endpoint is the one that answers", { skip: !up && SKIP_LIVE }, async () => {
  const { BACKEND_URL } = await import("./helpers.js");
  const init = { method: "POST", redirect: "manual" as const, headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "t", version: "0" } } }) };
  const withSlash = await fetch(`${BACKEND_URL}/mcp/`, init);
  const noSlash = await fetch(`${BACKEND_URL}/mcp`, init);
  assert.equal(withSlash.status, 200);
  assert.ok(noSlash.status === 200 || (noSlash.status >= 300 && noSlash.status < 400), `/mcp -> ${noSlash.status}`);
});
