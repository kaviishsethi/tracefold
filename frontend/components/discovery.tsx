"use client";

import { type PlannedSearch, type PresetInfo, type QueryPlan } from "@/lib/api";
import { cx } from "./ui";

const STATUS_STYLE: Record<PresetInfo["status"], string> = {
  benchmarked: "text-mute",
  experimental: "text-med",
  legacy: "text-faint",
};

export function StatusTag({ status }: { status: PresetInfo["status"] | string | null | undefined }) {
  if (!status) return null;
  return (
    <span className={cx("discovery-status text-xs", STATUS_STYLE[status as PresetInfo["status"]] ?? "text-faint")}>
      {status}
    </span>
  );
}

export function searchFilters(s: PlannedSearch): string {
  const out: string[] = [];
  if (s.category) out.push(`category ${s.category}`);
  if (s.topic && s.topic !== "general") out.push(`topic ${s.topic}`);
  if (s.exact_match) out.push("exact phrase");
  if (s.include_domains?.length) out.push(`${s.include_domains_mode === "prefer" ? "prefers" : "only"} ${s.include_domains.join(", ")}`);
  if (s.exclude_domains?.length) out.push(`excludes ${s.exclude_domains.length} domains`);
  return out.join(" · ") || "open web";
}


/** Human labels only; API identifiers and exact query text stay unchanged. */
export function searchLabel(id: string): string {
  const labels: Record<string, string> = {
    leak_watch: "Reported leaks", document_copies: "Document copies", code_exposure: "Code exposure", broad_triage: "Broad search",
    leak_news: "Leak reports", leak_news_alias: "Product leak reports", leaked_email: "Leaked emails", leaked_deck: "Leaked presentations",
    doc_sharing: "Shared documents", policy_copies: "Policy copies", security_docs: "Security documents", code_hosts_name: "Code by company name",
    code_hosts_domain: "Code by domain", paste_sites: "Paste sites", breach_coverage: "Breach reports",
  };
  const fallback = id.replaceAll("_", " ");
  return labels[id] ?? fallback.charAt(0).toUpperCase() + fallback.slice(1);
}

/** The exact searches a plan sends. This is the preview the user approves. */
export function PlanSearches({ plan }: { plan: QueryPlan }) {
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Search queries and providers">
      <table className="w-full min-w-[620px] text-left text-[13px]">
        <thead className="text-xs text-faint">
          <tr className="border-b border-line">
            {["Provider", "Query sent", "Filters", "Preset"].map((h) => (
              <th key={h} className="px-4 py-2 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {plan.searches.map((s) => (
            <tr key={s.query_id} className="border-b border-line last:border-0 align-top">
              <td className="px-4 py-2.5 font-mono text-xs text-mute">{s.provider}</td>
              <td className="px-4 py-2.5 font-mono text-xs text-ink">{s.query}</td>
              <td className="px-4 py-2.5 text-xs text-mute" title={s.exclude_domains?.join(", ") ?? undefined}>
                {searchFilters(s)} · {s.num_results} results
              </td>
              <td className="px-4 py-2.5 text-xs">
                <span className="mr-1.5 font-mono text-ink-2">{searchLabel(s.template_id)}</span>
                <StatusTag status={s.preset_status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

