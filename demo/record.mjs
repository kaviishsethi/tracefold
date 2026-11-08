// Records the web-app shots of docs/DEMO_VIDEO.md as 1080p clips, one per section, by driving the real app.
// The Claude Code (MCP) and Wi-Fi-off shots are recorded by hand. Usage:
//   node record.mjs                # all clips
//   node record.mjs 03 05          # only some clips
// Needs the engine, web app and Ollama running, and a search key for clip 03. Output: demo/out/NN-name.mp4
import { chromium } from "playwright";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, renameSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out");
const RAW = join(OUT, "raw");
const APP = process.env.TRACEFOLD_APP ?? "http://localhost:3100";
const WS = process.env.TRACEFOLD_WORKSPACE ?? "ws_demo";
const SAMPLES = join(HERE, "..", "frontend", "public", "examples");
const FIXTURES = join(HERE, "..", "server", "fixtures", "private");
// Pages are laid out and recorded at 1280x720, then scaled to 1080p by ffmpeg, so the interface reads large on video.
const SIZE = { width: 1280, height: 720 };

// ---------- engine API, through the web app's proxy ----------
async function api(path, init = {}) {
  const res = await fetch(`${APP}/api/engine/workspaces/${WS}${path}`, init);
  const text = await res.text();
  if (!res.ok) throw new Error(`${init.method ?? "GET"} ${path} -> ${res.status} ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : null;
}
async function upload(path, name) {
  const form = new FormData();
  form.append("file", new Blob([readFileSync(path)]), name);
  return api("/uploads", { method: "POST", body: form });
}
async function scanAndWait(body) {
  const { scan_id } = await api("/scans", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  for (let i = 0; i < 180; i++) {
    const s = await api(`/scans/${scan_id}`);
    if (!["queued", "running"].includes(s.state)) return s;
    await sleep(1000);
  }
  throw new Error(`scan ${scan_id} didn't finish`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- a visible cursor (Playwright videos don't draw one) ----------
const CURSOR = `
  addEventListener("DOMContentLoaded", () => {
    const c = document.createElement("div");
    c.id = "__demo_cursor";
    Object.assign(c.style, { position: "fixed", left: "0", top: "0", width: "22px", height: "22px", marginLeft: "-11px",
      marginTop: "-11px", borderRadius: "50%", background: "rgba(255,255,255,0.85)", boxShadow: "0 0 0 2px rgba(0,0,0,0.45)",
      pointerEvents: "none", zIndex: "2147483647", transition: "transform 120ms ease", transform: "scale(1)" });
    document.body.appendChild(c);
    addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; }, true);
    addEventListener("mousedown", () => { c.style.transform = "scale(0.7)"; }, true);
    addEventListener("mouseup", () => { c.style.transform = "scale(1)"; }, true);
  });`;

let lastMouse = { x: SIZE.width / 2, y: SIZE.height / 2 };
async function moveTo(page, locator, { pause = 500 } = {}) {
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) throw new Error("element not visible");
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  const steps = Math.max(12, Math.round(Math.hypot(x - lastMouse.x, y - lastMouse.y) / 18));
  await page.mouse.move(x, y, { steps });
  lastMouse = { x, y };
  await sleep(pause);
}
async function click(page, locator, opts = {}) {
  await moveTo(page, locator, { pause: 350 });
  await page.mouse.down();
  await sleep(90);
  await page.mouse.up();
  await sleep(opts.after ?? 900);
}
async function scrollBy(page, dy, ms = 1200) {
  const n = 24;
  for (let i = 0; i < n; i++) {
    await page.mouse.wheel(0, dy / n);
    await sleep(ms / n);
  }
}
async function ready(page) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await sleep(800);
}

// ---------- recording ----------
async function record(browser, name, fn) {
  mkdirSync(RAW, { recursive: true });
  const context = await browser.newContext({ viewport: SIZE, deviceScaleFactor: 1, colorScheme: "dark", recordVideo: { dir: RAW, size: SIZE } });
  // Hide Next's dev-mode overlay in recordings.
  await context.addInitScript(`addEventListener("load", () => {
    const st = document.createElement("style"); st.textContent = "nextjs-portal{display:none!important}"; document.head.appendChild(st);
  });`);
  await context.addInitScript(CURSOR);
  const page = await context.newPage();
  const t0 = Date.now();
  let start = 0;
  const mark = () => { start = (Date.now() - t0) / 1000; };  // trims the blank page load from the clip
  try {
    await fn(page, mark);
  } finally {
    const video = page.video();
    await context.close();
    const raw = await video.path();
    const mp4 = join(OUT, `${name}.mp4`);
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-ss", String(Math.max(0, start - 0.2)), "-i", raw,
      "-vf", "scale=1920:1080:flags=lanczos", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-r", "30", mp4]);
    renameSync(raw, join(RAW, `${name}.webm`));
    console.log(`saved ${mp4}`);
  }
}

