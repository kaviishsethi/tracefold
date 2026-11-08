// Small shared pieces for the app pages. Keep this file tiny.
import Link from "next/link";
import type { ReactNode } from "react";
import type { Finding, Scan, Severity } from "@/lib/api";
import { relativeTime, where } from "@/lib/format";
import { cx } from "./ui";

export function H1({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-8">
      <h1 className="text-2xl tracking-[-0.03em] text-ink">{children}</h1>
      {sub && <p className="mt-1 text-sm text-mute">{sub}</p>}
    </div>
  );
}

export function Dot({ severity }: { severity: Severity | null | undefined }) {
  const c = severity === "high" ? "bg-crit" : severity === "medium" ? "bg-med" : severity === "low" ? "bg-low" : "bg-faint";
  return <span aria-label={severity ?? "unrated"} className={cx("inline-block size-2 shrink-0 rounded-full", c)} />;
}

export function source(scan: Pick<Scan, "started_from">): string {
  return scan.started_from === "assistant" ? "Coding assistant" : scan.started_from === "app" ? "Web app" : "Command line";
}

export function scanState(scan: Scan): { text: string; tone: "busy" | "done" | "bad" } {
  switch (scan.state) {
    case "queued":
    case "running":
      return { text: "Checking…", tone: "busy" };
    case "completed":
      return { text: "Done", tone: "done" };
    case "partial":
      return { text: "Done, but some checks didn't finish", tone: "bad" };
    case "cancelled":
      return { text: "Cancelled", tone: "bad" };
    case "interrupted":
      return { text: "Interrupted. Run it again.", tone: "bad" };
    default:
      return { text: scan.errors[0]?.message ?? "Failed", tone: "bad" };
  }
}

export function findingPlace(f: Finding): string {
  const loc = f.latest?.evidence[0]?.location;
  const pos = loc ? where(loc) : "";
  return [f.path, pos].filter(Boolean).join(" · ");
}

export function FindingRow({ f, href }: { f: Finding; href: string }) {
  return (
    <Link href={href} className="flex items-center gap-3 border-t border-line px-4 py-3 first:border-t-0 hover:bg-panel-2">
      <Dot severity={f.latest?.severity} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[15px] text-ink">{f.latest?.title ?? f.rule_id ?? "Finding"}</span>
        <span className="block truncate text-[13px] text-faint">{findingPlace(f) || "Location withheld"}</span>
      </span>
      {f.status !== "open" && (
        <span className="shrink-0 text-xs text-local">{f.status === "no_longer_observed" ? "No longer found" : "Not found after fix"}</span>
      )}
      <span className="shrink-0 text-xs text-faint">{relativeTime(f.latest?.created_at)}</span>
    </Link>
  );
}

export function Box({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("overflow-hidden rounded-card border border-line bg-panel", className)}>{children}</div>;
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="px-4 py-3 text-sm text-mute">{children}</p>;
}
