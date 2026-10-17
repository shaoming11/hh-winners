import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { useTempDataDir } from "./helpers.js";

const dir = useTempDataDir();                     // before config.ts is loaded
const { CONFIG } = await import("../src/config.js");
const { memo, remember, allSpaces, spaceKey } = await import("../src/memory.js");

test("memory: DATA_DIR override is honoured", () => {
  assert.equal(CONFIG.dataDir, dir);
  assert.ok(existsSync(join(dir, "spaces")));
});

test("memory: memo + remember persist to disk", () => {
  const m = memo("terminal", "room 1", true);
  assert.equal(m.key, spaceKey("terminal", "room 1"));
  assert.equal(m.isGroup, true);
  remember(m, { role: "user", text: "hello bench", sender: "+1555", name: "Sam" });
  remember(m, { role: "assistant", text: "hi Sam" });
  const p = join(dir, "spaces", m.key + ".json");
  assert.ok(existsSync(p), "file written");
  const disk = JSON.parse(readFileSync(p, "utf8"));
  assert.equal(disk.turns.length, 2);
  assert.equal(disk.participants["+1555"], "Sam");
  assert.equal(disk.turns[0].text, "hello bench");
  assert.ok(disk.turns[0].ts);
  // same object comes back from the cache; isGroup sticks even when asked as a dm
  assert.strictEqual(memo("terminal", "room 1"), m);
  assert.equal(m.isGroup, true);
});

test("memory: reload from disk in a fresh process", () => {
  const m = memo("imessage", "+15550001");
  remember(m, { role: "user", text: "remember me", sender: "+15550001", name: "Ana" });
  const script = `const { memo } = await import("./src/memory.ts"); const m = memo("imessage", "+15550001"); console.log(JSON.stringify({ n: m.turns.length, name: m.participants["+15550001"], text: m.turns[0].text }));`;
  const out = execFileSync(process.execPath, ["--import", "tsx", "--input-type=module", "-e", script],
    { cwd: new URL("..", import.meta.url).pathname, env: { ...process.env, DATA_DIR: dir }, encoding: "utf8" });
  const got = JSON.parse(out.trim().split("\n").pop()!);
  assert.deepEqual(got, { n: 1, name: "Ana", text: "remember me" });
});

test("memory: capped at 40 turns, oldest dropped", () => {
  const m = memo("terminal", "busy");
  for (let i = 0; i < 45; i++) remember(m, { role: i % 2 ? "assistant" : "user", text: `t${i}` });
  assert.equal(m.turns.length, 40);
  assert.equal(m.turns[0].text, "t5");
  assert.equal(m.turns[39].text, "t44");
  const disk = JSON.parse(readFileSync(join(dir, "spaces", m.key + ".json"), "utf8"));
  assert.equal(disk.turns.length, 40);
});

test("memory: allSpaces lists every persisted space", () => {
  const keys = allSpaces().map((s) => s.key).sort();
  assert.deepEqual(keys, [spaceKey("imessage", "+15550001"), spaceKey("terminal", "busy"), spaceKey("terminal", "room 1")].sort());
  const room = allSpaces().find((s) => s.spaceId === "room 1")!;
  assert.equal(room.platform, "terminal");
  assert.equal(room.isGroup, true);
});
