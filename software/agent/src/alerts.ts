/** Speaks first when it matters, and only then.  Watches the backend's state stream; critical
 *  alerts go out after a short coalescing window (with a camera still when the bench stopped on
 *  its own), warnings are batched longer, a finished run gets one summary - merged into the same
 *  message when they land together.  A stop that a person asked for is not announced to that
 *  person (their chat reply already says so) and is never called "the bench stopped itself".
 *  Every notification is recorded on the alert so no one is told twice, and the frontend shows who
 *  was told.  State events arrive several times a second, so handling is serialised and every alert
 *  id is claimed the moment it is seen. */
import { attachment } from "spectrum-ts";
import { backend, type Alert, type NotifyKind, type Person, type State } from "./backend.js";
import { CONFIG } from "./config.js";
import { summarize, stepWords, doseWords } from "./brain.js";
import { clearAll, remember, type SpaceMemo } from "./memory.js";

export type Sender = {
  /** resolve a destination space for a person (by id/phone) or a memo; returns a send function */
  reach(target: { personId?: string; memo?: SpaceMemo }): Promise<null | { send(content: unknown): Promise<void>; memo: SpaceMemo; channel: string }>;
};

const REQUESTED_BY = /requested by (\S+)/i;
export const requestedBy = (text: string): string | null => REQUESTED_BY.exec(text)?.[1]?.replace(/[.,;:]$/, "") ?? null;

export class AlertWatcher {
  private pendingWarn = new Map<string, Alert>();
  private pendingCrit = new Map<string, Alert>();
  private pendingSummary: { text: string; exclude: string[] } | null = null;
  private claimed = new Set<string>();          // alert ids sent or in flight by this process
  private warnTimer: NodeJS.Timeout | null = null;
  private critTimer: NodeJS.Timeout | null = null;
  private lastOutcome: string | null = null;
  private lastRunId: string | null = null;
  private latest: State | null = null;
  private busy = false;
  private stop: (() => void) | null = null;

  constructor(private sender: Sender) {}

  start(): void {
    this.stop = backend.watch((s) => this.enqueue(s),
      (e) => console.warn("[alerts] stream error, will retry", (e as { message?: string })?.message ?? ""));
    console.log("[alerts] watching", CONFIG.backendUrl);
  }

  close(): void {
    this.stop?.();
    if (this.warnTimer) clearTimeout(this.warnTimer);
    if (this.critTimer) clearTimeout(this.critTimer);
  }

  /** one state at a time; intermediate states are skipped, only the newest is handled */
  private enqueue(s: State): void {
    this.latest = s;
    if (this.busy) return;
    this.busy = true;
    void (async () => {
      while (this.latest) {
        const st = this.latest;
        this.latest = null;
        try { await this.onState(st); } catch (e) { console.error("[alerts]", e); }
      }
      this.busy = false;
    })();
  }

  private async recipients(kind: NotifyKind, exclude: string[] = []): Promise<string[]> {
    const people = await backend.people().catch(() => ({}));
    const subs = Object.values(people).filter((p) => wantsNotice(p, kind)).map((p) => p.id);
    return [...new Set([...CONFIG.operatorPhones, ...subs])].filter((id) => !exclude.includes(id));
  }

  private async onState(s: State): Promise<void> {
    for (const a of s.alerts) {
      if (a.resolved || this.claimed.has(a.id) || a.notified.some((n) => n.startsWith("agent:"))) continue;
      if (a.severity === "info") continue;
      this.claimed.add(a.id);
      if (a.severity === "critical") {
        this.pendingCrit.set(a.id, a);
        if (!this.critTimer) this.critTimer = setTimeout(() => { this.critTimer = null; void this.flushCritical(s); }, CONFIG.criticalBatchMs);
      } else {
        this.pendingWarn.set(a.id, a);
        if (!this.warnTimer) this.warnTimer = setTimeout(() => { this.warnTimer = null; void this.flushWarnings(s); }, CONFIG.warningBatchMs);
      }
    }
    const r = s.run;
    if (r && (r.run_id !== this.lastRunId || r.outcome !== this.lastOutcome)) {
      const was = this.lastOutcome;
      this.lastRunId = r.run_id; this.lastOutcome = r.outcome;
      if (r.outcome === "running" && was !== "running") {      // a new run: every chat starts fresh
        const n = clearAll(); if (n) console.log(`[alerts] new run ${r.run_id}: cleared ${n} chat log(s)`);
      }
      if (was === "running" && (r.outcome === "complete" || r.outcome === "SAFE_STOP")) {
        const who = r.faults.map(requestedBy).find(Boolean) ?? null;
        const summary = { text: runSummary(s), exclude: who ? [who] : [] };
        if (this.critTimer) this.pendingSummary = summary;              // merge into the alert message
        else await this.broadcast(summary.text, r.outcome === "SAFE_STOP", `run:${r.run_id}:${r.outcome}`, null, summary.exclude, r.outcome === "SAFE_STOP" ? "critical" : "run_complete");
        // the task is finished: once the summary is out, every chat log is cleared (the run itself stays on the backend)
        setTimeout(() => { const n = clearAll(); if (n) console.log(`[alerts] run ${r.run_id} ${r.outcome}: cleared ${n} chat log(s)`); },
                   CONFIG.warningBatchMs + 15000);
      }
    }
  }

