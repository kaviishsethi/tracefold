"use client";

import { useEffect, useState } from "react";
import { api, ws, type ApiError, type Finding, type FindingKind, type Page } from "@/lib/api";
import { useCurrentWorkspace } from "@/components/shell";
import { Box, FindingRow, H1, Note } from "@/components/bits";
import { ErrorNote } from "@/components/ui";

const GROUPS: [FindingKind, string, string][] = [
  ["public_exposure", "Found on public pages", "Nothing found on the public pages checked so far."],
  ["local_risk", "Risks in your files", "No risks found in the files checked so far."],
];

export default function Findings() {
  const { current: workspace } = useCurrentWorkspace();
  const [all, setAll] = useState<Finding[] | null>(null);
  const [showClosed, setShowClosed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspace) return;
    (async () => {
      const out: Finding[] = [];
      let cursor: string | null = null;
      do {
        const page: Page<Finding> = await api<Page<Finding>>(ws(workspace.id, `/findings?limit=100${cursor ? `&cursor=${cursor}` : ""}`));
        out.push(...page.items);
        cursor = page.next_cursor;
      } while (cursor && out.length < 1000);
      setAll(out);
    })().catch((e: ApiError) => setError(e.message));
  }, [workspace]);

  const visible = (all ?? []).filter((f) => showClosed || f.status === "open");
  const closed = (all ?? []).filter((f) => f.status !== "open").length;

  return (
    <div>
      <H1 sub="From every scan, whether it came from this app or your coding assistant.">Findings</H1>
      <ErrorNote error={error} />
      {GROUPS.map(([kind, label, empty]) => {
        const items = visible.filter((f) => f.kind === kind);
        return (
          <section key={kind} className="mb-8">
            <h2 className="mb-3 text-sm font-medium text-ink">
              {label} {all && <span className="text-faint">{items.length}</span>}
            </h2>
            <Box>{all === null ? <Note>Loading…</Note> : items.length ? items.map((f) => <FindingRow key={f.finding_id} f={f} href={`/findings/${f.finding_id}`} />) : <Note>{empty}</Note>}</Box>
          </section>
        );
      })}
      {closed > 0 && (
        <button onClick={() => setShowClosed((v) => !v)} className="text-sm text-mute underline underline-offset-4 hover:text-ink">
          {showClosed ? "Hide closed" : `Show ${closed} closed`}
        </button>
      )}
    </div>
  );
}
