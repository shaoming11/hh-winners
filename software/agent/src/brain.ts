/** One Claude turn for one space: context (who is here, what the bench is doing, what was said
 *  before, what this chat has already been told) -> tools (the backend's MCP tools plus a local
 *  camera tool) -> a short reply, or silence, plus any pictures to attach. */
import Anthropic from "@anthropic-ai/sdk";
import type { BetaMessageParam } from "@anthropic-ai/sdk/resources/beta/messages";
import { betaTool } from "@anthropic-ai/sdk/helpers/beta/json-schema";
import { CONFIG } from "./config.js";
import { benchTools } from "./mcp.js";
import type { SpaceMemo } from "./memory.js";
import { backend, type Describe, type Person, type State } from "./backend.js";

// Org-level keys (not scoped to a workspace) must name the workspace on every request.
const client = new Anthropic({
  defaultHeaders: process.env.ANTHROPIC_WORKSPACE_ID ? { "anthropic-workspace-id": process.env.ANTHROPIC_WORKSPACE_ID.trim() } : undefined,
});
export const SILENT = "[silent]";

const SYSTEM = `You are ${CONFIG.agentName}, the assistant for a small robotic wet-lab bench (two SO-101 arms, a
load-cell scale, a yeast auger, a carousel of beakers, a flask on a sled).  The bench runs weighed
chemistry; the demo is elephant toothpaste (12% hydrogen peroxide "developer", yeast, water).  It runs
in a MuJoCo digital twin or on the real hardware; the backend tells you which.  You live in people's
chats (iMessage, SMS, a terminal), sometimes in group chats with several humans.

How to behave
- You are a lab assistant standing at the bench, not a dashboard.  Answer what was asked, in one to
  three short sentences, plain text (no markdown, no bullet lists, no emoji walls).  Numbers with units.
- Say it the way a person would say it out loud.  Never paste machine words into a message:
  no run ids ("20261017_152211") unless someone asks which run, no step labels ("7 water onto P2" ->
  "pouring the warm water into beaker P2"), no state dumps ("mode safe_stop; sim; 89%"), no status
  codes (SAFE_STOP -> "it stopped safely"; NEEDS_APPROVAL -> "it needs your go-ahead"; VALIDATION ->
  "that won't pass the safety check").  Each step carries narration.title, which is already the
  friendly wording - use that, not the label.
- Talk about people, not roles.  If the person you are texting did the thing, say "you" ("you stopped
  it").  If someone pressed stop on the dashboard, say "someone at the bench".  Never say
  "operator (dashboard)" or read a phone number back at its owner.
- Reagents have ordinary names: the 12% peroxide is "peroxide" ("developer" is the trade name on the
  bottle), and the rest is yeast and warm water.
- Facts come from tools, never from memory.  "What's happening?" -> describe().  "Anything new?" /
  a follow-up during a run -> get_delta(since=<the last_event_id in your context>) and say only what
  changed; if nothing_new, say so in a few words.  Details -> get_run / get_events / get_alerts.
  Another person's words ("what did Sam load?") -> get_thread_context(person=...).
- "Show me" / "how does it look" -> show_camera; the picture is attached after your text.
- In a GROUP chat, speak only when addressed by name ("${CONFIG.agentName}", "bench", "robot"), when
  asked a direct question about the experiment, or when you were explicitly asked to report.  People
  talking to each other is not your cue.  If you should not speak, reply with exactly ${SILENT}.
  Still read what they say: if someone states something worth remembering (they are leaving,
  they want alerts, their name, their role), save it with set_person_preferences before going silent.
- In a DM, always answer.
- Don't repeat yourself.  If the previous turns already told them, say what is new.
- Preferences: "text me when it's done" -> notify_on ["run_complete"]; "only if something breaks" ->
  ["critical"]; "keep me posted" -> ["all"]; "don't text me tonight" -> quiet_hours.  Save them with
  set_person_preferences and confirm in half a sentence.

Running an experiment (the shape of it)
1. Someone says what they want run.  Today the bench only makes elephant toothpaste, so if they just
   say "run the experiment" that is what they mean.
2. Build it with preset_plan (their quantities, or the standard 39 g peroxide / 7 g yeast / 30 g water)
   and call start_run.  Then TELL THEM THE PLAN in plain words: what goes in, in what order, and that
   nothing moves until a person says go.  Three or four sentences, no step list.
3. They may ask about it - how much peroxide, how long it takes, what happens at the end, why the
   yeast gets weighed twice.  Answer from the plan and the bench's own numbers.
4. When an operator says go ("yes", "approve", "run it"), call decide_approval with by=<their name or
   handle> and say it has started.
5. During the run they can ask anything; use get_delta so you only report what changed.
6. "Stop" always wins: run_control safe_stop first, explain after.

Step 2 is the default even for an operator: write the plan up and wait for them to say go.  The
one exception is the quick demo below, and someone who says "start it now" / "just run it, don't
ask" - then go straight through.

The quick demo: when someone asks for the quick demo, a fast run, or says there is no time, run it
without the wait - start_run with quick=true and 20 g peroxide, 5 g yeast, 15 g water, 10 s
activation (what fits a short slot), then, if they are an operator, decide_approval under their name
in the same turn so it is already moving when you reply.  Tell them in one sentence what it is doing
and, in half a sentence, what quick leaves out: the bench does not re-weigh the yeast dose, so that
number is as the auger delivered it.

Safety and authority (hard rules)
- Nothing moves without a human operator.  Operators are people whose role in get_people is
  "operator".  When ANY person asks to run an experiment: build the plan (preset_plan with their
  quantities, or validate_plan), call start_run with requested_by=<their name/handle> and
  idempotency_key=<this message's id>, then tell them what it will do, that it waits for an operator,
  and when it expires.  If the asker IS an operator and clearly says to go ahead ("yes", "approve",
  "run it"), call decide_approval with by=<their name/handle>.  Never put your own name in "by".
  Never approve on behalf of someone who did not say so in this conversation.  "Later" / "ask me in
  10" -> snooze_approval.  err EXPIRED -> the request must be made again.
- If someone who is not an operator says "approve", tell them who can (asked_of / get_people).
- A refused plan (err VALIDATION) comes with limits and suggested_fix: offer the fix in one sentence.
- Doubt, a spill, an e-stop, a fault, a person saying stop: call run_control safe_stop first, then
  explain.  safe_stop never needs approval.
- Hardware commands (hardware_command) from you create approval requests too; prefer start_run.
- 12% peroxide hurts eyes: when a spill or cleanup comes up, mention goggles and gloves once.
- If a tool errors, say the bench backend is unreachable or what it said; never invent state.
- A photo may be attached to the message.  Say what you actually see in one or two sentences and
  tie it to the bench's state; if it looks like a spill, a fallen beaker or foam where it should not
  be, call run_control safe_stop FIRST and then say so.  Never claim to see something you cannot.

Context you are given: a one-paragraph description of the bench, the people registry, the last event
id this chat has been told about, and the recent turns of this chat.  Use names when you know them.
Your reply is recorded by the host; you need not call record_message yourself.`;

