"use client";

// "Onboard with your agent": a setup prompt people paste into their coding agent.
import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { siClaude, siGithubcopilot, siOpenai } from "simple-icons";
import { cx } from "./ui";

const PROMPT =
  "Set up Tracefold for our team: start the Tracefold scan engine with a local Ollama model, connect the Tracefold MCP server to this assistant with a grant that can't approve actions, add Tracefold's working instructions to this project, then run scan_changes on my current changes and walk me through the findings.";

const AGENTS = [
  { icon: siClaude, name: "Claude Code" },
  { icon: siOpenai, name: "Codex" },
  { icon: siGithubcopilot, name: "Copilot" },
];

export function AgentOnboard() {
  const [copied, setCopied] = useState(false);
  return (
    <div className="w-full max-w-[640px] rounded-card border border-white/15 bg-[#0d0d0e]/80 p-5 shadow-[0_20px_60px_-20px_rgb(0_0_0/0.8)] backdrop-blur-md">
      <div className="flex items-center justify-between gap-4">
        <p className="text-[15px] font-medium tracking-[-0.01em] text-ink">Onboard with your agent</p>
        <ul className="flex items-center gap-2.5 text-mute" aria-label="Works with">
          {AGENTS.map(({ icon, name }) => (
            <li key={name} title={name}>
              <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-label={name}>
                <path d={icon.path} />
              </svg>
            </li>
          ))}
        </ul>
      </div>
      <div className="mt-4 flex items-start gap-3 rounded-ctl border border-line bg-black/40 p-3.5">
        <p className="min-w-0 flex-1 font-mono text-[12.5px] leading-[1.6] text-ink-2">{PROMPT}</p>
        <button
          type="button"
          onClick={() => {
            navigator.clipboard?.writeText(PROMPT);
            setCopied(true);
            setTimeout(() => setCopied(false), 1800);
          }}
          className={cx(
            "inline-flex h-8 w-[84px] shrink-0 items-center justify-center gap-1.5 rounded-ctl border text-[13px] transition-colors duration-150",
            copied ? "border-ok/30 text-ok" : "border-line-strong bg-panel-2 text-ink hover:bg-raised",
          )}
        >
          {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <span role="status" className="sr-only">
        {copied ? "Setup prompt copied." : ""}
      </span>
    </div>
  );
}