  private async flushWarnings(s: State): Promise<void> {
    const list = [...this.pendingWarn.values()];
    this.pendingWarn.clear();
    if (!list.length) return;
    const lines = list.map(describe);
    const text = `Nothing urgent, just so you know:\n${lines.join("\n")}`;
    const sent = await this.broadcast(text, false, `alert:${list.map((a) => a.id).join(",")}`, null, [], "warning");
    await this.markAll(list, sent);
    void s;
  }

  private async flushCritical(s: State): Promise<void> {
    const list = [...this.pendingCrit.values()];
    this.pendingCrit.clear();
    const summary = this.pendingSummary;
    this.pendingSummary = null;
    if (!list.length && !summary) return;
    const requesters = [...new Set(list.map((a) => requestedBy(a.message)).filter((x): x is string => !!x))];
    const unexpected = list.filter((a) => !requestedBy(a.message));
    let text: string;
    let image: Buffer | null = null;
    if (unexpected.length) {
      text = `Heads up - the bench stopped itself.\n${unexpected.map(describe).join("\n")}`
        + (s.health.spill_detected ? `\nThat is 12% peroxide: goggles and gloves before you wipe it.` : "");
      image = await backend.snapshot("overview").catch(() => null);
    } else if (list.length) {
      const a = list[0];
      const where = s.run ? stepWords(s.run) : "";
      text = `Stopped${where ? ` while ${where}` : ""} - the arms are holding what they held, grippers closed.`;
      void a;
    } else {
      text = "";
    }
    if (summary) text = text ? `${text}\n${summary.text}` : summary.text;
    const exclude = [...new Set([...requesters, ...(summary?.exclude ?? [])])];
    const sent = await this.broadcast(text, true, `alert:${list.map((a) => a.id).join(",")}`, image, exclude, list.length ? "critical" : "run_complete");
    await this.markAll(list, sent.length ? sent : ["suppressed"]);
  }

  private async markAll(alerts: Alert[], channels: string[]): Promise<void> {
    for (const a of alerts) for (const ch of channels) await backend.markNotified(a.id, `agent:${ch}`).catch(() => {});
  }

  /** returns the channels that were reached */
  async broadcast(text: string, urgent: boolean, tag: string, image: Buffer | null = null, exclude: string[] = [],
                  kind: NotifyKind = "all"): Promise<string[]> {
    const reached: string[] = [];
    if (!text) return reached;
    for (const pid of await this.recipients(kind, exclude)) {
      const dest = await this.sender.reach({ personId: pid }).catch(() => null);
      if (!dest) continue;
      try {
        await dest.send(text);
        if (image) await dest.send(attachment(image, { name: "bench.jpg", mimeType: "image/jpeg" }));
        remember(dest.memo, { role: "assistant", text });
        await backend.recordMessage({ channel: dest.channel, person: pid, text, direction: "outbound", space_id: dest.memo.spaceId }).catch(() => {});
        reached.push(dest.channel);
      } catch (e) {
        console.warn(`[alerts] could not reach ${pid}:`, (e as Error).message);
      }
    }
    if (!reached.length) console.log(`[alerts] nobody to tell for ${tag}${urgent ? " (urgent)" : ""}${exclude.length ? ` (excluded ${exclude.join(",")})` : ""}: ${text.split("\n")[0]}`);
    return reached;
  }
}

/** does this person want this kind of unprompted message right now?  Criticals ignore quiet hours. */
export function wantsNotice(p: Person, kind: NotifyKind, now = new Date()): boolean {
  const on: NotifyKind[] = p.notify_on ?? (p.subscribed || p.role === "operator" ? ["all"] : []);
  if (!(on.includes("all") || on.includes(kind))) return false;
  if (kind !== "critical" && inQuietHours(p.quiet_hours, now)) return false;
  return true;
}

export function inQuietHours(q: Person["quiet_hours"], now = new Date()): boolean {
  if (!q?.start || !q?.end) return false;
  const hm = (() => {
    try {
      const parts = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: q.tz || undefined }).formatToParts(now);
      return `${parts.find((p) => p.type === "hour")?.value}:${parts.find((p) => p.type === "minute")?.value}`;
    } catch { return now.toTimeString().slice(0, 5); }
  })();
  return q.start <= q.end ? hm >= q.start && hm < q.end : hm >= q.start || hm < q.end;   // wraps midnight
}

const describe = (a: Alert) => `${a.message}${a.step ? ` (during ${a.step})` : ""}`;

export function runSummary(s: State): string {
  const r = s.run!;
  if (r.outcome === "complete") {
    const went = doseWords(r);
    const foam = s.chemistry?.foam_h_mm ? ` The foam came up to ${Math.round(s.chemistry.foam_h_mm)} mm.` : "";
    return `All done.${went ? ` ${went[0].toUpperCase()}${went.slice(1)} went in.` : ""}${foam} The notebook is on the dashboard.`;
  }
  const where = stepWords(r);
  const why = r.faults[r.faults.length - 1] ?? "";
  // "stopped by <someone>" is the backend's own wording; the person reading this does not need it
  // repeated back when they are the one who asked.
  const because = why && !/^stopped by/i.test(why) ? ` ${why[0].toUpperCase()}${why.slice(1)}.` : "";
  return `The run stopped safely${where ? ` while ${where}` : ""}. The arms are holding what they held and the grippers are closed.${because}`
    + ` Say reset when you want the bench cleared.`;
}
