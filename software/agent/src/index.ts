/** Wet Lab Bench on Photon: the message loop.  Every inbound message is written to the shared log,
 *  remembered per space, and answered (or deliberately not) by brain.ts with the backend's MCP tools.
 *  alerts.ts speaks first when the bench needs a human. */
import { Spectrum, attachment, type Message, type Space } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
import { terminal } from "spectrum-ts/providers/terminal";
import { CONFIG } from "./config.js";
import { backend } from "./backend.js";
import { memo, remember, markSeen, allSpaces, type SpaceMemo } from "./memory.js";
import { think, SILENT } from "./brain.js";
import { callTool, mcpClient, closeMcp } from "./mcp.js";
import { AlertWatcher, type Sender } from "./alerts.js";

type AnySpace = Space & { id: string; type?: "dm" | "group"; phone?: string };

async function main() {
  const providers: unknown[] = [];
  if (CONFIG.providers.includes("imessage")) {
    if (!CONFIG.projectId) console.warn("imessage requested but SPECTRUM_PROJECT_ID is unset - skipping");
    else providers.push(imessage.config());
  }
  if (CONFIG.providers.includes("terminal")) {
    providers.push(terminal.config({ commands: [
      { name: "/state", description: "what is the bench doing" },
      { name: "/qa", description: "health check" },
      { name: "/operator", description: "make me an operator (terminal only)" },
    ] }));
  }
  const app = await Spectrum({
    ...(CONFIG.projectId ? { projectId: CONFIG.projectId, projectSecret: CONFIG.projectSecret } : {}),
    providers: providers as never,
  } as never);

  // backend reachable?  register the configured operators in the shared people registry
  try {
    await mcpClient();
    for (const phone of CONFIG.operatorPhones) {
      await callTool("update_person", { person: phone, role: "operator", subscribed: true, channel: "imessage" });
    }
    console.log(`[agent] backend ok at ${CONFIG.backendUrl}; operators: ${CONFIG.operatorPhones.join(", ") || "(none configured)"}`);
  } catch (e) {
    console.error(`[agent] backend not reachable at ${CONFIG.backendUrl}: ${(e as Error).message}. Replies will say so.`);
  }

  // how alerts find people: a DM space we already know, else create one on iMessage
  const sender: Sender = {
    async reach({ personId, memo: m }) {
      if (m) return { send: async (c) => { await (await openSpace(m)).send(c as never); }, memo: m, channel: m.platform };
      if (!personId) return null;
      const known = allSpaces().find((s) => !s.isGroup && (s.spaceId === personId || Object.keys(s.participants).includes(personId)));
      if (known) return { send: async (c) => { await (await openSpace(known)).send(c as never); }, memo: known, channel: known.platform };
      if (CONFIG.providers.includes("imessage") && CONFIG.projectId && personId.startsWith("+")) {
        const im = imessage(app as never);
        const user = await im.user(personId);
        const dm = (await im.space.create(user)) as AnySpace;
        const mm = memo("imessage", dm.id, false);
        mm.participants[personId] = mm.participants[personId] ?? personId;
        return { send: async (c) => { await dm.send(c as never); }, memo: mm, channel: "imessage" };
      }
      if (CONFIG.providers.includes("terminal")) {
        const t = terminal(app as never);
        const sp = (await t.space.get("alerts")) as AnySpace;
        return { send: async (c) => { await sp.send(c as never); }, memo: memo("terminal", sp.id ?? "alerts", false), channel: "terminal" };
      }
      return null;
    },
  };
  async function openSpace(m: SpaceMemo): Promise<AnySpace> {
    if (m.platform === "imessage") return (await imessage(app as never).space.get(m.spaceId)) as AnySpace;
    return (await terminal(app as never).space.get(m.spaceId)) as AnySpace;
  }

  const seenLines = new Set<string>();
  const watcher = new AlertWatcher(sender);
  watcher.start();
  process.on("SIGINT", () => { watcher.close(); void closeMcp().finally(() => process.exit(0)); });
  console.log(`[agent] ${CONFIG.agentName} online on ${CONFIG.providers.join(", ")}`);

  for await (const [space, message] of app.messages as AsyncIterable<[AnySpace, Message]>) {
    if (message.direction === "outbound") continue;
    if (message.content.type !== "text") continue;
    const text = message.content.text.trim();
    if (!text) continue;
    const platform = space.__platform;
    const isGroup = space.type === "group";
    const senderId = message.sender?.id ?? "unknown";
    const senderName = (message.sender as { name?: string } | undefined)?.name;
    const m = memo(platform, space.id, isGroup);
    if (space.phone && !seenLines.has(space.phone)) { seenLines.add(space.phone); console.log(`[agent] our ${platform} line: ${space.phone}`); }
    console.log(`[agent] <- ${platform} ${isGroup ? "group" : "dm"} ${senderName ?? senderId}: ${text.slice(0, 80)}`);
    remember(m, { role: "user", text, sender: senderId, name: senderName });
    backend.recordMessage({ channel: platform, person: senderId, text, direction: "inbound", person_name: senderName, space_id: space.id }).catch(() => {});

    // bootstrap: "operator <code>" from any channel promotes the sender (code from .env)
    const boot = /^operator\s+(\S+)$/i.exec(text);
    if (boot && CONFIG.bootstrapCode && boot[1] === CONFIG.bootstrapCode) {
      await callTool("update_person", { person: senderId, role: "operator", subscribed: true, channel: platform, name: senderName }).catch(() => {});
      const r = `Got it, ${senderName ?? senderId} is an operator now: you can approve runs and you'll get alerts here.`;
      await message.reply(r); remember(m, { role: "assistant", text: r });
      continue;
    }
    // terminal-only conveniences for local testing
    if (platform === "terminal" && text === "/operator") {
      await callTool("update_person", { person: senderId, role: "operator", subscribed: true, channel: "terminal", name: senderName ?? "terminal user" }).catch(() => {});
      await space.send(`ok, ${senderId} is an operator now`);
      continue;
    }
    const prompt = text === "/state" ? "what is the bench doing right now?" : text === "/qa" ? "run a health check and tell me if anything needs attention" : text;

    await space.responding(async () => {
      let reply: string;
      let pics: { data: Buffer; name: string; mimeType: string }[] = [];
      let lastEvent = 0;
      try {
        const [state, people, desc] = await Promise.all([backend.state().catch(() => null), backend.people().catch(() => ({})),
          backend.describe().catch(() => null)]);
        lastEvent = desc?.last_event_id ?? 0;
        const out = await think({ memo: m, text: prompt, messageId: message.id, sender: message.sender ? { id: senderId, name: senderName } : undefined,
          platform, isGroup, state, describe: desc, people });
        reply = out.text; pics = out.attachments;
      } catch (e) {
        console.error("[agent] think failed:", e);
        const s = await backend.state().catch(() => null);
        reply = s ? `I can't think straight right now (model error), but the bench is: ${s.mode}${s.run ? `, run ${s.run.run_id} ${s.run.outcome}` : ""}.`
                  : `The bench backend is not answering, so I can't tell you anything reliable. If something is wrong at the bench, hit the e-stop.`;
      }
      if (lastEvent) markSeen(m, lastEvent);
      if (reply === SILENT) { console.log(`[agent] (silent in ${platform} ${isGroup ? "group" : "dm"})`); return; }
      await message.reply(reply);
      for (const pic of pics) await space.send(attachment(pic.data, { name: pic.name, mimeType: pic.mimeType }) as never).catch((e: Error) => console.warn("[agent] attachment failed:", e.message));
      remember(m, { role: "assistant", text: reply });
      backend.recordMessage({ channel: platform, person: senderId, text: reply, direction: "outbound", space_id: space.id }).catch(() => {});
    });
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
