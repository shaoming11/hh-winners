import { config as loadEnv } from "dotenv";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

// agent/.env first, then the repo root .env (where the hackathon keys live); neither overrides the shell
const here = dirname(fileURLToPath(import.meta.url));
loadEnv({ path: resolve(here, "../.env") });
loadEnv({ path: resolve(here, "../../../.env") });

const env = (k: string, d = "") => (process.env[k] ?? d).trim();

export const CONFIG = {
  backendUrl: env("BACKEND_URL", "http://127.0.0.1:8000").replace(/\/$/, ""),
  model: env("AGENT_MODEL", "claude-opus-5"),
  agentName: env("AGENT_NAME", "Bench"),
  /** texting "operator <code>" makes the sender an operator; empty disables it */
  bootstrapCode: env("AGENT_BOOTSTRAP_CODE"),
  projectId: env("SPECTRUM_PROJECT_ID") || env("PHOTON_PROJECT_ID"),
  projectSecret: env("SPECTRUM_PROJECT_SECRET") || env("PHOTON_SECRET") || env("PHOTON_PROJECT_SECRET"),
  providers: env("AGENT_PROVIDERS", "").split(",").map((s) => s.trim()).filter(Boolean),
  operatorPhones: env("OPERATOR_PHONES", "").split(",").map((s) => s.trim()).filter(Boolean),
  /** where spaces/*.json live; DATA_DIR overrides (tests point it at a temp dir) */
  dataDir: env("DATA_DIR") || new URL("../data/", import.meta.url).pathname,
  /** warnings are batched for this long before one message goes out */
  warningBatchMs: 20_000,
  /** criticals wait this long so a fault + its run summary (and any sibling alerts) become ONE message */
  criticalBatchMs: 1_500,
};
if (!CONFIG.providers.length) {
  CONFIG.providers = CONFIG.projectId ? ["imessage", "terminal"] : ["terminal"];
}