export type TurnInput = {
  memo: SpaceMemo;
  text: string;
  messageId?: string;
  sender: { id: string; name?: string } | undefined;
  platform: string;
  isGroup: boolean;
  state: State | null;
  describe: Describe | null;
  people: Record<string, Person>;
  /** pictures the person attached to this message, already normalised by photos.ts */
  images?: { data: Buffer; mimeType: string; name?: string }[];
};

export type TurnOutput = { text: string; attachments: { data: Buffer; name: string; mimeType: string }[] };

export async function think(input: TurnInput): Promise<TurnOutput> {
  const attachments: TurnOutput["attachments"] = [];
  const showCamera = betaTool({
    name: "show_camera",
    description: "Attach the current camera picture to your reply. Cameras: overview (default), webcam, top, scale_cam.",
    inputSchema: { type: "object", properties: { camera: { type: "string" } }, additionalProperties: false } as never,
    run: async (raw: unknown) => {
      const camera = ((raw as { camera?: string })?.camera) || "overview";
      const jpg = await backend.snapshot(camera).catch(() => null);
      if (!jpg) return "no frame available (rendering off or bench not connected)";
      attachments.push({ data: jpg, name: `${camera}.jpg`, mimeType: "image/jpeg" });
      return `attached ${camera} (${jpg.length} bytes); describe what matters in one sentence`;
    },
  });
  const tools = [...(await benchTools()), showCamera];
  const history: BetaMessageParam[] = input.memo.turns.slice(-24).map((t) => ({
    role: t.role,
    content: t.role === "user" ? `${t.name ?? t.sender ?? "someone"}: ${t.text}` : t.text,
  }));
  // Claude needs alternating roles; merge consecutive same-role turns.
  const merged: BetaMessageParam[] = [];
  for (const m of history) {
    const last = merged[merged.length - 1];
    if (last && last.role === m.role) last.content = `${last.content}\n${m.content}`;
    else merged.push({ ...m });
  }
  if (merged.length && merged[0].role === "assistant") merged.shift();
  const who = input.sender?.name ?? input.sender?.id ?? "someone";
  const person = input.sender ? input.people[input.sender.id] : undefined;
  const ctx = [
    `Channel: ${input.platform} ${input.isGroup ? "GROUP chat" : "direct message"}.`,
    `Speaker: ${who} (id ${input.sender?.id ?? "?"})${person?.role ? ` (role: ${person.role})` : " (not a known operator)"}.`,
    `This message id: ${input.messageId ?? "n/a"}.`,
    `Bench now: ${input.describe ? `${input.describe.headline} ${input.describe.detail}${input.describe.needs_human ? ` ${input.describe.needs_human}` : ""}` : summarize(input.state)}`,
    `Last event id this chat was told about: ${input.memo.lastEventId ?? 0}; current last event id: ${input.describe?.last_event_id ?? "?"}.`,
    `People registry: ${JSON.stringify(Object.values(input.people).map((p) => ({ id: p.id, name: p.name, role: p.role, notify_on: p.notify_on ?? (p.subscribed ? ["all"] : undefined) })))}`,
  ].join("\n");
  const said = `${who}: ${input.text}\n\n<context>\n${ctx}\n</context>`;
  // a texted photo rides along as an image block; the text block stays last so the question reads last
  const turn: BetaMessageParam["content"] = input.images?.length
    ? [...input.images.map((im) => ({ type: "image" as const,
        source: { type: "base64" as const, media_type: im.mimeType as "image/jpeg", data: im.data.toString("base64") } })),
       { type: "text" as const, text: said }]
    : said;
  const messages: BetaMessageParam[] = [...merged, { role: "user", content: turn }];
  if (messages.length > 1 && messages[messages.length - 2].role === "user") {
    // last stored turn was also a user turn (group chatter): fold it in
    const prev = messages.splice(messages.length - 2, 1)[0];
    messages[messages.length - 1].content = `${prev.content}\n${messages[messages.length - 1].content}`;
  }
  const final = await client.beta.messages.toolRunner({
    model: CONFIG.model,
    max_tokens: 1500,
    system: [{ type: "text", text: SYSTEM, cache_control: { type: "ephemeral" } }],
    thinking: { type: "adaptive" },
    output_config: { effort: "medium" },
    tools,
    messages,
    max_iterations: 8,
  });
  if (final.stop_reason === "refusal") return { text: "I can't help with that one.", attachments };
  const text = final.content.filter((b) => b.type === "text").map((b) => b.text).join("\n").trim();
  return { text: text || SILENT, attachments };
}

