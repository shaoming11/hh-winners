/** The backend's MCP tools, exposed to Claude through the SDK tool runner.  Tool schemas come
 *  from the server at startup, so a new backend tool is available to the agent without a deploy. */
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { betaTool } from "@anthropic-ai/sdk/helpers/beta/json-schema";
import { CONFIG } from "./config.js";

let client: Client | null = null;

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
  const c = await mcpClient();
  const res = await c.callTool({ name, arguments: args });
  const parts = (res.content as { type: string; text?: string; mimeType?: string }[]) ?? [];
  const text = parts.map((p) => (p.type === "text" ? p.text : p.type === "image" ? "[image]" : `[${p.type}]`)).join("\n");
  if ((res as { isError?: boolean }).isError) return `ERROR: ${text}`;
  return text || JSON.stringify(res.structuredContent ?? {});
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
