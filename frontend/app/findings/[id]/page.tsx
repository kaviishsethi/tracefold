"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ExternalLink, FileWarning, Globe, Upload } from "lucide-react";
import {
  RECHECK_LABEL,
  RISK_REVIEW_LABEL,
  STATE_MEANING,
  api,
  isTerminal,
  uploadFiles,
  useScan,
  ws,
  type ApiError,
  type Evidence,
  type Finding,
  type FindingDetail,
  type Observation,
  type RecheckAccepted,
  type Workspace,
} from "@/lib/api";
import { host, path as urlPath, relativeTime, shortId, where } from "@/lib/format";
import { useCrumb, useCurrentWorkspace } from "@/components/shell";
import { Button, Empty, ErrorNote, Field, Loading, Panel, SeverityBadge, StatusPill, cx, inputClass } from "@/components/ui";
import { ActionCard, useActions } from "../../actions/action-card";

const KIND_LABEL = { public_exposure: "Public exposure", local_risk: "Potential risk in your files" } as const;
const ORIGIN_LABEL = { matcher: "Public matcher", rule: "Rule", model: "Model suggestion, needs review" } as const;
const REVIEW_LABEL = { unreviewed: "Not reviewed yet", acknowledged: "Acknowledged", dismissed: "Dismissed" } as const;

function Redacted({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\[[A-Z0-9_-]+\])/g).map((p, i) =>
        /^\[[A-Z0-9_-]+\]$/.test(p) ? (
          <span key={i} className="rounded border border-local-line bg-local-bg px-1 text-local">
            {p}
          </span>
        ) : (
          p
        ),
      )}
    </>
  );
}

function Prop({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_1fr] items-center gap-3 py-2">
      <dt className="text-[13px] text-faint">{label}</dt>
      <dd className="min-w-0 text-[13px] text-ink">{children}</dd>
    </div>
  );
}

