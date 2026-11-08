"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

/** A one-line shell command with a copy button. */
export function CopyCommand({ command }: { command: string }) {
  const [done, setDone] = useState(false);
  return (
    <div className="flex items-center gap-2 rounded-ctl border border-line bg-bg py-1.5 pl-3 pr-1.5">
      <code className="min-w-0 flex-1 truncate font-mono text-[13px] text-ink-2">{command}</code>
      <button
        type="button"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(command);
            setDone(true);
            setTimeout(() => setDone(false), 1500);
          } catch {}
        }}
        className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-[6px] px-2 text-xs text-mute hover:bg-raised hover:text-ink"
      >
        {done ? <Check className="size-3.5 text-local" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
        {done ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

export const CONNECT_AWS = "cd server && uv run tracefold connect-aws";
export const CONNECT_AWS_PROMPT =
  "In the Tracefold repository, run `cd server && uv run tracefold connect-aws` so Tracefold can turn off leaked AWS keys. It uses my AWS CLI login; if I'm not signed in, tell me to run `aws sso login` or `aws configure` first. Don't print the key it creates.";