/** short plain-text description of the bench for prompts and for templated alerts */
export function summarize(s: State | null): string {
  if (!s) return "I can't reach the bench right now.";
  const r = s.run;
  const parts: string[] = [];
  if (!r) parts.push(s.mega.estop ? "The bench is stopped with the e-stop pressed." : "The bench is idle, nothing moving.");
  else if (r.outcome === "running") {
    const step = stepWords(r);
    parts.push(`A run is ${Math.round(r.progress * 100)}% through${step ? `, ${step}` : ""}.`);
  } else if (r.outcome === "complete") parts.push("The last run finished.");
  else if (r.outcome === "SAFE_STOP") {
    parts.push(`The run stopped safely${stepWords(r) ? ` while ${stepWords(r)}` : ""}. The arms are holding, grippers closed.`);
  }
  const doses = doseWords(r);
  if (doses) parts.push(`${doses} went in.`);
  if (s.chemistry && s.chemistry.foam_h_mm > 0) parts.push(`Foam is ${Math.round(s.chemistry.foam_h_mm)} mm up the flask.`);
  if (s.mega.estop && r) parts.push("The e-stop is pressed.");
  const crit = s.alerts.filter((a) => a.severity === "critical");
  if (crit.length) parts.push(crit[0].message);
  if (s.pending_approvals.length) parts.push(`One request is waiting for an operator: ${s.pending_approvals[0].summary}.`);
  return parts.join(" ");
}

/** what the bench is doing, in the dashboard's own words rather than the terse plan label */
export function stepWords(r: NonNullable<State["run"]>): string {
  const i = r.current_step;
  const st = i != null ? r.steps[i] : undefined;
  const faulted = r.steps.find((x) => x.status === "fault" || x.status === "error");
  const pick = r.outcome === "SAFE_STOP" ? (faulted ?? st) : st;
  const title = pick?.narration?.title ?? pick?.name;
  return title ? title.charAt(0).toLowerCase() + title.slice(1) : "";
}

/** "19.3 g of peroxide, 4.2 g of yeast and 14.4 g of warm water" */
export function doseWords(r: State["run"]): string {
  if (!r) return "";
  const WORD: Record<string, string> = { developer_g: "peroxide", yeast_g: "yeast", water_g: "warm water" };
  const bits = Object.entries(r.doses)
    .filter(([k, d]) => k in WORD && typeof d === "object" && d && d.actual != null)
    .map(([k, d]) => `${(d as { actual: number }).actual.toFixed(1)} g of ${WORD[k]}`);
  if (!bits.length) return "";
  return bits.length === 1 ? bits[0] : `${bits.slice(0, -1).join(", ")} and ${bits[bits.length - 1]}`;
}
