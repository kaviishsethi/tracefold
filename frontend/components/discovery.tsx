"use client";

import { type PlannedSearch, type PresetInfo, type QueryPlan } from "@/lib/api";
import { cx } from "./ui";

const STATUS_STYLE: Record<PresetInfo["status"], string> = {
  benchmarked: "border-local-line text-local",
  experimental: "border-med/30 text-med",
  legacy: "border-line text-faint",
};

export function StatusTag({ status }: { status: PresetInfo["status"] | string | null | undefined }) {
  if (!status) return null;
  return (
    <span className={cx("rounded-md border px-1.5 py-px text-[11px]", STATUS_STYLE[status as PresetInfo["status"]] ?? "border-line text-faint")}>
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

/** The exact searches a plan sends. This is the preview the user approves. */
export function PlanSearches({ plan }: { plan: QueryPlan }) {
  return (
    <div className="overflow-x-auto">
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
                <span className="mr-1.5 font-mono text-ink-2">{s.template_id}</span>
                <StatusTag status={s.preset_status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

