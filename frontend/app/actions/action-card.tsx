"use client";

// Approval cards for remediation actions. Used by /actions and by the remediation panel on /findings/[id].
// Nothing is sent or changed until a named person approves here.

import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ArrowUpRight, Check, ChevronDown, Copy, ExternalLink, KeyRound, Mail, Pencil } from "lucide-react";
import { ACTION_STATUS_LABEL, ApiError, api, ws, type Action, type ActionStatus, type Page, type Workspace } from "@/lib/api";
import { host as hostOf, path as pathOf, relativeTime } from "@/lib/format";
import { Button, Field, cx, inputClass } from "@/components/ui";

// ---------- loading ----------

const ORDER: ActionStatus[] = ["drafted", "failed", "awaiting_manual_submission", "executing", "submitted", "completed", "rejected"];

export function sortActions(items: Action[]): Action[] {
  return [...items].sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status) || b.created_at.localeCompare(a.created_at));
}

/** Every action in a workspace (optionally for one finding). `unavailable` means the engine has no remediation endpoints. */
export function useActions(workspaceId: string | null, findingId?: string) {
  const [items, setItems] = useState<Action[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!workspaceId) return;
    let alive = true;
    (async () => {
      try {
        const all: Action[] = [];
        let cursor: string | null = null;
        do {
          const q = new URLSearchParams({ limit: "100" });
          if (findingId) q.set("finding_id", findingId);
          if (cursor) q.set("cursor", cursor);
          const page: Page<Action> = await api<Page<Action>>(ws(workspaceId, `/actions?${q}`));
          all.push(...page.items);
          cursor = page.next_cursor;
        } while (cursor);
        if (!alive) return;
        setItems(sortActions(all));
        setError(null);
        setUnavailable(false);
      } catch (e) {
        if (!alive) return;
        const err = e as ApiError;
        if (err.status === 404) setUnavailable(true);
        else setError(err);
      }
    })();
    return () => {
      alive = false;
    };
  }, [workspaceId, findingId, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const replace = useCallback((a: Action) => setItems((xs) => (xs ? xs.map((x) => (x.action_id === a.action_id ? a : x)) : xs)), []);
  return { items, error, unavailable, reload, replace };
}

// ---------- errors in the user's terms ----------

export function actionError(e: unknown, a: Action, workspaceId: string): { text: string; reload?: boolean } {
  const err = e as ApiError;
  const host = a.target.host ?? "this host";
  switch (err.code) {
    case "no_takedown_contact":
      return {
        text: `Add a takedown contact for ${host}: uv run tracefold add-takedown-contact ${workspaceId} ${host} --email <address> (or --form-url <url> if the host only takes its web form).`,
      };
    case "remediation_profile_missing":
      return {
        text: `Set your company details first. They sign the letter: uv run tracefold set-remediation-profile ${workspaceId} --company "<name>" --reply-to <email>`,
      };
    case "aws_remediation_not_configured":
      return {
        text: "The engine has no AWS remediation credentials. Set TRACEFOLD_AWS_REMEDIATION_ACCESS_KEY_ID and TRACEFOLD_AWS_REMEDIATION_SECRET_ACCESS_KEY for a remediation IAM principal, restart the engine, then approve again.",
      };
    case "version_conflict":
      return { text: "Someone changed this action while you had it open. Reload to see the latest version.", reload: true };
    case "invalid_state":
      return { text: `${err.message} Reload to see where it stands.`, reload: true };
    case "attestation_required":
      return { text: "Tick the box to confirm you're authorized before approving." };
  }
  if (err.status === 403) return { text: "This app's access grant can't approve or change actions. Ask the operator to add the approve capability." };
  return { text: err.message || "Something went wrong." };
}

// ---------- small pieces ----------

const STATUS_TONE: Record<ActionStatus, string> = {
  drafted: "border-accent/30 bg-accent/10 text-accent",
  awaiting_manual_submission: "border-med/25 bg-med/10 text-med",
  executing: "border-line-strong bg-panel-2 text-ink",
  submitted: "border-line-strong bg-panel-2 text-ink",
  completed: "border-ok/25 bg-ok/10 text-ok",
  failed: "border-crit/25 bg-crit/10 text-crit",
  rejected: "border-line text-faint",
};

