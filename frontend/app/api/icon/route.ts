// Site icons for the leak timeline, fetched from the site itself: read the icon its home page declares
// (<link rel="icon"> / apple-touch-icon), fall back to /favicon.ico, drop empty placeholders, cache for a day.
// Only public hosts are fetched: names that resolve to private, loopback or link-local addresses are refused.
import { lookup } from "node:dns/promises";
import { isIP } from "node:net";
import { NextResponse, type NextRequest } from "next/server";

const HOST = /^(?=.{1,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$/;
const MAX_HTML = 512 * 1024;
const MAX_ICON = 256 * 1024;
const DAY = 86_400_000;
const cache = new Map<string, { at: number; body: Buffer | null; type: string }>();

function privateAddress(ip: string): boolean {
  if (isIP(ip) === 6) {
    const v = ip.toLowerCase();
    return v === "::1" || v === "::" || v.startsWith("fc") || v.startsWith("fd") || v.startsWith("fe80") || v.startsWith("::ffff:");
  }
  const [a, b] = ip.split(".").map(Number);
  return (
    a === 10 || a === 127 || a === 0 || a >= 224 ||
    (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127)
  );
}

async function publicHost(host: string): Promise<boolean> {
  if (!HOST.test(host) || host.endsWith(".local") || host.endsWith(".internal") || host === "localhost") return false;
  try {
    const addrs = await lookup(host, { all: true });
    return addrs.length > 0 && addrs.every((a) => !privateAddress(a.address));
  } catch {
    return false;
  }
}

/** HTTPS GET with a timeout, a size cap, and redirects only to other public hosts. */
async function get(url: string, max: number): Promise<{ body: Buffer; type: string } | null> {
  let current = url;
  for (let hop = 0; hop < 4; hop++) {
    const u = new URL(current);
    if (u.protocol !== "https:" || !(await publicHost(u.hostname))) return null;
    const res = await fetch(current, {
      redirect: "manual",
      signal: AbortSignal.timeout(4000),
      headers: { "user-agent": "Mozilla/5.0 (compatible; Tracefold icon fetch)", accept: "text/html,image/*;q=0.9,*/*;q=0.5" },
    }).catch(() => null);
    if (!res) return null;
    const loc = res.headers.get("location");
    if (res.status >= 300 && res.status < 400 && loc) {
      current = new URL(loc, current).toString();
      continue;
    }
    if (!res.ok || !res.body) return null;
    const reader = res.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > max) {
        await reader.cancel();
        break;
      }
      chunks.push(value);
    }
    return { body: Buffer.concat(chunks), type: res.headers.get("content-type") ?? "" };
  }
  return null;
}

/** Icon links the page declares, best first: apple-touch-icon, then the largest or SVG icon, then any icon. */
function declaredIcons(html: string, base: string): string[] {
  const found: { href: string; score: number }[] = [];
  for (const [tag] of html.matchAll(/<link\b[^>]*>/gi)) {
    const rel = /\brel\s*=\s*["']?([^"'>]+)/i.exec(tag)?.[1].toLowerCase() ?? "";
    const href = /\bhref\s*=\s*["']([^"']+)["']/i.exec(tag)?.[1];
    if (!href || !/(^|\s)(icon|apple-touch-icon(-precomposed)?)(\s|$)/.test(rel)) continue;
    const size = Number(/\bsizes\s*=\s*["']?(\d+)/i.exec(tag)?.[1] ?? 0);
    const score = (rel.includes("apple-touch-icon") ? 1000 : 0) + Math.min(size, 512) + (/\.svg(\?|$)/i.test(href) ? 300 : 0);
    try {
      found.push({ href: new URL(href, base).toString(), score });
    } catch {}
  }
  return found.sort((a, b) => b.score - a.score).map((f) => f.href);
}

/** True when every pixel of the first BMP-encoded image in an .ico file is transparent. */
function blankIco(buf: Buffer): boolean {
  if (buf.length < 22 || buf.readUInt16LE(0) !== 0 || buf.readUInt16LE(2) !== 1) return false;
  const size = buf.readUInt32LE(14);
  const offset = buf.readUInt32LE(18);
  if (offset + size > buf.length || size < 40) return false;
  if (buf.subarray(offset, offset + 4).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47]))) return false;
  const header = buf.readUInt32LE(offset);
  const width = buf.readInt32LE(offset + 4);
  if (buf.readUInt16LE(offset + 14) !== 32 || width <= 0) return false;
  for (let i = 0; i < width * width && offset + header + i * 4 + 3 < buf.length; i++) if (buf[offset + header + i * 4 + 3] > 20) return false;
  return true;
}

async function findIcon(host: string): Promise<{ body: Buffer; type: string } | null> {
  const home = `https://${host}/`;
  const page = await get(home, MAX_HTML);
  const declared = page && page.type.includes("html") ? declaredIcons(page.body.toString("utf8"), home) : [];
  for (const url of [...declared.slice(0, 3), `${home}favicon.ico`]) {
    const icon = await get(url, MAX_ICON);
    if (!icon || icon.body.length < 64) continue;
    const type = icon.type.split(";")[0].trim().toLowerCase();
    if (!type.startsWith("image/") && !/\.ico(\?|$)/i.test(url)) continue;
    if (blankIco(icon.body)) continue;
    return { body: icon.body, type: type.startsWith("image/") ? type : "image/x-icon" };
  }
  return null;
}

export async function GET(req: NextRequest) {
  const host = (req.nextUrl.searchParams.get("host") ?? "").toLowerCase();
  if (!HOST.test(host)) return new NextResponse(null, { status: 400 });
  let hit = cache.get(host);
  if (!hit || Date.now() - hit.at > DAY) {
    const icon = await findIcon(host).catch(() => null);
    hit = { at: Date.now(), body: icon?.body ?? null, type: icon?.type ?? "" };
    cache.set(host, hit);
  }
  if (!hit.body) return new NextResponse(null, { status: 404, headers: { "cache-control": "public, max-age=3600" } });
  // Served only as an <img>; the CSP keeps an SVG icon from running anything if opened directly.
  return new NextResponse(new Uint8Array(hit.body), {
    headers: { "content-type": hit.type, "cache-control": "public, max-age=86400", "content-security-policy": "default-src 'none'; style-src 'unsafe-inline'" },
  });
}
