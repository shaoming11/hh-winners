/** Shared bits for the agent tests: a temp data dir (set BEFORE src/config.ts is imported), a
 *  reachable-backend probe for the live tests, and a State factory. */
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { Alert, State } from "../src/backend.js";

export function useTempDataDir(): string {
  const dir = mkdtempSync(join(tmpdir(), "wlb-agent-test-"));
  process.env.DATA_DIR = dir;
  return dir;
}

export const BACKEND_URL = (process.env.BACKEND_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

/** true when a backend answers /api/state; live tests skip (loudly) otherwise */
export async function backendUp(): Promise<boolean> {
  try {
    const r = await fetch(`${BACKEND_URL}/api/state`, { signal: AbortSignal.timeout(3000) });
    return r.ok;
  } catch {
    return false;
  }
}
export const SKIP_LIVE = `no backend at ${BACKEND_URL} (start one and set BACKEND_URL)`;

export function mkAlert(o: Partial<Alert> = {}): Alert {
  return { id: "a1", ts: "2026-10-17T00:00:00Z", severity: "critical", code: "SPILL", message: "spill of 3.2 g on the scale",
    run_id: null, step: "pour developer", data: {}, acknowledged_by: null, resolved: false, notified: [], ...o };
}

export function mkState(o: Partial<State> = {}): State {
  return {
    v: "0.1.0", ts: "2026-10-17T00:00:00Z", bench_t: 1, backend: "sim", mode: "idle", run: null,
    health: { ok: true, spill_detected: false, spilled_g: 0, arm_settle_overruns: 0, open_alerts: 0 },
    alerts: [], pending_approvals: [], chemistry: { foam_h_mm: 0, spilled_total_g: 0 }, mega: { estop: false, fault: null },
    ...o,
  };
}

export function mkRun(outcome: string, o: Partial<NonNullable<State["run"]>> = {}): NonNullable<State["run"]> {
  return {
    run_id: "r1", outcome, progress: outcome === "complete" ? 1 : 0.4, plan: { title: "Elephant toothpaste" },
    current_step: 1,
    steps: [{ name: "home", status: "ok" },
            { name: "2 developer onto P1", status: outcome === "SAFE_STOP" ? "fault" : "running",
              narration: { title: "Weighing out 39 g of hydrogen peroxide" } },
            { name: "7 activate", status: "pending", narration: { title: "Waiting 60 s: yeast activation" } }],
    doses: { developer_g: { target: 39, actual: 38.6, error: -0.4, topups: 1 }, yeast_g: { target: 7, actual: null, error: null, topups: 0 } },
    faults: outcome === "SAFE_STOP" ? ["spill detected"] : [], operator: "sam",
    ...o,
  };
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
export async function until(cond: () => boolean, ms = 2000): Promise<void> {
  const t0 = Date.now();
  while (!cond()) { if (Date.now() - t0 > ms) throw new Error("timed out waiting"); await sleep(10); }
}
