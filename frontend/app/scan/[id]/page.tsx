"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { api, coverageNote, isTerminal, useScan, ws, type Finding, type FindingKind, type Page, type Scan, type Stage } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Box, Crumbs, Disclosure, FindingRow, H1, Note, scanState, source } from "@/components/bits";
import { AgentPrompt, scanPrompt } from "@/components/agent-prompt";
import { SourcesPanel } from "@/components/scan-sources";
import { LedgerPanel } from "@/components/scan-ledger";
import { ConfirmButton } from "@/components/confirm-button";
import { groupByPage, PageMatchRow } from "@/components/page-matches";
import { LeakTimeline } from "@/components/leak-timeline";
import { ErrorNote, Spinner, cx } from "@/components/ui";

const STAGES: Record<string, { label: string; doing: string; check?: "public_match" | "local_risk" }> = {
  parse: { label: "Read files", doing: "Extracting text from each file" },
  public_discovery: { label: "Search", doing: "Looking for public pages that mention the company", check: "public_match" },
  public_retrieval: { label: "Fetch pages", doing: "Downloading the pages search returned", check: "public_match" },
  public_match: { label: "Compare", doing: "Checking those pages for passages from your files", check: "public_match" },
  local_rules: { label: "Local rules", doing: "Scanning for keys, secrets and risky code", check: "local_risk" },
  model_review: { label: "Local model review", doing: "A model on this machine reviews what the rules flagged", check: "local_risk" },
};

/** Ticks once a second so the elapsed time stays live. */
function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