// A plain title card: the Tracefold mark and name in bold, centered, with one line under it.
const TITLE_CARD = `<!doctype html><html><head>
  <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@700&family=Inter:wght@400&display=swap" rel="stylesheet">
  </head><body style="margin:0;height:100vh;background:#0a0c0c;display:flex;align-items:center;justify-content:center">
  <div style="text-align:center;color:#eef2f1">
    <div style="display:inline-flex;align-items:center;gap:18px;font-family:Manrope,-apple-system,Arial,sans-serif;
      font-weight:700;font-size:72px;letter-spacing:-0.035em;line-height:1">
      <svg viewBox="0 0 256 256" width="80" height="80" fill="none" stroke="#eef2f1" stroke-width="16"
        stroke-linecap="round" stroke-linejoin="round">
        <path d="M32 32H224V184L168 224V184H88V224L32 184Z"/><path d="M32 32L88 80V184M224 32L168 80V184"/>
      </svg>
      Tracefold
    </div>
    <div style="margin-top:26px;font-family:Inter,-apple-system,Arial,sans-serif;font-size:26px;color:#9aa3a1">
      Catch, fix and prevent security leaks.</div>
  </div></body></html>`;

async function titleCard(page, mark, seconds) {
  await page.setContent(TITLE_CARD, { waitUntil: "domcontentloaded", timeout: 15_000 });
  await page.evaluate(() => Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 4000))])).catch(() => {});
  await sleep(300);
  mark();
  await sleep(seconds * 1000);
}

