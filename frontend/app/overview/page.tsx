"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Upload } from "lucide-react";
import { api, listScans, ws, type Action, type ApiError, type Finding, type Page, type Scan } from "@/lib/api";
import { useCurrentWorkspace } from "@/components/shell";
import { Card, Dot, H1, Note, Stat, findingPlace } from "@/components/bits";
import { ScansTable } from "@/components/scans-table";
import { ErrorNote, LinkButton, cx } from "@/components/ui";

const DAYS = 14;
const SEV_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

async function allFindings(wsId: string): Promise<Finding[]> {
  const out: Finding[] = [];
  let cursor: string | null = null;
  do {
    const page: Page<Finding> = await api<Page<Finding>>(ws(wsId, `/findings?limit=100${cursor ? `&cursor=${cursor}` : ""}`));
    out.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor && out.length < 1000);
  return out;
}

/** Scans per day for the last two weeks, split by where they came from. */
function ScanChart({ scans }: { scans: Scan[] }) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Array.from({ length: DAYS }, (_, i) => {
    const d = new Date(today);
    d.setDate(d.getDate() - (DAYS - 1 - i));
    return d;
  });
  const buckets = days.map((d) => {
    const next = new Date(d);
    next.setDate(next.getDate() + 1);
    const inDay = scans.filter((s) => {
      const t = new Date(s.created_at);
      return t >= d && t < next;
    });
    return { d, assistant: inDay.filter((s) => s.started_from === "assistant").length, other: inDay.filter((s) => s.started_from !== "assistant").length };
  });
  const max = Math.max(1, ...buckets.map((b) => b.assistant + b.other));
  return (
    <div className="px-5 pb-4 pt-5">
      <div className="flex h-40 items-end gap-1.5">
        {buckets.map((b) => {
          const total = b.assistant + b.other;
          return (
            <div key={b.d.toISOString()} className="group flex h-full flex-1 flex-col justify-end" title={`${b.d.toLocaleDateString()}: ${total} scans`}>
              {total > 0 ? (
                <>
                  <div className="rounded-t-[3px] bg-ink-2/70" style={{ height: `${(b.other / max) * 100}%` }} />
                  <div className={cx("bg-accent", b.other === 0 && "rounded-t-[3px]")} style={{ height: `${(b.assistant / max) * 100}%` }} />
                </>
              ) : (
                <div className="h-px bg-line-strong" />
              )}
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-faint">
        <span>{days[0].toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
        <span>Today</span>
      </div>
      <div className="mt-3 flex gap-4 text-xs text-mute">
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-sm bg-accent" /> Coding assistant
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-sm bg-ink-2/70" /> Web app and CLI
        </span>
      </div>
    </div>
  );
}

export default function Overview() {
  const { current: workspace } = useCurrentWorkspace();
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [scans, setScans] = useState<Scan[] | null>(null);
  const [approvals, setApprovals] = useState<Action[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspace) return;
    allFindings(workspace.id).then(setFindings).catch((e: ApiError) => setError(e.message));
    listScans(workspace.id, 100).then((p) => setScans(p.items)).catch(() => setScans([]));
    api<Page<Action>>(ws(workspace.id, "/actions?status=drafted&limit=100"))
      .then((p) => setApprovals(p.items))
      .catch(() => setApprovals([]));
  }, [workspace]);

  if (!workspace) return null;
  const open = (findings ?? []).filter((f) => f.status === "open");
  const pub = open.filter((f) => f.kind === "public_exposure").length;
  const local = open.length - pub;
  const weekAgo = Date.now() - 7 * 86400_000;
  const week = (scans ?? []).filter((s) => new Date(s.created_at).getTime() >= weekAgo);
  const fromAssistant = week.filter((s) => s.started_from === "assistant").length;
  const attention = [...open]
    .sort((a, b) => (SEV_RANK[a.latest?.severity ?? ""] ?? 3) - (SEV_RANK[b.latest?.severity ?? ""] ?? 3) || (b.latest?.created_at ?? "").localeCompare(a.latest?.created_at ?? ""))
    .slice(0, 6);
  const dash = findings === null ? "–" : undefined;

  return (
    <div>
      <H1
        sub={workspace.name}
        right={
          <LinkButton href="/scan" size="sm" className="!bg-accent !text-[#0a0c0c]">
            <Upload className="size-3.5" aria-hidden /> New scan
          </LinkButton>
        }
      >
        Overview
      </H1>
      <ErrorNote error={error} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Found on public pages" value={dash ?? pub} tone={pub ? "crit" : undefined} sub="Open copies of your text" href="/findings" />
        <Stat label="Risks in your files" value={dash ?? local} sub="Secrets, logging, markers" href="/findings" />
        <Stat label="Waiting for approval" value={approvals.length} tone={approvals.length ? "accent" : undefined} sub="Takedowns and key shut-offs" href="/actions" />
        <Stat label="Scans this week" value={scans === null ? "–" : week.length} sub={`${fromAssistant} from your coding assistant`} href="/scan" />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Card title="Needs attention" right={<Link href="/findings" className="text-xs text-mute hover:text-ink">View all</Link>}>
          {findings === null ? (
            <Note>Loading…</Note>
          ) : attention.length === 0 ? (
            <Note>Nothing open. New scans show up here as they finish.</Note>
          ) : (
            attention.map((f) => (
              <Link key={f.finding_id} href={`/findings/${f.finding_id}`} className="flex items-center gap-3 border-t border-line px-5 py-3 first:border-t-0 hover:bg-panel-2">
                <Dot severity={f.latest?.severity} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink">{f.latest?.title ?? "Finding"}</span>
                  <span className="block truncate text-xs text-faint">{findingPlace(f) || "Location withheld"}</span>
                </span>
                <span className="shrink-0 text-xs text-faint">{f.kind === "public_exposure" ? "Public page" : "Your files"}</span>
              </Link>
            ))
          )}
        </Card>

        <Card title="Scans, last 14 days">{scans === null ? <Note>Loading…</Note> : <ScanChart scans={scans} />}</Card>
      </div>

      <Card title="Recent scans" className="mt-4" right={<Link href="/scan" className="text-xs text-mute hover:text-ink">New scan</Link>}>
        <ScansTable scans={scans} limit={6} empty="No scans yet. Upload files, or ask your coding assistant to run scan_changes." />
      </Card>
    </div>
  );
}
