// Contact form handler. Until the company has a real inbox/CRM, submissions are appended to
// .data/contact-messages.jsonl (gitignored). Replace the write with email/CRM delivery before launch.
import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

const TOPICS = ["enterprise", "support", "security"] as const;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export async function POST(req: Request) {
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "Invalid request." }, { status: 400 });
  }
  const str = (k: string, max: number) => (typeof body[k] === "string" ? (body[k] as string).trim().slice(0, max) : "");
  const msg = {
    topic: TOPICS.includes(body.topic as (typeof TOPICS)[number]) ? body.topic : "enterprise",
    email: str("email", 200),
    name: str("name", 120),
    company: str("company", 160),
    role: str("role", 120),
    message: str("message", 5000),
    at: new Date().toISOString(),
  };
  if (!EMAIL.test(msg.email)) return NextResponse.json({ detail: "Enter a valid email address." }, { status: 422 });
  if (!msg.name) return NextResponse.json({ detail: "Enter your name." }, { status: 422 });
  if (msg.message.length < 10) return NextResponse.json({ detail: "Tell us a little more about what you need." }, { status: 422 });

  const dir = path.join(process.cwd(), ".data");
  await mkdir(dir, { recursive: true });
  await appendFile(path.join(dir, "contact-messages.jsonl"), JSON.stringify(msg) + "\n");
  return NextResponse.json({ ok: true });
}
