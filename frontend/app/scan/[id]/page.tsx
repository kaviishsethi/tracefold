"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, ArrowUpRight, Check, ChevronRight, Minus, X } from "lucide-react";
import {
  COMPARISON_LABEL,
  DISCOVERY_OUTCOME,
  FETCH_LABEL,
  STATE_MEANING,
  allSources,
  api,
  coverageNote,
  isTerminal,
  recentScans,
  useScan,
  ws,
  type ApiError,
  type Coverage,
  type Finding,
  type FindingKind,
  type Page,
  type Scan,
  type SourcePage,
  type SourceRow,
  type Stage,
} from "@/lib/api";
import { host as hostOf } from "@/lib/format";
import { relativeTime, shortId } from "@/lib/format";
import { Button, ErrorNote, LinkButton, Loading, PageHeader, Panel, SeverityBadge, Spinner, StatusPill, cx } from "@/components/ui";
import { useCrumb, useCurrentWorkspace } from "@/components/shell";

const STAGE_LABEL: Record<string, string> = {
  parse: "Read and parse files",
  public_discovery: "Search for candidate pages",
  public_retrieval: "Fetch public pages",
  public_match: "Compare with public pages",
  local_rules: "Run local risk rules",
  model_review: "Local model review",
  publish: "Publish findings",
};

const TITLE: Record<Scan["state"], string> = {
  queued: "Waiting to run",
  running: "Scanning",
  completed: "Scan completed",
  partial: "Scan partly completed",
  failed: "Scan failed",
  cancelled: "Scan cancelled",
  interrupted: "Scan interrupted",
};

const KIND_TITLE: Record<FindingKind, string> = {
  public_exposure: "Public exposure",
  local_risk: "Potential risks in your files",
};

const COVERAGE_TONE: Record<Coverage["status"], string> = {
  complete: "text-local",
  partial: "text-med",
  failed: "text-crit",
  not_requested: "text-faint",
};

function label(key: string) {
  return key.replace(/_/g, " ");
}

function StageIcon({ status }: { status: Stage["status"] }) {
  if (status === "done") return <Check className="size-4 text-local" aria-label="done" />;
  if (status === "running") return <Spinner className="text-ink" />;
  if (status === "failed") return <X className="size-4 text-crit" aria-label="failed" />;
  if (status === "skipped" || status === "cancelled") return <Minus className="size-4 text-faint" aria-label={status} />;
  return <span className="size-1.5 rounded-full bg-raised" aria-label="pending" />;
}

/** The scan log: built from what the engine reports (stages, coverage, errors). No invented lines. */
function logLines(scan: Scan): { text: string; tone: string }[] {
  const out: { text: string; tone: string }[] = [{ text: `scan ${scan.scan_id} · checks: ${scan.checks.join(", ")}`, tone: "text-ink-2" }];
  if (scan.started_at) out.push({ text: `started ${new Date(scan.started_at).toLocaleTimeString([], { hour12: false })}`, tone: "text-faint" });
  for (const s of scan.stages) {
    if (s.status === "pending") continue;
    out.push({
      text: `[${s.name}] ${s.status}${s.detail ? ` · ${s.detail}` : ""}`,
      tone: s.status === "failed" ? "text-crit" : s.status === "done" ? "text-local" : s.status === "running" ? "text-ink" : "text-faint",
    });
  }
  for (const c of scan.coverage) {
    if (c.status === "complete" || c.status === "not_requested") continue;
    out.push({ text: `coverage ${c.scope}:${c.id} ${c.status}${c.reason ? ` · ${c.reason}` : ""}`, tone: c.status === "failed" ? "text-crit" : "text-med" });
  }
  for (const e of scan.errors) out.push({ text: `error ${e.code}: ${e.message}${e.retryable ? " (retryable)" : ""}`, tone: "text-crit" });
  if (scan.finished_at) out.push({ text: `finished ${new Date(scan.finished_at).toLocaleTimeString([], { hour12: false })} · ${scan.state}`, tone: "text-ink-2" });
  return out;
}

const COMPARISON_TONE: Record<SourceRow["comparison_status"], string> = {
  matched: "text-accent",
  no_match: "text-mute",
  incomplete: "text-med",
  not_compared: "text-faint",
};

