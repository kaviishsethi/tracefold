"use client";
import { useEffect, useState } from "react";
import { allSources, COMPARISON_LABEL, DISCOVERY_OUTCOME, FETCH_LABEL, type ApiError, type Scan, type SourcePage } from "@/lib/api";
import { ErrorNote, Loading, Panel, cx } from "./ui";
const hostOf = (url: string) => { try { return new URL(url).host; } catch { return url; } };
const COMPARISON_TONE: Record<string, string> = { matched: "text-accent", no_match: "text-mute", not_compared: "text-faint", failed: "text-med" };
export function SourcesPanel({ workspaceId, scan }: { workspaceId: string; scan: Scan }) {
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
  const unconfigured = !!d && d.provider_queries.length > 0 && d.provider_queries.every((q) => `${q.error ?? ""} ${q.status}`.includes("not_configured"));
  if (unconfigured && page.items.length === 0)
    return (
      <section className="rounded-card border border-med/30 bg-med/[0.06] px-4 py-3.5 text-sm">
        <p className="font-medium text-ink">Public search isn&apos;t set up</p>
        <p className="mt-1 text-mute">
          Add <code className="font-mono text-[13px] text-ink-2">EXA_API_KEY</code> or <code className="font-mono text-[13px] text-ink-2">TAVILY_API_KEY</code> to{" "}
          <code className="font-mono text-[13px] text-ink-2">server/.env</code>, restart the engine, and scan again.
        </p>
      </section>
    );
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
          <p className={cx("text-[13px]", d.outcome === "search_failed" || d.outcome === "no_candidates" || d.outcome === "budget_exhausted" ? "text-med" : "text-ink-2")}>
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