function elapsed(from: string | null, now: number) {
  const ms = from ? now - new Date(from).getTime() : 0;
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function StageMark({ status }: { status: Stage["status"] }) {
  if (status === "done") return <span className="grid size-5 place-content-center rounded-full bg-accent/15"><Check className="size-3 text-accent" strokeWidth={3} aria-hidden /></span>;
  if (status === "running") return <Loader2 className="size-5 animate-spin text-accent" aria-hidden />;
  if (status === "failed") return <span className="grid size-5 place-content-center rounded-full bg-crit/15"><X className="size-3 text-crit" strokeWidth={3} aria-hidden /></span>;
  return <span className="grid size-5 place-content-center"><span className="size-2 rounded-full border border-line-strong" /></span>;
}

/** Live progress while a scan runs: one row per stage this scan will actually run. */
function Progress({ scan }: { scan: Scan }) {
  const now = useNow(true);
  const stages = scan.stages.filter((s) => {
    const meta = STAGES[s.name];
    return meta && s.status !== "skipped" && (!meta.check || scan.checks.includes(meta.check));
  });
  if (!stages.length) return null;
  const finished = stages.filter((s) => s.status === "done").length;
  const pct = Math.round(((finished + (stages.some((s) => s.status === "running") ? 0.5 : 0)) / stages.length) * 100);
  return (
    <section className="mb-8 overflow-hidden rounded-card border border-line bg-panel">
      <header className="flex min-h-14 items-center justify-between gap-3 border-b border-line pl-4 pr-4">
        <h2 className="text-sm font-medium text-ink">
          Step {Math.min(finished + 1, stages.length)} of {stages.length}
        </h2>
        <span className="font-mono text-xs tabular-nums text-faint">{elapsed(scan.started_at ?? scan.created_at, now)}</span>
      </header>
      <div className="h-0.5 bg-line">
        <div className="h-full bg-accent transition-[width] duration-700 ease-out" style={{ width: `${pct}%` }} />
      </div>
      <ol>
        {stages.map((s) => {
          const meta = STAGES[s.name];
          return (
            <li key={s.name} className="flex items-center gap-3 border-t border-line px-4 py-3.5 first:border-t-0">
              <StageMark status={s.status} />
              <span className="min-w-0 flex-1">
                <span className={cx("block text-sm", s.status === "pending" ? "text-mute" : s.status === "failed" ? "text-crit" : "text-ink")}>{meta.label}</span>
                {(s.status === "running" || s.status === "failed") && (
                  <span className="block truncate text-[13px] text-faint">
                    {s.status === "failed" && s.detail ? s.detail.replaceAll("_", " ") : meta.doing}
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

interface AutoDiscovery {
  status: "ready" | "unavailable";
  companies?: string[];
  own_company?: string | null;
  found_in_files?: string[];
  privacy_notice?: string;
  reason?: string;
}

/** Automatic discovery: which company names the local model found in the files, and what that means for privacy. */
function Identified({ auto }: { auto: AutoDiscovery }) {
  return (
    <p className="mb-8 text-sm text-mute" title={auto.privacy_notice}>
      {auto.status === "ready" ? (
        <>
          {(() => {
            const names = auto.found_in_files ? [...(auto.own_company ? [auto.own_company] : []), ...auto.found_in_files] : auto.companies ?? [];
            return (
              <>
                Searched for{" "}
                {names.map((n, i) => (
                  <span key={n}>
                    {i > 0 && (i === names.length - 1 ? " and " : ", ")}
                    <span className="text-ink">{n}</span>
                  </span>
                ))}
              </>
            );
          })()}
        </>
      ) : (
        <span className="text-med">
          {auto.reason === "company_not_identified"
            ? "No company name found in the files, so public pages weren't searched."
            : auto.reason === "invalid_identity_output"
              ? "The local model's answer couldn't be read, so public pages weren't searched."
              : auto.reason === "identity_step_failed"
                ? "Something went wrong reading the company name, so public pages weren't searched. Scan again."
                : "The local model isn't running, so public pages weren't searched."}
        </span>
      )}
    </p>
  );
}

const GROUPS: [FindingKind, string, string][] = [
  ["public_exposure", "On public pages", "public_match"],
  ["local_risk", "In your files", "local_risk"],
];

export default function ScanDetail() {
  const { id } = useParams<{ id: string }>();
  const { current: workspace } = useCurrentWorkspace();
  const router = useRouter();
  const { scan, error } = useScan(workspace?.id ?? null, id);
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const done = scan ? isTerminal(scan.state) : false;

  useEffect(() => {
    if (!workspace || !done) return;
    api<Page<Finding>>(ws(workspace.id, `/findings?scan_id=${id}&limit=100`))
      .then((p) => setFindings(p.items))
      .catch(() => setFindings([]));
  }, [workspace, id, done]);

  if (error) return <ErrorNote error={error.message} />;
  if (!scan)
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );

  const st = scanState(scan);
  const canDelete = workspace?.capabilities.includes("configure") ?? false;
  const openFindings = (findings ?? []).filter((f) => f.status === "open");
  // A page that copies a file counts once, however many passages match.
  const open = openFindings.filter((f) => f.kind !== "public_exposure").length + groupByPage(openFindings.filter((f) => f.kind === "public_exposure")).length;
  const sites = new Set(groupByPage(openFindings.filter((f) => f.kind === "public_exposure")).map((g) => g.url)).size;
  const risks = openFindings.filter((f) => f.kind !== "public_exposure").length;
  const result = [
    sites ? `Likely leaked on ${sites} ${sites === 1 ? "site" : "sites"}` : "",
    risks ? `${risks} ${risks === 1 ? "risk" : "risks"} in your files` : "",
  ].filter(Boolean).join(" · ");
  const leakGroups = groupByPage(openFindings.filter((f) => f.kind === "public_exposure"));
  const files = [...new Set((findings ?? []).map((f) => f.path).filter(Boolean))] as string[];
  const title = !done ? st.text : st.tone === "bad" && scan.state !== "partial" ? st.text : findings === null ? "Done"
    : sites ? (files.length === 1 ? files[0] : `${files.length} files`) : result || "Nothing found";
  const reused = (scan.public_discovery as { outcome?: string } | null | undefined)?.outcome === "reused_recent_results";
  const requested = (check: string) => scan.coverage.some((c) => c.scope === "check" && c.id === check && c.status !== "not_requested");
  const drafted = typeof scan.summary.actions_drafted === "number" ? scan.summary.actions_drafted : 0;
  const auto = scan.summary.automatic_discovery as AutoDiscovery | undefined;
  const problems = scan.coverage.filter((c) => c.status === "partial" || c.status === "failed");

  return (
    <div>
      <Crumbs trail={[["/scan", "Scans"]]} />
      <div>
        <H1
          sub={`${source(scan)} · ${relativeTime(scan.created_at)}${scan.recheck_of ? " · recheck" : ""}${reused ? " · reused recent search results" : ""}${scan.state === "partial" ? " · some checks didn't finish" : ""}`}
          right={
            done ? (
              <>
                {canDelete && (
                  <ConfirmButton
                    label="Delete"
                    question="Delete this scan and its findings?"
                    onConfirm={async () => {
                      await api(ws(workspace!.id, `/scans/${scan.scan_id}`), { method: "DELETE" });
                      window.dispatchEvent(new Event("tracefold:actions-changed"));
                      router.push("/scan");
                    }}
                    className="mr-2"
                  />
                )}
                {open > 0 && <AgentPrompt text={scanPrompt(scan.scan_id)} label="Copy fix prompt" />}
              </>
            ) : undefined
          }
        >
          <span className="inline-flex items-center gap-3">
            {st.tone === "busy" && <Spinner className="size-5" />}
            {title}
          </span>
        </H1>
      </div>

      {drafted > 0 && (
        <Link href="/actions" className="mb-8 flex items-center justify-between rounded-card border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-ink">
          {drafted} {drafted === 1 ? "fix needs" : "fixes need"} your approval
          <span className="font-medium underline underline-offset-4">Review</span>
        </Link>
      )}

      {!done && <Progress scan={scan} />}
      {!done && <p className="-mt-5 mb-8 text-xs text-faint">You can leave this page. The scan keeps running and shows up under Scans.</p>}

      {auto && <Identified auto={auto} />}

      {done &&
        GROUPS.filter(([, , check]) => requested(check)).map(([kind, label]) => {
          const items = (findings ?? []).filter((f) => f.kind === kind);
          const note = coverageNote(scan, kind, items.length);
          const searchFailed = scan.coverage.some((c) => c.scope === "check" && c.id === "public_match" && c.reason === "discovery_search_failed");
          if (kind === "public_exposure" && items.length === 0 && (searchFailed || auto?.status === "unavailable")) return null; // explained elsewhere
          if (kind === "public_exposure" && findings !== null && leakGroups.length > 0) return <LeakTimeline key={kind} groups={leakGroups} />;
          return (
            <section key={kind} className="mb-8">
              <h2 className="mb-3 text-sm font-medium text-ink">{label}</h2>
              <Box>
                {findings === null ? (
                  <Note>Loading…</Note>
                ) : kind === "public_exposure" ? (
                  groupByPage(items).map((g) => <PageMatchRow key={g.key} g={g} />)
                ) : (
                  items.map((f) => <FindingRow key={f.finding_id} f={f} href={`/findings/${f.finding_id}`} />)
                )}
                {findings !== null && note && <Note>{note}</Note>}
              </Box>
            </section>
          );
        })}

      {done && workspace && scan.checks.includes("public_match") && auto?.status !== "unavailable" && (
        <div className="mb-4">
          <SourcesPanel workspaceId={workspace.id} scan={scan} />
        </div>
      )}

      {done && workspace && (
        <div className="mb-8">
          <LedgerPanel workspaceId={workspace.id} scanId={scan.scan_id} />
        </div>
      )}

      {done && (problems.length > 0 || scan.errors.length > 0) && (
        <Disclosure label="What didn't finish">
          <ul className="mt-3 space-y-1">
            {problems.map((c) => (
              <li key={c.scope + c.id}>
                {c.id}: {c.status}
                {c.reason ? ` (${c.reason.replaceAll("_", " ")})` : ""}
              </li>
            ))}
            {scan.errors.map((e) => (
              <li key={e.code}>{e.message}</li>
            ))}
          </ul>
        </Disclosure>
      )}
    </div>
  );
}