/** Every public page this scan looked at: matches, no-matches, failures and blocked URLs, with how each was found. */
function SourcesPanel({ workspaceId, scan }: { workspaceId: string; scan: Scan }) {
  const [page, setPage] = useState<SourcePage | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    allSources(workspaceId, scan.scan_id)
      .then((p) => alive && setPage(p))
      .catch((e: ApiError) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [workspaceId, scan.scan_id]);
  if (error) return <ErrorNote error={error} />;
  if (!page) return <Loading />;
  const d = page.discovery;
  const rows = [...page.items].sort(
    (a, b) => Number(b.comparison_status === "matched") - Number(a.comparison_status === "matched") || b.match_count - a.match_count,
  );
  const matched = rows.filter((r) => r.comparison_status === "matched").length;
  return (
    <Panel
      title={d ? "Pages found by search" : "Public pages checked"}
      meta={`${rows.length} ${rows.length === 1 ? "page" : "pages"} · ${matched} matched`}
    >
      {d && (
        <div className="space-y-2 border-b border-line px-4 py-3">
          <p className={cx("text-[13px]", d.outcome === "search_failed" || d.outcome === "no_candidates" ? "text-med" : "text-ink-2")}>
            {DISCOVERY_OUTCOME[d.outcome ?? ""] ?? d.outcome}
          </p>
          <ul className="space-y-0.5 text-xs">
            {d.provider_queries.map((q) => (
              <li key={q.query_id} className="flex flex-wrap gap-x-2">
                <span className="w-12 shrink-0 font-mono text-faint">{q.provider}</span>
                <span className="font-mono text-ink-2">{q.query}</span>
                <span className={q.status === "ok" ? "text-faint" : "text-crit"}>
                  {q.status === "ok" ? `${q.returned} returned${q.truncated ? " (extra results dropped)" : ""}` : `${q.status}${q.error ? ` · ${q.error}` : ""}`}
                </span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-faint">{d.note}</p>
        </div>
      )}
      {rows.length === 0 ? (
        <p className="px-4 py-6 text-[13px] text-mute">No public pages were fetched in this scan.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-[13px]">
            <thead className="text-xs text-faint">
              <tr className="border-b border-line">
                {["Page", d ? "Found by" : "Source", "Fetch", "Comparison"].map((h) => (
                  <th key={h} className="px-4 py-2.5 font-normal">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const o = r.discovery_origins[0];
                return (
                  <tr key={r.source_id} className={cx("border-b border-line align-top last:border-0", r.comparison_status === "matched" && "bg-accent/[0.05]")}>
                    <td className="max-w-[420px] px-4 py-2.5">
                      {r.fetch_status === "blocked" ? (
                        <span className="block truncate font-mono text-xs text-faint" title={r.original_url}>
                          {r.original_url}
                        </span>
                      ) : (
                        <a href={r.original_url} target="_blank" rel="noreferrer noopener" className="group block min-w-0">
                          <span className="block truncate text-ink group-hover:underline">{r.title ?? hostOf(r.original_url)}</span>
                          <span className="block truncate font-mono text-[11px] text-faint">{r.original_url}</span>
                        </a>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-xs text-mute">
                      {o ? (
                        <>
                          {o.provider} · {o.query_id} · #{o.rank}
                          {r.discovery_origins.length > 1 && <span className="text-faint"> +{r.discovery_origins.length - 1}</span>}
                        </>
                      ) : (
                        <span className="font-mono">{r.source_id}</span>
                      )}
                    </td>
                    <td className={cx("whitespace-nowrap px-4 py-2.5 text-xs", r.fetch_status === "fetched" ? "text-mute" : "text-med")} title={r.failure_reason ?? undefined}>
                      {FETCH_LABEL[r.fetch_status]}
                      {r.failure_reason && r.fetch_status !== "fetched" ? ` · ${r.failure_reason}` : ""}
                      {r.freshness === "cached" ? " · cached" : ""}
                    </td>
                    <td className={cx("whitespace-nowrap px-4 py-2.5 text-xs font-medium", COMPARISON_TONE[r.comparison_status])}>
                      {COMPARISON_LABEL[r.comparison_status]}
                      {r.match_count > 0 ? ` · ${r.match_count} ${r.match_count === 1 ? "passage" : "passages"}` : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function Results({ workspaceId, scan }: { workspaceId: string; scan: Scan }) {
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    (async () => {
      const all: Finding[] = [];
      let cursor: string | null = null;
      try {
        for (let i = 0; i < 20; i++) {
          const q: string = `/findings?scan_id=${encodeURIComponent(scan.scan_id)}&limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
          const page: Page<Finding> = await api<Page<Finding>>(ws(workspaceId, q));
          all.push(...page.items);
          cursor = page.next_cursor;
          if (!cursor) break;
        }
        if (alive) setFindings(all);
      } catch (e) {
        if (alive) setError((e as ApiError).message);
      }
    })();
    return () => {
      alive = false;
    };
  }, [workspaceId, scan.scan_id]);

  if (error) return <ErrorNote error={error} />;
  if (!findings) return <Loading />;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {(["public_exposure", "local_risk"] as const).map((kind) => {
        const list = findings.filter((f) => f.kind === kind);
        const note = coverageNote(scan, kind, list.length);
        return (
          <Panel
            key={kind}
            title={KIND_TITLE[kind]}
            meta={`${list.length} ${list.length === 1 ? "finding" : "findings"}`}
            actions={
              list.length > 0 ? (
                <Link href="/findings" className="text-xs text-mute hover:text-ink">
                  All findings
                </Link>
              ) : undefined
            }
          >
            {note && <p className={cx("px-4 py-3 text-[13px]", list.length ? "border-b border-line text-med" : "text-mute")}>{note}</p>}
            {list.length > 0 && (
              <ul className="divide-y divide-line">
                {list.map((f) => (
                  <li key={f.finding_id}>
                    <Link href={`/findings/${f.finding_id}`} className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-panel-2">
                      <span className="w-[72px] shrink-0">
                        <SeverityBadge severity={f.latest?.severity} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink">{f.latest?.title ?? f.rule_id ?? f.check_id}</span>
                        <span className="block truncate font-mono text-xs text-faint">{f.path ?? (kind === "public_exposure" ? "path withheld" : f.rule_id ?? "")}</span>
                      </span>
                      <StatusPill status={f.status} />
                      <ChevronRight className="size-4 shrink-0 text-faint transition-transform group-hover:translate-x-0.5" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        );
      })}
    </div>
  );
}

export default function ScanView() {
  const { id } = useParams<{ id: string }>();
  const { current } = useCurrentWorkspace();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const logBox = useRef<HTMLDivElement>(null);
  useCrumb(`Scan ${shortId(id)}`);

  useEffect(() => {
    setWorkspaceId(recentScans().find((s) => s.scan_id === id)?.workspace_id ?? current?.id ?? null);
  }, [id, current]);

  const { scan, error } = useScan(workspaceId, id);
  const lines = scan ? logLines(scan) : [];

  useEffect(() => {
    const el = logBox.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  if (error) return <ErrorNote error={error.status === 404 ? "This scan isn't in the current workspace, or it no longer exists." : error.message} />;
  if (!scan || !workspaceId) return <Loading />;

  const terminal = isTerminal(scan.state);
  const done = scan.stages.filter((s) => s.status !== "pending" && s.status !== "running").length;
  const canCancel = !terminal && (current?.capabilities.includes("cancel") ?? false);
  const drafted = typeof scan.summary.actions_drafted === "number" ? scan.summary.actions_drafted : null;
  const isolation = typeof scan.summary.retrieval_isolation === "string" ? scan.summary.retrieval_isolation : null;
  const modelReview = scan.summary.model_review as { status?: string; reason?: string; reviewed?: number } | undefined;
  const sum = (k: string) => (typeof scan.summary[k] === "number" ? (scan.summary[k] as number) : null);

  async function cancel() {
    setCancelling(true);
    setCancelError(null);
    try {
      await api(ws(workspaceId!, `/scans/${scan!.scan_id}/cancel`), { method: "POST" });
    } catch (e) {
      setCancelError((e as ApiError).message);
    } finally {
      setCancelling(false);
    }
  }

  const counters: [string, number | null, string?][] = [
    ["Files parsed", sum("files_parsed")],
    [
      scan.public_discovery ? "Pages found and fetched" : "Public sources fetched",
      scan.checks.includes("public_match") ? sum("public_sources_ok") : null,
      sum("public_sources_requested") != null ? `of ${sum("public_sources_requested")} requested` : scan.checks.includes("public_match") ? undefined : "not requested",
    ],
    ["Local rule hits", scan.checks.includes("local_risk") ? sum("local_rule_hits") : null, scan.checks.includes("local_risk") ? undefined : "not requested"],
    ["Observations published", sum("observations")],
  ];

  const details: [string, string][] = [
    ["Created", relativeTime(scan.created_at)],
    ...(scan.finished_at ? ([["Finished", relativeTime(scan.finished_at)]] as [string, string][]) : []),
    ...(scan.public_discovery
      ? ([["Discovery plan", `${shortId(scan.public_discovery.query_plan_id)} · ${scan.public_discovery.mode}`]] as [string, string][])
      : []),
    ...(scan.public_freshness ? ([["Public pages", scan.public_freshness]] as [string, string][]) : []),
    ...(isolation ? ([["Retrieval isolation", label(isolation)]] as [string, string][]) : []),
    ...(modelReview?.status
      ? ([["Model review", `${label(modelReview.status)}${modelReview.reason ? ` · ${modelReview.reason}` : ""}${modelReview.reviewed != null ? ` · ${modelReview.reviewed} reviewed` : ""}`]] as [string, string][])
      : []),
    ...(scan.recheck_of ? ([["Recheck of", scan.recheck_of]] as [string, string][]) : []),
    ...Object.entries(scan.budget).map(([k, v]) => [`Budget: ${label(k)}`, String(v)] as [string, string]),
  ];

  return (
    <div>
      <PageHeader
        title={TITLE[scan.state]}
        subtitle={
          <>
            {STATE_MEANING[scan.state]} <span className="font-mono text-[13px] text-faint">{scan.scan_id}</span>
          </>
        }
        right={
          <>
            {canCancel && (
              <Button variant="danger" size="sm" onClick={cancel} loading={cancelling}>
                Cancel scan
              </Button>
            )}
            {terminal && (
              <LinkButton href={`/egress?scan=${encodeURIComponent(scan.scan_id)}`} variant="secondary" size="sm">
                Outbound requests <ArrowUpRight className="size-3.5" aria-hidden />
              </LinkButton>
            )}
          </>
        }
      />
      <ErrorNote error={cancelError} />

      <div
        className="mb-4 h-1 overflow-hidden rounded-full bg-panel-2"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={scan.stages.length}
        aria-valuenow={done}
      >
        <div
          className={cx(
            "h-full rounded-full transition-[width] duration-700 ease-out-expo",
            !terminal ? "bg-ink" : scan.state === "completed" ? "bg-local" : scan.state === "partial" ? "bg-med" : "bg-crit",
          )}
          style={{ width: `${scan.stages.length ? (done / scan.stages.length) * 100 : 0}%` }}
        />
      </div>

      <div className="mb-6 grid grid-cols-2 overflow-hidden rounded-card border border-line bg-line [gap:1px] lg:grid-cols-4">
        {counters.map(([name, value, hint]) => (
          <div key={name} className="bg-panel px-5 py-4">
            <p className="text-xs text-mute">{name}</p>
            <p className={cx("mt-1.5 font-mono text-2xl tabular-nums", value == null ? "text-faint" : "text-ink")}>{value ?? "–"}</p>
            {hint && <p className="mt-1 text-xs text-faint">{hint}</p>}
          </div>
        ))}
      </div>

      {terminal && drafted != null && drafted > 0 && (
        <Link
          href="/actions"
          className="mb-6 flex items-center gap-3 rounded-card border border-accent/30 bg-accent/[0.07] px-4 py-3 text-sm transition-colors hover:bg-accent/[0.11]"
        >
          <span className="font-medium text-accent">
            {drafted} {drafted === 1 ? "action" : "actions"} waiting for approval
          </span>
          <span className="text-mute">Nothing is sent or changed until a person approves.</span>
          <ArrowRight className="ml-auto size-4 text-accent" aria-hidden />
        </Link>
      )}

      <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Panel title="Pipeline" bodyClassName="py-2">
          <ol>
            {scan.stages.map((s) => (
              <li key={s.name} className="px-4 py-2.5">
                <div className="flex items-center gap-3 text-sm">
                  <span className="flex size-5 items-center justify-center">
                    <StageIcon status={s.status} />
                  </span>
                  <span className={cx("flex-1", s.status === "pending" ? "text-faint" : "text-ink")}>{STAGE_LABEL[s.name] ?? label(s.name)}</span>
                  {s.status !== "pending" && s.status !== "done" && s.status !== "running" && <span className="text-xs text-faint">{s.status}</span>}
                </div>
                {s.detail && <p className="ml-8 mt-1 text-xs leading-relaxed text-mute">{s.detail}</p>}
              </li>
            ))}
          </ol>
        </Panel>

        <Panel
          title="Scan log"
          meta={`${lines.length} lines`}
          className="bg-[#0b0b0b]"
          actions={
            !terminal ? (
              <span className="flex items-center gap-1.5 text-xs text-mute">
                <span className="size-1.5 animate-pulse rounded-full bg-local" /> live
              </span>
            ) : undefined
          }
        >
          <div ref={logBox} className="scroll-thin h-[320px] overflow-auto px-4 py-3 font-mono text-[12.5px] leading-6">
            {lines.map((l, i) => (
              <div key={i} className={cx("whitespace-pre-wrap", l.tone)}>
                {l.text}
              </div>
            ))}
            {!terminal && <span className="animate-pulse text-faint">▍</span>}
          </div>
        </Panel>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Panel title="Coverage" meta="what was checked, and what wasn't">
          {scan.coverage.length === 0 ? (
            <p className="px-4 py-6 text-[13px] text-mute">{terminal ? "The engine reported no coverage for this scan." : "Coverage appears as stages finish."}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-left text-[13px]">
                <thead className="text-xs text-faint">
                  <tr className="border-b border-line">
                    {["Scope", "Item", "Status", "Reason", "Counts"].map((h) => (
                      <th key={h} className="px-4 py-2.5 font-normal">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {scan.coverage.map((c) => (
                    <tr key={`${c.scope}:${c.id}`} className="border-b border-line last:border-0">
                      <td className="px-4 py-2.5 text-mute">{c.scope}</td>
                      <td className="max-w-[220px] truncate px-4 py-2.5 font-mono text-xs text-ink" title={c.id}>
                        {c.id}
                      </td>
                      <td className={cx("whitespace-nowrap px-4 py-2.5 text-xs font-medium", COVERAGE_TONE[c.status])}>{label(c.status)}</td>
                      <td className="px-4 py-2.5 text-xs text-mute">{c.reason ?? "–"}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-faint">
                        {Object.entries(c.counts)
                          .map(([k, v]) => `${label(k)} ${v}`)
                          .join(" · ") || "–"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Details" className="self-start">
          <dl className="divide-y divide-line text-[13px]">
            {details.map(([k, v]) => (
              <div key={k} className="flex items-start justify-between gap-4 px-4 py-2.5">
                <dt className="shrink-0 text-faint">{k}</dt>
                <dd className="min-w-0 break-words text-right text-ink-2">{v}</dd>
              </div>
            ))}
          </dl>
          {scan.errors.length > 0 && (
            <ul className="border-t border-line bg-crit/[0.05] px-4 py-3 text-xs">
              {scan.errors.map((e, i) => (
                <li key={i} className="py-0.5">
                  <span className="font-mono text-crit">{e.code}</span> <span className="text-ink-2">{e.message}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      {terminal && scan.checks.includes("public_match") && (
        <div className="mt-6">
          <SourcesPanel workspaceId={workspaceId} scan={scan} />
        </div>
      )}

      {terminal && (
        <div className="mt-6">
          <Results workspaceId={workspaceId} scan={scan} />
        </div>
      )}
    </div>
  );
}
