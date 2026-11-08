"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronRight } from "lucide-react";
import type { Finding } from "@/lib/api";
import { relativeTime, where } from "@/lib/format";
import { Dot } from "./bits";
import { cx } from "./ui";

/** All passages from one file found on one public page. */
export interface PageMatch {
  key: string;
  url: string;
  title: string;
  path: string;
  items: Finding[];
  latestAt: string | undefined;
}

function pageTitle(f: Finding, url: string): string {
  const t = f.latest?.evidence[0]?.public?.discovery_origins?.[0]?.title;
  if (t) return t;
  try {
    const u = new URL(url);
    return u.host.replace(/^www\./, "") + (u.pathname === "/" ? "" : u.pathname);
  } catch {
    return url;
  }
}

/** Groups public findings by (file, page). Each passage is still its own finding underneath. */
export function groupByPage(findings: Finding[]): PageMatch[] {
  const groups = new Map<string, PageMatch>();
  for (const f of findings) {
    const url = f.latest?.evidence[0]?.public?.url ?? "";
    const key = `${f.path ?? ""}|${url}`;
    const g = groups.get(key);
    if (g) {
      g.items.push(f);
      if ((f.latest?.created_at ?? "") > (g.latestAt ?? "")) g.latestAt = f.latest?.created_at;
    } else {
      groups.set(key, { key, url, title: pageTitle(f, url), path: f.path ?? "", items: [f], latestAt: f.latest?.created_at });
    }
  }
  const out = [...groups.values()];
  for (const g of out)
    g.items.sort((a, b) => (a.latest?.evidence[0]?.location.line_start ?? 0) - (b.latest?.evidence[0]?.location.line_start ?? 0));
  return out.sort((a, b) => b.items.length - a.items.length);
}

export const passageLabel = (f: Finding) => {
  const loc = f.latest?.evidence[0]?.location;
  return loc ? where(loc) : "Passage";
};

/** One row per page; expands to list the matching passages, each linking to its finding. */
export function PageMatchRow({ g }: { g: PageMatch }) {
  const [open, setOpen] = useState(false);
  const n = g.items.length;
  const first = g.items[0];
  return (
    <div className="border-t border-line first:border-t-0">
      <button
        type="button"
        onClick={() => (n === 1 ? undefined : setOpen((o) => !o))}
        aria-expanded={n > 1 ? open : undefined}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-panel-2"
      >
        <Dot severity={first.latest?.severity} />
        <span className="min-w-0 flex-1">
          {n === 1 ? (
            <Link href={`/findings/${first.finding_id}`} className="block truncate text-[15px] text-ink hover:underline">
              {g.title}
            </Link>
          ) : (
            <span className="block truncate text-[15px] text-ink">{g.title}</span>
          )}
          <span className="block truncate text-[13px] text-faint">
            {g.path} · {n} matching {n === 1 ? "passage" : "passages"}
          </span>
        </span>
        <span className="shrink-0 text-xs text-faint">{relativeTime(g.latestAt)}</span>
        {n > 1 && <ChevronRight className={cx("size-4 shrink-0 text-faint transition-transform", open && "rotate-90")} aria-hidden />}
      </button>
      {open && (
        <ul className="border-t border-line bg-bg/40 py-1">
          {g.items.map((f) => (
            <li key={f.finding_id}>
              <Link href={`/findings/${f.finding_id}`} className="flex items-center justify-between gap-3 py-2 pl-9 pr-4 text-[13px] text-ink-2 hover:bg-panel-2 hover:text-ink">
                <span>
                  {passageLabel(f)}
                  {f.latest?.title?.startsWith("Edited") && <span className="ml-2 text-xs text-faint">edited</span>}
                </span>
                {f.status !== "open" && <span className="text-xs text-local">No longer found</span>}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
