"use client";

import { useState } from "react";
import { api, ws, type Action, type ApiError } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { Disclosure } from "./bits";
import { Button, cx, inputClass } from "./ui";

const HINTS: Record<string, string> = {
  no_takedown_contact: "Add a contact for this site first: uv run tracefold add-takedown-contact <workspace> <host> --email abuse@<host>",
  remediation_profile_missing: 'Set who signs requests first: uv run tracefold set-remediation-profile <workspace> --company "..." --reply-to legal@...',
  aws_remediation_not_configured: "Add AWS remediation credentials to server/.env and restart the engine (see SETUP.md).",
  forbidden: "This app's token can't approve. Re-run tracefold quickstart.",
};

/** What will happen if you approve, in one sentence. */
function plan(a: Action): string {
  if (a.kind === "disable_aws_key") return `Turn off AWS key ${a.target.access_key_id} in IAM. Anything still using it will stop working. No new key is created.`;
  const d = a.delivery;
  if (d?.method === "email") return `Email ${d.address} asking them to remove the copy at ${a.target.url}.${d.transport === "outbox" ? " (Saved to the outbox, not sent.)" : ""}`;
  if (d?.method === "form") return `${a.target.host} only takes requests through its own form. You'll get the letter to paste there.`;
  return `Ask ${a.target.host} to remove the copy at ${a.target.url}. No contact is set up for this site yet.`;
}

/** What happened, in one sentence. */
function outcome(a: Action): string {
  const r = a.result;
  switch (a.status) {
    case "submitted":
      return a.removal_observed ? "Removed. A later scan no longer finds the text." : `Sent${r.sent_to ? ` to ${r.sent_to}` : ""}. Not confirmed removed yet.`;
    case "awaiting_manual_submission":
      return "Approved. Submit the letter on the site's form, then mark it sent.";
    case "completed":
      return `Key turned off${r.iam_user ? ` for ${r.iam_user}` : ""}.`;
    case "rejected":
      return `Rejected${r.reason ? `: ${r.reason}` : ""}.`;
    case "failed":
      return r.error?.message ?? "Failed.";
    default:
      return "";
  }
}

/** One drafted fix. Approving runs it right away; the app's token is the company's, so no per-person sign-off is asked for. */
export function ActionCard({ action, workspaceId, onChange }: { action: Action; workspaceId: string; workspaceName?: string; onChange: (a: Action) => void }) {
  const a = action;
  const [mode, setMode] = useState<"idle" | "reject">("idle");
  const [reason, setReason] = useState("");
  const [letter, setLetter] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = (s: string) => ws(workspaceId, `/actions/${a.action_id}${s}`);
  const open = a.status === "drafted" || a.status === "failed";

  async function call(s: string, method: "POST" | "PATCH", json: unknown) {
    setBusy(true);
    setError(null);
    try {
      const next = await api<Action>(path(s), { method, json });
      onChange(next);
      setMode("idle");
      window.dispatchEvent(new Event("tracefold:actions-changed"));
    } catch (e) {
      const err = e as ApiError;
      setError(HINTS[err.code] ?? err.message);
    } finally {
      setBusy(false);
    }
  }

  async function copyLetter() {
    try {
      await navigator.clipboard.writeText(`${a.subject ?? ""}\n\n${a.body ?? ""}`);
    } catch {}
  }

  return (
    <div className="rounded-card border border-line bg-panel p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[15px] text-ink">{a.summary}</p>
          <p className="mt-1 text-sm text-mute">{open ? plan(a) : outcome(a)}</p>
        </div>
        <span className="shrink-0 text-xs text-faint">{relativeTime(a.updated_at)}</span>
      </div>

      {a.kind === "takedown_request" && a.target.excerpt && (
        <p className="mt-3 border-l-2 border-line-strong pl-3 font-mono text-[13px] leading-relaxed text-ink-2">&ldquo;{a.target.excerpt}&rdquo;</p>
      )}

      {error && <p className="mt-3 text-sm text-crit">{error}</p>}

      {open && mode === "idle" && (
        <div className="mt-4 flex gap-2">
          <Button size="sm" className="!bg-accent !text-[#0a0c0c]" loading={busy} onClick={() => call("/approve", "POST", { expected_version: a.version })}>
            {a.status === "failed" ? "Try again" : a.kind === "disable_aws_key" ? "Turn off key" : a.delivery?.method === "form" ? "Approve" : "Send request"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setMode("reject")}>
            Reject
          </Button>
        </div>
      )}

      {open && mode === "reject" && (
        <form
          className="mt-4 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!reason.trim()) return setError("Say why, so the team knows.");
            call("/reject", "POST", { reason: reason.trim(), expected_version: a.version });
          }}
        >
          <input aria-label="Reason" placeholder="Why reject?" className={inputClass} value={reason} onChange={(e) => setReason(e.target.value)} />
          <Button size="sm" type="submit" variant="secondary" loading={busy}>
            Reject
          </Button>
        </form>
      )}

      {a.status === "awaiting_manual_submission" && (
        <div className="mt-4 flex flex-wrap gap-2">
          {typeof a.result.form_url === "string" && (
            <a href={a.result.form_url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center rounded-ctl border border-line-strong px-3 text-[13px] text-ink">
              Open the form
            </a>
          )}
          <Button size="sm" variant="secondary" onClick={copyLetter}>
            Copy letter
          </Button>
          <Button size="sm" variant="secondary" loading={busy} onClick={() => call("/mark-submitted", "POST", { expected_version: a.version })}>
            Mark as sent
          </Button>
        </div>
      )}

      {a.kind === "takedown_request" && a.body && (
        <Disclosure label="See the letter" className="mt-4">
          {letter === null ? (
            <>
              <pre className="mt-3 whitespace-pre-wrap rounded-ctl border border-line bg-bg p-4 font-sans text-[13px] leading-relaxed text-ink-2">{a.body}</pre>
              {open && (
                <button onClick={() => setLetter(a.draft_body ?? a.body ?? "")} className="mt-2 text-mute underline underline-offset-4 hover:text-ink">
                  Edit
                </button>
              )}
            </>
          ) : (
            <div className="mt-3">
              <textarea aria-label="Letter" rows={12} className={cx(inputClass, "h-auto py-2 font-sans text-[13px] leading-relaxed")} value={letter} onChange={(e) => setLetter(e.target.value)} />
              <div className="mt-2 flex gap-2">
                <Button size="sm" variant="secondary" loading={busy} onClick={() => call("", "PATCH", { body: letter, expected_version: a.version }).then(() => setLetter(null))}>
                  Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setLetter(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </Disclosure>
      )}
    </div>
  );
}
