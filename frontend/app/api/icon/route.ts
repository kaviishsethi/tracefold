// Site icons for the leak timeline. Fetches the icon a site declares from DuckDuckGo's icon service (which only
// receives the host name) on the server, drops fully transparent placeholders, and caches for a day.
import { NextResponse, type NextRequest } from "next/server";

const HOST = /^(?=.{1,253}$)([a-z0-9-]{1,63}\.)+[a-z]{2,63}$/;

/** True when every pixel of the first BMP-encoded image in an .ico file is transparent. PNG-encoded icons are kept. */
function blankIco(buf: Buffer): boolean {
  if (buf.length < 22 || buf.readUInt16LE(0) !== 0 || buf.readUInt16LE(2) !== 1) return false;
  const size = buf.readUInt32LE(14);
  const offset = buf.readUInt32LE(18);
  if (offset + size > buf.length || size < 40) return false;
  if (buf.subarray(offset, offset + 4).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47]))) return false; // PNG inside
  const header = buf.readUInt32LE(offset);
  const width = buf.readInt32LE(offset + 4);
  const bpp = buf.readUInt16LE(offset + 14);
  if (bpp !== 32 || width <= 0) return false;
  const pixels = offset + header;
  const count = width * width;
  for (let i = 0; i < count && pixels + i * 4 + 3 < buf.length; i++) if (buf[pixels + i * 4 + 3] > 20) return false;
  return true;
}

export async function GET(req: NextRequest) {
  const host = (req.nextUrl.searchParams.get("host") ?? "").toLowerCase();
  if (!HOST.test(host)) return new NextResponse(null, { status: 400 });
  let res: Response;
  try {
    res = await fetch(`https://icons.duckduckgo.com/ip3/${host}.ico`, { cache: "force-cache", next: { revalidate: 86400 } });
  } catch {
    return new NextResponse(null, { status: 404 });
  }
  if (!res.ok) return new NextResponse(null, { status: 404 });
  const buf = Buffer.from(await res.arrayBuffer());
  if (buf.length < 64 || blankIco(buf)) return new NextResponse(null, { status: 404 });
  return new NextResponse(buf, {
    headers: { "content-type": res.headers.get("content-type") ?? "image/x-icon", "cache-control": "public, max-age=86400" },
  });
}