function Section({ title, meta, action, children }: { title: string; meta?: ReactNode; action?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-medium tracking-normal text-ink">
          {title}
          {meta != null && <span className="ml-2 font-normal text-faint">{meta}</span>}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function Explain({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="px-4 py-3">
      <p className="text-xs text-faint">{label}</p>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{children}</p>
    </div>
  );
}

// ---------- evidence ----------

const codeBox = "scroll-thin max-h-80 overflow-auto whitespace-pre-wrap rounded-ctl border border-line bg-[#0b0b0b] px-3 py-3 font-mono text-[12.5px] leading-6 text-ink-2";

function EvidenceText({ text, missing }: { text: string | null; missing: string }) {
  return <pre className={codeBox}>{text ? <Redacted text={text} /> : <span className="text-faint">{missing}</span>}</pre>;
}

function EvidenceBlock({ workspaceId, refEv }: { workspaceId: string; refEv: Evidence }) {
  const [ev, setEv] = useState<Evidence | null>(null);
  const [err, setErr] = useState<ApiError | null>(null);

  useEffect(() => {
    let alive = true;
    api<Evidence>(ws(workspaceId, `/evidence/${encodeURIComponent(refEv.evidence_id)}`))
      .then((e) => alive && setEv(e))
      .catch((e) => alive && setErr(e as ApiError));
    return () => {
      alive = false;
    };
  }, [workspaceId, refEv.evidence_id]);

  const e = ev ?? refEv;
  const loc = e.location;
  const at = where(loc);
  const withheld = err?.status === 403 || e.availability === "withheld_by_policy";
  const unavailable = e.availability === "evidence_unavailable";
  const missing = withheld
    ? err?.status === 403
      ? "Evidence text needs the read_evidence capability, which this app's grant doesn't have."
      : "Evidence text is withheld under this app's disclosure policy."
    : unavailable
      ? "The engine no longer has this evidence text."
      : err
        ? `Couldn't load evidence: ${err.message}`
        : !ev
          ? "Loading…"
          : "No text for this span.";

  const fileHead = (
    <p className="mb-2 truncate font-mono text-xs text-mute">
      {loc.path ?? "Path withheld"}
      {at && <span className="text-faint"> · {at}</span>}
    </p>
  );

  if (e.kind === "public_match" && e.public) {
    const pub = e.public;
    return (
      <div className="rounded-card border border-line bg-panel p-4">
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="min-w-0">
            <p className="mb-1 text-xs text-faint">Your file</p>
            {fileHead}
            <EvidenceText text={e.local_text} missing={missing} />
          </div>
          <div className="min-w-0">
            <p className="mb-1 text-xs text-faint">Public page</p>
            <a href={pub.url} target="_blank" rel="noreferrer" className="group mb-2 flex min-w-0 items-center gap-1.5 font-mono text-xs">
              <span className="shrink-0 text-ink">{host(pub.url)}</span>
              <span className="truncate text-faint">{urlPath(pub.url)}</span>
              <ExternalLink className="size-3.5 shrink-0 text-faint opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
            </a>
            <EvidenceText text={e.public_text} missing={missing} />
          </div>
        </div>
        <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-faint">
          <span title={pub.retrieved_at ?? undefined}>
            {pub.freshness === "cached" ? (
              <span className="text-med">Cached copy retrieved {pub.retrieved_at ? relativeTime(pub.retrieved_at) : "at an unknown time"}</span>
            ) : (
              <>Retrieved {pub.retrieved_at ? relativeTime(pub.retrieved_at) : "–"}</>
            )}
          </span>
          {e.matched_tokens != null && <span>{e.matched_tokens} matching tokens</span>}
          {e.segment_coverage != null && <span>{Math.round(e.segment_coverage * 100)}% of the passage</span>}
          {pub.mode === "discovered" && pub.discovery_origins?.length ? (
            <span>
              Found by search: {pub.discovery_origins.map((o) => `${o.provider} ${o.query_id} #${o.rank}`).join(", ")}
              {pub.provider ? ` · fetched via ${pub.provider}` : ""}
            </span>
          ) : (
            <span>Source {pub.source_id}</span>
          )}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-card border border-line bg-panel p-4">
      {fileHead}
      <EvidenceText text={e.local_text} missing={missing} />
      {e.rule_id && <p className="mt-2 text-xs text-faint">Rule {e.rule_id}</p>}
    </div>
  );
}

// ---------- recheck ----------

function Recheck({ workspace, f, onDone }: { workspace: Workspace; f: FindingDetail; onDone: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [acc, setAcc] = useState<RecheckAccepted | null>(null);
  const { scan, error: pollErr } = useScan(acc ? workspace.id : null, acc?.scan_id ?? null);
  const finished = scan ? isTerminal(scan.state) : false;
  const notified = useRef<string | null>(null);

  useEffect(() => {
    if (finished && acc && notified.current !== acc.scan_id) {
      notified.current = acc.scan_id;
      onDone();
    }
  }, [finished, acc, onDone]);

  const canRecheck = workspace.capabilities.includes("recheck");
  const result = acc ? f.rechecks.find((r) => r.recheck_id === acc.recheck_id) : null;

  async function start() {
    setBusy(true);
    setErr(null);
    setAcc(null);
    try {
      const input = await uploadFiles(workspace.id, files);
      setAcc(await api<RecheckAccepted>(ws(workspace.id, `/findings/${encodeURIComponent(f.finding_id)}/rechecks`), { method: "POST", json: { input_id: input.input_id } }));
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel>
      <div className="space-y-3 p-4 text-[13px]">
        <p className="text-mute">
          Upload the edited version of {f.path ? <span className="font-mono text-ink-2">{f.path}</span> : "the file"}. The engine checks only this finding against it.
        </p>
        {f.kind === "public_exposure" && (
          <p className="rounded-ctl border border-line bg-panel-2 px-3 py-2 text-xs leading-relaxed text-mute">
            A local recheck never closes a public exposure. That only changes when a fresh public scan no longer finds the text.
          </p>
        )}
        {canRecheck ? (
          <>
            <input ref={fileRef} type="file" multiple className="sr-only" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
                <Upload className="size-3.5" aria-hidden /> {files.length ? "Change file" : "Choose file"}
              </Button>
              {files.length > 0 && (
                <span className="truncate text-xs text-mute">
                  {files.map((x) => x.name).join(", ")}
                </span>
              )}
            </div>
            <Button size="sm" disabled={!files.length || (!!acc && !finished)} loading={busy} onClick={start}>
              Recheck
            </Button>
          </>
        ) : (
          <p className="text-xs text-faint">This app&apos;s access grant can&apos;t run rechecks.</p>
        )}
        {err && <p className="text-crit">{err}</p>}
        {pollErr && <p className="text-crit">{pollErr.message}</p>}
        {acc && !finished && (
          <p className="text-mute" aria-live="polite">
            {scan?.state === "queued" ? "Waiting to run…" : "Rechecking…"}
          </p>
        )}
        {acc && finished && (
          <div aria-live="polite" className="rounded-ctl border border-line px-3 py-2.5">
            {result?.outcome ? (
              <>
                <p className={cx("font-medium", result.outcome === "still_detected" ? "text-crit" : result.outcome === "inconclusive" ? "text-med" : "text-local")}>
                  {RECHECK_LABEL[result.outcome]}
                </p>
                {result.reason && <p className="mt-1 text-mute">{result.reason}</p>}
              </>
            ) : (
              <p className="text-mute">{scan ? STATE_MEANING[scan.state] : "Recheck finished."}</p>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}

// ---------- human review ----------

function Review({ workspaceId, f, onChange, onConflict }: { workspaceId: string; f: FindingDetail; onChange: (x: Finding) => void; onConflict: () => void }) {
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function send(state: "acknowledged" | "dismissed") {
    setBusy(true);
    setErr(null);
    try {
      onChange(
        await api<Finding>(ws(workspaceId, `/findings/${encodeURIComponent(f.finding_id)}/review`), {
          method: "PATCH",
          json: { state, reason: state === "dismissed" ? reason.trim() : null, expected_version: f.version },
        }),
      );
      setDismissing(false);
    } catch (e) {
      const x = e as ApiError;
      if (x.code === "version_conflict") {
        setErr("This finding changed since you opened it. Reloaded; try again.");
        onConflict();
      } else setErr(x.status === 403 ? "This app's access grant can't review findings." : x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-2">
      {dismissing ? (
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            send("dismissed");
          }}
        >
          <Field label="Why dismiss it?">
            <textarea
              className={cx(inputClass, "h-20 resize-none py-2")}
              required
              maxLength={500}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Test fixture, false positive…"
            />
          </Field>
          <div className="flex gap-2">
            <Button size="sm" type="submit" className="flex-1" loading={busy} disabled={!reason.trim()}>
              Dismiss
            </Button>
            <Button size="sm" type="button" variant="ghost" onClick={() => setDismissing(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex gap-2">
          {f.human_review !== "acknowledged" && (
            <Button size="sm" variant="secondary" className="flex-1" loading={busy} onClick={() => send("acknowledged")}>
              Acknowledge
            </Button>
          )}
          {f.human_review !== "dismissed" && (
            <Button size="sm" variant="ghost" className="flex-1" disabled={busy} onClick={() => setDismissing(true)}>
              Dismiss
            </Button>
          )}
        </div>
      )}
      {err && <p className="text-[13px] text-crit">{err}</p>}
    </div>
  );
}

// ---------- remediation ----------

function Remediation({ workspace, findingId }: { workspace: Workspace; findingId: string }) {
  const { items, error, unavailable, reload, replace } = useActions(workspace.id, findingId);
  if (unavailable) return <p className="text-[13px] text-mute">Approvals need an engine with remediation enabled. This one doesn&apos;t draft actions.</p>;
  if (error) return <ErrorNote error={error.message} />;
  if (!items) return <Loading />;
  if (!items.length)
    return (
      <p className="rounded-card border border-dashed border-line px-4 py-6 text-center text-[13px] text-mute">
        No actions drafted for this finding. The engine drafts takedown requests for public exposures and key disables for leaked AWS access keys.
      </p>
    );
  return (
    <div className="space-y-4">
      {items.map((a) => (
        <ActionCard key={a.action_id} action={a} workspace={workspace} onChange={replace} onReload={reload} showFindingLink={false} />
      ))}
    </div>
  );
}

// ---------- history ----------

function History({ f }: { f: FindingDetail }) {
  type Item = { at: string; text: ReactNode };
  const items: Item[] = [
    ...f.observations.map((o: Observation) => ({
      at: o.created_at,
      text: (
        <>
          Observed in scan <span className="font-mono text-xs text-mute">{shortId(o.scan_id)}</span>
          {o.revision ? <span className="text-faint"> · revision {o.revision}</span> : null}
          {o.severity && <span className="text-faint"> · {o.severity}</span>}
        </>
      ),
    })),
    ...f.rechecks.map((r) => ({
      at: r.created_at,
      text: (
        <>
          Recheck: {r.outcome ? RECHECK_LABEL[r.outcome] : "running or didn't finish"}
          {r.reason && <span className="text-faint"> · {r.reason}</span>}
        </>
      ),
    })),
  ].sort((a, b) => b.at.localeCompare(a.at));

  if (!items.length) return <p className="text-[13px] text-mute">No history yet.</p>;
  return (
    <ol>
      {items.map((a, i) => (
        <li key={i} className="relative flex gap-3 pb-5 last:pb-0">
          {i < items.length - 1 && <span className="absolute left-[3px] top-3 h-full w-px bg-line" aria-hidden />}
          <span className="mt-1.5 size-[7px] shrink-0 rounded-full border border-line-strong bg-raised" />
          <p className="text-[13px] text-ink-2">
            {a.text}
            <span className="ml-2 text-faint" title={a.at}>
              {relativeTime(a.at)}
            </span>
          </p>
        </li>
      ))}
    </ol>
  );
}

// ---------- page ----------

export default function FindingPage() {
  const { id } = useParams<{ id: string }>();
  const { current } = useCurrentWorkspace();
  const [f, setF] = useState<FindingDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useCrumb(f?.latest?.title ?? (f ? shortId(f.finding_id) : null));

  const load = useCallback(() => {
    if (!current) return;
    api<FindingDetail>(ws(current.id, `/findings/${encodeURIComponent(id)}`))
      .then((x) => {
        setF(x);
        setError(null);
      })
      .catch((e) => setError((e as ApiError).status === 404 ? "This finding doesn't exist in the current workspace." : (e as ApiError).message));
  }, [current, id]);

  useEffect(load, [load]);

  if (!current) return <Empty title="No workspace">This app&apos;s access grant doesn&apos;t cover a workspace yet.</Empty>;
  if (!f) return error ? <ErrorNote error={error} /> : <Loading />;

  const o = f.latest;
  const Icon = f.kind === "public_exposure" ? Globe : FileWarning;
  const explained = o && [o.conditions, o.missing_context, o.uncertainty, o.counterevidence, o.severity_rationale].some(Boolean);
  const loc = o?.evidence[0]?.location;

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0 space-y-9">
        <header>
          <p className="mb-2 text-xs text-faint">{KIND_LABEL[f.kind]}</p>
          <div className="flex items-center gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-ctl border border-line bg-panel-2">
              <Icon className="size-4 text-ink-2" aria-hidden />
            </span>
            <h1 className="text-[24px] leading-tight tracking-[-0.03em] text-ink">{o?.title ?? f.check_id}</h1>
          </div>
          {o?.claim ? (
            <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-mute">{o.claim}</p>
          ) : (
            <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-faint">The explanation is withheld under this app&apos;s disclosure policy, or wasn&apos;t written.</p>
          )}
          {o?.origin === "model" && (
            <p className="mt-2 text-[13px] text-med">This is a model-only suggestion. It hasn&apos;t been confirmed by a rule and needs your review.</p>
          )}
          {error && (
            <div className="mt-4">
              <ErrorNote error={error} />
            </div>
          )}
        </header>

        {explained && o && (
          <Section title="Why it was flagged">
            <Panel bodyClassName="divide-y divide-line">
              {o.conditions && <Explain label="When it's a problem">{o.conditions}</Explain>}
              {o.uncertainty && <Explain label="What's uncertain">{o.uncertainty}</Explain>}
              {o.missing_context && <Explain label="Context the review didn't have">{o.missing_context}</Explain>}
              {o.counterevidence && <Explain label="Evidence against it">{o.counterevidence}</Explain>}
              {o.severity_rationale && <Explain label="Why this severity">{o.severity_rationale}</Explain>}
            </Panel>
          </Section>
        )}

        <Section title="Evidence" meta={o?.evidence.length ?? 0}>
          {o?.evidence.length ? (
            <div className="space-y-3">
              {o.evidence.map((e) => (
                <EvidenceBlock key={e.evidence_id} workspaceId={current.id} refEv={e} />
              ))}
            </div>
          ) : (
            <p className="text-[13px] text-mute">No evidence attached to the latest observation.</p>
          )}
          <p className="mt-2 text-xs text-faint">Secret values are masked by the engine before evidence is stored or shown.</p>
        </Section>

        <div className="grid gap-6 lg:grid-cols-2">
          <Section title="Suggested fix">
            <Panel>
              {o?.suggested_fix || o?.verification_step ? (
                <div className="divide-y divide-line">
                  {o.suggested_fix && <Explain label="What to change">{o.suggested_fix}</Explain>}
                  {o.verification_step && <Explain label="How to check it">{o.verification_step}</Explain>}
                </div>
              ) : (
                <p className="p-4 text-[13px] text-mute">No suggested fix for this finding.</p>
              )}
            </Panel>
          </Section>

          <Section title="Recheck">
            <Recheck workspace={current} f={f} onDone={load} />
          </Section>
        </div>

        <Section title="Remediation" meta="needs approval before anything is sent or changed">
          <Remediation workspace={current} findingId={f.finding_id} />
        </Section>

        <Section title="History">
          <History f={f} />
        </Section>
      </div>

      {/* Properties */}
      <aside className="xl:sticky xl:top-20 xl:self-start">
        <div className="rounded-card border border-line bg-panel p-4">
          <dl className="divide-y divide-line">
            <Prop label="Status">
              <StatusPill status={f.status} />
            </Prop>
            <Prop label="Severity">
              <SeverityBadge severity={o?.severity} />
            </Prop>
            <Prop label="Type">{KIND_LABEL[f.kind]}</Prop>
            <Prop label="Review">{o ? RISK_REVIEW_LABEL[o.risk_review] : "–"}</Prop>
            {o && <Prop label="Source">{ORIGIN_LABEL[o.origin]}</Prop>}
            <Prop label="File">
              {f.path ?? loc?.path ? (
                <span className="block truncate font-mono text-xs" title={f.path ?? loc?.path ?? undefined}>
                  {f.path ?? loc?.path}
                </span>
              ) : (
                <span className="text-faint">Withheld</span>
              )}
            </Prop>
            {loc && where(loc) && <Prop label="Location">{where(loc)}</Prop>}
            <Prop label="Check">
              <span className="font-mono text-xs">{f.rule_id ?? f.check_id}</span>
            </Prop>
            <Prop label="Last seen">
              <span title={o?.created_at}>{relativeTime(o?.created_at)}</span>
            </Prop>
            <Prop label="Your review">{REVIEW_LABEL[f.human_review]}</Prop>
            {f.human_review === "dismissed" && f.human_review_reason && <Prop label="Reason">{f.human_review_reason}</Prop>}
          </dl>
          {current.capabilities.includes("review") ? (
            <Review workspaceId={current.id} f={f} onChange={(x) => setF({ ...f, ...x })} onConflict={load} />
          ) : (
            <p className="mt-3 text-xs text-faint">This app&apos;s access grant can&apos;t review findings.</p>
          )}
        </div>
      </aside>
    </div>
  );
}
