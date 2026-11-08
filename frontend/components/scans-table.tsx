"use client";

import Link from "next/link";
import { Trash2 } from "lucide-react";
import type { Scan } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { Note, scanState, source } from "./bits";
import { cx } from "./ui";

function result(s: Scan): { text: string; dot: string } {
  const st = scanState(s);
  if (st.tone === "busy") return { text: "Checking…", dot: "animate-pulse bg-accent" };
  const n = typeof s.summary.observations === "number" ? s.summary.observations : null;
  if (n === null) return { text: st.text, dot: "bg-med" };
  if (n === 0) return { text: "Nothing found", dot: "bg-local" };
  return { text: `${n} ${n === 1 ? "problem" : "problems"}`, dot: "bg-med" };
}

/** Scans from every client (web app, coding assistant, CLI), newest first. One line each: result, where it came from, when. */
export function ScansTable({
  scans,
  limit,
  empty,
  onDelete,
}: {
  scans: Scan[] | null;
  limit?: number;
  empty: string;
  onDelete?: (scanId: string) => void;
}) {
  if (scans === null) return <Note>Loading…</Note>;
  if (scans.length === 0) return <Note>{empty}</Note>;
  return (
    <ul>
      {scans.slice(0, limit).map((s) => {
        const r = result(s);
        return (
          <li key={s.scan_id} className="group relative border-t border-line first:border-t-0">
            <Link href={`/scan/${s.scan_id}`} className={cx("flex items-center gap-3 px-4 py-3 text-sm hover:bg-panel-2", onDelete && "pr-12")}>
              <span className={cx("size-2 shrink-0 rounded-full", r.dot)} />
              <span className="w-32 shrink-0 text-ink">{r.text}</span>
              <span className="min-w-0 flex-1 truncate text-mute">
                {source(s)}
                {s.recheck_of && " · recheck"}
              </span>
              <span className="shrink-0 text-faint">{relativeTime(s.created_at)}</span>
            </Link>
            {onDelete && r.text !== "Checking…" && (
              <button
                type="button"
                onClick={() => onDelete(s.scan_id)}
                aria-label="Delete scan"
                className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-faint opacity-0 transition-opacity hover:bg-raised hover:text-ink focus:opacity-100 group-hover:opacity-100"
              >
                <Trash2 className="size-3.5" aria-hidden />
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