export function ActionStatusPill({ status }: { status: ActionStatus }) {
  return (
    <span className={cx("inline-flex h-6 items-center rounded-md border px-2 text-xs font-medium whitespace-nowrap", STATUS_TONE[status])}>
      {ACTION_STATUS_LABEL[status]}
    </span>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1 py-2 sm:grid-cols-[112px_1fr] sm:gap-3">
      <dt className="text-[13px] text-faint">{label}</dt>
      <dd className="min-w-0 text-[13px] text-ink-2">{children}</dd>
    </div>
  );
}

function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono text-[12.5px] text-ink">{children}</span>;
}

const ACCENT = "bg-accent! text-[#0a0a0a]! hover:bg-[#ff9450]!";
const linkBtn =
  "inline-flex h-8 shrink-0 items-center justify-center gap-2 rounded-ctl border border-[#454541] bg-panel-2 px-3 text-[13px] font-medium whitespace-nowrap text-ink transition-colors duration-200 hover:border-[#5a5a55] hover:bg-raised";

const SIG_MARK = "\n\n[Signed by the approver when this request is approved]";
/** The engine returns the rendered letter, with a signature block it adds itself. Edit only the part above it. */
function editableBody(body: string): string {
  const i = body.indexOf(SIG_MARK);
  return i >= 0 ? body.slice(0, i) : body;
}

const APPROVER_KEY = "tracefold.approver";
function storedApprover(): { name: string; email: string; title: string } {
  try {
    const v = JSON.parse(localStorage.getItem(APPROVER_KEY) ?? "null");
    if (v && typeof v.name === "string") return { name: v.name, email: v.email ?? "", title: v.title ?? "" };
  } catch {}
  return { name: "", email: "", title: "" };
}
function storeApprover(v: { name: string; email: string; title: string }) {
  try {
    localStorage.setItem(APPROVER_KEY, JSON.stringify(v));
  } catch {}
}

function Delivery({ a }: { a: Action }) {
  const d = a.delivery;
  if (!d || d.method === "none")
    return <span className="text-med">No contact configured for {a.target.host}. Add one before approving.</span>;
  if (d.method === "email")
    return (
      <span>
        Will email <Mono>{d.address}</Mono>
        {d.transport === "outbox" ? " via the local outbox (written to a file, nothing leaves this machine)" : d.transport ? ` via ${d.transport}` : ""}
        {d.transport === "resend_not_configured" && <span className="text-med"> · Resend isn&apos;t configured on the engine</span>}
      </span>
    );
  return (
    <span>
      Host only accepts its web form
      {d.form_url && (
        <>
          {" "}
          at{" "}
          <a href={d.form_url} target="_blank" rel="noreferrer" className="font-mono text-[12.5px] text-ink hover:underline">
            {hostOf(d.form_url)}
            {pathOf(d.form_url)}
          </a>
        </>
      )}
      . Approving gives you the text to paste there.
    </span>
  );
}

/** What happened after approval, from the engine's own result. */
function Outcome({ a }: { a: Action }) {
  const r = a.result ?? {};
  const s = (k: string) => (typeof r[k] === "string" ? (r[k] as string) : null);
  const rows: ReactNode[] = [];
  if (a.approver?.name)
    rows.push(
      <Row key="by" label="Approved by">
        {a.approver.name}
        {a.approver.title ? `, ${a.approver.title}` : ""}
        {a.approver.email && <span className="text-faint"> · {a.approver.email}</span>}
        {a.approved_at && (
          <span className="text-faint" title={a.approved_at}>
            {" "}
            · {relativeTime(a.approved_at)}
          </span>
        )}
      </Row>,
    );
  if (s("sent_to"))
    rows.push(
      <Row key="to" label="Sent to">
        <Mono>{s("sent_to")}</Mono>
        {s("transport") && <span className="text-faint"> via {s("transport")}</span>}
      </Row>,
    );
  if (s("outbox_file"))
    rows.push(
      <Row key="ob" label="Outbox file">
        <Mono>{s("outbox_file")}</Mono>
      </Row>,
    );
  if (s("message_id"))
    rows.push(
      <Row key="mid" label="Message ID">
        <Mono>{s("message_id")}</Mono>
      </Row>,
    );
  if (s("submitted_via") === "host_form")
    rows.push(
      <Row key="form" label="Submitted">
        On the host&apos;s web form{s("note") ? `: ${s("note")}` : ""}
      </Row>,
    );
  if (s("iam_user"))
    rows.push(
      <Row key="iam" label="IAM user">
        <Mono>{s("iam_user")}</Mono>
      </Row>,
    );
  if (s("aws_status"))
    rows.push(
      <Row key="aws" label="Key status">
        {s("aws_status")}
      </Row>,
    );
  if (a.status === "rejected")
    rows.push(
      <Row key="rej" label="Rejected">
        {s("reason") ?? "No reason given"}
        {s("rejected_by") && <span className="text-faint"> · by {s("rejected_by")}</span>}
      </Row>,
    );
  if (a.status === "failed" && r.error)
    rows.push(
      <Row key="err" label="Error">
        <span className="text-crit">{r.error.message}</span> <span className="font-mono text-[11px] text-faint">{r.error.code}</span>
      </Row>,
    );
  if (a.kind === "takedown_request" && (a.status === "submitted" || a.status === "awaiting_manual_submission"))
    rows.push(
      <Row key="rm" label="Removal">
        {a.removal_observed ? (
          <span className="text-ok">A later public scan no longer found the text at this URL.</span>
        ) : a.status === "submitted" ? (
          "Submitted, not yet confirmed removed. A fresh public scan will show whether the text is gone."
        ) : (
          "Not submitted yet."
        )}
      </Row>,
    );
  if (!rows.length) return null;
  return <dl className="divide-y divide-line border-t border-line px-4 py-1">{rows}</dl>;
}