const CLIPS = {
  // 0:00–0:22 What Tracefold is
  "01-intro": (page, mark) => titleCard(page, mark, 22),

  // 0:22–0:35 Who it's for: industry checks
  "02-industry": async (page, mark) => {
    await page.goto(`${APP}/settings`);
    await ready(page);
    mark();
    await sleep(1200);
    await click(page, page.getByRole("button", { name: "Edit" }).first());
    await click(page, page.locator('button[aria-label^="Industry"]'), { after: 1500 });
    for (const label of ["Financial services", "Healthcare"]) await moveTo(page, page.getByRole("option", { name: label }), { pause: 900 });
    await click(page, page.getByRole("option", { name: "Healthcare" }), { after: 4000 });
    await moveTo(page, page.getByText(/Also checks for/), { pause: 3000 });
    await click(page, page.getByRole("button", { name: "Cancel" }), { after: 1500 });
  },

  // 0:35–1:10 Finding public copies (the progress card is sped up in the edit)
  "03-public-copies": async (page, mark) => {
    await page.goto(`${APP}/scan`);
    await ready(page);
    mark();
    await click(page, page.getByText("Sample files"));
    await click(page, page.getByRole("button", { name: "duolingo-internal-memo.md" }), { after: 1500 });
    await click(page, page.getByRole("button", { name: /^Check 1 file$/ }));
    await page.waitForURL(/\/scan\/scan_/, { timeout: 60_000, waitUntil: "commit" });
    await page.waitForFunction(() => !document.querySelector("main h1")?.textContent?.includes("Checking"), null, { timeout: 240_000 });
    await ready(page);
    await sleep(1500);
    await moveTo(page, page.getByText(/^Searched for/), { pause: 2500 });
    await moveTo(page, page.getByText(/public sites? shows? text from your documents/), { pause: 2500 });
    await scrollBy(page, 420);
    await sleep(1500);
    const view = page.getByRole("button", { name: "View passages" }).first();
    const many = (await view.count()) > 0; // the label flips to "Hide passages" once clicked
    const passage = many ? view : page.getByRole("link", { name: "View passage" }).first();
    await click(page, passage, { after: 1200 });
    if (many) {
      const link = page.locator("main li > a").first();
      const href = await link.getAttribute("href", { timeout: 5000 });
      console.log("  passage", href);
      await moveTo(page, link, { pause: 600 });
      await page.goto(`${APP}${href}`);
    }
    await page.waitForURL(/\/findings\/fnd_/, { waitUntil: "commit" });
    await ready(page);
    // End on the side-by-side comparison: the same sentence highlighted in the file and on the public page.
    // (Live news pages tend to show cookie banners and paywalls, so the clip doesn't open them.)
    await moveTo(page, page.locator("mark").first(), { pause: 2500 });
    await moveTo(page, page.locator("mark").last(), { pause: 4000 });
  },

  // 1:10–1:35 Risks in the file, and approving a takedown
  "04-risks-takedown": async (page, mark) => {
    // Prepare off camera: a GitLab sample scan (for "In your files") and a fresh takedown draft from the sample page list.
    const gl = await upload(join(SAMPLES, "gitlab-data-classification.md"), "gitlab-data-classification.md");
    const glScan = await scanAndWait({ input_id: gl.input_id, checks: ["local_risk"] });
    let drafted = (await api("/actions?status=drafted&limit=100")).items.find((a) => a.kind === "takedown_request");
    if (!drafted) {
      // Earlier sample takedowns were already approved; remove those sample scans so the roadmap match drafts a new one.
      const scans = (await api("/scans?limit=100")).items;
      for (const s of scans) {
        const fs = (await api(`/findings?scan_id=${s.scan_id}&limit=100`)).items;
        if (fs.length && fs.every((f) => f.path === "roadmap.md")) await api(`/scans/${s.scan_id}`, { method: "DELETE" });
      }
      const rm = await upload(join(FIXTURES, "roadmap.md"), "roadmap.md");
      const ws = await (await fetch(`${APP}/api/engine/workspaces`)).json();
      const manifest = ws.items.find((w) => w.id === WS)?.manifests?.[0];
      await scanAndWait({ input_id: rm.input_id, checks: ["public_match"], public_sources: { manifest_id: manifest, mode: "refresh" } });
      drafted = (await api("/actions?status=drafted&limit=100")).items.find((a) => a.kind === "takedown_request");
      if (!drafted) console.warn("No takedown draft could be prepared; the Approvals part of this clip will show existing ones.");
    }

    await page.goto(`${APP}/scan/${glScan.scan_id}`);
    await ready(page);
    mark();
    await moveTo(page, page.getByRole("heading", { name: "In your files" }).first(), { pause: 1500 });
    await moveTo(page, page.locator('a[href^="/findings/fnd_"]').first(), { pause: 3500 });
    await click(page, page.getByRole("link", { name: "Approvals" }), { after: 0 });
    await page.waitForURL(/\/actions/, { waitUntil: "commit" });
    await ready(page);
    await sleep(1500);
    const card = page.locator("div.rounded-card", { hasText: "remove the copied content" }).first();
    await moveTo(page, card.locator("p").first(), { pause: 2000 });
    await click(page, card.getByText("See the letter"), { after: 2500 });
    await scrollBy(page, 300);
    await sleep(2000);
    const approve = card.getByRole("button", { name: /Save email|Send request|Approve/ });
    if (await approve.count()) {
      await click(page, approve, { after: 1500 });
      await scrollBy(page, -400, 600);
      const done = page.getByText(/^\d+ done$/);
      if (await done.count()) await click(page, done, { after: 1200 });
      const result = page.getByText(/Not sent\. Email sending is off|^Sent to/).first();
      if (await result.count()) await moveTo(page, result, { pause: 3500 });
    }
  },

  // 1:35–1:45 Scheduled checks
  "05-schedule": async (page, mark) => {
    const last = (await api("/scans?limit=20")).items.find((s) => s.state === "completed" && !s.recheck_of);
    if (!last) throw new Error("no finished scan to schedule");
    await page.goto(`${APP}/scan/${last.scan_id}`);
    await ready(page);
    mark();
    await click(page, page.getByRole("button", { name: "Schedule" }).first(), { after: 1200 });
    await moveTo(page, page.getByLabel("How many"), { pause: 800 });
    await moveTo(page, page.locator('input[type="datetime-local"]'), { pause: 900 });
    await click(page, page.getByRole("button", { name: "Schedule" }).last(), { after: 2000 });
    await click(page, page.getByRole("link", { name: "Settings" }), { after: 0 });
    await page.waitForURL(/\/settings/, { waitUntil: "commit" });
    await ready(page);
    await moveTo(page, page.getByRole("heading", { name: "Scheduled checks" }), { pause: 3000 });
  },

  // 2:30–2:45 End card
  "06-end-card": (page, mark) => titleCard(page, mark, 15),
};

const FRESH = process.argv.includes("--fresh");
const wanted = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const names = Object.keys(CLIPS).filter((n) => !wanted.length || wanted.some((w) => n.startsWith(w)));
rmSync(RAW, { recursive: true, force: true });
const browser = await chromium.launch();
try {
  if (FRESH) {
    // A fresh start: delete finished scans (which also clears page memory) so clip 03 runs a real search.
    const r = await api("/scans", { method: "DELETE" });
    console.log(`--fresh: deleted ${r.scans} scans`);
  }
  for (const n of names) {
    console.log(`recording ${n}…`);
    await record(browser, n, CLIPS[n]);
  }
} finally {
  await browser.close();
}
