"use client";

import { useEffect, useState } from "react";
import { api, ws, type ApiError, type LedgerEvent, type Page } from "@/lib/api";
import { Disclosure } from "./bits";
import { ErrorNote, cx } from "./ui";

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

/** The outbound ledger for one scan, folded into one line: where requests went, with the full list on demand. */
export function LedgerPanel({ workspaceId, scanId }: { workspaceId: string; scanId: string }) {
  const [rows, setRows] = useState<LedgerEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  if (!rows) return null;

  const external = rows.filter((r) => kindOf(r) !== "model");
  const hosts = [...new Set(external.map((r) => r.destination_host))].sort();
  const shown = [...rows].sort((a, b) => a.at.localeCompare(b.at));
  const label = (
    <span className="flex min-w-0 items-center gap-2.5">
      <span className={cx("size-1.5 shrink-0 rounded-full", external.length ? "bg-med" : "bg-local")} />
      <span className="truncate">
        {external.length === 0 ? "Nothing left this machine" : `Sent to ${hosts.length === 1 ? hosts[0] : `${hosts.length} sites`}`}
      </span>
      <span className="shrink-0 text-faint">
        {rows.length} {rows.length === 1 ? "request" : "requests"}
      </span>
    </span>
  );
  if (rows.length === 0) return <p className="flex items-center gap-2.5 px-1 text-sm text-ink-2"><span className="size-1.5 rounded-full bg-local" />Nothing left this machine</p>;

  return (
    <Disclosure label={label}>
      <div className="-mx-4 -my-3 max-h-[420px] overflow-auto">
        <table className="w-full min-w-[560px] table-fixed text-left text-[13px]">
          <colgroup>
            <col className="w-[84px]" />
            <col className="w-[104px]" />
            <col />
            <col className="w-[56px]" />
          </colgroup>
          <tbody>
            {shown.map((r) => (
              <tr key={r.event_id} className={cx("border-b border-line last:border-0", failed(r.status) && "bg-crit/[0.05]")}>
                <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-faint" title={r.at}>
                  {time(r.at)}
                </td>
                <td className="whitespace-nowrap px-4 py-2 text-xs text-mute">{KIND[kindOf(r)]}</td>
                <td className="truncate px-4 py-2 text-xs text-ink-2" title={`${r.destination_host} ${sent(r)}`}>
                  {sent(r)}
                </td>
                <td className={cx("whitespace-nowrap px-4 py-2 text-right font-mono text-xs", failed(r.status) ? "text-crit" : "text-faint")}>{r.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Disclosure>
  );
}
