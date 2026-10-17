/** Inbound pictures: photos.ts normalisation, and one live turn where the model actually looks at
 *  a frame of the bench (the camera's own JPEG stands in for a texted photo). */
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { useTempDataDir, backendUp } from "./helpers.js";

useTempDataDir();
const { inboundImage } = await import("../src/photos.js");
const { memo } = await import("../src/memory.js");
const { think, SILENT } = await import("../src/brain.js");
const { closeMcp } = await import("../src/mcp.js");

/** smallest real PNG: 1x1, transparent */
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYGD4DwABBAEAX+XFDwAAAABJRU5ErkJggg==",
  "base64",
);

const att = (o: Partial<{ name: string; mimeType: string; read: () => Promise<Buffer> }> = {}) => ({
  type: "attachment" as const,
  name: "photo.png",
  mimeType: "image/png",
  read: async () => PNG,
  ...o,
});

test("photos: a real image comes back ready for the API", async () => {
  const got = await inboundImage(att());
  assert.ok("image" in got, JSON.stringify(got));
  assert.ok(got.image.data.length > 0);
  assert.match(got.image.mimeType, /^image\/(jpeg|png)$/);
});

test("photos: a PDF is refused with a sentence the sender can act on", async () => {
  const got = await inboundImage(att({ mimeType: "application/pdf", name: "protocol.pdf" }));
  assert.ok("error" in got);
  assert.match(got.error, /only look at pictures/i);
  assert.match(got.error, /pdf/i);
});

test("photos: an unknown mime type is refused, not guessed at", async () => {
  const got = await inboundImage(att({ mimeType: "", name: "blob" }));
  assert.ok("error" in got);
  assert.match(got.error, /unknown file type/i);
});

test("photos: a download failure asks for the photo again instead of throwing", async () => {
  const got = await inboundImage(att({ read: async () => { throw new Error("link expired"); } }));
  assert.ok("error" in got);
  assert.match(got.error, /didn't download/i);
  assert.match(got.error, /link expired/);
});

test("photos: HEIC from an iPhone is converted where sips exists, refused clearly where it doesn't", async () => {
  // sips converts by content, not extension, so a PNG labelled HEIC still exercises the path
  const got = await inboundImage(att({ mimeType: "image/heic", name: "IMG_0001.HEIC" }));
  if ("image" in got) assert.equal(got.image.mimeType, "image/jpeg", "converted to JPEG");
  else assert.match(got.error, /JPEG or PNG/i);
});

const hasKey = !!(process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_AUTH_TOKEN);
const up = await backendUp();
test("think: a texted photo of the bench is actually looked at", { skip: !hasKey ? "no ANTHROPIC_API_KEY in env" : !up ? "no backend" : false }, async (t) => {
  const { backend: be } = await import("../src/backend.js");
  const frame = await be.snapshot("overview").catch(() => null);
  if (!frame) { t.skip("backend: /api/snapshot 404s (rendering off); restart it with WLB_RENDER=1 for this test"); return; }
  const got = await inboundImage(att({ name: "bench.jpg", mimeType: "image/jpeg", read: async () => frame }));
  assert.ok("image" in got, JSON.stringify(got));
  const [state, desc] = await Promise.all([be.state(), be.describe().catch(() => null)]);
  const out = await think({ memo: memo("test", "dm-photo"), text: "(sent a photo of the bench) what do you make of this?",
    sender: { id: "+15550004", name: "Tester" }, platform: "test", isGroup: false, state, describe: desc, people: {},
    images: [got.image] });
  assert.ok(out.text && out.text !== SILENT, "a photo in a DM gets an answer");
  assert.match(out.text, /beaker|arm|bench|flask|scale|carousel|frame|picture|photo|image/i);
});

after(async () => { await closeMcp(); });
