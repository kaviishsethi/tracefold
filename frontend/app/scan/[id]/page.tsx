"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, coverageNote, isTerminal, useScan, ws, type Finding, type FindingKind, type Page } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Box, FindingRow, H1, Note, scanState, source } from "@/components/bits";
import { SourcesPanel } from "@/components/scan-sources";
import { ErrorNote, Spinner } from "@/components/ui";

const GROUPS: [FindingKind, string][] = [
  ["public_exposure", "Found on public pages"],
  ["local_risk", "Risks in your files"],
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
  const drafted = typeof scan.summary.actions_drafted === "number" ? scan.summary.actions_drafted : 0;
  const problems = scan.coverage.filter((c) => c.status === "partial" || c.status === "failed");

  return (
    <div>
      <Link href="/scan" className="text-sm text-mute hover:text-ink">
        ← Scans
      </Link>
      <div className="mt-4">
        <H1 sub={`${source(scan)} · ${relativeTime(scan.created_at)}${scan.recheck_of ? " · recheck" : ""}`}>
          <span className="inline-flex items-center gap-3">
            {st.tone === "busy" && <Spinner className="size-5" />}
            {st.text}
          </span>
        </H1>
      </div>

      {drafted > 0 && (
        <Link href="/actions" className="mb-8 flex items-center justify-between rounded-card border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-ink">
          {drafted} {drafted === 1 ? "fix needs" : "fixes need"} your approval
          <span className="font-medium">Review →</span>
        </Link>
      )}

      {done &&
        GROUPS.map(([kind, label]) => {
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

      {(problems.length > 0 || scan.errors.length > 0) && (
        <details className="text-sm text-mute">
          <summary className="cursor-pointer text-ink-2">What didn&apos;t finish</summary>
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
        </details>
      )}
    </div>
  );
}
