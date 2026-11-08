"use client";

import { useEffect, useState } from "react";
import { api, type ApiError, type Workspace } from "@/lib/api";
import { cx } from "@/components/ui";

const AGENT_PROMPT = "Set up Tracefold by following SETUP.md in the Tracefold repository. Protect this folder: <path to your project>. Our company is <company name>, <domain>; takedown replies go to <email>.";

const COMMANDS = [
  "cd server && uv sync && uv run tracefold quickstart --root <path to your project> --company \"<company>\" --reply-to <email>",
  "cd server && uv run tracefold serve --port 8787",
  "cd frontend && npm install && npm run dev",
];

function Copy({ text, className }: { text: string; className?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {}
      }}
      className={cx("shrink-0 rounded-ctl border border-line px-2.5 py-1 text-xs text-mute hover:text-ink", className)}
    >
      {done ? "Copied" : "Copy"}
    </button>
  );
}

export default function Setup() {
  const [status, setStatus] = useState<{ ok: boolean; ws?: Workspace; err?: ApiError } | null>(null);
  const check = () => {
    setStatus(null);
    api<{ items: Workspace[] }>("/workspaces")
      .then((r) => setStatus({ ok: r.items.length > 0, ws: r.items[0] }))
      .catch((err: ApiError) => setStatus({ ok: false, err }));
  };
  useEffect(check, []);

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl tracking-[-0.03em] text-ink">Set up Tracefold</h1>

      {status && !status.ok && (
        <div className="mt-6 flex items-center justify-between gap-4 rounded-card border border-line px-4 py-3 text-sm text-mute">
          <span>{status.err?.message ?? "The engine has no workspace yet. Run step 1."}</span>
          <button onClick={check} className="shrink-0 text-ink underline underline-offset-4">
            Check again
          </button>
        </div>
      )}

      <h2 className="mt-10 text-sm font-medium text-ink">With a coding agent</h2>
      <p className="mt-1 text-sm text-mute">Paste this into Claude Code, Codex or Copilot, opened in the Tracefold repository.</p>
      <div className="mt-3 flex items-start gap-3 rounded-card border border-line bg-panel p-4">
        <p className="flex-1 text-[15px] leading-relaxed text-ink">{AGENT_PROMPT}</p>
        <Copy text={AGENT_PROMPT} />
      </div>

      <h2 className="mt-10 text-sm font-medium text-ink">Or yourself</h2>
      <p className="mt-1 text-sm text-mute">From the repository root. Run the last two in separate terminals and leave them running.</p>
      <ol className="mt-3 space-y-2">
        {COMMANDS.map((c, i) => (
          <li key={c} className="flex items-center gap-3 rounded-card border border-line bg-panel px-4 py-3">
            <span className="font-mono text-xs text-faint">{i + 1}</span>
            <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap font-mono text-[13px] text-ink-2">{c}</code>
            <Copy text={c} />
          </li>
        ))}
      </ol>
      <p className="mt-4 text-sm text-mute">
        Full steps, including connecting a coding assistant and setting up takedowns, are in <code className="font-mono text-ink-2">SETUP.md</code>.
      </p>
    </div>
  );
}
