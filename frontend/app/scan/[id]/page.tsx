"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, coverageNote, isTerminal, useScan, ws, type Finding, type FindingKind, type Page, type Scan, type Stage } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Box, Crumbs, Disclosure, FindingRow, H1, Note, scanState, source } from "@/components/bits";
import { AgentPrompt, scanPrompt } from "@/components/agent-prompt";
import { SourcesPanel } from "@/components/scan-sources";
import { LedgerPanel } from "@/components/scan-ledger";
import { ErrorNote, Spinner, cx } from "@/components/ui";

const STAGE_LABEL: Record<string, string> = {
  parse: "Read files",
  public_discovery: "Search",
  public_retrieval: "Fetch pages",
  public_match: "Compare",
  local_rules: "Local rules",
  model_review: "Local model review",
  publish: "Publish",
};

const STAGE_TONE: Record<Stage["status"], string> = {
  pending: "bg-line-strong",
  running: "bg-accent animate-pulse",
  done: "bg-accent",
  failed: "bg-crit",
  skipped: "bg-transparent ring-1 ring-line-strong",
  cancelled: "bg-med",
};

/** The pipeline as the engine reports it: search, fetch and compare are the public half, rules and model the local half. */
function Stages({ scan }: { scan: Scan }) {
  const stages = scan.stages.filter((s) => s.name in STAGE_LABEL && s.name !== "publish");
  if (!stages.length) return null;
  return (
    <ol className="mb-8 flex flex-wrap items-center gap-2 text-[13px]" aria-label="Scan stages">
      {stages.map((s) => (
        <li key={s.name}>
          <span
            className={cx(
              "inline-flex items-center gap-2 rounded-ctl border border-line px-2.5 py-1",
              s.status === "skipped" ? "text-faint" : s.status === "failed" ? "text-crit" : "text-ink-2",
            )}
            title={s.detail ? s.detail.replaceAll("_", " ") : s.status}
          >
            <span className={cx("size-1.5 rounded-full", STAGE_TONE[s.status])} />
            {STAGE_LABEL[s.name]}
            {s.status === "skipped" && <span className="text-[11px]">skipped</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

interface AutoDiscovery {
  status: "ready" | "unavailable";
  companies?: string[];
  privacy_notice?: string;
  reason?: string;
}

/** Automatic discovery: which company names the local model found in the files, and what that means for privacy. */
function Identified({ auto }: { auto: AutoDiscovery }) {
  return (
    <p className="mb-8 text-sm text-mute" title={auto.privacy_notice}>
      {auto.status === "ready" ? (
        <>
          Searched for <span className="text-ink">{(auto.companies ?? []).join(", ")}</span>
        </>
      ) : (
        <span className="text-med">No company name found in the files, so public pages weren&apos;t searched.</span>
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
  const open = (findings ?? []).filter((f) => f.status === "open").length;
  const title = !done ? st.text : st.tone === "bad" && scan.state !== "partial" ? st.text : findings === null ? "Done" : open === 0 ? "Nothing found" : `${open} ${open === 1 ? "problem" : "problems"} found`;
  const requested = (check: string) => scan.coverage.some((c) => c.scope === "check" && c.id === check && c.status !== "not_requested");
  const drafted = typeof scan.summary.actions_drafted === "number" ? scan.summary.actions_drafted : 0;
  const auto = scan.summary.automatic_discovery as AutoDiscovery | undefined;
  const problems = scan.coverage.filter((c) => c.status === "partial" || c.status === "failed");

  return (
    <div>
      <Crumbs trail={[["/scan", "Scans"]]} current={relativeTime(scan.created_at)} />
      <div>
        <H1
          sub={`${source(scan)} · ${relativeTime(scan.created_at)}${scan.recheck_of ? " · recheck" : ""}${scan.state === "partial" ? " · some checks didn't finish" : ""}`}
          right={done && open > 0 ? <AgentPrompt text={scanPrompt(scan.scan_id)} label="Copy fix prompt" /> : undefined}
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

      {!done && <Stages scan={scan} />}

      {auto && <Identified auto={auto} />}

      {done &&
        GROUPS.filter(([, , check]) => requested(check)).map(([kind, label]) => {
          const items = (findings ?? []).filter((f) => f.kind === kind);
          const note = coverageNote(scan, kind, items.length);
          return (
            <section key={kind} className="mb-8">
              <h2 className="mb-3 text-sm font-medium text-ink">{label}</h2>
              <Box>
                {findings === null ? <Note>Loading…</Note> : items.map((f) => <FindingRow key={f.finding_id} f={f} href={`/findings/${f.finding_id}`} />)}
                {findings !== null && note && <Note>{note}</Note>}
              </Box>
            </section>
          );
        })}

      {done && workspace && scan.checks.includes("public_match") && <div className="mb-8"><SourcesPanel workspaceId={workspace.id} scan={scan} /></div>}

      {done && workspace && (
        <div className="mb-8">
          <LedgerPanel workspaceId={workspace.id} scanId={scan.scan_id} />
        </div>
      )}

      {(problems.length > 0 || scan.errors.length > 0) && (
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
