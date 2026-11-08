"use client";

import Link from "next/link";
import type { Scan } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { Note, scanState, source } from "./bits";
import { cx } from "./ui";

/** Scans from every client (web app, coding assistant, CLI), newest first. */
export function ScansTable({ scans, limit, empty }: { scans: Scan[] | null; limit?: number; empty: string }) {
  if (scans === null) return <Note>Loading…</Note>;
  if (scans.length === 0) return <Note>{empty}</Note>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead className="text-xs text-faint">
          <tr className="border-b border-line">
            {["Started from", "Result", "Checks", "When"].map((h, i) => (
              <th key={h} className={cx("px-5 py-2.5 font-normal", i === 3 && "text-right")}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {scans.slice(0, limit).map((s) => {
            const st = scanState(s);
            const n = typeof s.summary.observations === "number" ? s.summary.observations : null;
            return (
              <tr key={s.scan_id} className="border-b border-line last:border-0 hover:bg-panel-2">
                <td className="px-5 py-3">
                  <Link href={`/scan/${s.scan_id}`} className="flex items-center gap-2.5 text-ink">
                    <span className={cx("size-2 rounded-full", st.tone === "busy" ? "animate-pulse bg-accent" : st.tone === "done" ? "bg-local" : "bg-med")} />
                    {source(s)}
                    {s.recheck_of && <span className="text-xs text-faint">recheck</span>}
                  </Link>
                </td>
                <td className="px-5 py-3 text-mute">{st.tone === "busy" ? st.text : n === null ? st.text : n === 0 ? "Nothing found" : `${n} found`}</td>
                <td className="px-5 py-3 text-xs text-faint">{s.checks.map((c) => (c === "public_match" ? "Public pages" : "Your files")).join(" · ")}</td>
                <td className="px-5 py-3 text-right text-faint">{relativeTime(s.created_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
