import { test } from "node:test";
import assert from "node:assert/strict";
import { wantsNotice, inQuietHours } from "../src/alerts.js";
import type { Person } from "../src/backend.js";

const op: Person = { id: "op", name: "Op", role: "operator" };
const fan: Person = { id: "fan", subscribed: true };
const quietOnly: Person = { id: "qo", notify_on: ["run_complete"] };

// a Tuesday, well clear of any quiet-hours window used below
const DAY = new Date("2026-10-13T15:00:00.000Z");

test("wantsNotice: operator default (no notify_on, no subscribed) gets everything", () => {
  assert.equal(wantsNotice(op, "critical", DAY), true);
  assert.equal(wantsNotice(op, "warning", DAY), true);
  assert.equal(wantsNotice(op, "run_complete", DAY), true);
  assert.equal(wantsNotice(op, "approvals", DAY), true);
});

test("wantsNotice: legacy subscribed:true behaves like notify_on all", () => {
  assert.equal(wantsNotice(fan, "critical", DAY), true);
  assert.equal(wantsNotice(fan, "warning", DAY), true);
});

test("wantsNotice: a person with notify_on restricted to run_complete does not get a warning", () => {
  assert.equal(wantsNotice(quietOnly, "warning", DAY), false);
  assert.equal(wantsNotice(quietOnly, "run_complete", DAY), true);
  assert.equal(wantsNotice(quietOnly, "critical", DAY), false, "critical is not in notify_on at all");
});

test("wantsNotice: a person with no role, no subscribed and no notify_on gets nothing", () => {
  const nobody: Person = { id: "n" };
  assert.equal(wantsNotice(nobody, "critical", DAY), false);
  assert.equal(wantsNotice(nobody, "warning", DAY), false);
});

test("wantsNotice: quiet hours suppress a warning but never a critical", () => {
  // 02:00 America/New_York is inside a 23:00-08:00 quiet window
  const nightUtc = new Date("2026-10-13T06:00:00.000Z");   // 02:00 America/New_York (EDT, UTC-4)
  const p: Person = { id: "p", notify_on: ["all"], quiet_hours: { start: "23:00", end: "08:00", tz: "America/New_York" } };
  assert.equal(wantsNotice(p, "warning", nightUtc), false, "quiet hours suppress a warning");
  assert.equal(wantsNotice(p, "critical", nightUtc), true, "criticals ignore quiet hours");
  assert.equal(wantsNotice(p, "warning", DAY), true, "daytime is outside the quiet window");
});

test("inQuietHours: wrap-around midnight window, America/New_York, at the edges", () => {
  const q = { start: "23:00", end: "08:00", tz: "America/New_York" };
  // 22:59 America/New_York -> just before the window opens
  assert.equal(inQuietHours(q, new Date("2026-10-14T02:59:00.000Z")), false);
  // 23:00 America/New_York -> window opens (inclusive start)
  assert.equal(inQuietHours(q, new Date("2026-10-14T03:00:00.000Z")), true);
  // 03:30 America/New_York (well past midnight, still inside the wrapped window)
  assert.equal(inQuietHours(q, new Date("2026-10-14T07:30:00.000Z")), true);
  // 08:00 America/New_York -> window closes (exclusive end)
  assert.equal(inQuietHours(q, new Date("2026-10-14T12:00:00.000Z")), false);
  // 12:00 America/New_York -> broad daylight, well outside the window
  assert.equal(inQuietHours(q, new Date("2026-10-14T16:00:00.000Z")), false);
});

test("inQuietHours: a non-wrapping window (start < end) still works", () => {
  const q = { start: "09:00", end: "17:00", tz: "America/New_York" };
  assert.equal(inQuietHours(q, new Date("2026-10-13T15:00:00.000Z")), true);   // 11:00 EDT
  assert.equal(inQuietHours(q, new Date("2026-10-13T06:00:00.000Z")), false); // 02:00 EDT
});

test("inQuietHours: missing start/end, or no quiet_hours at all, is never quiet", () => {
  assert.equal(inQuietHours(undefined, DAY), false);
  assert.equal(inQuietHours(null as unknown as undefined, DAY), false);
  assert.equal(inQuietHours({ start: "23:00" } as unknown as { start: string; end: string }, DAY), false);
});
