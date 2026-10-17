/** Thin HTTP client for the parts of the backend the agent uses outside of MCP tool calls:
 *  the SSE state stream (proactive alerts), alert bookkeeping, shared-context write-back. */
import { EventSource } from "eventsource";
import { CONFIG } from "./config.js";

export type Alert = {
  id: string; ts: string; severity: "info" | "warning" | "critical"; code: string; message: string;
  run_id?: string | null; step?: string | null; data: Record<string, unknown>;
  acknowledged_by?: string | null; resolved: boolean; notified: string[];
};
export type NotifyKind = "critical" | "warning" | "run_complete" | "approvals" | "all";
export type Person = {
  id: string; name?: string; role?: string; channel?: string; preferred_channel?: string; space_id?: string;
  subscribed?: boolean; notify_on?: NotifyKind[]; quiet_hours?: { start: string; end: string; tz?: string } | null;
  notes?: { ts: string; note: string }[]; last_seen?: string;
};
export type Describe = { headline: string; detail: string; needs_human: string | null; last_event_id: number };
export type State = {
  v: string; ts: string; bench_t: number; backend: string; mode: string;
  run: null | { run_id: string; outcome: string; progress: number; plan?: { title: string } | null;
    current_step?: number | null; steps: { name: string; status: string }[];
    doses: Record<string, { target: number; actual: number | null; error: number | null; topups: number } | number>;
    faults: string[]; operator: string; notebook_html?: string | null; recipe?: Record<string, number> | null };
  health: { ok: boolean; spill_detected: boolean; spilled_g: number; arm_settle_overruns: number; open_alerts: number };
  alerts: Alert[];
  pending_approvals: { id: string; summary: string; requested_by: string; status: string }[];
  chemistry?: { foam_h_mm: number; spilled_total_g: number } | null;
  mega: { estop: boolean; fault: string | null };
};

const j = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const r = await fetch(CONFIG.backendUrl + path, {
    ...init, headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${init?.method ?? "GET"} ${path} -> ${r.status} ${await r.text()}`);
  return (await r.json()) as T;
};

export const backend = {
  state: () => j<State>("/api/state"),
  describe: () => j<Describe>("/api/describe"),
  people: () => j<Record<string, Person>>("/api/people"),
  markNotified: (alertId: string, channel: string) =>
    j(`/api/alerts/${alertId}/notified`, { method: "POST", body: JSON.stringify({ channel }) }),
  recordMessage: (m: { channel: string; person: string; text: string; direction: "inbound" | "outbound";
    person_name?: string; space_id?: string }) =>
    j<{ event_id: number }>("/api/messages", { method: "POST", body: JSON.stringify(m) }),
  snapshot: async (camera = "overview"): Promise<Buffer | null> => {
    const r = await fetch(`${CONFIG.backendUrl}/api/snapshot/${camera}.jpg`);
    return r.ok ? Buffer.from(await r.arrayBuffer()) : null;
  },
  /** state snapshots as they change; reconnects on its own */
  watch(onState: (s: State) => void, onError?: (e: unknown) => void): () => void {
    const es = new EventSource(`${CONFIG.backendUrl}/api/stream`);
    es.addEventListener("state", (ev: MessageEvent) => {
      try { onState(JSON.parse(ev.data as string) as State); } catch (e) { onError?.(e); }
    });
    es.onerror = (e) => onError?.(e);
    return () => es.close();
  },
};
