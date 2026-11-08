"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { RISK_REVIEW_LABEL, api, ws, type ApiError, type Finding, type FindingKind, type Page } from "@/lib/api";
import { relativeTime, where } from "@/lib/format";
import { NewScanButton, useCurrentWorkspace } from "@/components/shell";
import { Empty, ErrorNote, Loading, PageHeader, Panel, SeverityBadge, StatusPill, cx } from "@/components/ui";

type Filter = "open" | "all";

const SECTIONS: { kind: FindingKind; title: string; meta: string; none: Record<Filter, string> }[] = [
  {
    kind: "public_exposure",
    title: "Public exposure",
    meta: "your text found on a public page",
    none: {
      open: "No open public exposures. Only scans that ran public matching can find them.",
      all: "No public exposures recorded. Only scans that ran public matching can find them.",
    },
  },
  {
    kind: "local_risk",
    title: "Potential risks in your files",
    meta: "from reviewing the files you scanned",
    none: {
      open: "No open potential risks in your files.",
      all: "No potential risks recorded for this workspace.",
    },
  },
];

const HUMAN_REVIEW: Record<string, string> = { acknowledged: "Acknowledged", dismissed: "Dismissed" };

async function allFindings(workspaceId: string): Promise<Finding[]> {
  const out: Finding[] = [];
  let cursor: string | null = null;
  do {
    const q = new URLSearchParams({ limit: "100" });
    if (cursor) q.set("cursor", cursor);
    const page: Page<Finding> = await api<Page<Finding>>(ws(workspaceId, `/findings?${q}`));
    out.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor);
  return out;
}

function FindingRows({ rows }: { rows: Finding[] }) {
  const router = useRouter();
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] text-left text-[13px]">
        <thead className="text-xs text-faint">
          <tr className="border-b border-line">
            <th className="w-[110px] px-4 py-2.5 font-normal">Severity</th>
            <th className="px-4 py-2.5 font-normal">Finding</th>
            <th className="px-4 py-2.5 font-normal">Where</th>
            <th className="px-4 py-2.5 font-normal">Review</th>
            <th className="px-4 py-2.5 font-normal">Status</th>
            <th className="px-4 py-2.5 font-normal">Last seen</th>
            <th className="w-8" />
          </tr>
        </thead>
        <tbody>
          {rows.map((f) => {
            const o = f.latest;
            const loc = o?.evidence[0]?.location;
            const at = loc ? where(loc) : "";
            const filePath = f.path ?? loc?.path ?? null;
            return (
              <tr
                key={f.finding_id}
                onClick={() => router.push(`/findings/${f.finding_id}`)}
                className="group h-12 cursor-pointer border-b border-line transition-colors duration-150 last:border-0 hover:bg-panel-2"
              >
                <td className="px-4">
                  <SeverityBadge severity={o?.severity} />
                </td>
                <td className="max-w-[340px] px-4">
                  <Link href={`/findings/${f.finding_id}`} onClick={(e) => e.stopPropagation()} className="block truncate font-medium text-ink">
                    {o?.title ?? f.check_id}
                  </Link>
                  {f.human_review !== "unreviewed" && <span className="block text-xs text-faint">{HUMAN_REVIEW[f.human_review]}</span>}
                </td>
                <td className="max-w-[260px] px-4">
                  {filePath ? (
                    <span className="block truncate font-mono text-[12.5px] text-ink-2" title={filePath}>
                      {filePath}
                      {at && <span className="text-faint"> · {at}</span>}
                    </span>
                  ) : (
                    <span className="text-faint">{at || "Path withheld"}</span>
                  )}
                </td>
                <td className={cx("px-4", o?.risk_review === "supported" ? "text-ink-2" : "text-mute")}>{o ? RISK_REVIEW_LABEL[o.risk_review] : "–"}</td>
                <td className="px-4">
                  <StatusPill status={f.status} />
                </td>
                <td className="px-4 text-mute" title={o?.created_at}>
                  {relativeTime(o?.created_at)}
                </td>
                <td className="pr-3 text-faint">
                  <ChevronRight className="size-4 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-ink" aria-hidden />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FindingsInner() {
  const router = useRouter();
  const params = useSearchParams();
  const filter: Filter = params.get("status") === "all" ? "all" : "open";
  const { current } = useCurrentWorkspace();
  const [all, setAll] = useState<Finding[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!current) return;
    let alive = true;
    setAll(null);
    setError(null);
    allFindings(current.id)
      .then((xs) => alive && setAll(xs))
      .catch((e) => alive && setError((e as ApiError).message));
    return () => {
      alive = false;
    };
  }, [current]);

  if (!current)
    return (
      <div>
        <PageHeader title="Findings" />
        <Empty title="No workspace">This app&apos;s access grant doesn&apos;t cover a workspace yet.</Empty>
      </div>
    );

  const shown = (all ?? []).filter((f) => filter === "all" || f.status === "open");
  const count = (k: Filter) => (all ? all.filter((f) => k === "all" || f.status === "open").length : null);

  return (
    <div>
      <PageHeader
        title="Findings"
        subtitle="What the engine found in your scans. Public exposure and potential risks in your files are kept separate."
        right={
          <div role="tablist" aria-label="Status" className="flex gap-1">
            {(["open", "all"] as Filter[]).map((k) => (
              <button
                key={k}
                role="tab"
                aria-selected={filter === k}
                onClick={() => router.replace(k === "open" ? "/findings" : "/findings?status=all", { scroll: false })}
                className={cx(
                  "inline-flex h-8 shrink-0 items-center gap-2 rounded-ctl px-3 text-[13px] transition-colors duration-150",
                  filter === k ? "bg-raised text-ink" : "text-mute hover:bg-panel-2 hover:text-ink",
                )}
              >
                {k === "open" ? "Open" : "All"}
                <span className="font-mono text-[11px] text-faint">{count(k) ?? "–"}</span>
              </button>
            ))}
          </div>
        }
      />
      <ErrorNote error={error} />

      {!all ? (
        error ? null : <Loading />
      ) : all.length === 0 ? (
        <Empty title="No findings yet" action={<NewScanButton size="md" />}>
          Scan files to check them for potential risks and, if you choose, for copies on public pages.
        </Empty>
      ) : (
        <div className="space-y-6">
          {SECTIONS.map((s) => {
            const rows = shown.filter((f) => f.kind === s.kind);
            return (
              <Panel key={s.kind} title={s.title} meta={`${rows.length} · ${s.meta}`}>
                {rows.length ? <FindingRows rows={rows} /> : <p className="px-4 py-6 text-[13px] text-mute">{s.none[filter]}</p>}
              </Panel>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function Findings() {
  return (
    <Suspense fallback={<Loading />}>
      <FindingsInner />
    </Suspense>
  );
}