// ---------- the card ----------

export function ActionCard({
  action: a,
  workspace,
  onChange,
  onReload,
  showFindingLink = true,
}: {
  action: Action;
  workspace: Workspace;
  onChange: (a: Action) => void;
  onReload: () => void;
  showFindingLink?: boolean;
}) {
  const canApprove = workspace.capabilities.includes("approve");
  const decidable = a.status === "drafted" || a.status === "failed";
  const [mode, setMode] = useState<null | "approve" | "reject" | "edit" | "submitted">(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<{ text: string; reload?: boolean } | null>(null);
  const [copied, setCopied] = useState(false);

  // approve
  const [who, setWho] = useState({ name: "", email: "", title: "" });
  const [attest, setAttest] = useState(false);
  // reject
  const [reason, setReason] = useState("");
  // edit
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  // mark submitted
  const [note, setNote] = useState("");

  const p = (suffix: string) => ws(workspace.id, `/actions/${encodeURIComponent(a.action_id)}${suffix}`);

  async function run(fn: () => Promise<Action>) {
    setBusy(true);
    setErr(null);
    try {
      onChange(await fn());
      setMode(null);
    } catch (e) {
      setErr(actionError(e, a, workspace.id));
    } finally {
      setBusy(false);
    }
  }

  function open(m: typeof mode) {
    setErr(null);
    setMode(m);
    if (m === "approve") {
      setWho(storedApprover());
      setAttest(false);
    }
    if (m === "reject") setReason("");
    if (m === "edit") {
      setSubject(a.subject ?? "");
      setBody(a.draft_body ?? editableBody(a.body ?? "")); // draft_body: raw editable text from newer engines
    }
    if (m === "submitted") setNote("");
  }

  const approve = () => {
    const approver = { name: who.name.trim(), email: who.email.trim(), ...(who.title.trim() ? { title: who.title.trim() } : {}) };
    storeApprover({ name: approver.name, email: approver.email, title: who.title.trim() });
    return run(() => api<Action>(p("/approve"), { method: "POST", json: { approver, attest_authorized: attest, expected_version: a.version } }));
  };

  const isTakedown = a.kind === "takedown_request";
  const keyId = a.target.access_key_id ?? "(masked)";
  const company = workspace.name;
  const formUrl = (typeof a.result?.form_url === "string" ? a.result.form_url : null) ?? a.delivery?.form_url ?? null;

  return (
    <article className="overflow-hidden rounded-card border border-line bg-panel shadow-[0_12px_32px_rgb(0_0_0/0.2)]">
      <header className="flex min-h-11 flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md border border-line bg-panel-2">
            {isTakedown ? <Mail className="size-3.5 text-mute" aria-hidden /> : <KeyRound className="size-3.5 text-mute" aria-hidden />}
          </span>
          <h3 className="truncate text-[13px] font-medium text-ink">{isTakedown ? a.summary : `Disable AWS access key ${keyId}`}</h3>
          <span className="hidden truncate text-xs text-faint sm:inline" title={a.created_at}>
            drafted {relativeTime(a.created_at)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {showFindingLink && (
            <Link href={`/findings/${a.finding_id}`} className="inline-flex items-center gap-1 text-xs text-mute hover:text-ink">
              Finding <ArrowUpRight className="size-3" aria-hidden />
            </Link>
          )}
          <ActionStatusPill status={a.status} />
        </div>
      </header>

      {isTakedown ? (
        <div className="px-4 py-2">
          <dl className="divide-y divide-line">
            <Row label="Page">
              {a.target.url ? (
                <a href={a.target.url} target="_blank" rel="noreferrer" className="group inline-flex max-w-full items-center gap-1.5 font-mono text-[12.5px]">
                  <span className="shrink-0 text-ink">{a.target.host ?? hostOf(a.target.url)}</span>
                  <span className="truncate text-faint">{pathOf(a.target.url)}</span>
                  <ExternalLink className="size-3.5 shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
                </a>
              ) : (
                <span className="text-faint">{a.target.host ?? "–"}</span>
              )}
            </Row>
            <Row label="Copied text">
              {a.target.excerpt ? (
                <blockquote className="rounded-ctl border border-line bg-[#0b0b0b] px-3 py-2 font-mono text-[12px] leading-5 text-ink-2">{a.target.excerpt}</blockquote>
              ) : (
                <span className="text-faint">Withheld under this app&apos;s disclosure policy.</span>
              )}
              {a.target.retrieved_at && (
                <span className="mt-1 block text-xs text-faint" title={a.target.retrieved_at}>
                  As retrieved {relativeTime(a.target.retrieved_at)}
                </span>
              )}
            </Row>
            <Row label="Delivery">
              <Delivery a={a} />
            </Row>
          </dl>
          {a.body != null ? (
            <details className="group mb-2 mt-1">
              <summary className="flex cursor-pointer list-none items-center gap-1.5 py-1.5 text-[13px] text-mute hover:text-ink">
                <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden />
                Full letter
              </summary>
              <div className="mt-1 rounded-ctl border border-line bg-[#0b0b0b]">
                {a.subject && (
                  <p className="border-b border-line px-3 py-2 text-[12.5px] text-ink">
                    <span className="text-faint">Subject </span>
                    {a.subject}
                  </p>
                )}
                <pre className="scroll-thin max-h-96 overflow-auto whitespace-pre-wrap px-3 py-3 font-mono text-[12px] leading-5 text-ink-2">{a.body}</pre>
              </div>
            </details>
          ) : (
            <p className="mb-2 mt-1 text-xs text-faint">The letter is withheld under this app&apos;s disclosure policy.</p>
          )}
        </div>
      ) : (
        <div className="px-4 py-3 text-[13px] leading-relaxed text-mute">
          <p>
            Approving sets <Mono>{keyId}</Mono> to <span className="text-ink">Inactive</span> in IAM, using your company&apos;s remediation
            credentials. The leaked key itself is never used.
          </p>
          <p className="mt-1.5">No new key is created. Anything still using this key will stop working until you issue and deploy a replacement.</p>
        </div>
      )}

      <Outcome a={a} />

      {/* manual form submission */}
      {a.status === "awaiting_manual_submission" && (
        <div className="space-y-3 border-t border-line px-4 py-3">
          <p className="text-[13px] text-mute">Approved. This host only takes requests on its own web form: paste the letter there, then mark it submitted.</p>
          <div className="flex flex-wrap gap-2">
            {formUrl && (
              <a href={formUrl} target="_blank" rel="noreferrer" className={linkBtn}>
                Open the form <ExternalLink className="size-3.5" aria-hidden />
              </a>
            )}
            {a.body != null && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  navigator.clipboard?.writeText([a.subject, a.body].filter(Boolean).join("\n\n"));
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1800);
                }}
              >
                {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
                {copied ? "Copied" : "Copy letter"}
              </Button>
            )}
            {canApprove && mode !== "submitted" && (
              <Button size="sm" onClick={() => open("submitted")}>
                Mark as submitted
              </Button>
            )}
          </div>
          {mode === "submitted" && (
            <form
              className="flex flex-col gap-2 sm:flex-row sm:items-end"
              onSubmit={(e) => {
                e.preventDefault();
                run(() => api<Action>(p("/mark-submitted"), { method: "POST", json: { note: note.trim() || null, expected_version: a.version } }));
              }}
            >
              <div className="flex-1">
                <Field label="Note (optional)">
                  <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Confirmation number, ticket link…" maxLength={500} />
                </Field>
              </div>
              <div className="flex gap-2">
                <Button type="submit" loading={busy}>
                  Confirm submitted
                </Button>
                <Button type="button" variant="ghost" onClick={() => setMode(null)}>
                  Cancel
                </Button>
              </div>
            </form>
          )}
        </div>
      )}

      {/* edit letter */}
      {mode === "edit" && (
        <form
          className="space-y-3 border-t border-line px-4 py-3"
          onSubmit={(e) => {
            e.preventDefault();
            run(() => api<Action>(p(""), { method: "PATCH", json: { subject: subject.trim() || null, body: body.trim() ? body : null, expected_version: a.version } }));
          }}
        >
          <Field label="Subject">
            <input className={inputClass} value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={200} />
          </Field>
          <Field label="Letter" hint="Your name, title and company are signed at the bottom when you approve.">
            <textarea
              className={cx(inputClass, "h-72 resize-y py-2.5 font-mono text-[12.5px] leading-5")}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              maxLength={5000}
            />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={busy} disabled={!subject.trim() || !body.trim()}>
              Save letter
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setMode(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {/* approve */}
      {mode === "approve" && (
        <form
          className="space-y-3 border-t border-line bg-panel-2/40 px-4 py-4"
          onSubmit={(e) => {
            e.preventDefault();
            approve();
          }}
        >
          <p className="text-[13px] text-ink">
            {isTakedown
              ? a.delivery?.method === "email"
                ? `Sign and send this request to ${a.delivery.address}.`
                : a.delivery?.method === "form"
                  ? "Sign this request. You'll paste it into the host's web form next."
                  : "Sign this request."
              : `Set ${keyId} to Inactive in IAM now.`}
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Your name">
              <input className={inputClass} required autoComplete="name" value={who.name} onChange={(e) => setWho({ ...who, name: e.target.value })} />
            </Field>
            <Field label="Work email">
              <input
                className={inputClass}
                required
                type="email"
                autoComplete="email"
                value={who.email}
                onChange={(e) => setWho({ ...who, email: e.target.value })}
              />
            </Field>
            <Field label="Title (optional)">
              <input className={inputClass} autoComplete="organization-title" value={who.title} onChange={(e) => setWho({ ...who, title: e.target.value })} />
            </Field>
          </div>
          <label className="flex items-start gap-2.5 text-[13px] text-ink-2">
            <input type="checkbox" required checked={attest} onChange={(e) => setAttest(e.target.checked)} className="mt-0.5 size-4 accent-[#fd802e]" />
            <span>I&apos;m authorized to act for {company} and confirm this request is accurate.</span>
          </label>
          <div className="flex gap-2">
            <Button type="submit" loading={busy} disabled={!who.name.trim() || !who.email.trim() || !attest} className={ACCENT}>
              {isTakedown ? (a.delivery?.method === "email" ? "Approve and send" : "Approve") : "Approve and disable key"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setMode(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {/* reject */}
      {mode === "reject" && (
        <form
          className="flex flex-col gap-2 border-t border-line px-4 py-3 sm:flex-row sm:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            run(() => api<Action>(p("/reject"), { method: "POST", json: { reason: reason.trim(), expected_version: a.version } }));
          }}
        >
          <div className="flex-1">
            <Field label="Why reject this?">
              <input className={inputClass} required value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Not our content, already handled…" maxLength={500} />
            </Field>
          </div>
          <div className="flex gap-2">
            <Button type="submit" variant="danger" loading={busy} disabled={!reason.trim()}>
              Reject
            </Button>
            <Button type="button" variant="ghost" onClick={() => setMode(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {err && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-2 border-t border-crit/25 bg-crit/10 px-4 py-2.5 text-[13px] text-crit">
          <span className="min-w-0 break-words">{err.text}</span>
          {err.reload && (
            <Button size="sm" variant="secondary" onClick={onReload}>
              Reload
            </Button>
          )}
        </div>
      )}

      {/* decision bar */}
      {decidable && mode === null && (
        <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3">
          {canApprove ? (
            <>
              <span className="text-xs text-faint">{a.status === "failed" ? "The last attempt failed. You can approve again." : "Nothing is sent or changed until you approve."}</span>
              <div className="flex items-center gap-2">
                {isTakedown && a.body != null && (
                  <Button variant="ghost" size="sm" onClick={() => open("edit")}>
                    <Pencil className="size-3.5" aria-hidden /> Edit letter
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => open("reject")}>
                  Reject
                </Button>
                <Button size="sm" className={ACCENT} onClick={() => open("approve")}>
                  Approve
                </Button>
              </div>
            </>
          ) : (
            <span className="text-xs text-faint">This app&apos;s access grant can&apos;t approve actions. Someone with approve access needs to sign off.</span>
          )}
        </footer>
      )}
    </article>
  );
}
