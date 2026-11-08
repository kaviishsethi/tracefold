"use client";

import Link from "next/link";
import { useState } from "react";
import type { PageMatch } from "./page-matches";
import { passageLabel } from "./page-matches";
import { cx } from "./ui";

function host(url: string): string {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/** "Duolingo will replace contract workers with AI | The Verge" -> site "The Verge", headline before it. */
function split(title: string, url: string): { site: string; headline: string } {
  const m = title.match(/^(.*\S)\s+[|\-–—]\s+([^|\-–—]{2,40})$/);
  if (m) return { site: m[2].trim(), headline: m[1].trim() };
  const h = host(url);
  const name = h.split(".").slice(-2, -1)[0] ?? h;
  return { site: name.charAt(0).toUpperCase() + name.slice(1), headline: title };
}

function day(ts: string | undefined) {
  if (!ts) return { month: "", year: "" };
  const d = new Date(ts);
  return { month: d.toLocaleString("en", { month: "short" }), day: d.getDate(), year: d.getFullYear() };
}

/** The icon the site declares (served by /api/icon, which drops empty placeholders), or its first letter. */
function SiteIcon({ url, site }: { url: string; site: string }) {
  const [failed, setFailed] = useState(false);
  const h = host(url);
  return (
    <span className={cx("grid size-10 shrink-0 place-content-center overflow-hidden rounded-[8px] border", !failed && h ? "border-transparent bg-white" : "border-line bg-raised")}>
      {!failed && h ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`/api/icon?host=${encodeURIComponent(h)}`}
          alt=""
          referrerPolicy="no-referrer"
          className="size-6"
          onError={() => setFailed(true)}
          onLoad={(e) => e.currentTarget.naturalWidth < 8 && setFailed(true)}
        />
      ) : (
        <span className="text-sm font-semibold text-ink-2">{site.charAt(0).toUpperCase()}</span>
      )}
    </span>
  );
}

/** One public page with its passages from every file in the scan. */
interface Site {
  key: string;
  url: string;
  title: string;
  files: PageMatch[]; // one per file, each with that file's passages
  latestAt: string | undefined;
}

function bySite(groups: PageMatch[]): Site[] {
  const out = new Map<string, Site>();
  for (const g of groups) {
    const s = out.get(g.url);
    if (s) {
      s.files.push(g);
      if ((g.latestAt ?? "") > (s.latestAt ?? "")) s.latestAt = g.latestAt;
    } else out.set(g.url, { key: g.url, url: g.url, title: g.title, files: [g], latestAt: g.latestAt });
  }
  return [...out.values()];
}

function SiteCard({ g }: { g: Site }) {
  const [open, setOpen] = useState(false);
  const { site, headline } = split(g.title, g.url);
  const items = g.files.flatMap((f) => f.items);
  const n = items.length;
  return (
    <div className="rounded-card border border-line bg-panel p-5">
      <div className="flex items-center gap-3">
        <SiteIcon url={g.url} site={site} />
        <div className="min-w-0">
          <p className="truncate text-[15px] font-medium text-ink">{site}</p>
          <p className="truncate text-xs text-faint">{host(g.url)}</p>
        </div>
      </div>
      <p className="mt-4 text-sm leading-relaxed text-ink-2">{headline}</p>
      <p className="mt-3 text-[13px] text-mute">
        {g.files.length === 1 ? (
          <>
            {n} {n === 1 ? "passage" : "passages"} from <span className="font-mono text-[12px] text-ink-2">{g.files[0].path}</span>
          </>
        ) : (
          <>
            {n} passages from {g.files.length} files:{" "}
            {g.files.map((f, i) => (
              <span key={f.key}>
                {i > 0 && ", "}
                <span className="font-mono text-[12px] text-ink-2">{f.path}</span> ({f.items.length})
              </span>
            ))}
          </>
        )}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {n === 1 ? (
          <Link href={`/findings/${items[0].finding_id}`} className="inline-flex h-8 items-center rounded-ctl border border-line-strong px-3 text-[13px] text-ink hover:bg-panel-2">
            View passage
          </Link>
        ) : (
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="inline-flex h-8 items-center rounded-ctl border border-line-strong px-3 text-[13px] text-ink hover:bg-panel-2"
          >
            {open ? "Hide passages" : "View passages"}
          </button>
        )}
        <a href={g.url} target="_blank" rel="noreferrer noopener" className="inline-flex h-8 items-center rounded-ctl px-3 text-[13px] text-mute hover:text-ink">
          Open page
        </a>
      </div>
      {open && (
        <ul className="mt-3 border-t border-line pt-2">
          {items.map((f) => (
            <li key={f.finding_id}>
              <Link href={`/findings/${f.finding_id}`} className="flex items-center justify-between rounded-[6px] px-2 py-1.5 text-[13px] text-ink-2 hover:bg-panel-2 hover:text-ink">
                <span>
                  {g.files.length > 1 && <span className="mr-2 font-mono text-[12px] text-faint">{f.path}</span>}
                  {passageLabel(f)}
                  {f.latest?.title?.startsWith("Edited") && <span className="ml-2 text-xs text-faint">edited</span>}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** A count of sites, then one card per site along a line, alternating sides on wide screens. */
export function LeakTimeline({ groups }: { groups: PageMatch[] }) {
  const merged = bySite(groups);
  const sites = new Set(merged.map((g) => host(g.url))).size;
  const files = [...new Set(groups.map((g) => g.path))];
  const count = (g: Site) => g.files.reduce((n, f) => n + f.items.length, 0);
  const ordered = merged.sort((a, b) => (b.latestAt ?? "").localeCompare(a.latestAt ?? "") || count(b) - count(a));
  return (
    <section className="mb-10">
      <div className="mb-10 rounded-card border border-crit/30 bg-crit/[0.06] px-6 py-8 text-center">
        <p className="text-5xl font-semibold tracking-[-0.03em] text-crit">{sites}</p>
        <p className="mt-2 text-lg font-medium text-ink">{sites === 1 ? "site" : "sites"} with text from your files</p>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-mute">
          Passages from{" "}
          {files.map((f, i) => (
            <span key={f}>
              {i > 0 && (i === files.length - 1 ? " and " : ", ")}
              <span className="font-mono text-[13px] text-ink-2">{f}</span>
            </span>
          ))}{" "}
          appear
          on these public pages. Check each one before asking for a takedown.
        </p>
      </div>

      <div className="relative">
        <div aria-hidden className="absolute bottom-0 left-5 top-0 w-px bg-line-strong lg:left-1/2" />
        <ol className="space-y-8">
          {ordered.map((g, i) => {
            const d = day(g.latestAt);
            return (
              <li key={g.key} className="relative grid grid-cols-[40px_1fr] gap-4 lg:grid-cols-[1fr_56px_1fr] lg:gap-6">
                <div className={cx("hidden lg:block", i % 2 === 1 && "lg:order-3")}>
                  <SiteCard g={g} />
                </div>
                <div className="relative z-10 flex justify-center lg:order-2">
                  <span className="grid size-10 place-content-center rounded-full border border-line-strong bg-raised text-center text-[10px] font-medium leading-tight text-ink-2 lg:size-14 lg:text-[11px]">
                    {d.month}
                    <br />
                    {d.day}
                  </span>
                </div>
                <div className={cx("lg:hidden")}>
                  <SiteCard g={g} />
                </div>
                <div className={cx("hidden lg:block", i % 2 === 1 ? "lg:order-1" : "lg:order-3")} />
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
