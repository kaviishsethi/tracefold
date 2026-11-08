"use client";

import { useEffect, useState } from "react";
import { api, ws, type ApiError, type LedgerEvent, type Page } from "@/lib/api";
import { ErrorNote, Loading, Panel, cx } from "./ui";

type Kind = "search" | "fetch" | "model" | "other";

const KIND: Record<Kind, string> = {
  search: "Searches",
  fetch: "Page fetches",
  model: "Local model",
  other: "Other",
};

function kindOf(e: LedgerEvent): Kind {
  if (e.destination_category === "local_model") return "model";
  if (e.purpose.startsWith("search")) return "search";
  if (e.purpose.startsWith("extract") || e.purpose.startsWith("fetch") || e.purpose.includes("retriev")) return "fetch";
  return "other";
}

const failed = (s: string) => s.startsWith("denied") || s.startsWith("error") || s === "failed" || /^(http_)?[45]\d\d$/.test(s);

/** What was actually sent: the query for searches, the URL for fetches, the endpoint for the local model. */
function sent(e: LedgerEvent): string {
  const p = e.payload_summary as Record<string, unknown>;
  if (typeof p.query === "string") return p.query;
  if (Array.isArray(p.urls) && p.urls.length) return p.urls.map(String).join(", ");
  if (typeof p.url === "string") return p.url;
  if (typeof p.endpoint === "string") return `${p.method ?? ""} ${p.endpoint}${p.model ? ` · ${p.model}` : ""}`.trim();
  return e.purpose.replaceAll("_", " ");
}

function time(ts: string) {
  const d = new Date(ts);
  return isNaN(+d) ? ts : d.toLocaleTimeString([], { hour12: false });
}

async function allEvents(workspaceId: string, scanId: string): Promise<LedgerEvent[]> {
  const out: LedgerEvent[] = [];
  let cursor: string | null = null;
  for (let i = 0; i < 10; i++) {
    const q: string = `/scans/${encodeURIComponent(scanId)}/ledger?limit=100${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
    const page: Page<LedgerEvent> = await api<Page<LedgerEvent>>(ws(workspaceId, q));
    out.push(...page.items);
    cursor = page.next_cursor;
    if (!cursor) break;
  }
  return out;
}

/** The outbound ledger for one scan: every request the engine made, as its gateway recorded it. */
export function LedgerPanel({ workspaceId, scanId }: { workspaceId: string; scanId: string }) {
  const [rows, setRows] = useState<LedgerEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind | "">("");

  useEffect(() => {
    let alive = true;
    allEvents(workspaceId, scanId)
      .then((r) => alive && setRows(r))
      .catch((e: ApiError) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [workspaceId, scanId]);

  if (error) return <ErrorNote error={error} />;
  if (!rows) return <Loading />;

  const counts = (Object.keys(KIND) as Kind[]).map((k) => [k, rows.filter((r) => kindOf(r) === k).length] as const).filter(([, n]) => n > 0);
  const external = rows.filter((r) => kindOf(r) !== "model");
  const hosts = [...new Set(external.map((r) => r.destination_host))].sort();
  const shown = rows.filter((r) => !kind || kindOf(r) === kind).sort((a, b) => a.at.localeCompare(b.at));

  return (
    <Panel title="What left this machine" meta={`${rows.length} ${rows.length === 1 ? "request" : "requests"}`}>
      <div className="space-y-1.5 border-b border-line px-4 py-3 text-[13px] text-ink-2">
        {rows.length === 0 ? (
          <p>No outbound requests. Local rules and the local model make no outside requests.</p>
        ) : (
          <>
            <p>
              {external.length === 0
                ? "Nothing was sent outside this machine."
                : `${external.length} ${external.length === 1 ? "request" : "requests"} went to ${hosts.join(", ")}.`}{" "}
              {counts.some(([k]) => k === "model") && "Local model calls stayed on this machine."}
            </p>
            <p className="text-xs text-faint">
              Each row is what the engine&apos;s outbound gateway recorded: search queries are the fixed queries shown above, fetches are public URLs. Provider keys are masked.
            </p>
          </>
        )}
      </div>
      {rows.length > 0 && (
        <>
          <div role="group" aria-label="Request type" className="flex flex-wrap gap-1 border-b border-line px-3 py-2">
            {([["", rows.length] as const, ...counts]).map(([k, n]) => (
              <button
                key={k || "all"}
                aria-pressed={kind === k}
                onClick={() => setKind(k)}
                className={cx(
                  "inline-flex h-8 items-center gap-2 rounded-ctl px-3 text-[13px] transition-colors",
                  kind === k ? "bg-raised text-ink" : "text-mute hover:bg-panel-2 hover:text-ink",
                )}
              >
                {k ? KIND[k] : "All"}
                <span className="font-mono text-[11px] text-faint">{n}</span>
              </button>
            ))}
          </div>
          <div className="max-h-[420px] overflow-auto">
            <table className="w-full min-w-[640px] table-fixed text-left text-[13px]">
              <colgroup>
                <col className="w-[88px]" />
                <col className="w-[110px]" />
                <col className="w-[150px]" />
                <col />
                <col className="w-[64px]" />
              </colgroup>
              <thead className="sticky top-0 bg-panel text-xs text-faint">
                <tr className="border-b border-line">
                  {["Time", "Type", "Destination", "Sent", "Status"].map((h) => (
                    <th key={h} className="px-4 py-2.5 font-normal">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <tr key={r.event_id} className={cx("border-b border-line align-top last:border-0", failed(r.status) && "bg-crit/[0.05]")}>
                    <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-faint" title={r.at}>
                      {time(r.at)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2 text-xs text-mute">{KIND[kindOf(r)]}</td>
                    <td className="truncate px-4 py-2 font-mono text-xs text-ink-2">{r.destination_host}</td>
                    <td className="truncate px-4 py-2 text-xs text-ink" title={sent(r)}>
                      {sent(r)}
                    </td>
                    <td className={cx("whitespace-nowrap px-4 py-2 font-mono text-xs", failed(r.status) ? "text-crit" : "text-faint")}>{r.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}
