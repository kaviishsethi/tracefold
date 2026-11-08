// Same-origin proxy to the Tracefold engine. Holds the app's engine token server-side so the browser never sees it.
// Configure in .env.local:
//   TRACEFOLD_ENGINE_URL=http://127.0.0.1:8787
//   TRACEFOLD_APP_TOKEN=tf_...            (from `uv run tracefold add-client upload-app --workspace <id>`)
import { NextRequest, NextResponse } from "next/server";

const ENGINE_URL = (process.env.TRACEFOLD_ENGINE_URL ?? "http://127.0.0.1:8787").replace(/\/+$/, "");
const SEGMENT = /^[A-Za-z0-9_.-]{1,100}$/;
const FORWARD_HEADERS = ["content-type", "idempotency-key"];

function envelope(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message, retryable: status >= 500 }, request_id: null }, { status });
}

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const token = process.env.TRACEFOLD_APP_TOKEN;
  if (!token) return envelope(503, "app_not_configured", "Set TRACEFOLD_APP_TOKEN in frontend/.env.local, then restart the app.");
  const { path } = await ctx.params;
  if (!path.length || !path.every((p) => SEGMENT.test(p) && p !== "." && p !== ".."))
    return envelope(404, "not_found", "Resource not found.");
  const url = `${ENGINE_URL}/v1/${path.join("/")}${req.nextUrl.search}`;
  const headers: Record<string, string> = { authorization: `Bearer ${token}` };
  for (const h of FORWARD_HEADERS) {
    const v = req.headers.get(h);
    if (v) headers[h] = v;
  }
  let res: Response;
  try {
    res = await fetch(url, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return envelope(502, "engine_unreachable", `The Tracefold engine isn't reachable at ${ENGINE_URL}. Start it with \`uv run tracefold serve\`.`);
  }
  return new NextResponse(res.body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json", "cache-control": "no-store" },
  });
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
export const dynamic = "force-dynamic";
