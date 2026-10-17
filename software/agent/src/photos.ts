/** Inbound pictures.  Someone texts a photo of the bench ("is this a spill?"); this turns the
 *  provider's attachment into something Claude can look at.
 *
 *  Two things stand in the way.  iPhones send HEIC, which the API does not accept, and a 12 MP
 *  photo is far more pixels than a judgement about a bench needs.  macOS ships `sips`, so when it
 *  is there every image is re-encoded to a long edge of 1568 px (the API's recommended maximum)
 *  as JPEG; without it, the four accepted formats pass through and anything else is refused with a
 *  sentence the sender can act on. */
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";

const run = promisify(execFile);

/** what the API accepts directly */
const ACCEPTED = new Set(["image/jpeg", "image/png", "image/gif", "image/webp"]);
/** 5 MB is the API's per-image ceiling; leave room for base64's 4/3 inflation */
const MAX_BYTES = 3_500_000;
const LONG_EDGE = 1568;

export type InboundAttachment = {
  type: "attachment";
  name?: string;
  mimeType?: string;
  size?: number;
  read: () => Promise<Buffer>;
};

export type InboundImage = { data: Buffer; mimeType: string; name: string };

let sipsChecked = false;
let haveSips = false;

async function sipsAvailable(): Promise<boolean> {
  if (!sipsChecked) {
    sipsChecked = true;
    haveSips = await run("sips", ["--version"]).then(() => true, () => false);
  }
  return haveSips;
}

/** re-encode to JPEG at LONG_EDGE via sips; returns null if sips is absent or fails */
async function toJpeg(buf: Buffer, name: string): Promise<Buffer | null> {
  if (!(await sipsAvailable())) return null;
  const dir = await mkdtemp(join(tmpdir(), "bench-photo-"));
  try {
    const src = join(dir, name.replace(/[^\w.-]/g, "_") || "in");
    const dst = join(dir, "out.jpg");
    await writeFile(src, buf);
    await run("sips", ["-s", "format", "jpeg", "-Z", String(LONG_EDGE), src, "--out", dst]);
    return await readFile(dst);
  } catch {
    return null;
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

/** Read one inbound attachment into something Claude can see, or explain why we can't.
 *  `{ error }` is a sentence meant to be sent back to the person as-is. */
export async function inboundImage(a: InboundAttachment): Promise<{ image: InboundImage } | { error: string }> {
  const mime = (a.mimeType ?? "").toLowerCase();
  const name = a.name ?? "photo";
  if (!mime.startsWith("image/")) {
    return { error: `I can only look at pictures, and that came through as ${mime || "an unknown file type"}.` };
  }
  let data: Buffer;
  try {
    data = await a.read();
  } catch (e) {
    return { error: `That picture didn't download (${(e as Error).message}); can you send it again?` };
  }
  const converted = await toJpeg(data, name);
  if (converted) return { image: { data: converted, mimeType: "image/jpeg", name: "photo.jpg" } };
  if (!ACCEPTED.has(mime)) {
    return { error: `I can't read ${mime} on this machine - send it as a JPEG or PNG and I'll take a look.` };
  }
  if (data.length > MAX_BYTES) {
    return { error: `That photo is ${(data.length / 1e6).toFixed(1)} MB, past what I can look at - a smaller one works.` };
  }
  return { image: { data, mimeType: mime, name } };
}
