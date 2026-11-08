"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ws, type ApiError, type Finding, type FindingKind, type Page } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Card, Chips, Dot, H1, Note, findingPlace } from "@/components/bits";
import { ErrorNote, StatusPill, cx } from "@/components/ui";

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
  const count = (k: Where) => byState.filter((f) => k === "all" || f.kind === k).length;
  const rows = byState
    .filter((f) => where === "all" || f.kind === where)
    .sort((a, b) => (SEV_RANK[a.latest?.severity ?? ""] ?? 3) - (SEV_RANK[b.latest?.severity ?? ""] ?? 3) || (b.latest?.created_at ?? "").localeCompare(a.latest?.created_at ?? ""));

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

      <Card title={`${rows.length} ${rows.length === 1 ? "finding" : "findings"}`}>
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
                {rows.map((f) => (
                  <tr
                    key={f.finding_id}
                    onClick={() => router.push(`/findings/${f.finding_id}`)}
                    className="cursor-pointer border-b border-line last:border-0 hover:bg-panel-2"
                  >
                    <td className="px-5 py-3">
                      <a href={`/findings/${f.finding_id}`} onClick={(e) => e.preventDefault()} className="flex items-center gap-3 text-ink">
                        <Dot severity={f.latest?.severity} />
                        <span className="truncate">{f.latest?.title ?? f.rule_id ?? "Finding"}</span>
                      </a>
                    </td>
                    <td className="max-w-[260px] truncate px-5 py-3 font-mono text-xs text-mute">{findingPlace(f) || "Withheld"}</td>
                    <td className="px-5 py-3 text-mute">{f.kind === "public_exposure" ? "Public page" : "Your files"}</td>
                    <td className="px-5 py-3">
                      <StatusPill status={f.status} />
                    </td>
                    <td className="px-5 py-3 text-right text-faint">{relativeTime(f.latest?.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
