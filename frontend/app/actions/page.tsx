"use client";

import { NewScanButton, useCurrentWorkspace } from "@/components/shell";
import type { Action } from "@/lib/api";
import { Empty, ErrorNote, Loading, PageHeader } from "@/components/ui";
import { ActionCard, useActions } from "./action-card";

export default function Approvals() {
  const { current } = useCurrentWorkspace();
  const { items, error, unavailable, reload, replace } = useActions(current?.id ?? null);

  if (!current)
    return (
      <div>
        <PageHeader title="Approvals" />
        <Empty title="No workspace">This app&apos;s access grant doesn&apos;t cover a workspace yet.</Empty>
      </div>
    );

  const needsYou = (a: Action) => a.status === "drafted" || a.status === "failed" || a.status === "awaiting_manual_submission";
  const pending = (items ?? []).filter(needsYou);
  const rest = (items ?? []).filter((a) => !needsYou(a));

  return (
    <div>
      <PageHeader
        title="Approvals"
        subtitle="Takedown requests and key disables drafted from your findings. Nothing is sent or changed until a named person approves it here."
      />
      <ErrorNote error={error ? error.message : null} />

      {unavailable ? (
        <Empty title="Approvals aren't available on this engine">
          This engine doesn&apos;t have remediation enabled, so it doesn&apos;t draft takedown requests or key disables. Run an engine version with
          remediation to approve them here.
        </Empty>
      ) : !items ? (
        error ? null : <Loading />
      ) : items.length === 0 ? (
        <Empty title="Nothing to approve" action={<NewScanButton size="md" />}>
          After a scan, the engine drafts a takedown request for each public exposure and a disable request for each leaked AWS access key.
        </Empty>
      ) : (
        <div className="space-y-10">
          <section>
            <h2 className="mb-3 text-sm font-medium tracking-normal text-ink">
              Needs you <span className="ml-1 font-normal text-faint">{pending.length}</span>
            </h2>
            {pending.length ? (
              <div className="space-y-4">
                {pending.map((a) => (
                  <ActionCard key={a.action_id} action={a} workspace={current} onChange={replace} onReload={reload} />
                ))}
              </div>
            ) : (
              <p className="rounded-card border border-dashed border-line px-4 py-6 text-center text-[13px] text-mute">Nothing is waiting on you.</p>
            )}
          </section>
          {rest.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-medium tracking-normal text-ink">
                Decided <span className="ml-1 font-normal text-faint">{rest.length}</span>
              </h2>
              <div className="space-y-4">
                {rest.map((a) => (
                  <ActionCard key={a.action_id} action={a} workspace={current} onChange={replace} onReload={reload} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
