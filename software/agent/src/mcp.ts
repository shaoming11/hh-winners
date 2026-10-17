/** The backend's MCP tools, exposed to Claude through the SDK tool runner.  Tool schemas come
 *  from the server at startup, so a new backend tool is available to the agent without a deploy. */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { betaTool } from "@anthropic-ai/sdk/helpers/beta/json-schema";
import { CONFIG } from "./config.js";

let client: Client | null = null;

/** per-call ceiling; a dead session hangs rather than failing, so every call needs one */
const TOOL_TIMEOUT_MS = 20_000;

/** The SDK's own `timeout` option does not save us: when the backend goes away the call's promise
 *  simply never settles, and node then exits silently because nothing is left holding the loop open.
 *  An explicit timer both bounds the call and keeps the process alive long enough to reconnect. */
async function withTimeout<T>(p: Promise<T>, ms: number, what: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      p,
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error(`${what} timed out after ${ms} ms`)), ms); }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function mcpClient(): Promise<Client> {
  if (client) return client;
  const c = new Client({ name: "wet-lab-bench-agent", version: "0.1.0" });
  await c.connect(new StreamableHTTPClientTransport(new URL(CONFIG.backendUrl + "/mcp/")));
  client = c;
  return c;
}

/** drop the connection (shutdown, tests); the next mcpClient() reconnects */
export async function closeMcp(): Promise<void> {
  const c = client;
  client = null;
  await c?.close().catch(() => {});
}

export async function callTool(name: string, args: Record<string, unknown>): Promise<string> {
  // Restarting the backend kills the MCP session, and the cached client never notices: every later
  // call would fail and the agent would look brain-dead until someone restarted it too.  A thrown
  // error here is a transport/session failure (a tool that fails answers with isError instead, see
  // below), so the recovery is to drop the client and reconnect once.  Mutating tools are safe to
  // retry this way: a call that threw at the transport did not reach the bench, and start_run is
  // idempotency-keyed on the chat message id.
  for (let attempt = 0; ; attempt++) {
    const c = await mcpClient();
    try {
      // A session killed by a backend restart does not error, it HANGS: without this timeout the
      // agent waits forever on the first call after a bounce.  20 s is well past the slowest tool
      // (a camera render) and well inside a texting-latency budget.
      const res = await withTimeout(c.callTool({ name, arguments: args }, undefined, { timeout: TOOL_TIMEOUT_MS }),
                                    TOOL_TIMEOUT_MS, `mcp ${name}`);
      const parts = (res.content as { type: string; text?: string; mimeType?: string }[]) ?? [];
      const text = parts.map((p) => (p.type === "text" ? p.text : p.type === "image" ? "[image]" : `[${p.type}]`)).join("\n");
      if ((res as { isError?: boolean }).isError) return `ERROR: ${text}`;
      return text || JSON.stringify(res.structuredContent ?? {});
    } catch (e) {
      if (attempt > 0) throw e;
      console.warn(`[mcp] ${name} failed (${(e as Error).message}); reconnecting and retrying once`);
      await closeMcp();
    }
  }
}

/** Tools Claude may call.  `omit` hides tools the agent must never drive on its own. */
export async function benchTools(omit: string[] = ["camera_snapshot"]) {
  const c = await mcpClient();
  const { tools } = await c.listTools();
  return tools
    .filter((t) => !omit.includes(t.name))
    .map((t) =>
      betaTool({
        name: t.name,
        description: t.description ?? t.name,
        inputSchema: t.inputSchema as Parameters<typeof betaTool>[0]["inputSchema"],
        run: async (input: unknown) => callTool(t.name, (input ?? {}) as Record<string, unknown>),
      }),
    );
}
