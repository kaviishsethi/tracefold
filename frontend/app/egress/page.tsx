"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import { api, recentScans, ws, type ApiError, type LedgerEvent, type Page, type RecentScan } from "@/lib/api";
import { relativeTime, shortId } from "@/lib/format";
import { useCurrentWorkspace } from "@/components/shell";
import { Select } from "@/components/select";
import { Button, Empty, ErrorNote, Loading, PageHeader, Panel, cx } from "@/components/ui";

function time(ts: string) {
  const d = new Date(ts);
  return isNaN(+d) ? ts : d.toLocaleTimeString([], { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
}

function compact(p: Record<string, unknown>) {
  return Object.entries(p)
    .map(([k, v]) => `${k}=${typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)}`)
    .join(" ");
}

const failed = (s: string) => s.startsWith("denied") || s.startsWith("error") || s === "failed" || /^http_[45]/.test(s);

function StatusChip({ status }: { status: string }) {
  return (
    <span
      className={cx(
        "inline-flex h-5 items-center rounded px-1.5 font-mono text-[10.5px] font-semibold tracking-wide whitespace-nowrap",
        failed(status) ? "bg-crit/15 text-crit" : "text-faint ring-1 ring-line ring-inset",
      )}
    >
      {status.toUpperCase()}
    </span>
  );
}

function EgressInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { current } = useCurrentWorkspace();
  const [recent, setRecent] = useState<RecentScan[]>([]);
  const [scanId, setScanId] = useState<string>(params.get("scan") ?? "");
  const [rows, setRows] = useState<LedgerEvent[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [category, setCategory] = useState("");

  useEffect(() => {
    if (!current) return;
    const list = recentScans(current.id);
    setRecent(list);
    setScanId((s) => s || list[0]?.scan_id || "");
  }, [current]);

  const load = useCallback(
    async (after: string | null) => {
      if (!current || !scanId) return;
      const q = `/scans/${encodeURIComponent(scanId)}/ledger?limit=100${after ? `&cursor=${encodeURIComponent(after)}` : ""}`;
      const page = await api<Page<LedgerEvent>>(ws(current.id, q));
      setRows((r) => (after && r ? [...r, ...page.items] : page.items));
      setCursor(page.next_cursor);
    },
    [current, scanId],
  );

  useEffect(() => {
    setRows(null);
    setSel(null);
    setError(null);
    setCategory("");
    load(null).catch((e: ApiError) => setError(e.status === 404 ? "This scan isn't in the current workspace, or it no longer exists." : e.message));
  }, [load]);

  async function more() {
    setLoadingMore(true);
    try {
      await load(cursor);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoadingMore(false);
    }
  }

  function pick(id: string) {
    setScanId(id);
    router.replace(`/egress?scan=${encodeURIComponent(id)}`);
  }

  const options = [...recent.map((s) => ({ value: s.scan_id, label: `${shortId(s.scan_id)} · ${s.label}` }))];
  if (scanId && !options.some((o) => o.value === scanId)) options.unshift({ value: scanId, label: shortId(scanId) });

  const row = rows?.find((r) => r.event_id === sel) ?? null;
  const categories = [...new Set((rows ?? []).map((r) => r.destination_category))].sort();
  const shown = (rows ?? []).filter((r) => !category || r.destination_category === category);
  const stats: [string, number | undefined, string][] = [
    ["Requests", rows?.length, "text-ink"],
    ["Destinations", rows ? new Set(rows.map((r) => r.destination_host)).size : undefined, "text-ink"],
    ["Categories", rows ? categories.length : undefined, "text-ink"],
    ["Denied or failed", rows?.filter((r) => failed(r.status)).length, rows?.some((r) => failed(r.status)) ? "text-crit" : "text-ink"],
  ];

  return (
    <div>
      <PageHeader
        title="Egress"
        subtitle="Every outbound request the engine made for this scan. Private file text is never sent; public pages are fetched by a separate worker."
        right={
          options.length > 0 ? <Select label="Scan" value={scanId} onChange={pick} options={options} align="end" size="md" className="max-w-[340px]" /> : undefined
        }
      />
      <ErrorNote error={error} />

      {!scanId ? (
        <Empty title="Pick a scan" action={<Link href="/scan" className="text-sm text-ink underline-offset-4 hover:underline">Start a scan</Link>}>
          The ledger is kept per scan. This browser hasn&apos;t started a scan yet, and the engine doesn&apos;t list past scans.
        </Empty>
      ) : (
        <>
          <div className="mb-6 grid grid-cols-2 overflow-hidden rounded-card border border-line bg-line [gap:1px] lg:grid-cols-4">
            {stats.map(([name, v, tone]) => (
              <div key={name} className="bg-panel px-5 py-4">
                <p className="text-xs text-mute">{name}</p>
                <p className={cx("mt-1.5 font-mono text-2xl tabular-nums", tone)}>
                  {v ?? "–"}
                  {cursor && v != null && name === "Requests" ? "+" : ""}
                </p>
              </div>
            ))}
          </div>

          <div className={cx("grid gap-6", row && "2xl:grid-cols-[minmax(0,1fr)_420px]")}>
            {!rows ? (
              error ? null : <Loading />
            ) : rows.length === 0 ? (
              <Empty title="No outbound requests for this scan">
                Nothing left the engine. That&apos;s expected for a scan without public matching, since local rules and the local model make no outside requests.
              </Empty>
            ) : (
              <Panel>
                <div className="flex flex-col gap-3 border-b border-line p-3 sm:flex-row sm:items-center">
                  <div role="tablist" aria-label="Category" className="flex flex-wrap gap-1">
                    {["", ...categories].map((c) => (
                      <button
                        key={c || "all"}
                        role="tab"
                        aria-selected={category === c}
                        onClick={() => setCategory(c)}
                        className={cx(
                          "inline-flex h-8 items-center gap-2 rounded-ctl px-3 text-[13px] transition-colors duration-150",
                          category === c ? "bg-raised text-ink" : "text-mute hover:bg-panel-2 hover:text-ink",
                        )}
                      >
                        {c ? c.replace(/_/g, " ") : "All"}
                        <span className="font-mono text-[11px] text-faint">{rows.filter((r) => !c || r.destination_category === c).length}</span>
                      </button>
                    ))}
                  </div>
                  <span className="text-xs text-faint sm:ml-auto">Payloads are summarized and redacted by the engine&apos;s gateway.</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[900px] text-left text-[13px]">
                    <thead className="text-xs text-faint">
                      <tr className="border-b border-line">
                        {["Time", "Category", "Destination", "Purpose", "Source", "Payload", "Status"].map((h) => (
                          <th key={h} className="px-4 py-2.5 font-normal">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {shown.map((r) => (
                        <tr
                          key={r.event_id}
                          onClick={() => setSel(r.event_id === sel ? null : r.event_id)}
                          className={cx(
                            "cursor-pointer border-b border-line transition-colors duration-150 last:border-0",
                            r.event_id === sel ? "bg-raised" : failed(r.status) ? "bg-crit/[0.05] hover:bg-crit/[0.09]" : "hover:bg-panel-2",
                          )}
                        >
                          <td className="whitespace-nowrap px-4 py-2.5 font-mono text-xs text-faint" title={r.at}>
                            {time(r.at)}
                          </td>
                          <td className="whitespace-nowrap px-4 py-2.5 text-xs text-mute">{r.destination_category}</td>
                          <td className="max-w-[240px] truncate px-4 py-2.5 font-mono text-xs text-ink">{r.destination_host}</td>
                          <td className="whitespace-nowrap px-4 py-2.5 text-mute">{r.purpose}</td>
                          <td className="max-w-[140px] truncate px-4 py-2.5 font-mono text-xs text-mute">{r.source_id ?? "–"}</td>
                          <td className="max-w-[260px] truncate px-4 py-2.5 font-mono text-xs text-faint">{compact(r.payload_summary)}</td>
                          <td className="px-4 py-2.5">
                            <StatusChip status={r.status} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {cursor && (
                  <div className="border-t border-line p-3 text-center">
                    <Button variant="ghost" size="sm" onClick={more} loading={loadingMore}>
                      Load more
                    </Button>
                  </div>
                )}
              </Panel>
            )}

            {row && (
              <Panel
                className="rise self-start 2xl:sticky 2xl:top-20"
                title={<span className="font-mono text-xs">{shortId(row.event_id)}</span>}
                meta={<span className="font-mono">{row.destination_host}</span>}
                actions={
                  <button onClick={() => setSel(null)} aria-label="Close" className="rounded-md p-1 text-faint transition-colors hover:bg-raised hover:text-ink">
                    <X className="size-4" aria-hidden />
                  </button>
                }
              >
                <dl className="divide-y divide-line text-sm">
                  {(
                    [
                      ["Status", <StatusChip key="s" status={row.status} />],
                      ["Category", row.destination_category],
                      ["Purpose", row.purpose],
                      ["Source", row.source_id ?? "None"],
                      ["When", `${relativeTime(row.at)} · ${time(row.at)}`],
                    ] as const
                  ).map(([k, v]) => (
                    <div key={k} className="flex items-center justify-between gap-4 px-4 py-3">
                      <dt className="text-faint">{k}</dt>
                      <dd className="text-right text-ink">{v}</dd>
                    </div>
                  ))}
                </dl>
                <p className="border-t border-line px-4 pt-3 text-xs text-faint">Payload summary</p>
                <pre className="scroll-thin max-h-[50vh] overflow-auto whitespace-pre-wrap break-all bg-[#0b0b0b] px-4 py-3 font-mono text-xs leading-5 text-ink-2">
                  {JSON.stringify(row.payload_summary, null, 2)}
                </pre>
              </Panel>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function Egress() {
  return (
    <Suspense fallback={<Loading />}>
      <EgressInner />
    </Suspense>
  );
}
