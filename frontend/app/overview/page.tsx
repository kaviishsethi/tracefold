"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, ChevronRight } from "lucide-react";
import { api, recentScans, ws, type Action, type ApiError, type Capabilities, type Finding, type Page, type RecentScan } from "@/lib/api";
import { relativeTime, shortId } from "@/lib/format";
import { useCurrentWorkspace, NewScanButton } from "@/components/shell";
import { Empty, ErrorNote, Loading, PageHeader, Panel, SEVERITY_STYLE, StatusPill, cx } from "@/components/ui";

const MAX_PAGES = 10;

/** Every finding the app can read, up to MAX_PAGES × 100. `capped` says whether there were more. */
async function allFindings(workspaceId: string): Promise<{ items: Finding[]; capped: boolean }> {
  const items: Finding[] = [];
  let cursor: string | null = null;
  for (let i = 0; i < MAX_PAGES; i++) {
    const q: string = `/findings?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
    const page: Page<Finding> = await api<Page<Finding>>(ws(workspaceId, q));
    items.push(...page.items);
    cursor = page.next_cursor;
    if (!cursor) return { items, capped: false };
  }
  return { items, capped: true };
}

const DELIVERY: Record<string, string> = {
  outbox: "Approved takedowns are written to the outbox (.eml), not sent",
  resend: "Approved takedowns are emailed through Resend",
  resend_not_configured: "Resend selected but not configured",
};

export default function Overview() {
  const { current } = useCurrentWorkspace();
  const [findings, setFindings] = useState<{ items: Finding[]; capped: boolean } | null>(null);
  const [approvals, setApprovals] = useState<number | null | "hidden">(null);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [capsError, setCapsError] = useState<string | null>(null);
  const [recent, setRecent] = useState<RecentScan[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Capabilities>("/capabilities")
      .then(setCaps)
      .catch((e: ApiError) => setCapsError(e.message));
  }, []);

  useEffect(() => {
    if (!current) return;
    setRecent(recentScans(current.id));
    setFindings(null);
    setError(null);
    allFindings(current.id)
      .then(setFindings)
      .catch((e: ApiError) => setError(e.message));
    api<Page<Action>>(ws(current.id, "/actions?status=drafted&limit=100"))
      .then((p) => setApprovals(p.items.length))
      .catch(() => setApprovals("hidden"));
  }, [current]);

  if (!current)
    return (
      <Empty title="No workspace" action={<NewScanButton size="md" />}>
        This app&apos;s token doesn&apos;t cover a workspace yet. Follow the setup steps to grant one.
      </Empty>
    );
  if (error) return <ErrorNote error={error} />;
  if (!findings) return <Loading />;

  const open = findings.items.filter((f) => f.status === "open");
  const exposures = open.filter((f) => f.kind === "public_exposure");
  const risks = open.filter((f) => f.kind === "local_risk");
  const plus = findings.capped ? "+" : "";
  const latest = recent[0] ?? null;

  const metrics: { label: string; value: string; hint: string; tone?: string; href?: string; n: number }[] = [
    { label: "Public exposure", value: `${exposures.length}${plus}`, n: exposures.length, hint: "Open findings: your text on an approved public page", tone: "text-crit", href: "/findings" },
    { label: "Potential risks", value: `${risks.length}${plus}`, n: risks.length, hint: "Open findings in your files", tone: "text-med", href: "/findings" },
    ...(approvals === "hidden"
      ? []
      : [{ label: "Waiting for approval", value: approvals == null ? "–" : String(approvals), n: approvals ?? 0, hint: "Drafted takedowns and key disables", tone: "text-accent", href: "/actions" }]),
    { label: "Latest scan", value: latest ? relativeTime(latest.at) : "None", n: latest ? 1 : 0, hint: "Started from this browser", href: latest ? `/scan/${latest.scan_id}` : "/scan" },
  ];

  return (
    <div>
      <PageHeader
        title="Overview"
        subtitle={`${current.name} · ${current.source_type === "local_dir" ? "local folder" : "uploads only"} · ${current.disclosure} disclosure`}
        right={<NewScanButton size="md" />}
      />

      <div className={cx("mb-6 grid grid-cols-2 overflow-hidden rounded-card border border-line bg-line [gap:1px]", metrics.length === 4 ? "lg:grid-cols-4" : "lg:grid-cols-3")}>
        {metrics.map((m) => (
          <Link key={m.label} href={m.href ?? "#"} className="bg-panel px-5 py-4 transition-colors hover:bg-panel-2">
            <p className="text-[13px] text-mute">{m.label}</p>
            <p className={cx("mt-2 text-[32px] font-medium leading-none tracking-[-0.04em] tabular-nums", m.n ? (m.tone ?? "text-ink") : "text-faint")}>{m.value}</p>
            <p className="mt-2 text-xs text-faint">{m.hint}</p>
          </Link>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Panel
          title="Needs attention"
          meta={`${open.length}${plus} open`}
          actions={
            <Link href="/findings" className="text-xs text-mute hover:text-ink">
              View all
            </Link>
          }
        >
          {open.length === 0 ? (
            <div className="px-4 py-12 text-center">
              <p className="text-sm font-medium text-ink">No open findings</p>
              <p className="mx-auto mt-1 max-w-sm text-[13px] text-mute">
                {findings.items.length
                  ? "Every finding is either not detected in the checked version or no longer observed. That only covers what was scanned."
                  : "Nothing has been scanned in this workspace yet, so there is nothing to report."}
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-line">
              {open.slice(0, 8).map((f) => {
                const sev = f.latest?.severity;
                return (
                  <li key={f.finding_id}>
                    <Link href={`/findings/${f.finding_id}`} className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-panel-2">
                      <span className={cx("h-8 w-[3px] shrink-0 rounded-full", sev ? SEVERITY_STYLE[sev].bar : "bg-raised")} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink">{f.latest?.title ?? f.rule_id ?? f.check_id}</span>
                        <span className="block truncate text-xs text-faint">
                          {f.kind === "public_exposure" ? "Public exposure" : "Potential risk"}
                          {f.path ? ` · ${f.path}` : ""}
                        </span>
                      </span>
                      <StatusPill status={f.status} />
                      <ChevronRight className="size-4 shrink-0 text-faint transition-transform group-hover:translate-x-0.5" aria-hidden />
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        <div className="space-y-6">
          <Panel
            title="Engine"
            actions={
              <Link href="/settings" className="inline-flex items-center gap-1 text-xs text-mute hover:text-ink">
                Details <ArrowUpRight className="size-3" aria-hidden />
              </Link>
            }
          >
            {capsError ? (
              <p className="px-4 py-4 text-[13px] text-crit">{capsError}</p>
            ) : !caps ? (
              <Loading />
            ) : (
              <dl className="divide-y divide-line text-[13px]">
                <div className="flex items-center justify-between gap-4 px-4 py-2.5">
                  <dt className="text-faint">Version</dt>
                  <dd className="font-mono text-xs text-ink">{caps.engine_version}</dd>
                </div>
                <div className="flex items-start justify-between gap-4 px-4 py-2.5">
                  <dt className="shrink-0 text-faint">Local model</dt>
                  <dd className={cx("text-right", caps.model.available ? "text-local" : "text-med")}>
                    {caps.model.available ? String(caps.model.model_id ?? caps.model.model ?? "Ready") : `Unavailable${caps.model.reason ? ` · ${caps.model.reason}` : ""}`}
                  </dd>
                </div>
                <div className="flex items-start justify-between gap-4 px-4 py-2.5">
                  <dt className="shrink-0 text-faint">Takedowns</dt>
                  <dd className="text-right text-ink-2">{DELIVERY[caps.remediation?.takedown_delivery ?? ""] ?? caps.remediation?.takedown_delivery ?? "–"}</dd>
                </div>
                <div className="flex items-start justify-between gap-4 px-4 py-2.5">
                  <dt className="shrink-0 text-faint">AWS key disabling</dt>
                  <dd className={cx("text-right", caps.remediation?.aws_key_disable === "configured" ? "text-ink-2" : "text-mute")}>
                    {caps.remediation?.aws_key_disable === "configured" ? "Configured" : "Not configured"}
                  </dd>
                </div>
              </dl>
            )}
          </Panel>

          <Panel
            title="Latest scans"
            meta="this browser"
            actions={
              <Link href="/scan" className="text-xs text-mute hover:text-ink">
                New scan
              </Link>
            }
          >
            {recent.length === 0 ? (
              <p className="px-4 py-5 text-[13px] text-mute">No scans started from this browser. The engine has no list of past scans.</p>
            ) : (
              <ul className="divide-y divide-line">
                {recent.slice(0, 5).map((s) => (
                  <li key={s.scan_id}>
                    <Link href={`/scan/${s.scan_id}`} className="group flex items-center gap-3 px-4 py-2.5 text-[13px] transition-colors hover:bg-panel-2">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-ink-2">{s.label}</span>
                        <span className="block font-mono text-[11px] text-faint">{shortId(s.scan_id)}</span>
                      </span>
                      <span className="shrink-0 text-xs text-faint">{relativeTime(s.at)}</span>
                      <ChevronRight className="size-4 shrink-0 text-faint transition-transform group-hover:translate-x-0.5" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
