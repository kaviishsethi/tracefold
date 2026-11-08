"use client";

import { useState } from "react";
import { Bot, Check } from "lucide-react";
import type { Finding } from "@/lib/api";
import { where } from "@/lib/format";
import { cx } from "./ui";

/** Copies a ready-made instruction for the user's coding agent, which reaches Tracefold through its MCP tools. */
export function AgentPrompt({ text, label = "Copy for your agent", className }: { text: string; label?: string; className?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      title={text}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1800);
        } catch {}
      }}
      className={cx(
        "inline-flex h-8 shrink-0 items-center gap-2 rounded-ctl border border-line-strong bg-panel px-3 text-[13px] text-ink transition-colors hover:bg-panel-2",
        className,
      )}
    >
      {done ? <Check className="size-3.5 text-local" aria-hidden /> : <Bot className="size-3.5 text-accent" aria-hidden />}
      {done ? "Copied" : label}
    </button>
  );
}

function place(f: Finding): string {
  const loc = f.latest?.evidence[0]?.location;
  const pos = loc ? where(loc) : "";
  return [f.path, pos].filter(Boolean).join(", ");
}

/** What to ask the agent for one finding. Uses the tracefold MCP tools; approving stays with a person. */
export function findingPrompt(f: Finding, publicUrl?: string | null): string {
  const id = f.finding_id;
  const at = place(f) || "a scanned file";
  if (f.kind === "public_exposure") {
    return [
      `Tracefold found text from ${at} on a public page${publicUrl ? ` (${publicUrl})` : ""}.`,
      `Call the tracefold tool explain_finding with finding_id "${id}" and include_evidence true, check whether this was meant to be public, and tell me what you find.`,
      "If a takedown request was drafted, leave approving it to me in the Tracefold app.",
    ].join(" ");
  }
  return [
    `Tracefold flagged "${f.latest?.title ?? "a risk"}" in ${at} (finding ${id}).`,
    f.latest?.suggested_fix ? `Suggested fix: ${f.latest.suggested_fix}` : "",
    `Fix it in the code, then call the tracefold tool recheck_fix with finding_id "${id}" and tell me the outcome.`,
    "Don't print or test any secret value you see.",
  ]
    .filter(Boolean)
    .join(" ");
}

/** One instruction to work through every open risk from a scan. */
export function scanPrompt(scanId: string): string {
  return [
    `Call the tracefold tool get_findings with scan_id "${scanId}".`,
    "For each finding under local_risk, fix it in the code, then call recheck_fix with its finding_id.",
    "For anything under public_exposure, call explain_finding and tell me what you find; leave takedown approvals to me.",
    "Finish with a short summary of each outcome. Don't print or test any secret value you see.",
  ].join(" ");
}
