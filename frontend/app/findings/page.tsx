"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ws, type ApiError, type Finding, type FindingKind, type Page } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Card, Chips, Dot, H1, Note, findingPlace } from "@/components/bits";
import { ErrorNote, StatusPill, cx } from "@/components/ui";
import { groupByPage, passageLabel, type PageMatch } from "@/components/page-matches";

type Where = "all" | FindingKind;
type State = "open" | "all";
const SEV_RANK: Record<string, number> = { high: 0, medium: 1, low: 2 };

export default function Findings() {
  const { current: workspace } = useCurrentWorkspace();
  const router = useRouter();
  const [all, setAll] = useState<Finding[] | null>(null);
  const [where, setWhere] = useState<Where>("all");
  const [state, setState] = useState<State>("open");
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!workspace) return;
    (async () => {
      const out: Finding[] = [];
      let cursor: string | null = null;
      do {
        const page: Page<Finding> = await api<Page<Finding>>(ws(workspace.id, `/findings?limit=100${cursor ? `&cursor=${cursor}` : ""}`));
        out.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor && out.length < 1000);
      setAll(out);
    })().catch((e: ApiError) => setError(e.message));
  }, [workspace]);

  const byState = (all ?? []).filter((f) => state === "all" || f.status === "open");
  const count = (k: Where) => {
    const local = byState.filter((f) => f.kind === "local_risk").length;
    const pages = groupByPage(byState.filter((f) => f.kind === "public_exposure")).length;
    return k === "all" ? local + pages : k === "local_risk" ? local : pages;
  };
  const rows = byState
    .filter((f) => where === "all" || f.kind === where)
    .sort((a, b) => (SEV_RANK[a.latest?.severity ?? ""] ?? 3) - (SEV_RANK[b.latest?.severity ?? ""] ?? 3) || (b.latest?.created_at ?? "").localeCompare(a.latest?.created_at ?? ""));

  // One row per page that copies a file; its passages open underneath.
  const display: (Finding | PageMatch)[] = [...groupByPage(rows.filter((f) => f.kind === "public_exposure")), ...rows.filter((f) => f.kind !== "public_exposure")];
  const toggle = (k: string) => setExpanded((s) => (s.has(k) ? new Set([...s].filter((x) => x !== k)) : new Set([...s, k])));
  const shown = display.length;

  return (
    <div>
      <H1>Findings</H1>
      <ErrorNote error={error} />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Chips<Where>
          value={where}
          onChange={setWhere}
          options={[
            ["all", "All", count("all")],
            ["public_exposure", "Public pages", count("public_exposure")],
            ["local_risk", "Your files", count("local_risk")],
          ]}
        />
        <Chips<State> value={state} onChange={setState} options={[["open", "Open"], ["all", "All, including closed"]]} />
      </div>

      <Card title={`${shown} ${shown === 1 ? "finding" : "findings"}`}>
        {all === null ? (
          <Note>Loading…</Note>
        ) : rows.length === 0 ? (
          <Note>{state === "open" ? "Nothing open here. Findings from new scans show up as they finish." : "No findings yet."}</Note>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="text-xs text-faint">
                <tr className="border-b border-line">
                  {["Finding", "Where", "Found in", "Status", "Last seen"].map((h, i) => (
                    <th key={h} className={cx("px-5 py-2.5 font-normal", i === 4 && "text-right")}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {display.map((item) =>
                  "items" in item ? (
                    <PageGroupRows key={item.key} g={item} open={expanded.has(item.key)} onToggle={() => toggle(item.key)} onOpen={(id) => router.push(`/findings/${id}`)} />
                  ) : (
                    <tr
                      key={item.finding_id}
                      onClick={() => router.push(`/findings/${item.finding_id}`)}
                      className="cursor-pointer border-b border-line last:border-0 hover:bg-panel-2"
                    >
                      <td className="px-5 py-3">
                        <a href={`/findings/${item.finding_id}`} onClick={(e) => e.preventDefault()} className="flex items-center gap-3 text-ink">
                          <Dot severity={item.latest?.severity} />
                          <span className="truncate">{item.latest?.title ?? item.rule_id ?? "Finding"}</span>
                        </a>
                      </td>
                      <td className="max-w-[260px] truncate px-5 py-3 font-mono text-xs text-mute">{findingPlace(item) || "Withheld"}</td>
                      <td className="px-5 py-3 text-mute">Your files</td>
                      <td className="px-5 py-3">
                        <StatusPill status={item.status} />
                      </td>
                      <td className="px-5 py-3 text-right text-faint">{relativeTime(item.latest?.created_at)}</td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function PageGroupRows({ g, open, onToggle, onOpen }: { g: PageMatch; open: boolean; onToggle: () => void; onOpen: (id: string) => void }) {
  const n = g.items.length;
  const first = g.items[0];
  const allClosed = g.items.every((f) => f.status !== "open");
  return (
    <>
      <tr onClick={() => (n === 1 ? onOpen(first.finding_id) : onToggle())} className="cursor-pointer border-b border-line last:border-0 hover:bg-panel-2">
        <td className="px-5 py-3">
          <span className="flex items-center gap-3 text-ink">
            <Dot severity={first.latest?.severity} />
            <span className="truncate">{g.title}</span>
            {n > 1 && <span className="shrink-0 text-xs text-faint">{n} passages</span>}
          </span>
        </td>
        <td className="max-w-[260px] truncate px-5 py-3 font-mono text-xs text-mute">{g.path || "Withheld"}</td>
        <td className="px-5 py-3 text-mute">Public page</td>
        <td className="px-5 py-3">
          <StatusPill status={allClosed ? first.status : "open"} />
        </td>
        <td className="px-5 py-3 text-right text-faint">{relativeTime(g.latestAt)}</td>
      </tr>
      {open &&
        g.items.map((f) => (
          <tr key={f.finding_id} onClick={() => onOpen(f.finding_id)} className="cursor-pointer border-b border-line bg-bg/40 hover:bg-panel-2">
            <td className="py-2 pl-12 pr-5 text-[13px] text-ink-2" colSpan={3}>
              {passageLabel(f)}
            </td>
            <td className="px-5 py-2">
              <StatusPill status={f.status} />
            </td>
            <td className="px-5 py-2 text-right text-xs text-faint">{relativeTime(f.latest?.created_at)}</td>
          </tr>
        ))}
    </>
  );
}
