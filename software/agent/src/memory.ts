/** What the agent remembers on its own disk: the conversation in each space (so a reply has
 *  context across hours and reconnects) and the handle of each space it has seen (so it can
 *  speak first).  Who people ARE lives in the backend's people registry, shared with the frontend. */
import { mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { CONFIG } from "./config.js";

export type Turn = { role: "user" | "assistant"; text: string; sender?: string; name?: string; ts: string };
export type SpaceMemo = {
  key: string; platform: string; spaceId: string; isGroup: boolean;
  participants: Record<string, string>;   // sender id -> display name if known
  turns: Turn[]; lastActive: string; summary?: string;
  lastEventId?: number;   // backend event id the chat has been brought up to date with
};

const DIR = join(CONFIG.dataDir, "spaces");
mkdirSync(DIR, { recursive: true });
const MAX_TURNS = 40;
const cache = new Map<string, SpaceMemo>();

export const spaceKey = (platform: string, spaceId: string) => `${platform}__${spaceId.replace(/[^A-Za-z0-9_+@.-]/g, "_")}`;

export function memo(platform: string, spaceId: string, isGroup = false): SpaceMemo {
  const key = spaceKey(platform, spaceId);
  let m = cache.get(key);
  if (!m) {
    const p = join(DIR, key + ".json");
    m = existsSync(p)
      ? (JSON.parse(readFileSync(p, "utf8")) as SpaceMemo)
      : { key, platform, spaceId, isGroup, participants: {}, turns: [], lastActive: new Date().toISOString() };
    cache.set(key, m);
  }
  m.isGroup = m.isGroup || isGroup;
  return m;
}

export function remember(m: SpaceMemo, t: Omit<Turn, "ts">): void {
  m.turns.push({ ...t, ts: new Date().toISOString() });
  if (m.turns.length > MAX_TURNS) m.turns.splice(0, m.turns.length - MAX_TURNS);
  if (t.sender && t.name) m.participants[t.sender] = t.name;
  m.lastActive = new Date().toISOString();
  writeFileSync(join(DIR, m.key + ".json"), JSON.stringify(m, null, 1));
}

export function markSeen(m: SpaceMemo, eventId: number): void {
  if (eventId > (m.lastEventId ?? 0)) { m.lastEventId = eventId; writeFileSync(join(DIR, m.key + ".json"), JSON.stringify(m, null, 1)); }
}

export function allSpaces(): SpaceMemo[] {
  return readdirSync(DIR).filter((f) => f.endsWith(".json"))
    .map((f) => memo(...(f.replace(/\.json$/, "").split("__") as [string, string])));
}
